"""Game state (character sheet, inventory, quests, places) and safe application of updates.

The model only *proposes* changes (as JSON). Everything is validated and clamped here,
so a confused small model can never corrupt the save.
"""
from __future__ import annotations

import copy
import uuid

from .appearance import normalize_appearance
from .portraits import normalize_portraits
from .util import as_int, clamp, deep_merge, truncate

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
    "locations": [],      # [{"name": str, "description": str, "connections": [str], "visited": bool}]
    "notes": "",
    "setup": "",          # "app": the player made their character on the start screen; "card": the card asks in the story
}

TOP_LEVEL_FROM_PLAYER = ("gold", "inventory", "quests", "location", "time", "weather", "locations")
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
        {"combat": merged["combat"]} if isinstance(merged.get("combat"), dict) else {})  # a fight in progress survives sheet edits


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
        "new_locations": [],
        "relationship_changes": [],
        "new_npcs": [],
        "memories": [],
    }
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
            delta = as_int(rc.get("delta", 0))
            if delta:
                updates["relationship_changes"].append(
                    {"npc": str(rc["npc"]).strip(), "delta": delta, "reason": truncate(str(rc.get("reason", "")), 120)}
                )
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
                changes.append(f"Quest '{existing['title']}': {q['status']}")
            existing["status"] = q["status"]
            if q["notes"]:
                existing["notes"] = q["notes"]
        else:
            state["quests"].append({"id": uuid.uuid4().hex[:8], **q})
            changes.append(f"New quest: {q['title']}")

    if updates.get("location"):
        if updates["location"] != state["location"]:
            changes.append(f"Location: {updates['location']}")
        state["location"] = updates["location"]
        _add_location(state, updates["location"], "", [], [], visited=True)
    if updates.get("time"):
        state["time"] = updates["time"]
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
