"""Persistence for playthroughs: conversations, messages, NPCs and game state."""
from __future__ import annotations

import json
import random
import re

from . import adventure
from .appearance import normalize_appearance
from .db import Database, pack_snapshot, unpack_snapshot
from .scenarios import normalize_portraits, normalize_scenario
from .state import new_state
from .portraits import process_reply
from .util import clamp, now, render_macros
from .playerlore import clean_entries
from .resources import start_pools
from . import routes, statusbook
from .cards import resolve_features
from .worldtime import format_now, time_label, weather_on

NPC_COLUMNS = ("name", "description", "personality", "speech_style", "appearance", "portraits", "in_prompt", "met", "relationship", "notes", "active", "is_main")


class NotFound(Exception):
    pass


def _skills_field(tpl: str, card_status: dict | None, abilities: list | None) -> dict:
    """The card's own "Skills" field (Lumencia's INFO block) lists the skills made on the start screen."""
    names = [str(a.get("name") or "").strip() for a in abilities or [] if isinstance(a, dict) and str(a.get("name") or "").strip()]
    field = next((f for f in statusbook.custom_fields(tpl) if re.match(r"^(skills?|habilidades?|abilities|powers|poderes)\b", f, re.I)), None)
    if not names or not field or str((card_status or {}).get(field) or "").strip() not in ("", "-"):
        return {}
    return {field: " / ".join(names)}


PLAYER_FIELDS = ("name", "race", "class", "level", "background", "description", "traits", "stats", "hp", "ac", "skills", "portraits")



def _json_list(raw) -> list:
    try:
        value = json.loads(raw or "[]")
    except ValueError:
        return []
    return value if isinstance(value, list) else []



def _focused(name: str, focus: set[str]) -> bool:
    """A character the route starts with: the full name, or its first name, is in the route's focus list."""
    n = name.lower().strip()
    return n in focus or n.split(" ")[0] in focus or any(f.split(" ")[0] == n for f in focus)


