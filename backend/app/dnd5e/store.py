"""The 5e character inside a game: changes from the sheet (add, remove, equip, pick, set), using features, rests,
and writing the worked-out numbers back into state["player"] so fights, prompts and the status block use them."""
from __future__ import annotations

import random

from ..dice import DiceRoller
from . import build
from .character import ABILS, SKILLS, derive, uses_for

# Library type -> where it goes on the character
SLOTS = {"class": "cls", "race": "race", "subrace": "subrace", "background": "background", "subclass": "subclass",
         "feat": "feats", "optionalfeature": "options", "spell": "spells", "baseitem": "items", "item": "items"}


def apply_change(char: dict, change: dict, lib) -> dict:
    char = {**char, "picks": dict(char.get("picks") or {}), "items": list(char.get("items") or []),
            "feats": list(char.get("feats") or []), "options": list(char.get("options") or []), "spells": list(char.get("spells") or [])}
    op = change.get("op")
    if op == "add":
        kind, name, source = change.get("type", ""), str(change.get("name", "")), str(change.get("source", "PHB"))
        if kind not in SLOTS:
            raise ValueError(f"{kind or 'That'} can't go on a sheet.")
        entry = lib.items.get((kind, name.lower(), source.upper()))
        if entry is None:
            raise ValueError(f"{name} ({source}) is not in the library.")
        if not change.get("homebrew"):
            reason = build.check_add(char, entry, kind, lib)
            if reason:
                raise ValueError(reason)
        ref = {"name": entry["name"], "source": entry["source"]}
        slot = SLOTS[kind]
        if slot == "items":
            char["items"].append({"type": kind, **ref, "qty": max(1, int(change.get("qty", 1))), "equipped": False,
                                  **({"homebrew": True} if change.get("homebrew") else {})})
        elif slot in ("feats", "options", "spells"):
            if any(x["name"].lower() == ref["name"].lower() for x in char[slot]):
                raise ValueError(f"{ref['name']} is already on the sheet.")
            char[slot].append({"type": kind, **ref, **({"homebrew": True} if change.get("homebrew") else {})})
        else:
            char[slot] = ref
            if slot == "race":
                char["subrace"] = None
            if slot == "cls":
                char["subclass"] = None
    elif op == "remove":
        slot = change.get("slot", "items")
        if slot not in ("items", "feats", "options", "spells", "extras"):
            raise ValueError("Can't remove that.")
        lst = list(char.get(slot) or [])
        i = int(change.get("index", -1))
        if not 0 <= i < len(lst):
            raise ValueError("Nothing there to remove.")
        lst.pop(i)
        char[slot] = lst
    elif op == "equip":
        i = int(change.get("index", -1))
        if not 0 <= i < len(char["items"]):
            raise ValueError("No such item.")
        char["items"][i] = {**char["items"][i], "equipped": bool(change.get("on", True))}
    elif op == "set":
        field, value = change.get("field"), change.get("value")
        if field == "scores":
            char["scores"] = {k: max(1, min(30, int((value or {}).get(k, char["scores"].get(k, 10))))) for k in ABILS}
        elif field == "level":
            char["level"] = max(1, min(20, int(value)))
        elif field == "hp_current":
            char["hp"] = {**(char.get("hp") or {}), "current": max(0, int(value))}
        elif field == "xp":
            char["xp"] = max(0, int(value))
        elif field == "extra":  # a homebrew feature typed by the player
            char["extras"] = list(char.get("extras") or []) + [{"name": str(value.get("name", ""))[:80], "text": str(value.get("text", ""))[:1500], "homebrew": True}]
        else:
            raise ValueError("Unknown field.")
    elif op == "pick":
        kind, value = change.get("kind"), change.get("value")
        if kind in ("skills", "expertise"):
            vals = [v.lower() for v in (value or []) if v.lower() in SKILLS]
            char["picks"][kind] = vals
        elif kind == "race_ability":
            char["picks"]["race_ability"] = {k: int(v) for k, v in (value or {}).items() if k in ABILS and int(v)}
        elif kind == "asi":
            char["picks"]["asi"] = [{k: int(v) for k, v in a.items() if k in ABILS} for a in value or []]
        else:
            raise ValueError("Unknown choice.")
    else:
        raise ValueError("Unknown change.")
    return char


def use_feature(char: dict, name: str, lib, rng: random.Random | None = None) -> tuple[dict, str]:
    sheet = derive(char, lib)
    f = next((x for x in sheet["features"] if x["name"].lower() == name.lower()), None)
    if f is None or "uses_max" not in f:
        raise ValueError(f"{name} has no uses to spend.")
    if f["used"] >= f["uses_max"]:
        raise ValueError(f"No uses of {f['name']} left until a {f['per']} rest.")
    char = {**char, "uses": {**(char.get("uses") or {}), f["name"]: f["used"] + 1}}
    line = f"✨ {f['name']} ({f['uses_max'] - f['used'] - 1}/{f['uses_max']} left)"
    if f["name"] == "Second Wind":
        roll = DiceRoller(rng).roll(f"1d10+{sheet['level']}")
        new_hp = min(sheet["hp_max"], sheet["hp"] + roll.total)
        char["hp"] = {**(char.get("hp") or {}), "current": new_hp}
        line += f": 🎲 1d10+{sheet['level']} = {roll.total} → {new_hp}/{sheet['hp_max']} HP"
    return char, line


