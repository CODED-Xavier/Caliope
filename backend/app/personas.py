"""Personas: player characters you keep and reuse on any start screen (name, background, looks, personality,
and your world additions)."""
from __future__ import annotations

import json

from .db import Database
from .util import now, truncate

MAX_BYTES = 40_000


class PersonaStore:
    def __init__(self, db: Database):
        self.db = db

    def list(self) -> list[dict]:
        return [self._row(r) for r in self.db.query("SELECT * FROM personas ORDER BY updated_at DESC")]

    def get(self, persona_id: int) -> dict:
        row = self.db.query_one("SELECT * FROM personas WHERE id = ?", (persona_id,))
        if not row:
            raise ValueError("That persona no longer exists.")
        return self._row(row)

    def save(self, data: dict, persona_id: int | None = None) -> dict:
        player = data.get("player") if isinstance(data.get("player"), dict) else {}
        lore = data.get("lore") if isinstance(data.get("lore"), list) else []
        name = truncate(str(data.get("name") or player.get("name") or "").strip(), 60)
        if not name:
            raise ValueError("Give the persona a name.")
        body = json.dumps({"player": player, "lore": lore[:30]}, ensure_ascii=False)
        if len(body.encode("utf-8")) > MAX_BYTES:
            raise ValueError("This persona is too long (shorten the background or the world additions).")
        ts = now()
        if persona_id:
            self.get(persona_id)
            self.db.execute("UPDATE personas SET name = ?, data = ?, updated_at = ? WHERE id = ?", (name, body, ts, persona_id))
        else:
            persona_id = self.db.execute("INSERT INTO personas(name, data, created_at, updated_at) VALUES(?,?,?,?)",
                                         (name, body, ts, ts)).lastrowid
        return self.get(persona_id)

    def delete(self, persona_id: int) -> None:
        self.db.execute("DELETE FROM personas WHERE id = ?", (persona_id,))

    @staticmethod
    def _row(r: dict) -> dict:
        data = json.loads(r["data"] or "{}")
        return {"id": r["id"], "name": r["name"], "player": data.get("player", {}), "lore": data.get("lore", []),
                "updated_at": r["updated_at"]}
