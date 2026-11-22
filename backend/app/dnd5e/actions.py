"""What a 5e character can do on a turn, sorted by what it costs (like Foundry's action list).

The standard actions are the combat rules every creature has. Features say their own cost in their text ("you can use
a bonus action to…", "you can use your reaction…", "when you hit… you can expend…"), and spells by their casting time.
"""
from __future__ import annotations

import re

from .character import derive
from .text import strip_tags

COSTS = ("action", "bonus", "reaction", "free")

# The rules' standard options, summed up in plain words (the full text is in the Library's rules).
STANDARD = [
    {"id": "rules:attack", "name": "Attack", "cost": "action", "kind": "attack", "text": "Make one weapon or unarmed attack (more with Extra Attack)."},
    {"id": "rules:dash", "name": "Dash", "cost": "action", "kind": "dash", "text": "Gain extra movement equal to your speed this turn."},
    {"id": "rules:disengage", "name": "Disengage", "cost": "action", "kind": "disengage", "text": "Your movement doesn't provoke opportunity attacks this turn."},
    {"id": "rules:dodge", "name": "Dodge", "cost": "action", "kind": "dodge", "text": "Attacks against you have disadvantage and you have advantage on DEX saves until your next turn."},
    {"id": "rules:help", "name": "Help", "cost": "action", "kind": "help", "text": "An ally gets advantage on their next check, or on their next attack against a foe within 5 ft of you."},
    {"id": "rules:hide", "name": "Hide", "cost": "action", "kind": "hide", "text": "Make a Dexterity (Stealth) check to hide."},
    {"id": "rules:ready", "name": "Ready", "cost": "action", "kind": "ready", "text": "Choose a trigger and an action; when it happens, you act with your reaction."},
    {"id": "rules:search", "name": "Search", "cost": "action", "kind": "search", "text": "Look for something: a Wisdom (Perception) or Intelligence (Investigation) check."},
    {"id": "rules:use_object", "name": "Use an Object", "cost": "action", "kind": "use_object", "text": "Use an object that needs your action (drink a potion, light a torch, pull a lever)."},
    {"id": "rules:grapple", "name": "Grapple", "cost": "action", "kind": "grapple", "text": "Replaces one attack: Strength (Athletics) against the target's Athletics or Acrobatics; on a win it is grappled (speed 0)."},
    {"id": "rules:shove", "name": "Shove", "cost": "action", "kind": "shove", "text": "Replaces one attack: Strength (Athletics) contest to knock the target prone or push it 5 ft."},
    {"id": "rules:opportunity", "name": "Opportunity Attack", "cost": "reaction", "kind": "opportunity", "text": "When a foe you can see leaves your reach, make one melee attack against it."},
    {"id": "rules:interact", "name": "Interact with an object", "cost": "free", "kind": "interact", "text": "Once per turn, for free: draw a weapon, open a door, pick something up."},
]

FREE_TRIGGERS = re.compile(r"\b(no action required|when you hit|when you score|when you roll|additional action|immediately after)\b", re.I)
REACTION = re.compile(r"\b(use your reaction|as a reaction|your reaction to|reaction,? you can|use a reaction)\b", re.I)
BONUS = re.compile(r"\bbonus action\b", re.I)
ACTION = re.compile(r"\b(as an action|use your action|use an action|take an action|an action to|action to \w+|the magic action)\b", re.I)


def cost_of(text: str) -> str | None:
    """What a feature costs, read from its text: action, bonus, reaction or free (triggered); None if it is always on."""
    t = strip_tags(str(text or ""))
    if REACTION.search(t):
        return "reaction"
    if BONUS.search(t):
        return "bonus"
    if FREE_TRIGGERS.search(t):
        return "free"
    if ACTION.search(t):
        return "action"
    return None


def _spell_cost(entry: dict) -> str | None:
    time = (entry.get("time") or [{}])[0]
    unit = str(time.get("unit", "")).lower()
    return {"action": "action", "bonus": "bonus", "reaction": "reaction"}.get(unit)


def options(char: dict, lib) -> dict:
    """{"action": [...], "bonus": [...], "reaction": [...], "free": [...]}: each option has id, name, cost, kind, text."""
    out = {c: [] for c in COSTS}
    for o in STANDARD:
        out[o["cost"]].append(dict(o))
    sheet = derive(char, lib)
    for f in sheet["features"]:
        cost = cost_of(f.get("text", ""))
        if not cost or (sheet["class"] == "Monk" and f["name"] == "Martial Arts"):  # the Martial Arts strike below covers it
            continue
        o = {"id": f"feature:{f['name']}", "name": f["name"], "cost": cost, "kind": "feature", "text": _short(f.get("text", ""))}
        if f.get("uses_max"):
            o["uses_left"] = f["uses_max"] - f.get("used", 0)
        if re.search(r"additional action", f.get("text", ""), re.I):
            o["grants"] = "action"
        out[cost].append(o)
    if sheet["class"] == "Monk":
        out["bonus"].insert(0, {"id": "rules:martial_arts", "name": "Martial Arts strike", "cost": "bonus", "kind": "bonus_attack",
                                "text": "After the Attack action with an unarmed strike or monk weapon: one unarmed strike."})
    for ref in char.get("spells") or []:
        e = lib.items.get(("spell", ref["name"].lower(), ref.get("source", "PHB").upper()))
        cost = _spell_cost(e or {})
        if not cost:
            continue
        lvl = int((e or {}).get("level", 0))
        cond = ((e or {}).get("time") or [{}])[0].get("condition", "")
        out[cost].append({"id": f"spell:{e['name']}", "name": e["name"], "cost": cost, "kind": "spell", "level": lvl,
                          "text": ("Cantrip. " if not lvl else f"Level {lvl} spell. ") + (strip_tags(cond).capitalize() + ". " if cond else "")
                          + _short((e or {}).get("entries"))})
    return out


def find(char: dict, lib, option_id: str) -> dict | None:
    for group in options(char, lib).values():
        for o in group:
            if o["id"] == option_id:
                return o
    return None


def _short(entries, limit: int = 220) -> str:
    from .text import render
    t = render(entries or "")
    return t if len(t) <= limit else t[: limit - 1].rsplit(" ", 1)[0] + "…"
