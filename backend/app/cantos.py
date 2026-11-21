"""Cantos (chapters), the recap, and the map bag (scene pictures you keep).

A game is told in Cantos. Closing one asks the model for a short chronicle of it; the chronicles of closed Cantos
go into the stable part of the prompt, so the Aedo remembers whole chapters even after the messages scroll away.
Rewinding or undoing into a closed Canto reopens it. The recap is only written when the player asks for it, and
is never added to the story. Kept pictures are listed with their place, in-game date and Canto.
"""
from __future__ import annotations

from .db import Database
from .util import now, truncate

CHRONICLE_PROMPT = """You are the chronicler of a roleplay story. Write the chronicle of the chapter below for the
game master's memory: 120 to 220 words, past tense, third person. Keep names, places, decisions, promises,
discoveries, fights and how relationships changed. No commentary, no title.

{previous}Chapter:
{text}"""

TITLE_PROMPT = """Give a title of 2 to 5 words to this chapter of a story, like a chapter in a novel. Only the title.

{chronicle}"""

EPILOGUE_PROMPT = """The story "{title}" has ended. Write its epilogue in {language}, from what really happened below.

1. Two to four paragraphs: what became of {player} and of each important character afterwards, true to their choices.
2. Then a heading "The story in brief" and 3 to 6 short bullet points with the key moments, in order.
No new adventures, no questions to the player.

{facts}"""

RECAP_PROMPT = """Write a "Previously, in {title}..." recap for the player who is coming back to this story:
90 to 170 words, second person ("you"), vivid but clear, ending with where things stand right now and what is
at stake. Use only the facts below. Write in {language}.

{facts}"""

