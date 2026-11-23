"""Game state (character sheet, inventory, quests, places) and safe application of updates.

The model only *proposes* changes (as JSON). Everything is validated and clamped here,
so a confused small model can never corrupt the save.
"""
from __future__ import annotations

import copy
import uuid

from .appearance import normalize_appearance
from .portraits import normalize_portraits
import json

from .util import as_int, clamp, deep_merge, truncate
from .reputation import EVENTS


def normalize_pools(raw):  # imported late: resources imports state
    from .resources import normalize_pools as f
    return f(raw)


def normalize_abilities(raw):
    from .resources import normalize_abilities as f
    return f(raw)

DEFAULT_STATE: dict = {
    "player": {
        "name": "Player",
        "race": "",
        "class": "",
        "level": 1,
        "background": "",
        "description": "",
        "traits": "",
        "stats": {"STR": 10, "DEX": 10, "CON": 10, "INT": 10, "WIS": 10, "CHA": 10},
        "hp": {"current": 10, "max": 10},
        "ac": 10,
        "skills": [],
        "portraits": {"default": "", "moods": []},   # your own picture(s), shown beside your messages
    },
    "gold": 0,
    "inventory": [],      # [{"name": str, "qty": int, "notes": str}]
    "quests": [],         # [{"id": str, "title": str, "status": "active|completed|failed", "notes": str}]
    "location": "",
    "time": "",
    "weather": "",
    "scene_mood": "",     # for the Jukebox: calm, tavern, tension, combat... (see app/jukebox.py)
    "locations": [],      # [{"name": str, "description": str, "connections": [str], "visited": bool}]
    "notes": "",
    "setup": "",          # "app": the player made their character on the start screen; "card": the card asks in the story
    "clock": {"minutes": 0},  # world calendar: minutes since the start of the card's starting day (app/worldtime.py)
    "date_label": "",     # "Sunday, 3 Frostmoon, 812 AE · 19:40 (evening)" when the card has a calendar
    "events": [],         # appointments: [{"id", "day", "hour", "text"}]
    "untracked": 0,       # replies the tracker skipped (quiet turns) and will read next time
    "resources": {},      # Mana, Aura...: {"Mana": {"current", "max", "regen", "color"}} (app/resources.py)
    "abilities": [],      # the player's abilities that spend them
    "card_status": {},    # the card's own INFO-block fields (Tier, EXP...) kept by the app (app/statusbook.py)
}

TOP_LEVEL_FROM_PLAYER = ("gold", "inventory", "quests", "location", "time", "weather", "scene_mood", "locations")
QUEST_STATUSES = ("active", "completed", "failed")
MAX_ITEMS = 8


def _norm_item(item) -> dict | None:
    if isinstance(item, str):
        item = {"name": item}
    if not isinstance(item, dict):
        return None
    name = str(item.get("name", "")).strip()
    if not name:
        return None
    return {"name": truncate(name, 80), "qty": max(1, as_int(item.get("qty", 1), 1)), "notes": truncate(str(item.get("notes", "")), 200)}


def new_state(template: dict | None = None, player_name: str | None = None) -> dict:
    state = copy.deepcopy(DEFAULT_STATE)
    tpl = dict(template or {})
    extras = {k: tpl.pop(k) for k in TOP_LEVEL_FROM_PLAYER if k in tpl}
    state["player"] = deep_merge(state["player"], tpl)
    for key, value in extras.items():
        state[key] = value
    if player_name:
        state["player"]["name"] = player_name
    hp = state["player"].setdefault("hp", {"current": 10, "max": 10})
    hp["max"] = max(1, as_int(hp.get("max", 10), 10))
    hp["current"] = int(clamp(as_int(hp.get("current", hp["max"]), hp["max"]), 0, hp["max"]))
    state["gold"] = max(0, as_int(state.get("gold", 0)))
    state["inventory"] = [i for i in (_norm_item(x) for x in state.get("inventory", [])) if i]
    state["player"]["portraits"] = normalize_portraits(state["player"].get("portraits"))
    return state


def normalize_state(state: dict) -> dict:
    """Make a user-edited state safe again (fills missing keys, fixes types)."""
    merged = deep_merge(copy.deepcopy(DEFAULT_STATE), state if isinstance(state, dict) else {})
    return new_state(
        {**merged["player"], **{k: merged[k] for k in TOP_LEVEL_FROM_PLAYER}},
        None,
    ) | {"notes": str(merged.get("notes", "")), "setup": merged.get("setup") if merged.get("setup") in ("app", "card") else ""} | (
        {"combat": merged["combat"]} if isinstance(merged.get("combat"), dict) else {}) | _calendar_part(merged)  # fights survive sheet edits