class ConversationRepository:
    def __init__(self, db: Database):
        self.db = db

    # ------------------------------------------------------------ conversations
    def create(self, scenario: dict | None = None, title: str = "", player_name: str | None = None,
               player: dict | None = None, setup: str = "", player_lore: list | None = None, start: str = "",
               party_mode: str = "", card_status: dict | None = None, companions: list | None = None,
               abilities: list | None = None, systems_state: dict | None = None, language: str = "") -> dict:
        """`player` comes from the start screen and is laid over the card's starting sheet.
        `card_status`: the card's own sheet (Tier, Attributes, Stats...) filled on the start screen.
        `setup` is "app" (made on the start screen), "card" (the card asks in the story) or ""."""
        """Start a new playthrough. `scenario` is a full scenario row (with `data`) or None for freeform."""
        data = scenario["data"] if scenario else normalize_scenario({"name": "Freeform adventure", "mode": "gm_world"})
        if companions:  # set up on the start screen (names, looks, pictures): this game's companions
            from .party import apply_companion_edits
            data = {**data, "npcs": apply_companion_edits(data.get("npcs") or [], companions)}
        snapshot = {**data, "name": scenario["name"] if scenario else data["name"]}
        if language in ("en", "pt-BR"):  # "play this card in Portuguese": this game's story language
            snapshot["language"] = language
        route = routes.resolve(data, start)  # None: the card's default start
        if route:
            snapshot["route"] = {k: route[k] for k in ("id", "name", "setting", "focus", "scenes")}
        ts = now()
        with self.db.transaction():
            cur = self.db.execute(
                "INSERT INTO conversations(title, scenario_id, scenario_snapshot, player_lore, created_at, updated_at) VALUES(?,?,?,?,?,?)",
                (title or snapshot["name"], scenario["id"] if scenario else None, json.dumps(snapshot, ensure_ascii=False),
                 json.dumps(clean_entries(player_lore or []), ensure_ascii=False), ts, ts),
            )
            conv_id = cur.lastrowid
            template = dict(data.get("player") or {})
            for key, value in (player or {}).items():
                if key in PLAYER_FIELDS and value not in (None, ""):
                    template[key] = value
            state = new_state(template, player_name or (player or {}).get("name"))
            if data.get("resources"):
                state["resources"] = start_pools(data["resources"])
                state["abilities"] = [dict(a) for a in data.get("abilities") or []]
            if data.get("systems"):  # the card's own sheet: its start, or the start screen's checked by its rules
                from .systems import merge_state
                state["systems"] = merge_state(data["systems"], systems_state)
            if abilities:  # your own skills, made on the start screen
                from .resources import MAX_ABILITIES, normalize_abilities
                mine = normalize_abilities([{**a, "own": True} for a in abilities if isinstance(a, dict)], data.get("resources"))
                state["abilities"] = ([dict(a) for a in state.get("abilities") or []] + mine)[:MAX_ABILITIES]
            cal = data.get("calendar") or {}
            if cal.get("enabled") and cal.get("months"):
                state["clock"] = {"minutes": 0, "seed": random.randrange(1, 1_000_000)}
                state["time"] = time_label(cal, 0)
                if cal.get("climate", "temperate") != "none":
                    state["weather"] = weather_on(cal, 0, state["clock"]["seed"])
                state["date_label"] = format_now(cal, 0)
            if setup in ("app", "card"):
                state["setup"] = setup
            if route and route["scenes"]:
                state["script"] = {"next": 0}
            adv = data.get("adventure") or {}
            if adv.get("scenes") and not route:
                first = adv["scenes"][0]
                adventure.enter(state, first["id"])
                if first.get("music"):
                    state["scene_mood"] = first["music"]
                if str(data.get("opening_message") or "").strip():
                    state["adventure"]["fresh"] = ""  # the opening already set the scene
            from .party import companions, start_party
            if not party_mode:
                party_mode = "companions" if companions(data) else "solo"
            start_party(state, data, party_mode)  # app/party.py: solo, or with the card's companions
            solo = state["party_mode"] == "solo"
            focus = {f.lower() for f in (route or {}).get("focus") or []}
            self.db.execute("INSERT INTO game_state(conversation_id, data) VALUES(?,?)", (conv_id, json.dumps(state, ensure_ascii=False)))
            for i, npc in enumerate(data.get("npcs", [])):
                if solo and npc.get("companion"):
                    continue
                if npc.get("route") and npc["route"] != ((route or {}).get("id") or "default"):
                    continue  # this character belongs to another route of the card
                self.add_npc(
                    conv_id,
                    npc["name"],
                    description=npc.get("description", ""),
                    personality=npc.get("personality", ""),
                    speech_style=npc.get("speech_style", ""),
                    appearance=npc.get("appearance"),
                    portraits=npc.get("portraits"),
                    in_prompt=npc.get("in_prompt", True),
                    met=True if focus and _focused(npc["name"], focus) else (False if focus else npc.get("met", True)),
                    relationship=npc.get("relationship", 0),
                    is_main=1 if (data["mode"] == "character" and i == 0) else 0,
                )
            opening_text = (route or {}).get("opening") or data.get("opening_message")
            if opening_text:
                opening = render_macros(opening_text, player_name or state["player"].get("name") or "the player", snapshot["name"])
                opening, extra, met = process_reply(opening, self.list_npcs(conv_id))
                tpl = statusbook.template_of(data)
                if tpl and extra.get("status") and resolve_features(data).get("status_by", "app") == "app":
                    statusbook.harvest(state, tpl, extra["status"])  # the opening's block gives the card's starting values
                    self.save_state(conv_id, state)
                mine = statusbook.clean_values(tpl, {**(card_status or {}), **_skills_field(tpl, card_status, abilities)}) if tpl and (card_status or abilities) else {}
                if mine:  # the sheet filled on the start screen: the story does not ask for it again
                    state["card_status"] = {**(state.get("card_status") or {}), **mine}
                    state["sheet_from_chat"] = True
                    self.save_state(conv_id, state)
                    if extra.get("status"):
                        extra["status"] = statusbook.render(tpl, state, self.list_npcs(conv_id))
                for npc_id in met:
                    self.update_npc(npc_id, met=True)
                self.add_message(conv_id, "assistant", opening, {"opening": True, **extra})
            tpl = statusbook.template_of(data)
            mine = statusbook.clean_values(tpl, {**(card_status or {}), **_skills_field(tpl, card_status, abilities)}) \
                if tpl and (card_status or abilities) and not state.get("sheet_from_chat") else {}
            if mine:  # no opening: the start screen's sheet still counts
                state["card_status"] = {**(state.get("card_status") or {}), **mine}
                state["sheet_from_chat"] = True
                self.save_state(conv_id, state)
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
            "player_lore": _json_list(row.get("player_lore")),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list(self) -> list[dict]:
        rows = self.db.query(
            # Only the card's name and mode are needed: read them inside SQLite instead of parsing every card copy.
            "SELECT c.id, c.title, c.scenario_id, json_extract(c.scenario_snapshot, '$.name') AS sname, "
            "json_extract(c.scenario_snapshot, '$.mode') AS smode, c.created_at, c.updated_at, "
            "(SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS message_count "
            "FROM conversations c ORDER BY c.updated_at DESC"
        )
        out = []
        for r in rows:
            snap = {"name": r["sname"] or "", "mode": r["smode"] or ""}
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

    def restart(self, conv_id: int, card: dict | None = None, keep: bool = True) -> dict:
        """The same game from the beginning: the card's opening (its current version, or this game's copy if the card is gone),
        the same start and character (HP full, the card's starting gold and items), the player's lore. The old run is kept
        (renamed "… (old run)") or deleted."""
        conv = self.get(conv_id)
        state = self.get_state(conv_id)
        snap = {k: v for k, v in conv["scenario"].items() if k != "route"}
        scenario = card or {"id": conv.get("scenario_id"), "name": snap.get("name", ""), "data": normalize_scenario(snap)}
        player = {k: v for k, v in (state.get("player") or {}).items() if k in PLAYER_FIELDS}
        hp = player.get("hp")
        if isinstance(hp, dict) and hp.get("max"):
            player["hp"] = {**hp, "current": hp["max"]}
        new = self.create(scenario, title=scenario["name"], player=player, setup=str(state.get("setup") or ""),
                          player_lore=conv.get("player_lore") or [], start=str((conv["scenario"].get("route") or {}).get("id") or ""),
                          party_mode=str(state.get("party_mode") or ""), language=str(conv["scenario"].get("language") or ""))
        if keep:
            title = re.sub(r"\s*\(old run\)$", "", conv["title"] or scenario["name"])[:100]
            self.rename(conv_id, f"{title} (old run)")
        else:
            self.delete(conv_id)
        return new

    def refresh_from_card(self, conv_id: int, card: dict) -> dict:
        """⟳ Update a running game from its card's current version: the card's text, lore, rules, calendar and sheet
        become this game's; new characters join (not yet met); characters the game hasn't changed get the card's new
        text and pictures. The story, relationships, notes, met/unmet, the route, gold and the sheet's values stay.
        A character the card moved to another route is put aside if the player hasn't met them yet."""
        conv = self.get(conv_id)
        old = conv["scenario"]
        data = card["data"]
        snap = {**data, "name": card["name"]}
        for key in ("sheet_template", "adventure", "language"):  # this game's own choices and copies
            if key in old:
                snap[key] = old[key]
        route_id = str((old.get("route") or {}).get("id") or "")
        try:
            route = routes.resolve(data, route_id)
        except ValueError:
            route = None
        if route:
            snap["route"] = {k: route[k] for k in ("id", "name", "setting", "focus", "scenes")}
        elif old.get("route"):
            snap["route"] = old["route"]  # the card no longer has this start: keep the game's copy
        old_npcs = {n["name"].lower(): n for n in old.get("npcs") or [] if n.get("name")}
        if any(n.get("companion") for n in old_npcs.values()):  # companions set up on the start screen keep their edits
            snap["npcs"] = [old_npcs.get(n["name"].lower(), n) if n.get("companion") else n for n in data.get("npcs") or []]
        state = self.get_state(conv_id)
        solo = state.get("party_mode") == "solo"
        here = route_id or "default"
        mine = {n["name"].lower(): n for n in self.list_npcs(conv_id)}
        added, updated, aside = [], [], []
        with self.db.transaction():
            for npc in data.get("npcs") or []:
                name = str(npc.get("name") or "").strip()
                if not name or (solo and npc.get("companion")):
                    continue
                elsewhere = npc.get("route") and npc["route"] != here
                have = mine.get(name.lower())
                if have is None:
                    if elsewhere:
                        continue
                    self.add_npc(conv_id, name, description=npc.get("description", ""), personality=npc.get("personality", ""),
                                 speech_style=npc.get("speech_style", ""), appearance=npc.get("appearance"),
                                 portraits=npc.get("portraits"), in_prompt=npc.get("in_prompt", True), met=False,
                                 relationship=npc.get("relationship", 0))
                    added.append(name)
                    continue
                if elsewhere:
                    if not have["met"] and have["active"]:
                        self.update_npc(have["id"], active=False)
                        aside.append(name)
                    continue
                was = old_npcs.get(name.lower()) or {}
                change = {}
                for key in ("description", "personality", "speech_style"):
                    new = str(npc.get(key) or "")
                    if new != have[key] and have[key] == str(was.get(key) or ""):  # the game never changed it
                        change[key] = new
                if normalize_appearance(npc.get("appearance")) != have["appearance"] \
                        and have["appearance"] == normalize_appearance(was.get("appearance")):
                    change["appearance"] = npc.get("appearance")
                pics = normalize_portraits(npc.get("portraits"))
                if pics != have["portraits"] and (pics["default"] or pics["moods"]) \
                        and have["portraits"] in (normalize_portraits(was.get("portraits")), normalize_portraits({})):
                    change["portraits"] = pics
                if change:
                    self.update_npc(have["id"], **change)
                    updated.append(name)
            if data.get("systems"):  # the card's sheet: new stats and parts join, the game's values stay
                from .systems import merge_state, normalize_state
                state["systems"] = normalize_state(data["systems"], state["systems"]) if state.get("systems") else merge_state(data["systems"], None)
            if data.get("resources") and not state.get("resources"):
                state["resources"] = start_pools(data["resources"])
            cal = data.get("calendar") or {}
            if cal.get("enabled") and cal.get("months") and not state.get("clock"):  # the card's calendar starts now
                state["clock"] = {"minutes": 0, "seed": random.randrange(1, 1_000_000)}
                state["time"] = time_label(cal, 0)
                if cal.get("climate", "temperate") != "none":
                    state["weather"] = weather_on(cal, 0, state["clock"]["seed"])
                state["date_label"] = format_now(cal, 0)
            self.save_state(conv_id, state)
            self.db.execute("UPDATE conversations SET scenario_snapshot = ?, updated_at = ? WHERE id = ?",
                            (json.dumps(snap, ensure_ascii=False), now(), conv_id))
        return {"added": added, "updated": updated, "aside": aside,
                "lore": len(((data.get("lorebook") or {}).get("entries")) or [])}

    def sync_card_portraits(self, scenario_id: int, old_npcs: list[dict], new_npcs: list[dict]) -> int:
        """Pictures added or changed in the card reach the games already started with it. A character whose pictures
        were changed inside a game (they differ from the card's old ones) keeps the game's pictures."""
        old = {n["name"].lower(): normalize_portraits(n.get("portraits")) for n in old_npcs if n.get("name")}
        new = {n["name"].lower(): normalize_portraits(n.get("portraits")) for n in new_npcs if n.get("name")}
        changed = {k: v for k, v in new.items() if v != old.get(k) and (v["default"] or v["moods"])}
        if not changed:
            return 0
        done = 0
        for row in self.db.query("SELECT id FROM conversations WHERE scenario_id = ?", (scenario_id,)):
            for npc in self.list_npcs(row["id"]):
                key = npc["name"].lower()
                mine = normalize_portraits(npc.get("portraits"))
                if key in changed and mine in (old.get(key), normalize_portraits({})) and mine != changed[key]:
                    self.update_npc(npc["id"], portraits=changed[key])
                    done += 1
        return done

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

    def set_sheet_template(self, conv_id: int, text: str) -> dict:
        """This game's sheet (Status tab), picked from the library; the card itself is not changed."""
        conv = self.get(conv_id)
        scenario = {**conv["scenario"], "sheet_template": str(text or "")[:2000]}
        self.db.execute("UPDATE conversations SET scenario_snapshot = ? WHERE id = ?", (json.dumps(scenario, ensure_ascii=False), conv_id))
        return self.get(conv_id)

    def set_adventure(self, conv_id: int, adv: dict) -> dict:
        """This game's copy of the adventure (a painted scene map is added to it)."""
        conv = self.get(conv_id)
        scenario = {**conv["scenario"], "adventure": adv}
        self.db.execute("UPDATE conversations SET scenario_snapshot = ? WHERE id = ?", (json.dumps(scenario, ensure_ascii=False), conv_id))
        return self.get(conv_id)

    def set_player_lore(self, conv_id: int, entries) -> dict:
        self.get(conv_id)
        self.db.execute("UPDATE conversations SET player_lore = ? WHERE id = ?",
                        (json.dumps(clean_entries(entries), ensure_ascii=False), conv_id))
        return self.get(conv_id)

    def set_summary(self, conv_id: int, summary: str, upto: int) -> None:
        self.db.execute("UPDATE conversations SET summary = ?, summary_upto = ? WHERE id = ?", (summary, upto, conv_id))

    # ----------------------------------------------------------------- messages
    _COLS = "id, conversation_id, role, content, meta, created_at"

    @staticmethod
    def _msg(row: dict, with_snapshot: bool = False) -> dict:
        meta = json.loads(row["meta"] or "{}")
        out = {
            "id": row["id"],
            "conversation_id": row["conversation_id"],
            "role": row["role"],
            "content": row["content"],
            "meta": meta,
            "created_at": row["created_at"],
        }
        if with_snapshot:
            out["snapshot"] = unpack_snapshot(row.get("snapshot"))
        return out

    def add_message(self, conv_id: int, role: str, content: str, meta: dict | None = None) -> dict:
        meta = dict(meta or {})
        snap = meta.pop("snapshot", None)  # undo data lives compressed in its own column
        cur = self.db.execute(
            "INSERT INTO messages(conversation_id, role, content, meta, snapshot, created_at) VALUES(?,?,?,?,?,?)",
            (conv_id, role, content, json.dumps(meta, ensure_ascii=False), pack_snapshot(snap), now()),
        )
        self.touch(conv_id)
        return self.get_message(cur.lastrowid)

    def get_message(self, message_id: int, with_snapshot: bool = False) -> dict:
        cols = self._COLS + (", snapshot" if with_snapshot else "")
        row = self.db.query_one(f"SELECT {cols} FROM messages WHERE id = ?", (message_id,))
        if not row:
            raise NotFound(f"Message {message_id} not found")
        return self._msg(row, with_snapshot)

    def list_messages(self, conv_id: int, after_id: int = 0, with_snapshot: bool = False) -> list[dict]:
        cols = self._COLS + (", snapshot" if with_snapshot else "")
        rows = self.db.query(f"SELECT {cols} FROM messages WHERE conversation_id = ? AND id > ? ORDER BY id", (conv_id, after_id))
        return [self._msg(r, with_snapshot) for r in rows]

    def count_replies(self, conv_id: int) -> int:
        """Finished replies of the GM (no opening scene, no reply cut off by an error or Stop)."""
        return self.db.query_one(
            "SELECT COUNT(*) AS n FROM messages WHERE conversation_id = ? AND role = 'assistant' "
            "AND json_extract(meta, '$.opening') IS NULL AND json_extract(meta, '$.interrupted') IS NULL", (conv_id,))["n"]

    def recent_messages(self, conv_id: int, limit: int) -> list[dict]:
        rows = self.db.query(f"SELECT {self._COLS} FROM messages WHERE conversation_id = ? ORDER BY id DESC LIMIT ?", (conv_id, limit))
        return [self._msg(r) for r in reversed(rows)]

    def has_meta(self, conv_id: int, key: str) -> bool:
        return self.db.query_one(f"SELECT 1 AS x FROM messages WHERE conversation_id = ? AND json_extract(meta, '$.{key}') IS NOT NULL LIMIT 1",
                                 (conv_id,)) is not None

    def last_message(self, conv_id: int) -> dict | None:
        row = self.db.query_one("SELECT * FROM messages WHERE conversation_id = ? ORDER BY id DESC LIMIT 1", (conv_id,))
        return self._msg(row, with_snapshot=True) if row else None

    def update_message(self, message_id: int, content: str) -> dict:
        self.get_message(message_id)
        self.db.execute("UPDATE messages SET content = ? WHERE id = ?", (content, message_id))
        return self.get_message(message_id)

    def update_message_meta(self, message_id: int, patch: dict, drop: tuple | list = ()) -> None:
        row = self.db.query_one("SELECT meta FROM messages WHERE id = ?", (message_id,))
        if not row:
            return
        meta = json.loads(row["meta"] or "{}")
        meta.update(patch)
        for key in drop:
            meta.pop(key, None)
        self.db.execute("UPDATE messages SET meta = ? WHERE id = ?", (json.dumps(meta, ensure_ascii=False), message_id))

    def set_message_snapshot(self, message_id: int, snap: dict | None) -> None:
        self.db.execute("UPDATE messages SET snapshot = ? WHERE id = ?", (pack_snapshot(snap), message_id))

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
        words = set(re.findall(r"[^\W_]+", name))
        for n in npcs:  # partial match on whole words ("Captain Varro" vs "Varro"), never "Al" inside "Albert"
            theirs = set(re.findall(r"[^\W_]+", n["name"].lower()))
            if words and theirs and (words <= theirs or theirs <= words):
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
    # ---------------------------------------------------------------- save points
    def fork(self, conv_id: int, message_id: int, title: str = "") -> int:
        """Copy a game up to `message_id` into a new game (a save point you can play from).

        The copy gets the sheet, characters and memories as they were right after that message, and every
        earlier message keeps its undo data, so rewind and regenerate keep working inside the copy.
        """
        conv = self.get(conv_id)
        rows = self.db.query("SELECT * FROM messages WHERE conversation_id = ? ORDER BY id", (conv_id,))
        if not any(r["id"] == message_id for r in rows):
            raise NotFound(f"Message {message_id} is not part of this game")
        keep = [r for r in rows if r["id"] <= message_id]
        later = [r for r in rows if r["id"] > message_id]
        metas = {r["id"]: json.loads(r["meta"] or "{}") for r in rows}
        snaps = {r["id"]: unpack_snapshot(r.get("snapshot")) for r in rows}
        # The state right after this message is the undo data of the first later message that has any
        # (a reply, or a fight action / time skip on a player message).
        point = next((snaps[r["id"]] for r in later if snaps[r["id"]]), None)
        state = point["state"] if point else self.get_state(conv_id)
        npcs = point["npcs"] if point else self.list_npcs(conv_id)

        # Characters get new ids in the copy; the undo data inside old messages is rewritten to match.
        old_ids: list[int] = [n["id"] for n in npcs]
        for r in keep:
            for n in (snaps[r["id"]] or {}).get("npcs", []):
                if n["id"] not in old_ids:
                    old_ids.append(n["id"])
        base = (self.db.query_one("SELECT COALESCE(MAX(id), 0) AS m FROM npcs") or {"m": 0})["m"]
        npc_map = {old: base + i + 1 for i, old in enumerate(old_ids)}

        ts = now()
        with self.db.transaction():
            cur = self.db.execute(
                "INSERT INTO conversations(title, scenario_id, scenario_snapshot, pinned_memory, player_lore, created_at, updated_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (title or f"⑂ {conv['title']}", conv["scenario_id"], json.dumps(conv["scenario"], ensure_ascii=False),
                 conv.get("pinned_memory", ""), json.dumps(conv.get("player_lore", []), ensure_ascii=False), ts, ts),
            )
            new_id = cur.lastrowid
            self.db.execute("INSERT INTO game_state(conversation_id, data) VALUES(?,?)", (new_id, json.dumps(state, ensure_ascii=False)))
            for n in npcs:
                self._insert_npc_copy(new_id, n, npc_map[n["id"]])
            msg_map: dict[int, int] = {}
            for r in keep:
                meta = metas[r["id"]]
                snap = snaps[r["id"]]
                if snap:
                    snap = {**snap, "npcs": [{**n, "id": npc_map[n["id"]]} for n in snap.get("npcs", [])]}
                c = self.db.execute(
                    "INSERT INTO messages(conversation_id, role, content, meta, snapshot, created_at) VALUES(?,?,?,?,?,?)",
                    (new_id, r["role"], r["content"], json.dumps(meta, ensure_ascii=False), pack_snapshot(snap), r["created_at"]),
                )
                msg_map[r["id"]] = c.lastrowid
            if conv["summary"] and conv["summary_upto"] in msg_map:
                self.db.execute("UPDATE conversations SET summary = ?, summary_upto = ? WHERE id = ?",
                                (conv["summary"], msg_map[conv["summary_upto"]], new_id))
            for m in self.db.query("SELECT * FROM memories WHERE conversation_id = ? AND (message_id IS NULL OR message_id <= ?)",
                                   (conv_id, message_id)):
                self.db.execute(
                    "INSERT INTO memories(conversation_id, message_id, text, kind, importance, participants, embedding, embed_model, created_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?)",
                    (new_id, msg_map.get(m["message_id"]) if m["message_id"] else None, m["text"], m["kind"], m["importance"],
                     m["participants"], m["embedding"], m["embed_model"], m["created_at"]),
                )
        return new_id

    def _insert_npc_copy(self, conv_id: int, n: dict, npc_id: int) -> None:
        self.db.execute(
            "INSERT INTO npcs(id, conversation_id, name, description, personality, speech_style, appearance, portraits, in_prompt, met, "
            "relationship, notes, active, is_main, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (npc_id, conv_id, n["name"], n["description"], n["personality"], n["speech_style"],
             json.dumps(n.get("appearance") or {}, ensure_ascii=False), json.dumps(n.get("portraits") or {}, ensure_ascii=False),
             int(n.get("in_prompt", True)), int(n.get("met", True)), n["relationship"], n["notes"],
             int(n["active"]), int(n["is_main"]), n["created_at"]),
        )

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