ROMAN = [(10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]


def roman(n: int) -> str:
    out = ""
    for value, mark in [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"), (50, "L"), (40, "XL")] + ROMAN:
        while n >= value:
            out += mark
            n -= value
    return out


def _transcript(msgs: list[dict], limit: int) -> str:
    lines = [f"{'Player' if m['role'] == 'user' else 'Story'}: {m['content']}" for m in msgs]
    text = "\n\n".join(lines)
    return text if len(text) <= limit else "…" + text[-limit:]


class CantoBook:
    def __init__(self, db: Database, llm):
        self.db = db
        self.llm = llm

    # ------------------------------------------------------------------ cantos
    def current(self, conv_id: int) -> dict:
        row = self.db.query_one("SELECT * FROM cantos WHERE conversation_id = ? AND closed_at IS NULL ORDER BY number DESC LIMIT 1", (conv_id,))
        if row:
            return row
        last = self.db.query_one("SELECT MAX(number) AS n, MAX(last_message_id) AS m FROM cantos WHERE conversation_id = ?", (conv_id,))
        number = int(last["n"] or 0) + 1
        first = int(last["m"] or 0) + 1 if last["n"] else 0
        cur = self.db.execute(
            "INSERT INTO cantos(conversation_id, number, title, chronicle, first_message_id, last_message_id, closed_at, created_at) "
            "VALUES(?,?,?,?,?,NULL,NULL,?)", (conv_id, number, "", "", first, now()))
        return self.db.query_one("SELECT * FROM cantos WHERE id = ?", (cur.lastrowid,))

    def list(self, conv_id: int) -> list[dict]:
        self.current(conv_id)
        rows = self.db.query("SELECT * FROM cantos WHERE conversation_id = ? ORDER BY number", (conv_id,))
        for r in rows:
            r["label"] = f"Canto {roman(r['number'])}"
            hi = r["last_message_id"] if r["last_message_id"] is not None else 10 ** 12
            r["messages"] = self.db.query_one("SELECT COUNT(*) AS n FROM messages WHERE conversation_id = ? AND id >= ? AND id <= ?",
                                              (conv_id, r["first_message_id"], hi))["n"]
        return rows

    def rename(self, canto_id: int, title: str) -> dict:
        self.db.execute("UPDATE cantos SET title = ? WHERE id = ?", (truncate(title.strip(), 80), canto_id))
        return self.db.query_one("SELECT * FROM cantos WHERE id = ?", (canto_id,))

    async def close(self, conv_id: int, title: str = "") -> dict:
        """Write the chronicle of the current Canto and open the next one."""
        canto = self.current(conv_id)
        msgs = self.db.query("SELECT id, role, content FROM messages WHERE conversation_id = ? AND id >= ? ORDER BY id",
                             (conv_id, canto["first_message_id"]))
        if sum(1 for m in msgs if m["role"] == "user") < 2:
            raise ValueError("This Canto is too short to close: play a little more first.")
        prev = self.db.query_one("SELECT chronicle FROM cantos WHERE conversation_id = ? AND number = ?", (conv_id, canto["number"] - 1))
        previous = f"Previous chapter (for context only):\n{truncate(prev['chronicle'], 800)}\n\n" if prev and prev["chronicle"] else ""
        chronicle = (await self.llm.chat([{"role": "user", "content": CHRONICLE_PROMPT.format(
            previous=previous, text=_transcript(msgs, 14000))}], max_tokens=420, temperature=0.4)).strip()
        if not chronicle:
            raise ValueError("The model did not write the chronicle. Is the model running?")
        if not title.strip():
            title = (await self.llm.chat([{"role": "user", "content": TITLE_PROMPT.format(chronicle=chronicle)}],
                                         max_tokens=20, temperature=0.6)).strip().split("\n")[0].strip('"*# ')
        self.db.execute("UPDATE cantos SET title = ?, chronicle = ?, last_message_id = ?, closed_at = ? WHERE id = ?",
                        (truncate(title, 80) or f"Canto {roman(canto['number'])}", chronicle, msgs[-1]["id"], now(), canto["id"]))
        self.current(conv_id)  # opens the next one
        return {"closed": self.db.query_one("SELECT * FROM cantos WHERE id = ?", (canto["id"],)), "cantos": self.list(conv_id)}

    def trim(self, conv_id: int, first_removed_id: int) -> None:
        """Messages from `first_removed_id` on were removed: drop the Cantos that began there, reopen the one cut in half."""
        self.db.execute("DELETE FROM cantos WHERE conversation_id = ? AND first_message_id >= ? AND number > 1",
                        (conv_id, first_removed_id))
        self.db.execute("UPDATE cantos SET closed_at = NULL, last_message_id = NULL, chronicle = '' "
                        "WHERE conversation_id = ? AND closed_at IS NOT NULL AND last_message_id >= ?", (conv_id, first_removed_id))
        open_ones = self.db.query("SELECT id FROM cantos WHERE conversation_id = ? AND closed_at IS NULL ORDER BY number", (conv_id,))
        for extra in open_ones[:-1]:  # only the last Canto can be open
            self.db.execute("DELETE FROM cantos WHERE id = ?", (extra["id"],))
        self.db.execute("DELETE FROM kept_pictures WHERE conversation_id = ? AND message_id >= ?", (conv_id, first_removed_id))

    def prompt_section(self, conv_id: int, max_chars: int) -> str:
        """Chronicles of the closed Cantos for the stable prompt (newest kept whole when space is short)."""
        rows = self.db.query("SELECT number, title, chronicle FROM cantos WHERE conversation_id = ? AND closed_at IS NOT NULL "
                             "AND chronicle != '' ORDER BY number", (conv_id,))
        if not rows:
            return ""
        parts, used = [], 0
        for r in reversed(rows):
            text = f"Canto {roman(r['number'])}, {r['title']}: {r['chronicle']}"
            if used + len(text) > max_chars:
                text = truncate(text, max(200, max_chars - used))
            parts.append(text)
            used += len(text)
            if used >= max_chars:
                break
        return "## The story so far, Canto by Canto (chronicles)\n" + "\n\n".join(reversed(parts))

    async def recap(self, conv_id: int, title: str, summary: str, language: str) -> str:
        chron = self.prompt_section(conv_id, 3000)
        recent = self.db.query("SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY id DESC LIMIT 6", (conv_id,))
        facts = "\n\n".join(x for x in (chron, f"Summary:\n{summary}" if summary else "",
                                        "Latest moments:\n" + _transcript(list(reversed(recent)), 5000)) if x)
        lang = {"pt-BR": "Brazilian Portuguese"}.get(language, "English")
        text = await self.llm.chat([{"role": "user", "content": RECAP_PROMPT.format(title=title, facts=facts, language=lang)}],
                                   max_tokens=320, temperature=0.7)
        return (text or "").strip()

    async def epilogue(self, conv_id: int, title: str, summary: str, language: str, player: str) -> str:
        """After THE END: what became of everyone, and the story in brief."""
        chron = self.prompt_section(conv_id, 4000)
        recent = self.db.query("SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY id DESC LIMIT 8", (conv_id,))
        facts = "\n\n".join(x for x in (chron, f"Summary:\n{summary}" if summary else "",
                                        "The last moments:\n" + _transcript(list(reversed(recent)), 6000)) if x)
        lang = {"pt-BR": "Brazilian Portuguese"}.get(language, "English")
        text = await self.llm.chat([{"role": "user", "content": EPILOGUE_PROMPT.format(
            title=title, facts=facts, language=lang, player=player or "the player's character")}], max_tokens=700, temperature=0.7)
        return (text or "").strip()

    # ------------------------------------------------------------------ the map bag
    def keep(self, conv_id: int, message_id: int, pic: dict, state: dict, title: str = "", auto: bool = False) -> dict:
        found = self.db.query_one("SELECT * FROM kept_pictures WHERE conversation_id = ? AND url = ?", (conv_id, pic["url"]))
        if found:
            return found
        canto = self.current(conv_id)
        place = str(state.get("location") or "")
        cur = self.db.execute(
            "INSERT INTO kept_pictures(conversation_id, message_id, url, prompt, title, location, date_label, canto, auto, created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (conv_id, message_id, pic["url"], pic.get("prompt", ""), truncate(title.strip(), 80) or place or "A scene", place,
             str(state.get("date_label") or state.get("time") or ""), canto["number"], 1 if auto else 0, now()))
        return self.db.query_one("SELECT * FROM kept_pictures WHERE id = ?", (cur.lastrowid,))

    def auto_keep(self, conv_id: int, message_id: int, pic: dict, state: dict) -> dict | None:
        """Keep the first picture of every place on its own."""
        place = str(state.get("location") or "")
        if place and self.db.query_one("SELECT 1 FROM kept_pictures WHERE conversation_id = ? AND lower(location) = lower(?)", (conv_id, place)):
            return None
        return self.keep(conv_id, message_id, pic, state, auto=True)

    def gallery(self, conv_id: int) -> list[dict]:
        rows = self.db.query("SELECT * FROM kept_pictures WHERE conversation_id = ? ORDER BY id", (conv_id,))
        for r in rows:
            r["canto_label"] = f"Canto {roman(r['canto'])}" if r.get("canto") else ""
        return rows

    def rename_picture(self, pic_id: int, title: str) -> dict:
        self.db.execute("UPDATE kept_pictures SET title = ? WHERE id = ?", (truncate(title.strip(), 80) or "A scene", pic_id))
        return self.db.query_one("SELECT * FROM kept_pictures WHERE id = ?", (pic_id,))

    def remove_picture(self, pic_id: int) -> dict | None:
        row = self.db.query_one("SELECT * FROM kept_pictures WHERE id = ?", (pic_id,))
        self.db.execute("DELETE FROM kept_pictures WHERE id = ?", (pic_id,))
        return row
