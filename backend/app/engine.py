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

from .appearance import appearance_line, appearance_seed
from .checks import find_checks
from . import adventure, aedo_desk, reputation, resources, routes, sheetchat, systems
from .places import find_place, place_picture
from .shop import find_offers, is_trade
from . import statusbook
from .signals import needs_tracking, quiet_minutes
from .cards import resolve_features
from .config import SettingsStore
from .conversations import ConversationRepository, NotFound
from .dice import DiceError, DiceRoller
from .llm import LLMError
from .jukebox import guess_mood
from .scenes import new_seed, picture_url, pixai_url, write_prompt
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


PREPARE_KINDS = ("combat", "time_skip", "trade", "ability", "rest")
_APP_MARKS = ("⚔", "🎲", "✨", "🛒", "💰", "⏳", "🛌", "🏁")


def strip_app_line(content: str, meta: dict) -> str:
    """The player's own words of a message the app added a result to (dice, purchase, time skip)."""
    line = (meta or {}).get("app_line") or ""
    if line and line in content:
        return content.replace(line, "").strip()
    # older messages: drop the paragraphs that start with one of the app's marks
    keep = [p for p in content.split("\n\n") if not p.strip().startswith(_APP_MARKS)]
    return "\n\n".join(keep).strip()


NOTES_LIMIT = 1500


def add_note(repo, npc: dict, note: str) -> bool:
    """Append one of the Aedo's notes to a character (skipping repeats; his oldest notes go first when it gets long)."""
    from .prompts import AEDO_MARK

    lines = [x for x in (npc.get("notes") or "").splitlines() if x.strip()]
    key = re.sub(r"\W+", " ", note.lower()).strip()
    if any(re.sub(r"\W+", " ", x.lower()).strip().endswith(key) for x in lines):
        return False
    lines.append(AEDO_MARK + note)
    while len("\n".join(lines)) > NOTES_LIMIT:
        old = next((i for i, x in enumerate(lines) if x.startswith(AEDO_MARK)), None)
        if old is None or old == len(lines) - 1:
            break
        lines.pop(old)
    repo.update_npc(npc["id"], notes="\n".join(lines))
    return True


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


USED_UP = re.compile(r"\b(potion|po[cç][aã]o|scroll|pergaminho|arrow|flecha|bolt|virote|dart|dardo|ration|ra[cç][aã]o|torch|tocha|"
                     r"oil|[oó]leo|bomb|bomba|flask|frasco|herb|erva|bandage|bandagem|antidote|ant[ií]doto|javelin|dagger)s?\b", re.I)

class BusyError(Exception):
    """The conversation is generating a reply right now."""


END_LINE = re.compile(r"^\s*[*_#\s]*(?:THE END|FIM)[.!*_\s]*$", re.I | re.M)


def story_ended(reply: str) -> bool:
    """The Aedo closed the story with its last line "THE END" (or "FIM"), as the card's ending section asks."""
    lines = [ln for ln in (reply or "").strip().splitlines() if ln.strip()]
    return bool(lines) and bool(END_LINE.match(lines[-1]))


def involved_changes(changes: list[dict], exchanges: list[tuple[str, str]]) -> list[dict]:
    """Relationship changes only for characters who are in the exchange (named in the reply or in what the player
    said or did, not only in the player's 'thoughts') and only with a reason. Anything else is dropped."""
    # where the character can be: the story's reply, or the player's own words and actions (not their 'thoughts')
    seen = " ".join(re.sub(r"(?<!\w)'[^'\n]+'(?!\w)", " ", u) + " " + r for u, r in exchanges).lower()
    out = []
    for rc in changes:
        name = str(rc.get("npc") or "").strip()
        parts = [p for p in re.split(r"\W+", name.lower()) if len(p) > 2]
        if not str(rc.get("reason") or "").strip() or not parts:
            continue
        if not any(re.search(rf"\b{re.escape(p)}\b", seen) for p in parts):
            continue  # not in the scene: only talked about elsewhere, or only in the player's thoughts
        out.append(rc)
    return out


