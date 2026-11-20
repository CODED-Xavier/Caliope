"""Persistence for playthroughs: conversations, messages, NPCs and game state."""
from __future__ import annotations

import json

from .appearance import normalize_appearance
from .db import Database
from .scenarios import normalize_portraits, normalize_scenario
from .state import new_state
from .portraits import process_reply
from .util import clamp, now, render_macros

NPC_COLUMNS = ("name", "description", "personality", "speech_style", "appearance", "portraits", "in_prompt", "met", "relationship", "notes", "active", "is_main")


class NotFound(Exception):
    pass


class ConversationRepository:
    def __init__(self, db: Database):
        self.db = db

    # ------------------------------------------------------------ conversations
    def create(self, scenario: dict | None = None, title: str = "", player_name: str | None = None) -> dict:
        """Start a new playthrough. `scenario` is a full scenario row (with `data`) or None for freeform."""
        data = scenario["data"] if scenario else normalize_scenario({"name": "Freeform adventure", "mode": "gm_world"})
        snapshot = {**data, "name": scenario["name"] if scenario else data["name"]}
        ts = now()
        with self.db.transaction():
            cur = self.db.execute(
                "INSERT INTO conversations(title, scenario_id, scenario_snapshot, created_at, updated_at) VALUES(?,?,?,?,?)",
                (title or snapshot["name"], scenario["id"] if scenario else None, json.dumps(snapshot, ensure_ascii=False), ts, ts),
            )
            conv_id = cur.lastrowid
            state = new_state(data.get("player"), player_name)
            self.db.execute("INSERT INTO game_state(conversation_id, data) VALUES(?,?)", (conv_id, json.dumps(state, ensure_ascii=False)))
            for i, npc in enumerate(data.get("npcs", [])):
                self.add_npc(
                    conv_id,
                    npc["name"],
                    description=npc.get("description", ""),
                    personality=npc.get("personality", ""),
                    speech_style=npc.get("speech_style", ""),
                    appearance=npc.get("appearance"),
                    portraits=npc.get("portraits"),
                    in_prompt=npc.get("in_prompt", True),
                    met=npc.get("met", True),
                    relationship=npc.get("relationship", 0),
                    is_main=1 if (data["mode"] == "character" and i == 0) else 0,
                )
            if data.get("opening_message"):
                opening = render_macros(data["opening_message"], player_name or state["player"].get("name") or "the player", snapshot["name"])
                opening, extra, met = process_reply(opening, self.list_npcs(conv_id))
                for npc_id in met:
                    self.update_npc(npc_id, met=True)
                self.add_message(conv_id, "assistant", opening, {"opening": True, **extra})
        return self.get(conv_id)

    def get(self, conv_id: int) -> dict:
        row = self.db.query_one("SELECT * FROM conversations WHERE id = ?", (conv_id,))
        if not row:
            raise NotFound(f"Conversation {conv_id} not found")
        return self._conv(row)

    @staticmethod
    def _conv(row: dict) -> dict:
        return {
            "id": row["id"],
            "title": row["title"],
            "scenario_id": row["scenario_id"],
            "scenario": json.loads(row["scenario_snapshot"] or "{}"),
            "summary": row["summary"],
            "summary_upto": row["summary_upto"],
            "pinned_memory": row.get("pinned_memory", "") or "",
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list(self) -> list[dict]:
        rows = self.db.query(
            "SELECT c.id, c.title, c.scenario_id, c.scenario_snapshot, c.created_at, c.updated_at, "
            "(SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS message_count "
            "FROM conversations c ORDER BY c.updated_at DESC"
        )
        out = []
        for r in rows:
            snap = json.loads(r["scenario_snapshot"] or "{}")
            out.append(
                {
                    "id": r["id"],
                    "title": r["title"],
                    "scenario_id": r["scenario_id"],
                    "scenario_name": snap.get("name", ""),
                    "mode": snap.get("mode", ""),
                    "message_count": r["message_count"],
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"],
                }
            )
        return out

    def rename(self, conv_id: int, title: str) -> dict:
        self.get(conv_id)
        self.db.execute("UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?", (title.strip()[:120], now(), conv_id))
        return self.get(conv_id)

    def touch(self, conv_id: int) -> None:
        self.db.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now(), conv_id))

    def delete(self, conv_id: int) -> None:
        self.get(conv_id)
        self.db.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))

    def set_pinned(self, conv_id: int, text: str, limit: int) -> dict:
        """Save the player's "remember this" box (never forgotten, always sent to the AI)."""
        self.get(conv_id)
        text = (text or "").replace("\r\n", "\n").strip()
        if len(text) > limit:
            raise ValueError(f"The memory box holds at most {limit} characters (you wrote {len(text)}).")
        self.db.execute("UPDATE conversations SET pinned_memory = ? WHERE id = ?", (text, conv_id))
        return self.get(conv_id)

    def set_summary(self, conv_id: int, summary: str, upto: int) -> None:
        self.db.execute("UPDATE conversations SET summary = ?, summary_upto = ? WHERE id = ?", (summary, upto, conv_id))

    # ----------------------------------------------------------------- messages
    @staticmethod
    def _msg(row: dict, with_snapshot: bool = False) -> dict:
        meta = json.loads(row["meta"] or "{}")
        snap = meta.pop("snapshot", None)
        out = {
            "id": row["id"],
            "conversation_id": row["conversation_id"],
            "role": row["role"],
            "content": row["content"],
            "meta": meta,
            "created_at": row["created_at"],
        }
        if with_snapshot:
            out["snapshot"] = snap
        return out

    def add_message(self, conv_id: int, role: str, content: str, meta: dict | None = None) -> dict:
        cur = self.db.execute(
            "INSERT INTO messages(conversation_id, role, content, meta, created_at) VALUES(?,?,?,?,?)",
            (conv_id, role, content, json.dumps(meta or {}, ensure_ascii=False), now()),
        )
        self.touch(conv_id)
        return self.get_message(cur.lastrowid)

    def get_message(self, message_id: int, with_snapshot: bool = False) -> dict:
        row = self.db.query_one("SELECT * FROM messages WHERE id = ?", (message_id,))
        if not row:
            raise NotFound(f"Message {message_id} not found")
        return self._msg(row, with_snapshot)

    def list_messages(self, conv_id: int, after_id: int = 0, with_snapshot: bool = False) -> list[dict]:
        rows = self.db.query("SELECT * FROM messages WHERE conversation_id = ? AND id > ? ORDER BY id", (conv_id, after_id))
        return [self._msg(r, with_snapshot) for r in rows]

    def last_message(self, conv_id: int) -> dict | None:
        row = self.db.query_one("SELECT * FROM messages WHERE conversation_id = ? ORDER BY id DESC LIMIT 1", (conv_id,))
        return self._msg(row, with_snapshot=True) if row else None

    def update_message(self, message_id: int, content: str) -> dict:
        self.get_message(message_id)
        self.db.execute("UPDATE messages SET content = ? WHERE id = ?", (content, message_id))
        return self.get_message(message_id)

    def update_message_meta(self, message_id: int, patch: dict) -> None:
        row = self.db.query_one("SELECT meta FROM messages WHERE id = ?", (message_id,))
        if not row:
            return
        meta = json.loads(row["meta"] or "{}")
        meta.update(patch)
        self.db.execute("UPDATE messages SET meta = ? WHERE id = ?", (json.dumps(meta, ensure_ascii=False), message_id))

    def delete_message(self, message_id: int) -> None:
        self.db.execute("DELETE FROM messages WHERE id = ?", (message_id,))

    # --------------------------------------------------------------------- NPCs
    def list_npcs(self, conv_id: int) -> list[dict]:
        rows = self.db.query("SELECT * FROM npcs WHERE conversation_id = ? ORDER BY is_main DESC, id", (conv_id,))
        return [self._npc(r) for r in rows]

    @staticmethod
    def _npc(row: dict) -> dict:
        row = dict(row)
        try:
            row["appearance"] = json.loads(row.get("appearance") or "{}")
        except ValueError:
            row["appearance"] = {}
        try:
            row["portraits"] = normalize_portraits(json.loads(row.get("portraits") or "{}"))
        except ValueError:
            row["portraits"] = normalize_portraits({})
        row["active"] = bool(row["active"])
        row["is_main"] = bool(row["is_main"])
        row["in_prompt"] = bool(row.get("in_prompt", 1))
        row["met"] = bool(row.get("met", 1))
        return row

    def get_npc(self, npc_id: int) -> dict:
        row = self.db.query_one("SELECT * FROM npcs WHERE id = ?", (npc_id,))
        if not row:
            raise NotFound(f"NPC {npc_id} not found")
        return self._npc(row)

    def find_npc(self, conv_id: int, name: str) -> dict | None:
        name = (name or "").strip().lower()
        if not name:
            return None
        npcs = self.list_npcs(conv_id)
        for n in npcs:
            if n["name"].lower() == name:
                return n
        for n in npcs:  # partial match ("Captain Varro" vs "Varro")
            low = n["name"].lower()
            if name in low or low in name:
                return n
        return None

    def add_npc(self, conv_id: int, name: str, description: str = "", personality: str = "", speech_style: str = "",
                relationship: int = 0, is_main: int = 0, notes: str = "", appearance: dict | None = None,
                portraits: dict | None = None, in_prompt: bool = True, met: bool = True) -> dict:
        existing = self.db.query_one("SELECT * FROM npcs WHERE conversation_id = ? AND name = ? COLLATE NOCASE", (conv_id, name))
        if existing:
            return self._npc(existing)
        cur = self.db.execute(
            "INSERT INTO npcs(conversation_id, name, description, personality, speech_style, appearance, portraits, in_prompt, met, "
            "relationship, notes, active, is_main, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,1,?,?)",
            (conv_id, name.strip(), description, personality, speech_style,
             json.dumps(normalize_appearance(appearance), ensure_ascii=False), json.dumps(normalize_portraits(portraits), ensure_ascii=False),
             1 if in_prompt else 0, 1 if met else 0, int(clamp(relationship, -100, 100)), notes, int(is_main), now()),
        )
        return self.get_npc(cur.lastrowid)

    def update_npc(self, npc_id: int, **fields) -> dict:
        self.get_npc(npc_id)
        sets, params = [], []
        for key, value in fields.items():
            if key not in NPC_COLUMNS or value is None:
                continue
            if key == "relationship":
                value = int(clamp(int(value), -100, 100))
            if key == "appearance":
                value = json.dumps(normalize_appearance(value), ensure_ascii=False)
            if key == "portraits":
                value = json.dumps(normalize_portraits(value), ensure_ascii=False)
            if key in ("active", "is_main", "in_prompt", "met"):
                value = 1 if value else 0
            sets.append(f"{key} = ?")
            params.append(value)
        if sets:
            self.db.execute(f"UPDATE npcs SET {', '.join(sets)} WHERE id = ?", (*params, npc_id))
        return self.get_npc(npc_id)

    def delete_npc(self, npc_id: int) -> None:
        self.get_npc(npc_id)
        self.db.execute("DELETE FROM npcs WHERE id = ?", (npc_id,))

    # -------------------------------------------------------------------- state
    def get_state(self, conv_id: int) -> dict:
        row = self.db.query_one("SELECT data FROM game_state WHERE conversation_id = ?", (conv_id,))
        if not row:
            raise NotFound(f"State for conversation {conv_id} not found")
        return json.loads(row["data"])

    def save_state(self, conv_id: int, state: dict) -> None:
        self.db.execute(
            "INSERT INTO game_state(conversation_id, data) VALUES(?, ?) "
            "ON CONFLICT(conversation_id) DO UPDATE SET data = excluded.data",
            (conv_id, json.dumps(state, ensure_ascii=False)),
        )

    # ---------------------------------------------------------------- snapshots
    def capture_snapshot(self, conv_id: int) -> dict:
        return {"state": self.get_state(conv_id), "npcs": self.list_npcs(conv_id)}

    def restore_snapshot(self, conv_id: int, snap: dict) -> None:
        """Roll state and NPCs back to an earlier capture (used by regenerate/undo)."""
        with self.db.transaction():
            self.save_state(conv_id, snap["state"])
            saved = {n["id"]: n for n in snap["npcs"]}
            current = {n["id"]: n for n in self.list_npcs(conv_id)}
            for npc_id in current:
                if npc_id not in saved:
                    self.db.execute("DELETE FROM npcs WHERE id = ?", (npc_id,))
            for npc_id, n in saved.items():
                if npc_id in current:
                    self.db.execute(
                        "UPDATE npcs SET description=?, personality=?, speech_style=?, appearance=?, portraits=?, in_prompt=?, met=?, "
                        "relationship=?, notes=?, active=?, is_main=? WHERE id=?",
                        (n["description"], n["personality"], n["speech_style"], json.dumps(n.get("appearance") or {}, ensure_ascii=False),
                         json.dumps(n.get("portraits") or {}, ensure_ascii=False), int(n.get("in_prompt", True)), int(n.get("met", True)),
                         n["relationship"], n["notes"], int(n["active"]), int(n["is_main"]), npc_id),
                    )
                else:
                    self.db.execute(
                        "INSERT INTO npcs(id, conversation_id, name, description, personality, speech_style, appearance, portraits, in_prompt, met, "
                        "relationship, notes, active, is_main, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (npc_id, conv_id, n["name"], n["description"], n["personality"], n["speech_style"],
                         json.dumps(n.get("appearance") or {}, ensure_ascii=False), json.dumps(n.get("portraits") or {}, ensure_ascii=False),
                         int(n.get("in_prompt", True)), int(n.get("met", True)), n["relationship"], n["notes"],
                         int(n["active"]), int(n["is_main"]), n["created_at"]),
                    )