def _calendar_part(merged: dict) -> dict:
    clock = merged.get("clock") if isinstance(merged.get("clock"), dict) else {}
    events = []
    for e in merged.get("events") if isinstance(merged.get("events"), list) else []:
        if isinstance(e, dict) and str(e.get("text", "")).strip():
            hour = e.get("hour")
            events.append({"id": str(e.get("id") or uuid.uuid4().hex[:8]), "day": as_int(e.get("day", 0)),
                           "hour": as_int(hour) if hour not in (None, "") else None, "text": truncate(str(e["text"]).strip(), 160),
                           "date": truncate(str(e.get("date", "")), 60)})
    return {"clock": {"minutes": max(0, as_int(clock.get("minutes", 0))), "seed": as_int(clock.get("seed", 0))}, "events": events[:40],
            "untracked": max(0, as_int(merged.get("untracked", 0))),
            "resources": normalize_pools(merged.get("resources")),
            "abilities": normalize_abilities(merged.get("abilities")),
            "card_status": {truncate(str(k), 40): truncate(str(v), 160) for k, v in list(
                (merged.get("card_status") if isinstance(merged.get("card_status"), dict) else {}).items())[:40]},
            "date_label": truncate(str(merged.get("date_label") or ""), 120),
            "wishes": truncate(str(merged.get("wishes") or ""), 600),          # the player's hints for the Aedo
            "finished": bool(merged.get("finished")),                           # the card's ending was reached
            "sheet_from_chat": bool(merged.get("sheet_from_chat")),
            "corrections": [truncate(" ".join(str(c).split()), 200) for c in (merged.get("corrections") or [])
                            if isinstance(c, str) and c.strip()][-20:],  # story facts the player fixed (/fix)
            "systems": _systems_part(merged.get("systems"))} | _story_part(merged)


def _systems_part(raw) -> dict:
    """The card's own sheet in play (app/systems.py): values and the loadout; the card's rules check them on use."""
    raw = raw if isinstance(raw, dict) else {}
    values = {truncate(str(k), 30): (v if isinstance(v, (int, float)) and not isinstance(v, bool) else truncate(str(v), 80))
              for k, v in list((raw.get("values") if isinstance(raw.get("values"), dict) else {}).items())[:30]}
    loadout = {truncate(str(k), 30): truncate(str(v or ""), 80)
               for k, v in list((raw.get("loadout") if isinstance(raw.get("loadout"), dict) else {}).items())[:16]}
    out = {"values": values, "loadout": loadout} if values or loadout else {}
    for key in ("owned", "board", "ranking", "steps", "step_days"):  # v2.36: shop, mission board, ranking, ladder
        if out and isinstance(raw.get(key), (list, dict)):
            out[key] = json.loads(json.dumps(raw[key]))[:200] if isinstance(raw[key], list) else json.loads(json.dumps(raw[key]))
    return out


def _story_part(merged: dict) -> dict:
    """Where the game stands in a route's fixed scenes and in an adventure's scenes (kept when the sheet is edited)."""
    out: dict = {}
    script = merged.get("script")
    if isinstance(script, dict):
        out["script"] = {"next": max(0, as_int(script.get("next", 0)))}
    if isinstance(merged.get("character5e"), dict):  # app/dnd5e: the 5e character and its worked-out numbers
        out["character5e"] = merged["character5e"]
        if isinstance(merged.get("character5e_sheet"), dict):
            out["character5e_sheet"] = merged["character5e_sheet"]
    for key in ("party5e", "party5e_sheet"):  # app/dnd5e/party5e.py: companions' 5e characters and their numbers
        if isinstance(merged.get(key), dict):
            out[key] = merged[key]
    if merged.get("party_mode") in ("solo", "companions"):  # app/party.py
        from .party import normalize_party
        out["party_mode"] = merged["party_mode"]
        out["party"] = normalize_party(merged.get("party"))
    log = merged.get("rep_log")
    if isinstance(log, list):
        out["rep_log"] = [e for e in log if isinstance(e, dict)][-60:]
    adv = merged.get("adventure")
    if isinstance(adv, dict):
        ids = lambda v: [str(x)[:60] for x in v if str(x).strip()][:300] if isinstance(v, list) else []  # noqa: E731
        out["adventure"] = {"scene": str(adv.get("scene") or "")[:60], "visited": ids(adv.get("visited")),
                            "xp_given": ids(adv.get("xp_given")), "fresh": str(adv.get("fresh") or "")[:60],
                            "fought": ids(adv.get("fought"))}
    return out


