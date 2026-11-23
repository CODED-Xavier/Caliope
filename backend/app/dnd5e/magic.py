"""Spells and class resources that change the numbers.

- Spell slots: spent from `char["slots_used"]` ({"1": 2}) and `char["pact_used"]`; a long rest refills all, a short
  rest refills pact slots.
- A spell's roll, read from its Library entry: a spell attack (d20 + spell attack vs AC) or a saving throw against
  your spell save DC (half damage on a success when the spell says so), its damage dice (cantrips grow with your
  level, levelled spells with the slot), or its healing (+ your spellcasting modifier when it says so).
- Divine Smite: 2d8 radiant + 1d8 per slot level above 1st (most 5d8), +1d8 against undead and fiends.
- Rage: +2 / +3 / +4 damage on Strength melee attacks and half damage from weapons. Sneak Attack: ⌈level/2⌉d6 once a
  turn with advantage or an ally next to the target.
"""
from __future__ import annotations

import re

from .text import strip_tags

ABIL_NAMES = {"strength": "str", "dexterity": "dex", "constitution": "con", "intelligence": "int", "wisdom": "wis", "charisma": "cha"}
FIENDISH = re.compile(r"undead|fiend|zombie|skeleton|ghoul|ghast|wight|wraith|vampire|lich|mummy|specter|ghost|demon|devil|imp\b|"
                      r"quasit|hell|abyss|succubus|incubus|lemure|dretch|banshee", re.I)


def slots_left(sheet: dict, char: dict) -> dict[str, int]:
    used = char.get("slots_used") or {}
    return {str(lv): max(0, int(n) - int(used.get(str(lv), 0))) for lv, n in (sheet.get("slots") or {}).items()}


def pact_left(sheet: dict, char: dict) -> int:
    p = sheet.get("pact")
    return max(0, int(p["count"]) - int(char.get("pact_used") or 0)) if p else 0


def spend_slot(char: dict, sheet: dict, at_least: int, level: int | None = None) -> tuple[dict, int]:
    """Spend a slot of `level` (or the lowest free one of at least `at_least`). Returns (char, the slot's level)."""
    left = slots_left(sheet, char)
    pact = sheet.get("pact")
    if level:
        if pact and int(pact["level"]) == int(level) and pact_left(sheet, char) and not left.get(str(level)):
            return {**char, "pact_used": int(char.get("pact_used") or 0) + 1}, int(level)
        if not left.get(str(level)):
            raise ValueError(f"No level {level} spell slots left.")
        used = dict(char.get("slots_used") or {})
        used[str(level)] = int(used.get(str(level), 0)) + 1
        return {**char, "slots_used": used}, int(level)
    for lv in sorted(int(k) for k, v in left.items() if v > 0):
        if lv >= at_least:
            return spend_slot(char, sheet, at_least, lv)
    if pact and int(pact["level"]) >= at_least and pact_left(sheet, char):
        return {**char, "pact_used": int(char.get("pact_used") or 0) + 1}, int(pact["level"])
    raise ValueError(f"No spell slots of level {at_least} or higher left." if at_least > 1 else "No spell slots left.")


def restore_slots(char: dict, when: str) -> dict:
    return {**char, "pact_used": 0, **({"slots_used": {}} if when == "long_rest" else {})}


def _text(e: dict) -> str:
    return " ".join(strip_tags(x) if isinstance(x, str) else " ".join(strip_tags(y) for y in x.get("entries", []) if isinstance(y, str))
                    for x in (e.get("entries") or []) if isinstance(x, (str, dict)))


def _raw(e: dict, key: str = "entries") -> str:
    import json
    return json.dumps(e.get(key) or [])


def spell_roll(e: dict, char_level: int, slot_level: int, mod: int) -> dict:
    """How a spell rolls: {kind: attack|save|heal|none, dice, dtype, save, half}."""
    lvl = int(e.get("level", 0))
    raw = _raw(e)
    text = _text(e)
    out: dict = {"kind": "none", "dice": "", "dtype": (e.get("damageInflict") or [""])[0], "save": "", "half": False}
    dmg = re.search(r"\{@damage ([^}|]+)", raw)
    if lvl == 0 and (e.get("scalingLevelDice") or {}).get("scaling"):
        sc = e["scalingLevelDice"]
        sc = sc[0] if isinstance(sc, list) else sc
        steps = sorted((int(k), v) for k, v in sc["scaling"].items())
        out["dice"] = next((v for k, v in reversed(steps) if char_level >= k), steps[0][1])
    elif dmg:
        out["dice"] = dmg.group(1).strip()
    if out["dice"] and lvl and slot_level > lvl:  # cast with a higher slot: "{@scaledamage 8d6|3-9|1d6}"
        up = re.search(r"\{@scaledamage [^|]+\|[^|]+\|([^}|]+)", _raw(e, "entriesHigherLevel"))
        if up:
            m = re.match(r"(\d+)d(\d+)", up.group(1).strip())
            if m:
                out["dice"] += f"+{int(m.group(1)) * (slot_level - lvl)}d{m.group(2)}"
    heal = re.search(r"regains? (?:a number of )?hit points", text, re.I)
    if heal and not dmg:
        dice = re.search(r"\{@dice ([^}|]+)", raw)
        base = dice.group(1).strip() if dice else ""
        up = re.search(r"\{@scaledice [^|]+\|[^|]+\|([^}|]+)", _raw(e, "entriesHigherLevel"))
        if up and lvl and slot_level > lvl:
            m = re.match(r"(\d+)d(\d+)", up.group(1).strip())
            if m and base:
                base += f"+{int(m.group(1)) * (slot_level - lvl)}d{m.group(2)}"
        if base:
            if re.search(r"spellcasting ability modifier", text, re.I):
                base += f"+{mod}" if mod >= 0 else str(mod)
            out.update(kind="heal", dice=base)
        return out
    if e.get("spellAttack"):
        out["kind"] = "attack"
    elif e.get("savingThrow"):
        out.update(kind="save", save=ABIL_NAMES.get(str(e["savingThrow"][0]).lower(), "dex"),
                   half=bool(re.search(r"half as much damage", text, re.I)))
    if not out["dice"] and out["kind"] != "save":
        out["kind"] = "none"
    return out


def smite_dice(slot_level: int, target_name: str = "") -> str:
    n = min(5, 1 + max(1, slot_level))
    return f"{n + (1 if FIENDISH.search(target_name or '') else 0)}d8"


def rage_bonus(level: int) -> int:
    return 4 if level >= 16 else 3 if level >= 9 else 2


def sneak_dice(level: int) -> str:
    return f"{(level + 1) // 2}d6"
