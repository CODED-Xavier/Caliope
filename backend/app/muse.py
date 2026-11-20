"""The Muse: a writer's room with the same model that plays the games.

You talk with her about stories, worlds and characters (talks are saved). When an idea is ready, "Make it a card"
turns the talk into a Calíope card. A small model writes good prose but unreliable long JSON, so she is asked for
the card one piece at a time (title, world, cast, each character, opening) and the app assembles and checks it.
"""
from __future__ import annotations

import re
from typing import AsyncIterator

from .db import Database
from .scenarios import normalize_scenario
from .util import estimate_tokens, now, truncate

MUSE_PROMPT = """You are the Muse of Calíope, a creative partner who helps {user} invent stories, worlds, characters and roleplay cards.
Calíope is an app where an AI game master (the Aedo) or an AI character plays the stories with the player.

How you work:
- Be a real collaborator: build on the ideas, offer two or three concrete options when there is a choice, ask one
  good question when something important is undecided, and point out contradictions kindly.
- Think in playable terms: what the player does, who they meet, what is at stake, what makes scenes fun.
- Characters need a clear role, a personality with a contradiction, a way of speaking and a look.
- Dark, mature and morally grey fiction is welcome when {user} wants it; it is fiction.
- Answer in the language {user} writes in. Keep answers focused (usually under 300 words) unless asked for more.
"""

SUMMARY_PROMPT = """Summarize this brainstorm for a writer who will continue it. Keep every decision, name, place, rule,
character detail and open question. Use short bullet points. Under 350 words.

Earlier summary:
{previous}

New part of the talk:
{talk}"""

KEEP_RECENT = 8
MAX_REPLY_TOKENS = 700


class MuseError(ValueError):
    pass


