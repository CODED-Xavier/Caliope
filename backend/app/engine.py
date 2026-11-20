"""The game loop. One call to `send()` is one full turn:

    player message -> retrieve memories + pick skills -> build prompt -> stream the reply
    -> save -> (optional) extract state changes + memories -> (optional) refresh summary

Everything is yielded as small event dicts so the API layer can stream them to the browser.
"""
from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from contextlib import aclosing
from typing import AsyncIterator

from .appearance import appearance_seed
from .checks import find_checks
from . import resources
from .shop import find_offers, is_trade
from . import statusbook
from .signals import needs_tracking, quiet_minutes
from .cards import resolve_features
from .config import SettingsStore
from .conversations import ConversationRepository, NotFound
from .dice import DiceError, DiceRoller
from .llm import LLMError
from .jukebox import guess_mood
from .scenes import new_seed, picture_url, write_prompt
from .lorebook import select_entries
from .memory import MemoryManager
from .portraits import process_reply
from .prompts import PromptBuilder, analysis_schema, reply_token_limit
from .skills import SkillManager
from .state import apply_state_updates, normalize_updates
from .status import split_template
from .writing import is_gm_message, strip_thoughts
from .util import clamp, estimate_tokens, extract_json, set_chars_per_token, truncate
from . import worldtime

log = logging.getLogger("rpg.engine")

DEFAULT_TITLES = ("", "Freeform adventure")


def scene_names(npcs: list[dict], *texts: str) -> list[str]:
    """Characters that look like they are in the scene: their name (or a part of it) is in the recent text."""
    blob = " ".join(t for t in texts if t).lower()
    words = set(re.findall(r"[^\W_]{3,}", blob))
    names = []
    for n in npcs:
        if not n["active"]:
            continue
        low = n["name"].lower()
        if low in blob or any(tok in words for tok in re.findall(r"[^\W_]{4,}", low)):
            names.append(n["name"])
    return names


def trim_incomplete(text: str) -> str:
    """If the reply was cut off by the length limit, go back to the last finished sentence."""
    t = text.strip()
    if not t or t[-1] in ".!?\u2026\"'\u201d\u2019*)]_`~":
        return t
    ends = list(re.finditer(r"[.!?\u2026][\"'\u201d\u2019*)\]_]*(?=\s|$)", t))
    if ends and ends[-1].end() >= len(t) * 0.4:
        return t[: ends[-1].end()].rstrip()
    return t


def with_latest_status(history: list[dict]) -> list[dict]:
    """The model sees only the newest status block (older ones would waste hundreds of tokens)."""
    out = [dict(h) for h in history]
    for h in reversed(out):
        if h["role"] == "assistant" and h.get("meta", {}).get("status"):
            h["content"] = f"{h['content']}\n\n{h['meta']['status']}"
            break
    return out


CONTINUE_PROMPT = ("[Continue your last reply exactly where it stopped. Do not repeat or summarize what you already "
                   "wrote, do not start over, and do not act for the player. Stop when it is the player's turn again.]")


class BusyError(Exception):
    """The conversation is generating a reply right now."""


