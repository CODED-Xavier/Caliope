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
from .cards import resolve_features
from .config import SettingsStore
from .conversations import ConversationRepository, NotFound
from .dice import DiceError, DiceRoller
from .llm import LLMError
from .lorebook import select_entries
from .memory import MemoryManager
from .portraits import process_reply
from .prompts import PromptBuilder, analysis_schema, reply_token_limit
from .skills import SkillManager
from .state import apply_state_updates, normalize_updates
from .status import split_template
from .util import clamp, estimate_tokens, extract_json, truncate

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
                 skills: SkillManager, dice: DiceRoller):
        self.repo = repo
        self.settings = settings
        self.llm = llm
        self.memory = memory
        self.skills = skills
        self.dice = dice
        self.prompts = PromptBuilder()
        self.rng = random.Random()
        self._locks: dict[int, asyncio.Lock] = {}

    def _lock(self, conv_id: int) -> asyncio.Lock:
        return self._locks.setdefault(conv_id, asyncio.Lock())

    # ------------------------------------------------------------------ public
    async def send(self, conv_id: int, text: str) -> AsyncIterator[dict]:
        try:
            self.repo.get(conv_id)
        except NotFound as exc:
            yield {"type": "error", "message": str(exc)}
            return
        text = (text or "").strip()
        if not text:
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
            user_msg = self.repo.add_message(conv_id, "user", text)
            self._auto_title(conv_id, text)
            yield {"type": "user_message", "message": user_msg}
            async with aclosing(self._reply(conv_id, user_msg)) as turn:
                async for event in turn:
                    yield event

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
            messages, _debug = self.prompts.build(
                scenario=scenario, state=state, npcs=npcs, summary=conv["summary"], memories=[],
                skills=self.skills.attached((scenario.get("skills") or {}).get("attached", [])),
                history=with_latest_status(history), settings=settings, pinned=conv.get("pinned_memory", ""),
                lore=lore, player_name=state["player"].get("name") or "",
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
        snap_msg = next((m for m in rows if m["role"] == "assistant" and m.get("snapshot")), None)
        if snap_msg:
            self.repo.restore_snapshot(conv_id, snap_msg["snapshot"])
        for m in rows:
            self.memory.delete_by_message(m["id"])
            self.repo.delete_message(m["id"])
        conv = self.repo.get(conv_id)
        if conv["summary"] and conv["summary_upto"] >= rows[0]["id"]:
            self.repo.set_summary(conv_id, "", 0)
        return len(rows)

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
            if not text.startswith("\U0001F3B2"):
                self.repo.rename(conv_id, truncate(f"{scenario_name}: {text}" if scenario_name else text, 60))

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
        query = user_msg["content"] + (" " + previous_text[-300:] if previous_text else "")
        active = scene_names(npcs, user_msg["content"], previous_text)
        memories = await self.memory.search(conv_id, query, active_names=active)
        skills = self.skills.attached((scenario.get("skills") or {}).get("attached", []))
        features = resolve_features(scenario, settings)
        hint = ""
        if features["appearance_hints"] and scenario.get("mode") != "character":
            hint = appearance_seed(self.rng, scenario.get("species") or [])

        recent = [m["content"] for m in reversed(history)]  # newest first, for the lorebook keyword scan
        lore = select_entries(scenario.get("lorebook"), recent, int(int(settings["context_window"]) * 0.1))
        messages, debug = self.prompts.build(
            scenario=scenario, state=state, npcs=npcs, summary=conv["summary"], memories=memories,
            skills=skills, history=with_latest_status(history), settings=settings, pinned=conv.get("pinned_memory", ""),
            appearance_hint=hint, lore=lore, status_due=self._status_due(conv_id, scenario),
            player_name=state["player"].get("name") or "",
        )
        yield {"type": "context", "debug": debug, "skills": [s["name"] for s in skills],
               "memories": [m["text"] for m in memories][: debug["memories"]]}

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

        timing: dict = {}
        if settings.get("show_timing", True):
            written = estimate_tokens(reply)
            write_s = max(0.001, t_end - (t_first or t_end))
            timing = {
                "first_word_s": round((t_first or t_end) - t_start, 1),
                "write_s": round(write_s, 1),
                "tokens_per_s": round(written / write_s, 1),
                "prompt_tokens": debug["prompt_tokens"],
                "stable_tokens": debug["stable_tokens"],
                "volatile_tokens": debug["volatile_tokens"],
            }
        reply, extra, met = process_reply(reply, npcs)
        for npc_id in met:
            self.repo.update_npc(npc_id, met=True)
        snapshot = self.repo.capture_snapshot(conv_id)
        meta = {"snapshot": snapshot, **extra}
        if timing:
            meta["timing"] = timing
        assistant_msg = self.repo.add_message(conv_id, "assistant", reply, meta)
        yield {"type": "assistant_message", "message": self.repo.get_message(assistant_msg["id"])}

        tracker = features["tracker"]
        if tracker == "off":
            await self._remember_exchange(conv_id, user_msg["content"], reply, assistant_msg["id"])
        else:
            count, exchanges = self._tracking_context(conv_id, features["tracker_interval"])
            if count % features["tracker_interval"] == 0:  # the tracker runs every N replies and reads all N exchanges
                yield {"type": "analysis_start"}
                t0 = time.perf_counter()
                result = await self._analyze(conv_id, scenario, exchanges, assistant_msg["id"], settings, tracker)
                timing["tracker_s"] = round(time.perf_counter() - t0, 1)
                if result is None:
                    await self._remember_exchange(conv_id, user_msg["content"], reply, assistant_msg["id"])
                else:
                    yield {"type": "state", **result}

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

    def _status_due(self, conv_id: int, scenario: dict) -> bool | None:
        """None when the card has no status block; otherwise whether this reply should write one."""
        info = scenario.get("information") or {}
        every = int(info.get("status_every") or 0)
        if not every or not split_template(info.get("post_history") or "")[1]:
            return None
        done = sum(1 for m in self.repo.list_messages(conv_id)
                   if m["role"] == "assistant" and not m["meta"].get("opening") and not m["meta"].get("interrupted"))
        return (done + 1) % every == 0

    def _tracking_context(self, conv_id: int, interval: int) -> tuple[int, list[tuple[str, str]]]:
        """(number of finished replies so far, the last `interval` exchanges as (player text, reply) pairs)."""
        msgs = [m for m in self.repo.list_messages(conv_id) if not m["meta"].get("opening") and not m["meta"].get("interrupted")]
        count = sum(1 for m in msgs if m["role"] == "assistant")
        pairs: list[tuple[str, str]] = []
        i = len(msgs) - 1
        while i >= 1 and len(pairs) < interval:
            if msgs[i]["role"] == "assistant" and msgs[i - 1]["role"] == "user":
                pairs.append((msgs[i - 1]["content"], msgs[i]["content"]))
                i -= 2
            else:
                i -= 1
        pairs.reverse()
        return count, pairs

    async def _remember_exchange(self, conv_id: int, user_text: str, reply: str, message_id: int) -> None:
        text = f"Player: {truncate(user_text, 200)} | Response: {truncate(reply, 300)}"
        await self.memory.add(conv_id, text, kind="exchange", importance=2, message_id=message_id)

    async def _analyze(self, conv_id: int, scenario: dict, exchanges: list[tuple[str, str]], message_id: int,
                       settings: dict, tracker: str = "full") -> dict | None:
        user_text, reply = exchanges[-1]
        state = self.repo.get_state(conv_id)
        npcs = self.repo.list_npcs(conv_id)
        prompt = self.prompts.analysis_messages(scenario=scenario, state=state, npcs=npcs, exchanges=exchanges, tracker=tracker)
        try:
            raw = await self.llm.chat(prompt, json_schema=analysis_schema(tracker), temperature=0.2,
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

        new_state, changes = apply_state_updates(state, updates)
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