class Muse:
    def __init__(self, db: Database, llm, get_settings):
        self.db = db
        self.llm = llm
        self._get = get_settings

    # ------------------------------------------------------------------ talks
    def list(self) -> list[dict]:
        return self.db.query("SELECT t.id, t.title, t.updated_at, (SELECT COUNT(*) FROM muse_messages m WHERE m.talk_id = t.id) AS messages "
                             "FROM muse_talks t ORDER BY t.updated_at DESC")

    def create(self, title: str = "") -> dict:
        ts = now()
        cur = self.db.execute("INSERT INTO muse_talks(title, summary, summary_upto, created_at, updated_at) VALUES(?,?,?,?,?)",
                              (truncate(title.strip(), 80) or "New idea", "", 0, ts, ts))
        return self.get(cur.lastrowid)

    def get(self, talk_id: int) -> dict:
        row = self.db.query_one("SELECT * FROM muse_talks WHERE id = ?", (talk_id,))
        if not row:
            raise MuseError("That talk with the Muse no longer exists.")
        msgs = self.db.query("SELECT id, role, content, created_at FROM muse_messages WHERE talk_id = ? ORDER BY id", (talk_id,))
        return {**row, "messages": msgs}

    def rename(self, talk_id: int, title: str) -> dict:
        self.get(talk_id)
        self.db.execute("UPDATE muse_talks SET title = ? WHERE id = ?", (truncate(title.strip(), 80) or "New idea", talk_id))
        return self.get(talk_id)

    def delete(self, talk_id: int) -> None:
        self.db.execute("DELETE FROM muse_messages WHERE talk_id = ?", (talk_id,))
        self.db.execute("DELETE FROM muse_talks WHERE id = ?", (talk_id,))

    def _add(self, talk_id: int, role: str, content: str) -> dict:
        ts = now()
        cur = self.db.execute("INSERT INTO muse_messages(talk_id, role, content, created_at) VALUES(?,?,?,?)", (talk_id, role, content, ts))
        self.db.execute("UPDATE muse_talks SET updated_at = ? WHERE id = ?", (ts, talk_id))
        return {"id": cur.lastrowid, "role": role, "content": content, "created_at": ts}

    def undo_last(self, talk_id: int) -> None:
        """Remove the Muse's last answer (and the message that asked for it), to ask again differently."""
        rows = self.db.query("SELECT id, role FROM muse_messages WHERE talk_id = ? ORDER BY id DESC LIMIT 2", (talk_id,))
        for r in rows:
            self.db.execute("DELETE FROM muse_messages WHERE id = ?", (r["id"],))
            if r["role"] == "user":
                break

    # ------------------------------------------------------------------ context
    def _player_name(self) -> str:
        return "the writer"

    def _budget(self) -> int:
        ctx = int(self._get().get("context_window") or 8192)
        return max(1500, ctx - MAX_REPLY_TOKENS - 400)

    async def _context(self, talk: dict) -> tuple[str, list[dict]]:
        """(summary, recent messages) that fit the model; older parts are folded into the summary first."""
        msgs = talk["messages"]
        summary, upto = talk.get("summary") or "", int(talk.get("summary_upto") or 0)
        recent = [m for m in msgs if m["id"] > upto]
        system = MUSE_PROMPT.format(user=self._player_name())
        cost = lambda: estimate_tokens(system + summary) + sum(estimate_tokens(m["content"]) + 6 for m in recent)  # noqa: E731
        if cost() > self._budget() and len(recent) > KEEP_RECENT:
            fold, recent = recent[:-KEEP_RECENT], recent[-KEEP_RECENT:]
            talk_text = "\n\n".join(f"{'Writer' if m['role'] == 'user' else 'Muse'}: {m['content']}" for m in fold)
            summary = (await self.llm.chat([{"role": "user", "content": SUMMARY_PROMPT.format(
                previous=summary or "(none)", talk=truncate(talk_text, 12000))}], max_tokens=600, temperature=0.3)).strip()
            upto = fold[-1]["id"]
            self.db.execute("UPDATE muse_talks SET summary = ?, summary_upto = ? WHERE id = ?", (summary, upto, talk["id"]))
        while recent and cost() > self._budget() and len(recent) > 2:
            recent = recent[1:]
        return summary, recent

    def _messages(self, summary: str, recent: list[dict], extra: str = "") -> list[dict]:
        system = MUSE_PROMPT.format(user=self._player_name())
        if summary:
            system += f"\n\nWhat you and the writer decided so far:\n{summary}"
        out = [{"role": "system", "content": system}]
        for m in recent:
            if out[-1]["role"] == m["role"]:
                out[-1]["content"] += "\n\n" + m["content"]
            else:
                out.append({"role": m["role"], "content": m["content"]})
        if extra:
            if out[-1]["role"] == "user":
                out[-1]["content"] += "\n\n" + extra
            else:
                out.append({"role": "user", "content": extra})
        if len(out) > 1 and out[1]["role"] == "assistant":  # many chat templates need a user turn first
            out.insert(1, {"role": "user", "content": "(continuing our talk)"})
        return out

    # ------------------------------------------------------------------ talking
    async def talk(self, talk_id: int, text: str) -> AsyncIterator[dict]:
        text = (text or "").strip()
        if not text:
            yield {"type": "error", "message": "Write something to the Muse first."}
            return
        talk = self.get(talk_id)
        if not talk["messages"] and talk["title"] == "New idea":
            self.db.execute("UPDATE muse_talks SET title = ? WHERE id = ?", (truncate(text.split("\n")[0], 60), talk_id))
        user_msg = self._add(talk_id, "user", text)
        yield {"type": "user_message", "message": user_msg}
        talk = self.get(talk_id)
        summary, recent = await self._context(talk)
        parts: list[str] = []
        try:
            async for piece in self.llm.stream_chat(self._messages(summary, recent), max_tokens=MAX_REPLY_TOKENS, temperature=0.9):
                parts.append(piece)
                yield {"type": "token", "text": piece}
        except Exception as exc:  # the model server went away: keep the question, report the problem
            yield {"type": "error", "message": f"The Muse could not answer: {exc}"}
            return
        reply = "".join(parts).strip()
        if not reply:
            yield {"type": "error", "message": "The Muse had nothing to say. Try again."}
            return
        yield {"type": "muse_message", "message": self._add(talk_id, "assistant", reply)}
        yield {"type": "done"}

    # ------------------------------------------------------------------ making a card
    async def _ask(self, summary: str, recent: list[dict], question: str, max_tokens: int, temperature: float = 0.7) -> str:
        msgs = self._messages(summary, recent, extra=(
            "[Card maker] We are now turning our talk into a card for the app. " + question +
            " Write only what is asked: no introduction, no comments, no markdown headings."))
        raw = await self.llm.chat(msgs, max_tokens=max_tokens, temperature=temperature)
        return re.sub(r"^\s*(sure|here( is|'s)|of course)[^\n]*\n", "", (raw or "").strip(), flags=re.I).strip()

    async def make_card(self, talk_id: int) -> AsyncIterator[dict]:
        talk = self.get(talk_id)
        if not talk["messages"]:
            yield {"type": "error", "message": "Talk with the Muse about your idea first."}
            return
        summary, recent = await self._context(talk)

        async def ask(step: str, question: str, max_tokens: int, temperature: float = 0.7) -> str:
            return await self._ask(summary, recent, question, max_tokens, temperature)

        try:
            yield {"type": "progress", "step": "Title and pitch"}
            name = first_line(await ask("name", "Give the card's title: at most 6 words.", 30))
            pitch = await ask("pitch", "Write a one or two sentence pitch of this card, for a list of cards.", 90)
            yield {"type": "progress", "step": "Who the AI plays"}
            who = (await ask("mode", "Does the AI play ONE single character with the player (answer CHARACTER), "
                                     "or is it a game master running a world with many characters (answer GM)? One word.", 5, 0.1)).upper()
            yield {"type": "progress", "step": "The world"}
            world = await ask("world", "Describe the world for the game master: places, factions, how magic or technology "
                                       "works, conflicts and secrets. 150 to 350 words, plain paragraphs.", 600)
            tone = await ask("tone", "Describe the tone and writing style of this story in 1 to 3 sentences.", 120)
            yield {"type": "progress", "step": "The characters"}
            listing = await ask("cast", "List the important characters we discussed (at most 8), one per line, as: "
                                        "Name - role. Only the list.", 250, 0.3)
            cast = parse_cast(listing)
            npcs = []
            for i, (cname, role) in enumerate(cast):
                yield {"type": "progress", "step": f"Character {i + 1} of {len(cast)}: {cname}"}
                sheet = parse_sheet(await ask("npc", (
                    f"Write the sheet of {cname} ({role}) as exactly five labeled lines:\n"
                    "Description: (who they are, history, what they want; 2-4 sentences)\n"
                    "Personality: (traits, a contradiction, habits)\nSpeech: (how they talk)\n"
                    "Looks: (hair, eyes, build, clothes)\nRace: (one or two words)"), 420))
                npcs.append({
                    "name": cname,
                    "description": (f"{role}. " if role else "") + sheet.get("description", ""),
                    "personality": sheet.get("personality", ""), "speech_style": sheet.get("speech", ""),
                    "appearance": {"race": sheet.get("race", ""), "extra": sheet.get("looks", "")},
                    "relationship": 0, "met": i == 0 and who.startswith("CHAR"), "in_prompt": True,
                })
            yield {"type": "progress", "step": "The opening scene"}
            opening = await ask("opening", "Write the opening message of the story: 120 to 250 words, in second person "
                                           "('you'), vivid, ending at a moment where the player must act.", 500, 0.9)
        except Exception as exc:  # the model server went away
            yield {"type": "error", "message": f"The Muse could not finish the card: {exc}"}
            return
        mode = "character" if who.startswith("CHAR") and npcs else ("gm_cast" if npcs else "gm_world")
        card = normalize_scenario({
            "name": name or talk["title"], "description": pitch, "mode": mode, "kind": "roleplay",
            "world": world, "tone": tone, "opening_message": opening, "npcs": npcs,
            "information": {"creator": "Calíope Muse", "creator_notes": f"Made with the Muse from the talk \"{talk['title']}\"."},
        }, default_mode=mode)
        yield {"type": "card", "card": card}
        yield {"type": "done"}