class ChatEngine:
    def __init__(self, repo: ConversationRepository, settings: SettingsStore, llm, memory: MemoryManager,
                 skills: SkillManager, dice: DiceRoller, rulebooks=None):
        self.repo = repo
        self.settings = settings
        self.llm = llm
        self.memory = memory
        self.skills = skills
        self.dice = dice
        self.rulebooks = rulebooks
        self.prompts = PromptBuilder()
        self.rng = random.Random()
        self._locks: dict[int, asyncio.Lock] = {}

    def _lock(self, conv_id: int) -> asyncio.Lock:
        return self._locks.setdefault(conv_id, asyncio.Lock())

    # ------------------------------------------------------------------ public
    async def send(self, conv_id: int, text: str, prepare=None, kind: str = "combat") -> AsyncIterator[dict]:
        """`prepare(state) -> (state, text)` runs inside the turn lock before the message is saved (used by
        combat: the app rolls and changes the state, then the result is sent to the GM as this message)."""
        try:
            self.repo.get(conv_id)
        except NotFound as exc:
            yield {"type": "error", "message": str(exc)}
            return
        text = (text or "").strip()
        if not text and prepare is None:
            yield {"type": "error", "message": "Empty message."}
            return
        lock = self._lock(conv_id)
        if lock.locked():
            yield {"type": "error", "message": "This conversation is still busy with the previous turn."}
            return
        async with lock:
            if text.lower().startswith("/roll"):
                try:
                    rolled = self.dice.roll(text[5:].strip() or "1d20")
                except DiceError as exc:
                    yield {"type": "error", "message": str(exc)}
                    return
                note = ""
                yield {"type": "dice", "roll": rolled.to_dict()}
                text = rolled.text + note
            meta = None
            if prepare is None:
                try:
                    prepare, text = self._time_skip(conv_id, text)
                except ValueError as exc:
                    yield {"type": "error", "message": str(exc)}
                    return
                kind = "time_skip"
            if prepare is not None:
                before = self.repo.capture_snapshot(conv_id)  # undo/rewind of this turn also undoes the dice results
                try:
                    new_state, line = prepare(self.repo.get_state(conv_id))
                except ValueError as exc:
                    yield {"type": "error", "message": str(exc)}
                    return
                self.repo.save_state(conv_id, new_state)
                text = f"{text}\n\n{line}".strip() if text else line
                meta = {"snapshot": before, kind: True}
                yield {"type": "state", "state": new_state, "npcs": self.repo.list_npcs(conv_id), "changes": []}
            user_msg = self.repo.add_message(conv_id, "user", text, meta)
            self._auto_title(conv_id, text)
            yield {"type": "user_message", "message": user_msg}
            async with aclosing(self._reply(conv_id, user_msg)) as turn:
                async for event in turn:
                    yield event

    def _time_skip(self, conv_id: int, text: str):
        """(prepare, text) for '/wait …' or 'I sleep until morning' in a game with a calendar, else (None, text)."""
        cal = self.repo.get(conv_id)["scenario"].get("calendar") or {}
        if not cal.get("enabled") or not cal.get("months"):
            if text.lower().startswith("/wait"):
                raise ValueError("This card has no calendar. Turn it on in the card editor (Calendar) to use /wait.")
            return None, text
        state = self.repo.get_state(conv_id)
        found = worldtime.parse_skip(cal, text, worldtime.clock_of(state))
        if not found:
            return None, text
        minutes, spec = found

        def prepare(st):
            before = worldtime.clock_of(st)
            worldtime.advance(st, cal, minutes)
            st["date_label"] = worldtime.format_now(cal, worldtime.clock_of(st))
            passed = worldtime.events_between(st, cal, before, worldtime.clock_of(st))
            note = worldtime.skip_note(cal, before, worldtime.clock_of(st), passed, spec, (st.get("clock") or {}).get("seed", 0))
            back = []
            rest = resources.rest_kind(minutes)
            if rest:  # resting refills the pools (each has its own rule)
                back += resources.regenerate(st, rest)
            if rest == "long_rest":
                hp = st["player"]["hp"]
                if hp["current"] < hp["max"]:
                    hp["current"] = hp["max"]
                    back.append(f"HP {hp['max']}/{hp['max']}")
            days = worldtime.day_index(cal, worldtime.clock_of(st)) - worldtime.day_index(cal, before)
            back += resources.regenerate(st, "day", days)
            if back:
                note += " Recovered: " + ", ".join(dict.fromkeys(back)) + "."
            return st, note

        return prepare, ("" if text.lower().startswith("/wait") else text)

    async def regenerate(self, conv_id: int) -> AsyncIterator[dict]:
        try:
            self.repo.get(conv_id)
        except NotFound as exc:
            yield {"type": "error", "message": str(exc)}
            return
        lock = self._lock(conv_id)
        if lock.locked():
            yield {"type": "error", "message": "This conversation is still busy with the previous turn."}
            return
        async with lock:
            last = self.repo.last_message(conv_id)
            if last and last["role"] == "assistant":
                if last["meta"].get("opening"):
                    yield {"type": "error", "message": "The opening scene cannot be regenerated."}
                    return
                self._rollback_message(conv_id, last)
                last = self.repo.last_message(conv_id)
            if not last or last["role"] != "user":
                yield {"type": "error", "message": "There is nothing to regenerate yet."}
                return
            yield {"type": "rolled_back", "last_message_id": last["id"]}
            async with aclosing(self._reply(conv_id, last)) as turn:
                async for event in turn:
                    yield event

    async def continue_reply(self, conv_id: int) -> AsyncIterator[dict]:
        """Keep writing the last reply from where it stopped (the new text is added to the same message)."""
        try:
            self.repo.get(conv_id)
        except NotFound as exc:
            yield {"type": "error", "message": str(exc)}
            return
        lock = self._lock(conv_id)
        if lock.locked():
            yield {"type": "error", "message": "This conversation is still busy with the previous turn."}
            return
        async with lock:
            last = self.repo.last_message(conv_id)
            if not last or last["role"] != "assistant" or last["meta"].get("opening"):
                yield {"type": "error", "message": "Only the last reply can be continued."}
                return
            settings = self.settings.all()
            conv = self.repo.get(conv_id)
            scenario = conv["scenario"]
            state = self.repo.get_state(conv_id)
            npcs = self.repo.list_npcs(conv_id)
            history = self.repo.list_messages(conv_id, after_id=conv["summary_upto"])
            recent = [m["content"] for m in reversed(history)]
            lore = select_entries(scenario.get("lorebook"), recent, int(int(settings["context_window"]) * 0.1))
            _, house = await self._rules_for(scenario, "", settings)
            tpl = self._status_template(scenario, settings)
            messages, _debug = self.prompts.build(
                scenario=scenario, state=state, npcs=npcs, summary=conv["summary"], memories=[],
                skills=self.skills.attached((scenario.get("skills") or {}).get("attached", [])),
                history=history if tpl else with_latest_status(history), settings=settings,
                app_status=statusbook.render(tpl, state, npcs) if tpl else None, pinned=conv.get("pinned_memory", ""), player_lore=conv.get("player_lore"),
                lore=lore, player_name=state["player"].get("name") or "", house_rules=house,
            )
            messages.append({"role": "user", "content": CONTINUE_PROMPT})
            yield {"type": "continue_start", "message_id": last["id"]}
            partial: list[str] = []
            error: str | None = None
            try:
                async with aclosing(self.llm.stream_chat(messages, max_tokens=reply_token_limit(settings))) as pieces:
                    async for piece in pieces:
                        partial.append(piece)
                        yield {"type": "token", "text": piece}
            except LLMError as exc:
                error = str(exc)
            # Keep whatever was written, even after an error or Stop (finally runs when the stream is closed).
            finally:
                added = trim_incomplete("".join(partial)) if error is None else "".join(partial).strip()
                if added:
                    joined = last["content"].rstrip() + ("\n\n" if added[:1].isupper() or added[:1] in "\"*[" else " ") + added
                    text, extra, met = process_reply(joined, npcs)
                    for npc_id in met:
                        self.repo.update_npc(npc_id, met=True)
                    self.repo.update_message(last["id"], text)
                    self.repo.update_message_meta(last["id"], {**extra, "continued": True})
            if error:
                yield {"type": "error", "message": error}
                return
            if not added:
                yield {"type": "error", "message": "The model had nothing to add."}
                return
            yield {"type": "message_updated", "message": self.repo.get_message(last["id"])}
            yield {"type": "done"}

    # ------------------------------------------------------- editing history
    def is_busy(self, conv_id: int) -> bool:
        return self._lock(conv_id).locked()

    def edit_message(self, message_id: int, content: str) -> dict:
        """Change the text of one message in place. Sheet, NPCs and memories are left as they are."""
        msg = self.repo.get_message(message_id)
        if self.is_busy(msg["conversation_id"]):
            raise BusyError("Wait for the current reply to finish before editing.")
        content = (content or "").strip()
        if not content:
            raise ValueError("A message cannot be empty.")
        self.repo.update_message(message_id, content)
        self.repo.update_message_meta(message_id, {"edited": True})
        return self.repo.get_message(message_id)

    def _truncate_after(self, conv_id: int, message_id: int, inclusive: bool) -> int:
        """Delete the messages after `message_id` (and itself if `inclusive`).

        Sheet and NPCs go back to how they were before the first removed reply, the
        memories created by removed messages are forgotten, and a summary that covered
        removed text is discarded (it is rebuilt automatically when the story gets long).
        """
        rows = self.repo.list_messages(conv_id, after_id=message_id - 1 if inclusive else message_id, with_snapshot=True)
        if not rows:
            return 0
        # The first saved state among the removed messages (a combat turn saves one on the player's message).
        snap_msg = next((m for m in rows if m.get("snapshot")), None)
        if snap_msg:
            self.repo.restore_snapshot(conv_id, snap_msg["snapshot"])
        for m in rows:
            self.memory.delete_by_message(m["id"])
            self.repo.delete_message(m["id"])
        conv = self.repo.get(conv_id)
        if conv["summary"] and conv["summary_upto"] >= rows[0]["id"]:
            self.repo.set_summary(conv_id, "", 0)
        return len(rows)

    def fork(self, conv_id: int, message_id: int) -> int:
        """Save point: a new game that starts from this message. The original game is not changed."""
        if self.is_busy(conv_id):
            raise BusyError("Wait for the current reply to finish before making a save point.")
        return self.repo.fork(conv_id, message_id)

    def rewind(self, conv_id: int, message_id: int, inclusive: bool = False) -> dict:
        """Go back in the story: remove everything after a message (and the message too if `inclusive`)."""
        if self.is_busy(conv_id):
            raise BusyError("Wait for the current reply to finish before rewinding.")
        msg = self.repo.get_message(message_id)
        if msg["conversation_id"] != conv_id:
            raise NotFound(f"Message {message_id} not found")
        if inclusive and msg["meta"].get("opening"):
            raise ValueError("The opening scene cannot be deleted. Rewind to it instead.")
        return {"removed": self._truncate_after(conv_id, message_id, inclusive)}

    async def resend(self, conv_id: int, message_id: int, content: str) -> AsyncIterator[dict]:
        """Edit one of the player's messages, discard everything after it and write a new reply."""
        lock = self._lock(conv_id)
        if lock.locked():
            yield {"type": "error", "message": "This conversation is still busy with the previous turn."}
            return
        async with lock:
            try:
                msg = self.repo.get_message(message_id)
            except NotFound as exc:
                yield {"type": "error", "message": str(exc)}
                return
            content = (content or "").strip()
            if msg["conversation_id"] != conv_id or msg["role"] != "user":
                yield {"type": "error", "message": "Only your own messages can be re-sent."}
                return
            if not content:
                yield {"type": "error", "message": "A message cannot be empty."}
                return
            self._truncate_after(conv_id, message_id, inclusive=False)
            conv = self.repo.get(conv_id)
            if conv["summary"] and conv["summary_upto"] >= message_id:
                self.repo.set_summary(conv_id, "", 0)
            self.repo.update_message(message_id, content)
            self.repo.update_message_meta(message_id, {"edited": True})
            user_msg = self.repo.get_message(message_id)
            yield {"type": "rolled_back", "last_message_id": message_id}
            async with aclosing(self._reply(conv_id, user_msg)) as turn:
                async for event in turn:
                    yield event

    def undo(self, conv_id: int) -> dict:
        """Remove the last exchange (assistant reply + player message), restoring state and NPCs."""
        removed = 0
        last = self.repo.last_message(conv_id)
        if last and last["role"] == "assistant" and not last["meta"].get("opening"):
            self._rollback_message(conv_id, last)
            removed += 1
            last = self.repo.last_message(conv_id)
        if last and last["role"] == "user":
            if last.get("snapshot"):  # a fight action or a time skip changed the state before this message
                self.repo.restore_snapshot(conv_id, last["snapshot"])
            self.repo.delete_message(last["id"])
            removed += 1
        return {"removed": removed}

    # ---------------------------------------------------------------- internals
    def _rollback_message(self, conv_id: int, message: dict) -> None:
        snap = message.get("snapshot")
        if snap:
            self.repo.restore_snapshot(conv_id, snap)
        self.memory.delete_by_message(message["id"])
        self.repo.delete_message(message["id"])
        conv = self.repo.get(conv_id)
        if conv["summary_upto"] >= message["id"]:  # summary covered a message that no longer exists
            self.repo.set_summary(conv_id, conv["summary"], 0 if not conv["summary"] else conv["summary_upto"])

    def _auto_title(self, conv_id: int, text: str) -> None:
        conv = self.repo.get(conv_id)
        scenario_name = conv["scenario"].get("name", "")
        if conv["title"] in DEFAULT_TITLES or conv["title"] == scenario_name:
            said = strip_thoughts(text)  # thoughts and GM messages never end up in the title
            if said and not said.startswith(("\U0001F3B2", "\u2694", "\u2728", "\U0001F6D2", "\U0001F4B0", "\u23f3", "\U0001F6CC")):
                self.repo.rename(conv_id, truncate(f"{scenario_name}: {said}" if scenario_name else said, 60))

    async def _reply(self, conv_id: int, user_msg: dict) -> AsyncIterator[dict]:
        t_start = time.perf_counter()
        settings = self.settings.all()
        conv = self.repo.get(conv_id)
        scenario = conv["scenario"]
        state = self.repo.get_state(conv_id)
        npcs = self.repo.list_npcs(conv_id)
        history = self.repo.list_messages(conv_id, after_id=conv["summary_upto"])

        previous_assistant = next((m for m in reversed(history[:-1]) if m["role"] == "assistant"), None)
        previous_text = previous_assistant["content"] if previous_assistant else ""
        said = strip_thoughts(user_msg["content"])  # NPC-visible part of the player's message
        query = said + (" " + previous_text[-300:] if previous_text else "")
        active = scene_names(npcs, said, previous_text)
        memories = await self.memory.search(conv_id, query, active_names=active)
        skills = self.skills.attached((scenario.get("skills") or {}).get("attached", []))
        features = resolve_features(scenario, settings)
        hint = ""
        if features["appearance_hints"] and scenario.get("mode") != "character":
            hint = appearance_seed(self.rng, scenario.get("species") or [])

        recent = [m["content"] for m in reversed(history)]  # newest first, for the lorebook keyword scan
        lore = select_entries(scenario.get("lorebook"), recent, int(int(settings["context_window"]) * 0.1))
        rules, house = await self._rules_for(scenario, query, settings)  # same text as the memory search: embedded once
        tpl = self._status_template(scenario, settings)  # the card's INFO block, kept by the app
        messages, debug = self.prompts.build(
            scenario=scenario, state=state, npcs=npcs, summary=conv["summary"], memories=memories,
            skills=skills, history=history if tpl else with_latest_status(history), settings=settings,
            app_status=statusbook.render(tpl, state, npcs) if tpl else None, pinned=conv.get("pinned_memory", ""), player_lore=conv.get("player_lore"),
            appearance_hint=hint, lore=lore, status_due=None if tpl else self._status_due(conv_id, scenario),
            player_name=state["player"].get("name") or "", rules=rules, house_rules=house,
        )
        yield {"type": "context", "debug": debug, "skills": [s["name"] for s in skills],
               "memories": [m["text"] for m in memories][: debug["memories"]], "rules": debug.get("rules", [])}

        player_name = state["player"].get("name") or "Player"
        stop = [f"\n{player_name}:", "\nPlayer:", "\nUser:"]

        partial: list[str] = []
        completed = False
        error: str | None = None
        t_first: float | None = None
        try:
            async with aclosing(self.llm.stream_chat(messages, stop=stop, max_tokens=reply_token_limit(settings))) as pieces:
                async for piece in pieces:
                    if t_first is None:
                        t_first = time.perf_counter()
                    partial.append(piece)
                    yield {"type": "token", "text": piece}
            completed = True
        except LLMError as exc:
            error = str(exc)
        finally:
            if not completed:
                text = "".join(partial).strip()
                if text:  # keep what was already written (error or the player pressed Stop)
                    self.repo.add_message(conv_id, "assistant", text, {"interrupted": True})
        if error:
            yield {"type": "error", "message": error}
            return
        t_end = time.perf_counter()

        reply = trim_incomplete("".join(partial))
        if not reply:
            yield {"type": "error", "message": "The model returned an empty reply. Try again or check the model in LM Studio."}
            return

        real_prompt = self._calibrate(messages)
        timing: dict = {}
        if settings.get("show_timing", True):
            written = estimate_tokens(reply)
            write_s = max(0.001, t_end - (t_first or t_end))
            timing = {
                "first_word_s": round((t_first or t_end) - t_start, 1),
                "write_s": round(write_s, 1),
                "tokens_per_s": round(written / write_s, 1),
                "prompt_tokens": real_prompt or debug["prompt_tokens"],
                "stable_tokens": debug["stable_tokens"],
                "volatile_tokens": debug["volatile_tokens"],
            }
        reply, extra, met = process_reply(reply, npcs)
        for npc_id in met:
            self.repo.update_npc(npc_id, met=True)
        if tpl and extra.get("status"):  # the model wrote the block anyway: keep the card's values it reports
            st = self.repo.get_state(conv_id)
            statusbook.harvest(st, tpl, extra.pop("status"))
            self.repo.save_state(conv_id, st)
        snapshot = self.repo.capture_snapshot(conv_id)
        meta = {"snapshot": snapshot, **extra}
        asked = find_checks(reply)  # "Make a DEX (Stealth) check, DC 13" becomes a roll button
        if asked:
            meta["checks"] = asked
        offers = find_offers(reply, scenario.get("currency") or "gold")  # "a lantern (5 gold)" becomes a buy button
        if offers:
            meta["offers"] = offers
        if timing:
            meta["timing"] = timing
        assistant_msg = self.repo.add_message(conv_id, "assistant", reply, meta)
        yield {"type": "assistant_message", "message": self.repo.get_message(assistant_msg["id"])}

        tracker = features["tracker"]
        place_before = self.repo.get_state(conv_id).get("location", "")
        if is_gm_message(user_msg["content"]):
            pass  # a message to the GM, outside the story: nothing to track or remember
        elif tracker == "off":
            await self._remember_exchange(conv_id, user_msg["content"], reply, assistant_msg["id"])
            mood = guess_mood(reply)  # no tracker: a quick keyword check names the scene's mood for the Jukebox
            st = self.repo.get_state(conv_id)
            if mood and mood != st.get("scene_mood"):
                st["scene_mood"] = mood
                self.repo.save_state(conv_id, st)
                yield {"type": "state", "state": st, "npcs": self.repo.list_npcs(conv_id), "changes": []}
        else:
            interval = features["tracker_interval"]
            skip_ok = bool(settings.get("tracker_skip", True))
            st = self.repo.get_state(conv_id)
            pending = int(st.get("untracked", 0)) + 1  # exchanges the tracker has not read yet, this one included
            if skip_ok:
                known = [n["name"] for n in npcs] + [state["player"].get("name") or ""] + [l["name"] for l in st.get("locations", [])]
                run = (needs_tracking(user_msg["content"], reply, known, list(st.get("resources") or {}))
                       or pending >= interval + 1)
            else:
                run = self.repo.count_replies(conv_id) % interval == 0
            count, exchanges = self._tracking_context(conv_id, min(pending, 4) if skip_ok else interval)
            if not run or not exchanges:
                yield {"type": "state", **self._quiet_turn(conv_id, scenario, user_msg["content"], reply, pending)}
            else:  # the tracker reads every exchange it has not seen yet
                yield {"type": "analysis_start"}
                t0 = time.perf_counter()
                result = await self._analyze(conv_id, scenario, exchanges, assistant_msg["id"], settings, tracker)
                timing["tracker_s"] = round(time.perf_counter() - t0, 1)
                if result is None:
                    await self._remember_exchange(conv_id, user_msg["content"], reply, assistant_msg["id"])
                else:
                    yield {"type": "state", **result}

        if settings.get("scene_pictures") and not is_gm_message(user_msg["content"]):
            place_now = self.repo.get_state(conv_id).get("location", "")
            first = not self.repo.has_meta(conv_id, "scene_picture")
            new_scene = first or (place_now and place_now != place_before) or "\u2694\ufe0f Combat starts" in user_msg["content"]
            if new_scene:
                pic = await self._scene_picture(conv_id, assistant_msg["id"], reply, settings)
                if pic:
                    yield {"type": "scene_picture", "message_id": assistant_msg["id"], "picture": pic}

        if tpl:  # the status block for this reply, filled by the app after the tracker ran
            block = statusbook.render(tpl, self.repo.get_state(conv_id), self.repo.list_npcs(conv_id))
            self.repo.update_message_meta(assistant_msg["id"], {"status": block})
            yield {"type": "message_updated", "message": self.repo.get_message(assistant_msg["id"])}

        if settings["auto_summary"]:
            t0 = time.perf_counter()
            summary = await self._maybe_summarize(conv_id, settings)
            if summary is not None:
                timing["summary_s"] = round(time.perf_counter() - t0, 1)
                yield {"type": "summary", "summary": summary}
        if settings.get("show_timing", True):
            timing["total_s"] = round(time.perf_counter() - t_start, 1)
            self.repo.update_message_meta(assistant_msg["id"], {"timing": timing})
            yield {"type": "timing", "timing": timing}
        yield {"type": "done"}

    async def _scene_picture(self, conv_id: int, message_id: int, text: str, settings: dict,
                             reroll_of: dict | None = None) -> dict | None:
        """Write a picture prompt for this scene and attach the picture link to the message (Pollinations paints it
        when the interface first shows it). A reroll keeps the prompt and changes only the seed."""
        try:
            if reroll_of and reroll_of.get("prompt"):
                prompt = reroll_of["prompt"]
            else:
                names = [n["name"] for n in self.repo.list_npcs(conv_id)]
                state = self.repo.get_state(conv_id)
                names.append(state["player"].get("name") or "")
                prompt = await write_prompt(self.llm, text, state, settings.get("scene_picture_style", ""), names)
        except (LLMError, ValueError) as exc:
            log.warning("Scene picture prompt failed: %s", exc)
            return None
        seed = new_seed()
        pic = {"prompt": prompt, "seed": seed, "url": picture_url(prompt, seed)}
        self.repo.update_message_meta(message_id, {"scene_picture": pic})
        return pic

    async def paint_scene(self, conv_id: int, message_id: int, reroll: bool = False) -> dict:
        """The 🖼 button: paint the scene of a reply (or another version of its picture)."""
        msg = self.repo.get_message(message_id)
        if msg["conversation_id"] != conv_id or msg["role"] != "assistant":
            raise NotFound("Only the GM's replies can be painted.")
        if self.is_busy(conv_id):
            raise BusyError("Wait for the current reply to finish.")
        pic = await self._scene_picture(conv_id, message_id, msg["content"], self.settings.all(),
                                        msg["meta"].get("scene_picture") if reroll else None)
        if not pic:
            raise LLMError("The model could not describe this scene. Is LM Studio running?")
        return self.repo.get_message(message_id)

    async def _rules_for(self, scenario: dict, query: str, settings: dict) -> tuple[list[dict], list[tuple[str, str]]]:
        """Rulebook passages that fit this turn, and the house rules of the card's books."""
        if not self.rulebooks or not scenario.get("rulebooks"):
            return [], []
        ids = self.rulebooks.ready_ids(scenario["rulebooks"])
        if not ids:
            return [], []
        passages = await self.rulebooks.passages_for_turn(ids, query, int(settings.get("rules_char_budget", 1400)))
        return passages, self.rulebooks.house_rules(ids)

    def _calibrate(self, messages: list[dict]) -> int | None:
        """Learn how many characters make one token for the model in use, from the real count the server reports,
        so the history is trimmed exactly instead of with a rough guess. Returns the real prompt size."""
        usage = getattr(self.llm, "last_usage", None) or {}
        real = int(usage.get("prompt_tokens") or 0)
        if real <= 50:
            return None
        chars = sum(len(m.get("content") or "") for m in messages)
        measured = chars / max(1, real - 6 * len(messages))  # ~6 tokens of chat template per message
        old = float(self.settings.get("chars_per_token"))
        new = round(max(2.5, min(5.0, old * 0.6 + measured * 0.4)), 3)
        if abs(new - old) >= 0.01:
            self.settings.update({"chars_per_token": new})
            set_chars_per_token(new)
        return real

    @staticmethod
    def _status_template(scenario: dict, settings: dict) -> str | None:
        """The card's INFO template when the app writes the block (the default), else None."""
        if resolve_features(scenario, settings).get("status_by", "app") != "app":
            return None
        return statusbook.template_of(scenario)

    def _status_due(self, conv_id: int, scenario: dict) -> bool | None:
        """None when the card has no status block; otherwise whether this reply should write one."""
        info = scenario.get("information") or {}
        every = int(info.get("status_every") or 0)
        if not every or not split_template(info.get("post_history") or "")[1]:
            return None
        return (self.repo.count_replies(conv_id) + 1) % every == 0

    def _tracking_context(self, conv_id: int, interval: int) -> tuple[int, list[tuple[str, str]]]:
        """(number of finished replies so far, the last `interval` exchanges as (player text, reply) pairs)."""
        count = self.repo.count_replies(conv_id)
        recent = self.repo.recent_messages(conv_id, interval * 2 + 8)  # only the last exchanges are read
        msgs = [m for m in recent if not m["meta"].get("opening") and not m["meta"].get("interrupted")]
        pairs: list[tuple[str, str]] = []
        i = len(msgs) - 1
        while i >= 1 and len(pairs) < interval:
            if msgs[i]["role"] == "assistant" and msgs[i - 1]["role"] == "user":
                if not is_gm_message(msgs[i - 1]["content"]):  # the tracker never reads thoughts or GM messages
                    pairs.append((strip_thoughts(msgs[i - 1]["content"]), msgs[i]["content"]))
                i -= 2
            else:
                i -= 1
        pairs.reverse()
        return count, pairs

    def _quiet_turn(self, conv_id: int, scenario: dict, user_text: str, reply: str, pending: int) -> dict:
        """No tracker this turn: code moves the clock a little and names the music mood; the tracker reads it later."""
        st = self.repo.get_state(conv_id)
        st["untracked"] = pending
        changes: list[str] = []
        cal = scenario.get("calendar") or {}
        if cal.get("enabled") and cal.get("months"):
            changes = self._move_clock(st, cal, {"minutes_passed": quiet_minutes(user_text, reply), "appointments": []})
        mood = guess_mood(reply)
        if mood:
            st["scene_mood"] = mood
        self.repo.save_state(conv_id, st)
        return {"state": st, "npcs": self.repo.list_npcs(conv_id), "changes": changes}

    @staticmethod
    def _move_clock(state: dict, cal: dict, updates: dict) -> list[str]:
        """The tracker's estimate moves the clock (at most 12 hours a turn); appointments get their exact day."""
        changes = []
        before = worldtime.clock_of(state)
        for ap in updates.get("appointments", []):  # "tomorrow" counts from when it was said, before the clock moves
            ev = worldtime.add_event(state, cal, ap["text"], ap.get("when", ""), ap.get("days_from_now"))
            if ev:
                changes.append("Appointment: " + worldtime.describe_event(cal, ev, worldtime.day_index(cal, before)))
        weather = state.get("weather")
        worldtime.advance(state, cal, min(updates.get("minutes_passed", 0), worldtime.MAX_TURN_MINUTES))
        after = worldtime.clock_of(state)
        state["date_label"] = worldtime.format_now(cal, after)
        if worldtime.day_index(cal, after) != worldtime.day_index(cal, before):
            changes.append("New day: " + worldtime.format_date(cal, worldtime.now(cal, after)))
            back = resources.regenerate(state, "day", worldtime.day_index(cal, after) - worldtime.day_index(cal, before))
            if back:
                changes.append("Recovered: " + ", ".join(back))
        if state.get("weather") and state.get("weather") != weather:
            changes.append(f"Weather: {state['weather']}")
        return changes

    async def _remember_exchange(self, conv_id: int, user_text: str, reply: str, message_id: int) -> None:
        text = f"Player: {truncate(strip_thoughts(user_text), 200)} | Response: {truncate(reply, 300)}"
        await self.memory.add(conv_id, text, kind="exchange", importance=2, message_id=message_id)

    async def _analyze(self, conv_id: int, scenario: dict, exchanges: list[tuple[str, str]], message_id: int,
                       settings: dict, tracker: str = "full") -> dict | None:
        user_text, reply = exchanges[-1]
        state = self.repo.get_state(conv_id)
        npcs = self.repo.list_npcs(conv_id)
        cal = scenario.get("calendar") or {}
        cal_on = bool(cal.get("enabled") and cal.get("months"))
        tpl = self._status_template(scenario, settings)
        status_lines = statusbook.tracker_lines(state, tpl) if tpl else ""
        res_line = resources.tracker_line(state)
        prompt = self.prompts.analysis_messages(scenario=scenario, state=state, npcs=npcs, exchanges=exchanges, tracker=tracker,
                                                calendar=cal if cal_on else None, status_fields=status_lines, resource_line=res_line)
        try:
            raw = await self.llm.chat(prompt, json_schema=analysis_schema(tracker, cal_on, bool(status_lines), bool(res_line)),
                                      temperature=0.2,
                                      max_tokens=700 if tracker == "full" else 450)
        except LLMError as exc:
            log.warning("State analysis failed: %s", exc)
            return None
        data = extract_json(raw)
        if data is None:
            log.warning("State analysis returned no JSON: %r", raw[:200])
            return None
        updates = normalize_updates(data)
        mode = scenario.get("mode", "gm_world")
        if tracker != "full" or mode == "character":
            # Lite tracking and character cards never touch the sheet, even if the model returns such fields.
            for key in ("hp_change", "gold_change"):
                updates[key] = 0
            updates["inventory_add"] = updates["inventory_remove"] = updates["quests"] = []
            updates["new_locations"] = []
        if mode == "character":
            updates["new_npcs"] = []
        if (state.get("combat") or {}).get("active") or any("\u2694" in u for u, _ in exchanges):
            updates["hp_change"] = 0  # in a fight the app already applied the damage
        if any(is_trade(u) for u, _ in exchanges):  # the app already moved the money and the items
            updates["gold_change"] = 0
            updates["inventory_add"] = updates["inventory_remove"] = []

        if cal_on:
            updates["time"] = ""  # the app's clock decides the time of day
            if cal.get("climate", "temperate") != "none":
                updates["weather"] = ""  # and the weather
        new_state, changes = apply_state_updates(state, updates)
        new_state["untracked"] = 0
        if status_lines:
            changes += statusbook.apply_changes(new_state, tpl, updates.get("status_changes", []))
        if res_line and not any(resources.is_ability(u) or "\u2694" in u for u, _ in exchanges):
            changes += resources.apply_tracker(new_state, updates.get("resource_changes", []))  # the app counted ✨/⚔ turns
        if cal_on:
            changes += self._move_clock(new_state, cal, updates)
        self.repo.save_state(conv_id, new_state)

        for npc in updates["new_npcs"]:
            if not self.repo.find_npc(conv_id, npc["name"]):
                self.repo.add_npc(conv_id, npc["name"], description=npc["description"], personality=npc["personality"],
                                  appearance=npc.get("appearance"))
                changes.append(f"New character: {npc['name']}")

        max_step = int(settings["relationship_max_step"])
        main = next((n for n in self.repo.list_npcs(conv_id) if n["is_main"]), None)
        for rc in updates["relationship_changes"]:
            npc = self.repo.find_npc(conv_id, rc["npc"])
            if mode == "character" and main:
                npc = main
            if not npc:
                continue
            delta = int(clamp(rc["delta"], -max_step, max_step))
            value = int(clamp(npc["relationship"] + delta, -100, 100))
            if value != npc["relationship"]:
                self.repo.update_npc(npc["id"], relationship=value)
                why = f" ({rc['reason']})" if rc["reason"] else ""
                changes.append(f"{npc['name']}: relationship {value - npc['relationship']:+d} \u2192 {value}{why}")

        added = 0
        for mem in updates["memories"]:
            if await self.memory.add(conv_id, mem["text"], kind="event", importance=mem["importance"], message_id=message_id,
                                     participants=mem.get("characters")):
                added += 1
        if added == 0 and not updates["memories"]:
            await self._remember_exchange(conv_id, user_text, reply, message_id)

        self.repo.update_message_meta(message_id, {"changes": changes})
        return {"state": new_state, "npcs": self.repo.list_npcs(conv_id), "changes": changes, "memories_added": added}

    async def _maybe_summarize(self, conv_id: int, settings: dict) -> str | None:
        """Fold the oldest rounds into the summary, in BLOCKS.

        The last `recent_rounds` rounds stay word for word. Once that window is full, a whole block of the
        oldest rounds is folded at once, so for the next few turns the start of the prompt stays identical
        and the model can reuse its earlier work instead of rereading everything.
        """
        conv = self.repo.get(conv_id)
        rows = [r for r in self.repo.list_messages(conv_id, after_id=conv["summary_upto"]) if not r["meta"].get("opening")]
        max_msgs = max(4, int(settings["recent_rounds"]) * 2)
        block_msgs = max(2, int(settings["fold_block_rounds"]) * 2)
        history_budget = (int(settings["context_window"]) - reply_token_limit(settings)) * 0.5
        total = sum(estimate_tokens(r["content"]) + 6 for r in rows)
        over_count = len(rows) > max_msgs
        over_tokens = total > history_budget * 0.85
        if not (over_count or over_tokens):
            return None
        if over_count:
            fold = max(block_msgs, len(rows) - max_msgs)
        else:  # long replies: fold until about half of the history budget is free again
            fold, remaining = 0, total
            for r in rows:
                if remaining <= history_budget * 0.55:
                    break
                remaining -= estimate_tokens(r["content"]) + 6
                fold += 1
            fold = max(fold, 2)
        fold = min(fold, len(rows) - 2)  # never fold the latest exchange
        fold -= fold % 2                 # whole rounds only
        if fold < 2:
            return None
        old = rows[:fold]
        summary = conv["summary"]
        language = conv["scenario"].get("language") or settings.get("response_language", "en")
        max_chars = int(settings["summary_char_budget"])
        chunk, size = [], 0
        try:
            for r in old:  # summarise in chunks so one call never gets huge
                line = f"{'Player' if r['role'] == 'user' else 'Narrator'}: {truncate(r['content'], 1500)}"
                chunk.append(line)
                size += len(line)
                if size > 6000:
                    summary = await self._summarize(summary, chunk, language, max_chars)
                    chunk, size = [], 0
            if chunk:
                summary = await self._summarize(summary, chunk, language, max_chars)
        except LLMError as exc:
            log.warning("Summarization failed: %s", exc)
            return None
        self.repo.set_summary(conv_id, summary, old[-1]["id"])
        return summary

    async def _summarize(self, previous: str, lines: list[str], language: str, max_chars: int = 1500) -> str:
        messages = self.prompts.summary_messages(previous=previous, transcript="\n".join(lines), language=language, max_chars=max_chars)
        text = await self.llm.chat(messages, temperature=0.3, max_tokens=500)
        return truncate(text.strip(), max_chars) or previous
