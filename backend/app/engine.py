"""The game loop. One call to `send()` is one full turn:

    player message -> retrieve memories + pick skills -> build prompt -> stream the reply
    -> save -> (optional) extract state changes + memories -> (optional) refresh summary

Everything is yielded as small event dicts so the API layer can stream them to the browser.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import aclosing
from typing import AsyncIterator

from .config import SettingsStore
from .conversations import ConversationRepository, NotFound
from .dice import DiceError, DiceRoller
from .llm import LLMError
from .memory import MemoryManager
from .prompts import ANALYSIS_SCHEMA, PromptBuilder
from .skills import SkillManager
from .state import apply_state_updates, normalize_updates
from .util import clamp, estimate_tokens, extract_json, truncate

log = logging.getLogger("rpg.engine")

DEFAULT_TITLES = ("", "Freeform adventure")


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
        settings = self.settings.all()
        conv = self.repo.get(conv_id)
        scenario = conv["scenario"]
        state = self.repo.get_state(conv_id)
        npcs = self.repo.list_npcs(conv_id)
        history = self.repo.list_messages(conv_id, after_id=conv["summary_upto"])

        previous_assistant = next((m for m in reversed(history[:-1]) if m["role"] == "assistant"), None)
        query = user_msg["content"] + (" " + previous_assistant["content"][-300:] if previous_assistant else "")
        memories = await self.memory.search(conv_id, query)
        skills = await self.skills.select(query, scenario.get("skills"))

        messages, debug = self.prompts.build(
            scenario=scenario, state=state, npcs=npcs, summary=conv["summary"], memories=memories,
            skills=skills, history=history, settings=settings,
        )
        yield {"type": "context", "debug": debug, "skills": [s["name"] for s in skills if s["name"] in debug["skills"]],
               "memories": [m["text"] for m in memories]}

        player_name = state["player"].get("name") or "Player"
        stop = [f"\n{player_name}:", "\nPlayer:", "\nUser:"]

        partial: list[str] = []
        completed = False
        error: str | None = None
        try:
            async with aclosing(self.llm.stream_chat(messages, stop=stop)) as pieces:
                async for piece in pieces:
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

        reply = "".join(partial).strip()
        if not reply:
            yield {"type": "error", "message": "The model returned an empty reply. Try again or check the model in LM Studio."}
            return

        snapshot = self.repo.capture_snapshot(conv_id)
        assistant_msg = self.repo.add_message(conv_id, "assistant", reply, {"snapshot": snapshot})
        yield {"type": "assistant_message", "message": self.repo.get_message(assistant_msg["id"])}

        if settings["state_tracking"]:
            yield {"type": "analysis_start"}
            result = await self._analyze(conv_id, scenario, user_msg["content"], reply, assistant_msg["id"], settings)
            if result is None:
                await self._remember_exchange(conv_id, user_msg["content"], reply, assistant_msg["id"])
            else:
                yield {"type": "state", **result}
        else:
            await self._remember_exchange(conv_id, user_msg["content"], reply, assistant_msg["id"])

        if settings["auto_summary"]:
            summary = await self._maybe_summarize(conv_id, settings)
            if summary is not None:
                yield {"type": "summary", "summary": summary}
        yield {"type": "done"}

    async def _remember_exchange(self, conv_id: int, user_text: str, reply: str, message_id: int) -> None:
        text = f"Player: {truncate(user_text, 200)} | Response: {truncate(reply, 300)}"
        await self.memory.add(conv_id, text, kind="exchange", importance=2, message_id=message_id)

    async def _analyze(self, conv_id: int, scenario: dict, user_text: str, reply: str, message_id: int,
                       settings: dict) -> dict | None:
        state = self.repo.get_state(conv_id)
        npcs = self.repo.list_npcs(conv_id)
        prompt = self.prompts.analysis_messages(scenario=scenario, state=state, npcs=npcs, user_text=user_text, reply=reply)
        try:
            raw = await self.llm.chat(prompt, json_schema=ANALYSIS_SCHEMA, temperature=0.2, max_tokens=700)
        except LLMError as exc:
            log.warning("State analysis failed: %s", exc)
            return None
        data = extract_json(raw)
        if data is None:
            log.warning("State analysis returned no JSON: %r", raw[:200])
            return None
        updates = normalize_updates(data)
        mode = scenario.get("mode", "gm_world")
        if mode == "character":  # character cards track the relationship, not a stat block
            for key in ("hp_change", "gold_change"):
                updates[key] = 0
            updates["inventory_add"] = updates["inventory_remove"] = updates["quests"] = []
            updates["new_npcs"] = []

        new_state, changes = apply_state_updates(state, updates)
        self.repo.save_state(conv_id, new_state)

        for npc in updates["new_npcs"]:
            if not self.repo.find_npc(conv_id, npc["name"]):
                self.repo.add_npc(conv_id, npc["name"], description=npc["description"], personality=npc["personality"])
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
            if await self.memory.add(conv_id, mem["text"], kind="event", importance=mem["importance"], message_id=message_id):
                added += 1
        if added == 0 and not updates["memories"]:
            await self._remember_exchange(conv_id, user_text, reply, message_id)

        self.repo.update_message_meta(message_id, {"changes": changes})
        return {"state": new_state, "npcs": self.repo.list_npcs(conv_id), "changes": changes, "memories_added": added}

    async def _maybe_summarize(self, conv_id: int, settings: dict) -> str | None:
        conv = self.repo.get(conv_id)
        rows = self.repo.list_messages(conv_id, after_id=conv["summary_upto"])
        rows = [r for r in rows if not r["meta"].get("opening")]
        keep = int(settings["keep_recent_messages"])
        history_budget = (int(settings["context_window"]) - int(settings["max_tokens"])) * 0.5
        total = sum(estimate_tokens(r["content"]) + 6 for r in rows)
        if len(rows) <= keep + 2 or total < history_budget * 0.8:
            return None
        old = rows[:-keep]
        summary = conv["summary"]
        language = conv["scenario"].get("language") or settings.get("response_language", "en")
        chunk, size = [], 0
        try:
            for r in old:  # summarise in chunks so one call never gets huge
                line = f"{'Player' if r['role'] == 'user' else 'Narrator'}: {truncate(r['content'], 1500)}"
                chunk.append(line)
                size += len(line)
                if size > 6000:
                    summary = await self._summarize(summary, chunk, language)
                    chunk, size = [], 0
            if chunk:
                summary = await self._summarize(summary, chunk, language)
        except LLMError as exc:
            log.warning("Summarization failed: %s", exc)
            return None
        self.repo.set_summary(conv_id, summary, old[-1]["id"])
        return summary

    async def _summarize(self, previous: str, lines: list[str], language: str) -> str:
        messages = self.prompts.summary_messages(previous=previous, transcript="\n".join(lines), language=language)
        text = await self.llm.chat(messages, temperature=0.3, max_tokens=500)
        return truncate(text.strip(), 2200) or previous