# ---------------------------------------------------------------- model updates
def _list(value) -> list:
    return value[:MAX_ITEMS] if isinstance(value, list) else []


def normalize_updates(raw) -> dict:
    """Coerce whatever the model returned into a strictly typed update dict."""
    raw = raw if isinstance(raw, dict) else {}
    updates: dict = {
        "hp_change": int(clamp(as_int(raw.get("hp_change", 0)), -500, 500)),
        "gold_change": int(clamp(as_int(raw.get("gold_change", 0)), -100000, 100000)),
        "inventory_add": [],
        "inventory_remove": [],
        "quests": [],
        "location": truncate(str(raw.get("location") or "").strip(), 80),
        "time": truncate(str(raw.get("time") or "").strip(), 60),
        "weather": truncate(str(raw.get("weather") or "").strip(), 60),
        "scene_mood": str(raw.get("scene_mood") or "").strip().lower(),
        "new_locations": [],
        "relationship_changes": [],
        "character_notes": [],
        "new_npcs": [],
        "memories": [],
        "minutes_passed": max(0, as_int(raw.get("minutes_passed", 0))),
        "resource_changes": [{"resource": str(c.get("resource", "")), "delta": as_int(c.get("delta", 0)),
                              "reason": truncate(str(c.get("reason", "")), 80)}
                             for c in _list(raw.get("resource_changes")) if isinstance(c, dict)],
        "status_changes": [{"field": str(c.get("field", "")), "value": str(c.get("value", ""))}
                           for c in _list(raw.get("status_changes")) if isinstance(c, dict)],
        "system_changes": [{k: c.get(k) for k in ("stat", "delta", "value", "buy", "gain", "step") if c.get(k) not in (None, "")}
                           for c in _list(raw.get("system_changes")) if isinstance(c, dict)],
        "appointments": [],
    }
    for ap in _list(raw.get("appointments")):
        if isinstance(ap, dict) and str(ap.get("text", "")).strip():
            updates["appointments"].append({"text": truncate(str(ap["text"]).strip(), 160), "when": truncate(str(ap.get("when", "")), 60),
                                            "days_from_now": ap.get("days_from_now")})
    for key in ("inventory_add", "inventory_remove"):
        for item in _list(raw.get(key)):
            norm = _norm_item(item)
            if norm:
                updates[key].append(norm)
    for q in _list(raw.get("quests")):
        if isinstance(q, dict) and str(q.get("title", "")).strip():
            status = str(q.get("status", "active")).lower()
            updates["quests"].append(
                {
                    "title": truncate(str(q["title"]).strip(), 100),
                    "status": status if status in QUEST_STATUSES else "active",
                    "notes": truncate(str(q.get("notes", "")), 240),
                }
            )
    for loc in _list(raw.get("new_locations")):
        if isinstance(loc, dict) and str(loc.get("name", "")).strip():
            conns = [str(c).strip() for c in _list(loc.get("connects_to")) if str(c).strip()]
            updates["new_locations"].append(
                {"name": truncate(str(loc["name"]).strip(), 80), "description": truncate(str(loc.get("description", "")), 240), "connects_to": conns}
            )
    for rc in _list(raw.get("relationship_changes")):
        if isinstance(rc, dict) and str(rc.get("npc", "")).strip():
            event = str(rc.get("event") or "").strip().lower().replace(" ", "_")
            delta = as_int(rc.get("delta", 0))
            if event in EVENTS or delta:  # an event from the table (the app gives its value), or an old-style number
                updates["relationship_changes"].append(
                    {"npc": str(rc["npc"]).strip(), "event": event if event in EVENTS else "", "delta": delta,
                     "reason": truncate(str(rc.get("reason", "")), 120)}
                )
    for cn in _list(raw.get("character_notes"))[:3]:
        if isinstance(cn, dict) and str(cn.get("npc", "")).strip() and len(str(cn.get("note", "")).strip()) >= 6:
            updates["character_notes"].append({"npc": str(cn["npc"]).strip(), "note": truncate(" ".join(str(cn["note"]).split()), 160)})
    for npc in _list(raw.get("new_npcs")):
        if isinstance(npc, dict) and str(npc.get("name", "")).strip():
            updates["new_npcs"].append(
                {
                    "name": truncate(str(npc["name"]).strip(), 60),
                    "description": truncate(str(npc.get("description", "")), 240),
                    "personality": truncate(str(npc.get("personality", "")), 240),
                    "appearance": normalize_appearance(npc.get("appearance")),
                }
            )
    for mem in _list(raw.get("memories")):
        if isinstance(mem, str):
            mem = {"text": mem}
        if isinstance(mem, dict) and str(mem.get("text", "")).strip():
            who = mem.get("characters", [])
            who = [truncate(str(c).strip(), 60) for c in who[:4] if str(c).strip()] if isinstance(who, list) else []
            updates["memories"].append(
                {"text": truncate(str(mem["text"]).strip(), 400), "importance": int(clamp(as_int(mem.get("importance", 3), 3), 1, 5)),
                 "characters": who}
            )
    return updates