class ChatEngine:
    def __init__(self, repo: ConversationRepository, settings: SettingsStore, llm, memory: MemoryManager,
                 skills: SkillManager, dice: DiceRoller, rulebooks=None):
        self.cantos = None  # set by Services (chapters, recap, map bag)
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

    _warming: dict = {}

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
                meta = {"snapshot": before, kind: True, "app_line": line}
                yield {"type": "state", "state": new_state, "npcs": self.repo.list_npcs(conv_id), "changes": []}
            if text and prepare is None and not text.startswith("/") and not resources.is_ability(text):
                st_now = self.repo.get_state(conv_id)
                named = resources.skills_in_text(text, st_now.get("abilities") or [])
                if named and not (st_now.get("combat") or {}).get("active"):  # "I use my soul forge": the app pays it
                    before = self.repo.capture_snapshot(conv_id)
                    used = resources.use_named_skills(st_now, named)
                    self.repo.save_state(conv_id, st_now)
                    meta = {"snapshot": before, "skills_used": used}
                    yield {"type": "state", "state": st_now, "npcs": self.repo.list_npcs(conv_id), "changes": []}
                elif st_now.get("character5e") and not (st_now.get("combat") or {}).get("active"):
                    sheet_used = self._sheet_uses(conv_id, st_now, text)  # "I use Lay on Hands", "I cast Cure Wounds"
                    if sheet_used:
                        meta = {**sheet_used[0], "sheet_uses": sheet_used[1]}
                        yield {"type": "state", "state": st_now, "npcs": self.repo.list_npcs(conv_id), "changes": []}
            user_msg = self.repo.add_message(conv_id, "user", text, meta)
            self._auto_title(conv_id, text)
            yield {"type": "user_message", "message": user_msg}
            async with aclosing(self._reply(conv_id, user_msg)) as turn:
                async for event in turn:
                    yield event
        self._warm_later(conv_id)  # the new reply joins the story's memory while the player reads it

    def _sheet_uses(self, conv_id: int, state: dict, text: str):
        """5e features and spells named in the message are spent on the sheet (the Aedo hears what was spent)."""
        from .dnd5e import chatuse
        try:
            before = self.repo.capture_snapshot(conv_id)
            used = chatuse.apply(state, text, resources._library())
        except Exception:  # noqa: BLE001 - spending from chat is a convenience: the message still goes through
            import logging
            logging.getLogger("rpg").exception("could not read 5e uses from the chat")
            return None
        if not used:
            return None
        self.repo.save_state(conv_id, state)
        return {"snapshot": before}, used

    _tasks: set = set()

    _summarizing: set = set()

    def _background(self, coro) -> None:
        try:
            task = asyncio.get_running_loop().create_task(coro)
        except RuntimeError:
            coro.close()
            return
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _warm_later(self, conv_id: int) -> None:
        if self.settings.get("ai_engine") != "builtin" or conv_id in self._summarizing:
            return  # a summary in progress warms the story itself when it is done
        self._background(self.warm(conv_id))

    async def _summarize_then_warm(self, conv_id: int, settings: dict) -> None:
        if conv_id in self._summarizing:
            return
        self._summarizing.add(conv_id)
        try:
            await self._maybe_summarize(conv_id, settings)
        except Exception as exc:  # the summary is tried again after the next reply
            log.warning("Summary failed: %s", exc)
        finally:
            self._summarizing.discard(conv_id)
        if settings.get("ai_engine") == "builtin":
            await self.warm(conv_id)

    async def _aedo_answer(self, conv_id: int, user_msg: dict) -> AsyncIterator[dict]:
        """A short answer out of character, from its own small prompt (the story's memory slot is not touched)."""
        t_start = time.perf_counter()
        settings = self.settings.all()
        conv = self.repo.get(conv_id)
        scenario = conv["scenario"]
        language = scenario.get("language") or settings.get("response_language", "en")
        fix = aedo_desk.FIX.match(user_msg["content"].strip())
        if fix:  # "/fix Aria is the Saintess": kept as a story fact, no model needed
            st = self.repo.get_state(conv_id)
            fact = aedo_desk.save_fact(st, fix.group(1))
            self.repo.save_state(conv_id, st)
            msg = self.repo.add_message(conv_id, "assistant", f"📌 Kept as a story fact: {fact}", {"ooc": True})
            yield {"type": "state", "state": st, "npcs": self.repo.list_npcs(conv_id), "changes": []}
            yield {"type": "assistant_message", "message": self.repo.get_message(msg["id"])}
            return
        messages = aedo_desk.build_messages(
            scenario=scenario, state=self.repo.get_state(conv_id), npcs=self.repo.list_npcs(conv_id),
            summary=conv["summary"], history=self.repo.list_messages(conv_id, after_id=conv["summary_upto"])[:-1],
            question=user_msg["content"], language=language, player_lore=conv.get("player_lore"))
        partial: list[str] = []
        t_first = None
        try:
            async with aclosing(self.llm.stream_chat(messages, max_tokens=900, temperature=0.4)) as pieces:
                async for piece in pieces:
                    t_first = t_first or time.perf_counter()
                    partial.append(piece)
                    yield {"type": "token", "text": piece}
        except LLMError as exc:
            yield {"type": "error", "message": str(exc)}
            return
        reply = "".join(partial).strip()
        if not reply:
            yield {"type": "error", "message": "The model returned nothing. Try again."}
            return
        reply, facts = aedo_desk.take_facts(reply)
        if facts:  # the Aedo agreed to a correction: the fixed fact is kept for the story
            st = self.repo.get_state(conv_id)
            kept = [aedo_desk.save_fact(st, f) for f in facts]
            self.repo.save_state(conv_id, st)
            reply = (reply + "\n\n" + "\n".join(f"📌 Kept as a story fact: {k}" for k in kept if k)).strip()
            yield {"type": "state", "state": st, "npcs": self.repo.list_npcs(conv_id), "changes": []}
        meta: dict = {"ooc": True}
        if settings.get("show_timing", True):
            meta["timing"] = {"first_word_s": round((t_first or time.perf_counter()) - t_start, 1),
                              "total_s": round(time.perf_counter() - t_start, 1)}
        msg = self.repo.add_message(conv_id, "assistant", reply, meta)
        yield {"type": "assistant_message", "message": self.repo.get_message(msg["id"])}

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
            npcs = self.repo.list_npcs(conv_id)
            messages = await self._story_prompt(conv_id, settings)
            messages.append({"role": "user", "content": CONTINUE_PROMPT})
            yield {"type": "continue_start", "message_id": last["id"]}
            partial: list[str] = []
            error: str | None = None
            try:
                async with aclosing(self.llm.stream_chat(messages, max_tokens=reply_token_limit(settings), story=True)) as pieces:
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
    async def _story_prompt(self, conv_id: int, settings: dict, extra_user: str | None = None) -> list[dict]:
        """The story's prompt as it stands (no memory search), used by Continue and by the warm-up."""
        conv = self.repo.get(conv_id)
        scenario = conv["scenario"]
        state = self.repo.get_state(conv_id)
        npcs = self.repo.list_npcs(conv_id)
        history = aedo_desk.without_ooc(self.repo.list_messages(conv_id, after_id=conv["summary_upto"]))
        if extra_user is not None:
            history = [*history, {"role": "user", "content": extra_user, "meta": {}}]
        recent = [m["content"] for m in reversed(history)]
        lore = select_entries(scenario.get("lorebook"), recent, int(int(settings["context_window"]) * 0.1))
        _, house = await self._rules_for(scenario, "", settings)
        tpl = self._status_template(scenario, settings)
        messages, _debug = self.prompts.build(
            scenario=scenario, state=state, npcs=npcs, summary=conv["summary"], memories=[],
            skills=self.skills.attached((scenario.get("skills") or {}).get("attached", [])),
            history=history if tpl else with_latest_status(history), settings=settings,
            app_status=statusbook.render(tpl, state, npcs) if tpl else None, pinned=conv.get("pinned_memory", ""),
            player_lore=conv.get("player_lore"), lore=lore, player_name=state["player"].get("name") or "", house_rules=house,
            cantos=self.cantos.prompt_section(conv_id, int(settings["context_window"]) * 3 // 10) if self.cantos else "",
        )
        return messages

    async def warm(self, conv_id: int) -> bool:
        """Read the story's prompt ahead of time (built-in engine only), while the player reads and types: the
        engine keeps it in the story's memory slot, so the next reply only reads the new message.
        Without this, the first reply after opening a game rereads everything (about a minute on an RX 580)."""
        settings = self.settings.all()
        if settings.get("ai_engine") != "builtin" or self.is_busy(conv_id):
            return False
        # No turn lock: if the player sends a message meanwhile, the engine finishes this first and reuses it.
        if self._warming.get(conv_id):
            return False
        self._warming[conv_id] = True
        try:
            messages = await self._story_prompt(conv_id, settings, extra_user="…")
            async with aclosing(self.llm.stream_chat(messages, max_tokens=1, story=True)) as pieces:
                async for _ in pieces:
                    pass
        except Exception as exc:  # only a head start: nothing is lost if it fails
            log.info("Warm-up skipped: %s", exc)
            return False
        finally:
            self._warming.pop(conv_id, None)
        return True

    async def _sheet_from_text(self, conv_id: int, text: str, tpl: str | None) -> tuple[dict, list[str]]:
        """Read a character sheet written in the chat into the Sheet tab and the card's status block."""
        st = self.repo.get_state(conv_id)
        fields = statusbook.custom_fields(tpl) if tpl else []
        opening = next((m["content"] for m in self.repo.list_messages(conv_id) if m["role"] == "assistant"), "")
        try:
            sheet = await sheetchat.read_sheet(self.llm, opening, text, fields, st.get("card_status"))
        except Exception as exc:  # the sheet stays as it was; the story goes on
            log.warning("Reading the sheet from the chat failed: %s", exc)
            return st, []
        if not sheet:
            return st, []
        st = self.repo.get_state(conv_id)
        got = sheetchat.apply_sheet(st, sheet, keep_existing=st.get("setup") != "card")
        if fields:
            got += statusbook.apply_changes(st, tpl, [x for x in sheet.get("status") or [] if isinstance(x, dict)])
        if got:
            st["sheet_from_chat"] = True
            self.repo.save_state(conv_id, st)
        return st, got

    async def sheet_from_message(self, conv_id: int, message_id: int) -> dict:
        """"📋 Use as my sheet" on one of your messages: read it again into the Sheet tab and the status."""
        msg = self.repo.get_message(message_id)
        if not msg or msg["conversation_id"] != conv_id or msg["role"] != "user":
            raise ValueError("Only your own messages can be used as your sheet.")
        if self.is_busy(conv_id):
            raise ValueError("This conversation is still busy with the previous turn.")
        async with self._lock(conv_id):
            conv = self.repo.get(conv_id)
            tpl = self._status_template(conv["scenario"], self.settings.all())
            st, got = await self._sheet_from_text(conv_id, msg["content"], tpl)
        if not got:
            raise ValueError("No sheet details were found in that message.")
        return {"state": st, "npcs": self.repo.list_npcs(conv_id), "changes": ["Your sheet: " + "; ".join(got)]}

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
            if m is rows[0] and self.cantos:
                self.cantos.trim(conv_id, m["id"])
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
            snap = self.repo.get_message(message_id, with_snapshot=True).get("snapshot")
            if snap:  # a fight action, trade, ability, rest or time skip: its dice and effects are undone
                content = strip_app_line(content, msg["meta"])
                if not content:
                    yield {"type": "error", "message": "This message is only the app's result (dice, purchase, rest…). "
                                                       "Use Undo or Rewind and take the action again to roll fresh."}
                    return
            self._truncate_after(conv_id, message_id, inclusive=False)
            conv = self.repo.get(conv_id)
            if conv["summary"] and conv["summary_upto"] >= message_id:
                self.repo.set_summary(conv_id, "", 0)
            if snap:
                self.repo.restore_snapshot(conv_id, snap)
                self.repo.set_message_snapshot(message_id, None)
                self.repo.update_message_meta(message_id, {}, drop=PREPARE_KINDS + ("app_line",))
                try:  # new words that still skip time ("I sleep until dawn") move the clock again
                    prepare, own = self._time_skip(conv_id, content)
                except ValueError:
                    prepare = None
                if prepare is not None:
                    before = self.repo.capture_snapshot(conv_id)
                    new_state, line = prepare(self.repo.get_state(conv_id))
                    self.repo.save_state(conv_id, new_state)
                    content = f"{own}\n\n{line}".strip() if own else line
                    self.repo.set_message_snapshot(message_id, before)
                    self.repo.update_message_meta(message_id, {"time_skip": True, "app_line": line})
                yield {"type": "state", "state": self.repo.get_state(conv_id), "npcs": self.repo.list_npcs(conv_id), "changes": []}
            self.repo.update_message(message_id, content)
            self.repo.update_message_meta(message_id, {"edited": True})
            user_msg = self.repo.get_message(message_id)
            yield {"type": "rolled_back", "last_message_id": message_id}
            yield {"type": "user_updated", "message": user_msg}
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
            if self.cantos:
                self.cantos.trim(conv_id, last["id"])
            removed += 1
        return {"removed": removed}

    # ---------------------------------------------------------------- internals
    def _rollback_message(self, conv_id: int, message: dict) -> None:
        snap = message.get("snapshot")
        if snap:
            self.repo.restore_snapshot(conv_id, snap)
        self.memory.delete_by_message(message["id"])
        if self.cantos:
            self.cantos.trim(conv_id, message["id"])
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
        if is_gm_message(user_msg["content"]):  # "/question": the Aedo answers outside the story
            async with aclosing(self._aedo_answer(conv_id, user_msg)) as answer:
                async for event in answer:
                    yield event
            return
        t_start = time.perf_counter()
        settings = self.settings.all()
        conv = self.repo.get(conv_id)
        scenario = conv["scenario"]
        state = self.repo.get_state(conv_id)
        npcs = self.repo.list_npcs(conv_id)
        history = aedo_desk.without_ooc(self.repo.list_messages(conv_id, after_id=conv["summary_upto"]))
        adv = scenario.get("adventure") or {}
        if adv.get("scenes") and not is_gm_message(user_msg["content"]):
            if adventure.move(adv, state, adventure.follow_player(adv, state, user_msg["content"])):
                self.repo.save_state(conv_id, state)  # the player walks into the next area: its text is read now

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
            cantos=self.cantos.prompt_section(conv_id, int(settings["context_window"]) * 3 // 10) if self.cantos else "",
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
            async with aclosing(self.llm.stream_chat(messages, stop=stop, max_tokens=reply_token_limit(settings), story=True)) as pieces:
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
        fight_now = (self.repo.get_state(conv_id).get("combat") or {})
        if asked and fight_now.get("active") and fight_now.get("reaction_round") == fight_now.get("round"):
            asked = []  # one check per round in a fight: the reaction is spent
        if asked:
            meta["checks"] = asked
        offers = find_offers(reply, scenario.get("currency") or "gold")  # "a lantern (5 gold)" becomes a buy button
        if offers:
            meta["offers"] = offers
        if timing:
            meta["timing"] = timing
        ended = story_ended(reply) and bool(scenario.get("ending") or scenario.get("length", "open") != "open")
        if ended:
            meta["finished"] = True
        adv = scenario.get("adventure") or {}
        if adv.get("scenes") and not is_gm_message(user_msg["content"]):
            st = self.repo.get_state(conv_id)
            went = adventure.move(adv, st, adventure.follow_story(adv, st, reply))
            if went:
                st["adventure"]["fresh"] = ""  # the story already walked in: no need to read the box again
                self.repo.save_state(conv_id, st)
                meta["scene"] = went  # shown under the reply: "📍 Goblin Ambush"
            offer = adventure.fight_offer(adv, st, user_msg["content"], reply)
            if offer:
                meta["fight"] = offer  # "⚔ A fight! 4 × Goblin [Start the fight]" under the reply
                meta.pop("checks", None)  # the fight starts instead: attacks are rolled by the app, not dodged with checks
        assistant_msg = self.repo.add_message(conv_id, "assistant", reply, meta)
        st = self.repo.get_state(conv_id)
        moved = routes.advance(st, scenario.get("route"))  # the planned scene was written: the next one comes after it
        moved = adventure.narrated(st) or moved
        if ended:
            st["finished"] = True  # the card's ending happened: the chat offers the epilogue
        if moved or ended:
            self.repo.save_state(conv_id, st)
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

        st_now = self.repo.get_state(conv_id)
        sheet_fields = statusbook.custom_fields(tpl) if tpl else []
        if sheetchat.wanted(st_now, self.repo.count_replies(conv_id) + 1, user_msg["content"], sheet_fields):
            # your character sheet written in the chat fills the Sheet tab and the card's status (once)
            st_now, got = await self._sheet_from_text(conv_id, user_msg["content"], tpl)
            if got:
                yield {"type": "state", "state": st_now, "npcs": self.repo.list_npcs(conv_id), "changes": ["Your sheet: " + "; ".join(got)]}

        place_now = self.repo.get_state(conv_id).get("location", "")
        card_places = scenario.get("places") or []
        here = find_place(card_places, place_now) if place_now else None
        # a new place of the card (not just new words for the same one, "Grand Hall" -> "Grand Hall, by the fire")
        arrived = here and (here is not find_place(card_places, place_before) or not self.repo.has_meta(conv_id, "scene_picture"))
        fixed = place_picture(here) if arrived else None
        if fixed and not is_gm_message(user_msg["content"]):  # a place the card has a picture for: shown at once
            self.repo.update_message_meta(assistant_msg["id"], {"scene_picture": fixed})
            if self.cantos and settings.get("auto_keep_pictures", True):
                kept = self.cantos.auto_keep(conv_id, assistant_msg["id"], fixed, self.repo.get_state(conv_id))
                if kept:
                    self.repo.update_message_meta(assistant_msg["id"], {"kept_picture": kept["id"]})
            yield {"type": "scene_picture", "message_id": assistant_msg["id"], "picture": fixed}
            yield {"type": "message_updated", "message": self.repo.get_message(assistant_msg["id"])}
        elif settings.get("scene_pictures") and not is_gm_message(user_msg["content"]):
            first = not self.repo.has_meta(conv_id, "scene_picture")
            new_scene = first or (place_now and place_now != place_before) or "\u2694\ufe0f Combat starts" in user_msg["content"]
            if new_scene:
                pic = await self._scene_picture(conv_id, assistant_msg["id"], reply, settings)
                if pic:
                    if self.cantos and settings.get("auto_keep_pictures", True):  # the first picture of each place goes in the map bag
                        kept = self.cantos.auto_keep(conv_id, assistant_msg["id"], pic, self.repo.get_state(conv_id))
                        if kept:
                            self.repo.update_message_meta(assistant_msg["id"], {"kept_picture": kept["id"]})
                    yield {"type": "scene_picture", "message_id": assistant_msg["id"], "picture": pic}
                    yield {"type": "message_updated", "message": self.repo.get_message(assistant_msg["id"])}

        if tpl:  # the status block for this reply, filled by the app after the tracker ran
            block = statusbook.render(tpl, self.repo.get_state(conv_id), self.repo.list_npcs(conv_id))
            self.repo.update_message_meta(assistant_msg["id"], {"status": block})
            yield {"type": "message_updated", "message": self.repo.get_message(assistant_msg["id"])}

        if settings["auto_summary"]:
            # Folding old rounds into the summary runs after the reply, in the background: you can read and send
            # meanwhile (it waits for its turn on the engine like any helper call).
            self._background(self._summarize_then_warm(conv_id, settings))
        if settings.get("show_timing", True):
            timing["total_s"] = round(time.perf_counter() - t_start, 1)
            self.repo.update_message_meta(assistant_msg["id"], {"timing": timing})
            yield {"type": "timing", "timing": timing}
        yield {"type": "done"}

    async def _scene_picture(self, conv_id: int, message_id: int, text: str, settings: dict,
                             reroll_of: dict | None = None, kind: str = "place") -> dict | None:
        """Write a picture prompt for this scene and attach the picture link to the message (Pollinations paints it
        when the interface first shows it). A reroll keeps the prompt and changes only the seed."""
        try:
            if reroll_of and reroll_of.get("prompt"):
                prompt = reroll_of["prompt"]
            else:
                npcs = self.repo.list_npcs(conv_id)
                names = [n["name"] for n in npcs]
                state = self.repo.get_state(conv_id)
                player = state["player"].get("name") or ""
                names.append(player)
                low = text.lower()
                people = [(n["name"], appearance_line(n.get("appearance") or {}) or truncate(n.get("description") or "", 160))
                          for n in npcs if n["name"].split()[0].lower() in low]
                if player:  # the player's character, when the scene shows them (by name or as "you")
                    people.append((player, truncate(state["player"].get("description") or "", 200)))
                prompt = await write_prompt(self.llm, text, state, settings.get("scene_picture_style", ""), names,
                                            kind=kind, people=people[:5])
        except (LLMError, ValueError) as exc:
            log.warning("Scene picture prompt failed: %s", exc)
            return None
        seed = new_seed()
        use_pixai = settings.get("picture_service") == "pixai" and settings.get("pixai_api_key")
        pic = {"prompt": prompt, "seed": seed, "url": (pixai_url if use_pixai else picture_url)(prompt, seed)}
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
                                        msg["meta"].get("scene_picture") if reroll else None, kind="scene")
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
        sys_def = scenario.get("systems") or {}
        sys_line = systems.tracker_line(sys_def, state.get("systems") or {}) if state.get("systems") else ""
        if sys_line:
            res_line = (res_line + "\n" + sys_line).strip()
        prompt = self.prompts.analysis_messages(scenario=scenario, state=state, npcs=npcs, exchanges=exchanges, tracker=tracker,
                                                calendar=cal if cal_on else None, status_fields=status_lines, resource_line=res_line,
                                                language=scenario.get("language") or settings.get("response_language", "en"))
        try:
            raw = await self.llm.chat(prompt, json_schema=analysis_schema(tracker, cal_on, bool(status_lines), bool(resources.tracker_line(state)),
                                                                          bool(sys_line)),
                                      temperature=0.2,
                                      max_tokens=1100 if tracker == "full" else 900)  # a cut JSON would lose the whole update
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
            # a sword "clattering from your grasp" is dropped, not lost: in a fight only used-up things leave the bag
            updates["inventory_remove"] = [i for i in updates["inventory_remove"] if USED_UP.search(str(i.get("name", "")))]
        if any(is_trade(u) for u, _ in exchanges):  # the app already moved the money and the items
            updates["gold_change"] = 0
            updates["inventory_add"] = updates["inventory_remove"] = []
        if mode != "character":
            updates["relationship_changes"] = involved_changes(updates["relationship_changes"], exchanges)

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
        if sys_line and new_state.get("systems"):
            day = (new_state.get("clock") or {}).get("minutes", 0) // 1440 + 1
            changes += systems.apply_changes(sys_def, new_state["systems"],
                                             [{**c, "day": day} if c.get("step") else c for c in updates.get("system_changes", [])])
        if cal_on:
            changes += self._move_clock(new_state, cal, updates)
        adv = scenario.get("adventure") or {}
        if adv.get("scenes") and updates.get("location"):
            st_adv = new_state.get("adventure") or {}
            went = adventure.move(adv, new_state, adventure.match_scene(adv, updates["location"], reply, st_adv.get("scene", "")))
            if went:
                changes.append(f"📍 Scene: {went}")
        self.repo.save_state(conv_id, new_state)

        for npc in updates["new_npcs"]:
            if not self.repo.find_npc(conv_id, npc["name"]):
                self.repo.add_npc(conv_id, npc["name"], description=npc["description"], personality=npc["personality"],
                                  appearance=npc.get("appearance"))
                changes.append(f"New character: {npc['name']}")

        max_step = int(settings["relationship_max_step"])
        main = next((n for n in self.repo.list_npcs(conv_id) if n["is_main"]), None)
        rep_log = new_state.setdefault("rep_log", [])
        for rc in updates["relationship_changes"]:
            npc = self.repo.find_npc(conv_id, rc["npc"])
            if mode == "character" and main:
                npc = main
            if not npc:
                continue
            if rc.get("event"):  # the model named what happened; the app's table says how much it counts
                delta = reputation.delta_for(rc["event"], npc["name"], rep_log)
            else:                # a number (a model that ignored the event list): capped below like any change
                delta = int(rc["delta"])
            delta = int(clamp(delta, -max_step, max_step))
            value = int(clamp(npc["relationship"] + delta, -100, 100))
            if value != npc["relationship"]:
                self.repo.update_npc(npc["id"], relationship=value)
                reputation.remember(new_state, npc["name"], rc.get("event", ""), value - npc["relationship"], rc["reason"])
                what = reputation.event_label(rc["event"]) if rc.get("event") else ""
                why = f" ({what}: {rc['reason']})" if what and rc["reason"] else f" ({what or rc['reason']})" if (what or rc["reason"]) else ""
                before, after = reputation.level(npc["relationship"])[0], reputation.level(value)[0]
                now = f", now {after}" if after != before else ""
                changes.append(f"{npc['name']}: relationship {value - npc['relationship']:+d} \u2192 {value}{why}{now}")
        if updates["relationship_changes"]:
            self.repo.save_state(conv_id, new_state)  # the reputation log (repeats count less)

        for cn in updates.get("character_notes", []):  # the Aedo's own notes (marked ✒), beside the player's
            npc = self.repo.find_npc(conv_id, cn["npc"])
            if npc and add_note(self.repo, npc, cn["note"]):
                changes.append(f"Note on {npc['name']}: {cn['note']}")

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
        rows = [r for r in aedo_desk.without_ooc(self.repo.list_messages(conv_id, after_id=conv["summary_upto"]))
                if not r["meta"].get("opening")]
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