def first_line(text: str) -> str:
    line = (text or "").strip().split("\n")[0]
    return truncate(line.strip().strip('"*#').strip(), 80)


def parse_cast(text: str) -> list[tuple[str, str]]:
    out, seen = [], set()
    for line in (text or "").splitlines():
        line = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip().strip("*")
        if not line:
            continue
        m = re.match(r"^\**([^\-–—:(]{2,60}?)\**\s*(?:[-–—:]|\()\s*(.*?)\)?\s*$", line)
        name, role = (m.group(1).strip(), m.group(2).strip()) if m else (line[:60].strip(), "")
        name = name.strip("*").strip()
        if not name or len(name.split()) > 6 or name.lower() in seen:
            continue
        seen.add(name.lower())
        out.append((name, truncate(role, 120)))
        if len(out) == 8:
            break
    return out


def parse_sheet(text: str) -> dict:
    out: dict[str, str] = {}
    key = None
    for line in (text or "").splitlines():
        m = re.match(r"^\s*\**\s*(description|personality|speech|speech style|looks|appearance|race)\s*\**\s*:\s*\**\s*(.*)$", line, re.I)
        if m:
            key = {"speech style": "speech", "appearance": "looks"}.get(m.group(1).lower(), m.group(1).lower())
            out[key] = m.group(2).strip()
        elif key and line.strip():
            out[key] = (out[key] + " " + line.strip()).strip()
    return {k: truncate(v, 900) for k, v in out.items()}