def apply_state_updates(state: dict, updates: dict) -> tuple[dict, list[str]]:
    """Apply validated updates to a copy of `state`. Returns (new_state, human-readable changes)."""
    state = copy.deepcopy(state)
    changes: list[str] = []
    hp = state["player"]["hp"]

    if updates.get("hp_change"):
        before = hp["current"]
        hp["current"] = int(clamp(before + updates["hp_change"], 0, hp["max"]))
        if hp["current"] != before:
            changes.append(f"HP {hp['current'] - before:+d} ({hp['current']}/{hp['max']})")

    if updates.get("gold_change"):
        before = state["gold"]
        state["gold"] = max(0, before + updates["gold_change"])
        if state["gold"] != before:
            changes.append(f"Gold {state['gold'] - before:+d} ({state['gold']})")

    inv = state["inventory"]
    for item in updates.get("inventory_add", []):
        existing = next((i for i in inv if i["name"].lower() == item["name"].lower()), None)
        if existing:
            existing["qty"] += item["qty"]
        else:
            inv.append(dict(item))
        changes.append(f"Item +{item['qty']} {item['name']}")
    for item in updates.get("inventory_remove", []):
        existing = next((i for i in inv if i["name"].lower() == item["name"].lower()), None)
        if existing:
            existing["qty"] -= item["qty"]
            if existing["qty"] <= 0:
                inv.remove(existing)
            changes.append(f"Item -{item['qty']} {item['name']}")

    for q in updates.get("quests", []):
        existing = next((x for x in state["quests"] if x["title"].lower() == q["title"].lower()), None)
        if existing:
            if existing["status"] != q["status"]:
                if existing["status"] == "active" and q["status"] in ("completed", "failed"):
                    # The AI only suggests the end of a quest; the player confirms it in the Bag tab.
                    if existing.get("suggested") != q["status"]:
                        existing["suggested"] = q["status"]
                        changes.append(f"Quest '{existing['title']}' looks {q['status']}: confirm it in the Bag tab")
                else:
                    existing["status"] = q["status"]
                    existing.pop("suggested", None)
                    changes.append(f"Quest '{existing['title']}': {q['status']}")
            if q["notes"]:
                existing["notes"] = q["notes"]
        else:
            new = {"id": uuid.uuid4().hex[:8], **q}
            if q["status"] != "active":  # a quest the AI reports as already over: the player confirms it
                new.update(status="active", suggested=q["status"])
            state["quests"].append(new)
            changes.append(f"New quest: {q['title']}")

    if updates.get("location"):
        if updates["location"] != state["location"]:
            changes.append(f"Location: {updates['location']}")
        state["location"] = updates["location"]
        _add_location(state, updates["location"], "", [], [], visited=True)
    if updates.get("time"):
        state["time"] = updates["time"]
    if updates.get("scene_mood"):
        from .jukebox import MOODS
        if updates["scene_mood"] in MOODS:
            state["scene_mood"] = updates["scene_mood"]
    if updates.get("weather"):
        if updates["weather"] != state.get("weather"):
            changes.append(f"Weather: {updates['weather']}")
        state["weather"] = updates["weather"]

    # After the current location exists, so "connects_to" can point at it.
    for loc in updates.get("new_locations", []):
        _add_location(state, loc["name"], loc["description"], loc["connects_to"], changes)

    return state, changes


def _add_location(state: dict, name: str, description: str, connects_to: list[str], changes: list[str], visited: bool = False) -> None:
    locs = state["locations"]
    loc = next((l for l in locs if l["name"].lower() == name.lower()), None)
    if loc is None:
        loc = {"name": name, "description": description, "connections": [], "visited": False}
        locs.append(loc)
        changes.append(f"New place: {name}")
    elif description and not loc["description"]:
        loc["description"] = description
    if visited:
        loc["visited"] = True
    for other_name in connects_to:
        other = next((l for l in locs if l["name"].lower() == other_name.lower()), None)
        if other is None or other is loc:
            continue
        if other["name"] not in loc["connections"]:
            loc["connections"].append(other["name"])
        if loc["name"] not in other["connections"]:
            other["connections"].append(loc["name"])