def rest(char: dict, when: str, lib) -> dict:
    """A short rest refills short-rest uses; a long rest refills everything and HP."""
    sheet = derive(char, lib)
    per = {f["name"]: f.get("per") for f in sheet["features"] if f.get("per")}
    keep = {} if when == "long_rest" else {k: v for k, v in (char.get("uses") or {}).items() if per.get(k) == "long"}
    char = {**char, "uses": keep}
    if when == "long_rest":
        char["hp"] = {**(char.get("hp") or {}), "current": sheet["hp_max"]}
    return char


def sync_player(state: dict, lib) -> dict:
    """The worked-out sheet into state["player"] (what fights, prompts and the status block read) and a cache."""
    char = state.get("character5e")
    if not char:
        return {}
    sheet = derive(char, lib)
    p = state.setdefault("player", {})
    p.update(**{"class": sheet["class"] + (f" ({sheet['subclass']})" if sheet["subclass"] else ""), "level": sheet["level"],
                "race": " ".join(x for x in (sheet["subrace"], sheet["race"]) if x), "ac": sheet["ac"],
                "background": p.get("background") or sheet["background"]})
    p["hp"] = {"current": sheet["hp"], "max": sheet["hp_max"]}
    p["stats"] = {k.upper(): v["score"] for k, v in sheet["abilities"].items()}
    p["skills"] = [f"{n.title()} {'+' if s['bonus'] >= 0 else ''}{s['bonus']}" for n, s in sheet["skills"].items() if s["proficient"]]
    state["character5e_sheet"] = {k: sheet[k] for k in ("ac", "attacks", "saves", "skills", "prof", "initiative", "speed", "hp_max", "level")}
    return sheet


def _find(lib, kinds: tuple, name: str, edition: str) -> dict | None:
    from .library import edition_of
    n = (name or "").strip().lower()
    if not n:
        return None
    hits = [e for (k, key, _), e in lib.items.items() if k in kinds and key == n and edition_of(e) == edition]
    hits.sort(key=lambda e: (e.get("source") not in ("PHB", "XPHB"), not e.get("srd")))
    return hits[0] if hits else None


def convert(state: dict, lib, edition: str = "2014") -> dict:
    """A free-form sheet (name, race, class, level, stats, HP, inventory) as a 5e character, matched in the Library."""
    from .character import new_character
    p = state.get("player") or {}
    char = new_character(edition)
    race_words = str(p.get("race") or "").split()
    for kind, key, words in (("class", "cls", [str(p.get("class") or "").split("(")[0]]), ("race", "race", [" ".join(race_words), race_words[-1] if race_words else ""]),
                             ("background", "background", [str(p.get("background") or "").split(".")[0].split(",")[0]])):
        for w in words:
            e = _find(lib, (kind,), w, edition)
            if e:
                char[key] = {"name": e["name"], "source": e["source"]}
                break
    char["level"] = max(1, min(20, int(p.get("level") or 1)))
    stats = p.get("stats") or {}
    char["scores"] = {k: int(stats.get(k.upper(), 10)) for k in ABILS}
    race = lib.items.get(("race", str((char.get("race") or {}).get("name", "")).lower(), str((char.get("race") or {}).get("source", "")).upper())) if char.get("race") else None
    if race and race.get("name") == "Human" and not race.get("ability"):  # their sheet already has the +1s
        char["scores"] = {k: v - 1 for k, v in char["scores"].items()}
    skills = [str(x).split("+")[0].split("-")[0].strip().lower() for x in p.get("skills") or []]
    char["picks"]["skills"] = [s for s in skills if s in SKILLS]
    for it in state.get("inventory") or []:
        e = _find(lib, ("baseitem", "item"), it.get("name", ""), edition)
        if e:
            kind = "baseitem" if (("baseitem", e["name"].lower(), e["source"].upper()) in lib.items) else "item"
            t = str(e.get("type", "")).split("|")[0]
            char["items"].append({"type": kind, "name": e["name"], "source": e["source"], "qty": int(it.get("qty", 1)),
                                  "equipped": t in ("LA", "MA", "HA", "S", "M", "R")})
    notes = str(p.get("notes") or "")
    for e in [x for (k, _, _), x in lib.items.items() if k == "optionalfeature" and "FS:F" in (x.get("featureType") or [])]:
        if f"Fighting Style: {e['name']}" in notes or f"Style: {e['name']}" in notes:
            char["options"].append({"type": "optionalfeature", "name": e["name"], "source": e["source"]})
            break
    hp = p.get("hp") or {}
    char["hp"] = {"current": hp.get("current"), "rolls": []}
    return char


__all__ = ["apply_change", "use_feature", "rest", "sync_player", "uses_for"]
