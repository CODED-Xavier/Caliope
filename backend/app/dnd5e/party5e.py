"""Companions with real 5e sheets, built by the system around the hero.

A balanced party usually has a front-liner, a healer, a spellcaster and a support (buffer), but in D&D this is
blurry: a Cleric heals and buffs, a War Cleric or a Bladesinger Wizard stands in the front line. So each class
(and some subclasses) covers one or more roles, and the system fills the roles the hero and the others leave open.
A companion whose card already names a class keeps it.
"""
from __future__ import annotations

import re

from .build import _style_options, _subclass_level
from .character import ABILS, SKILLS, derive

ORDER = ["front", "healer", "caster", "support"]
ROLE_LABELS = {"front": "front-liner", "healer": "healer", "caster": "spellcaster", "support": "support"}
CLASS_ROLES = {
    "fighter": {"front"}, "barbarian": {"front"}, "monk": {"front"}, "rogue": {"front"}, "ranger": {"front"},
    "paladin": {"front", "healer", "support"}, "cleric": {"healer", "support"}, "druid": {"healer", "caster"},
    "wizard": {"caster"}, "sorcerer": {"caster"}, "warlock": {"caster"}, "bard": {"support", "healer", "caster"},
    "artificer": {"support"},
}
SUBCLASS_ROLES = {  # a subclass that moves a class into another role (matched by a word of its name)
    "war": {"front"}, "tempest": {"front"}, "forge": {"front"}, "bladesinging": {"front"}, "hexblade": {"front"},
    "valor": {"front"}, "swords": {"front"}, "eldritch knight": {"caster"}, "arcane trickster": {"caster"},
    "shepherd": {"support"}, "life": {"healer"}, "lore": {"support", "caster"}, "battle smith": {"front"},
}
PREFERRED = {  # which class the system reaches for first to fill a role
    "front": ["Fighter", "Paladin", "Barbarian"], "healer": ["Cleric", "Druid", "Paladin"],
    "caster": ["Wizard", "Sorcerer", "Warlock"], "support": ["Bard", "Cleric", "Paladin"],
}
SUBCLASS_FOR = {
    "front": ["War Domain", "Champion", "Bladesinging", "Oath of Devotion", "Path of the Berserker", "Hunter", "Thief"],
    "healer": ["Life Domain", "Circle of the Land", "Oath of Devotion", "College of Lore"],
    "caster": ["School of Evocation", "Draconic Bloodline", "The Fiend", "Circle of the Land"],
    "support": ["College of Lore", "Knowledge Domain", "Oath of Devotion"],
}
PRIORITY = {  # standard array, best score first
    "barbarian": "str con dex wis cha int", "fighter": "str con dex wis cha int", "paladin": "str cha con wis dex int",
    "monk": "dex wis con str int cha", "rogue": "dex con int wis cha str", "ranger": "dex wis con str int cha",
    "cleric": "wis str con dex cha int", "druid": "wis con dex int cha str", "wizard": "int con dex wis cha str",
    "sorcerer": "cha con dex wis int str", "warlock": "cha con dex wis int str", "bard": "cha dex con wis int str",
    "artificer": "int con dex wis cha str",
}
BACKGROUND_FOR = {"front": "Soldier", "healer": "Acolyte", "caster": "Sage", "support": "Entertainer"}
STANDARD = [15, 14, 13, 12, 10, 8]


def roles_of(cls_name: str, subclass_name: str = "") -> set:
    roles = set(CLASS_ROLES.get(str(cls_name or "").lower(), set()))
    sub = str(subclass_name or "").lower()
    for word, extra in SUBCLASS_ROLES.items():
        if word in sub.split() or word == sub or (" " in word and word in sub):
            roles |= extra
    return roles


def char_roles(char: dict | None) -> set:
    char = char or {}
    return roles_of((char.get("cls") or {}).get("name", ""), (char.get("subclass") or {}).get("name", ""))


def missing_roles(covered: set) -> list[str]:
    return [r for r in ORDER if r not in covered]


def _find(lib, kind: str, name: str, edition: str):
    from .store import _find as find
    return find(lib, (kind,), name, edition)


def _any(lib, kind: str, edition: str):
    from .library import edition_of
    hits = sorted((e for (k, _, _), e in lib.items.items() if k == kind and edition_of(e) == edition),
                  key=lambda e: (not e.get("srd"), e["name"]))
    return hits[0] if hits else None


def _ref(e: dict | None) -> dict | None:
    return {"name": e["name"], "source": e["source"]} if e else None


def class_hint(lib, comp: dict, edition: str):
    """The class the card names: its sheet's class, else a class word in its description ("a halfling rogue")."""
    hint = str(((comp.get("sheet") or {}).get("class")) or "").strip()
    if hint:
        e = _find(lib, "class", hint, edition)
        if e:
            return e
    words = set(re.findall(r"[a-z]+", str(comp.get("description") or "").lower()))
    for name in CLASS_ROLES:
        if name in words:
            e = _find(lib, "class", name, edition)
            if e:
                return e
    return None


def _pick_class(lib, comp: dict, role: str | None, taken: list[str], edition: str):
    e = class_hint(lib, comp, edition)
    if e:
        return e
    options = [c for c in PREFERRED.get(role or "front", []) if _find(lib, "class", c, edition)]
    fresh = [c for c in options if c not in taken]
    name = (fresh or options or [None])[0]
    return _find(lib, "class", name, edition) if name else _any(lib, "class", edition)


def _pick_race(lib, comp: dict, edition: str):
    from .library import edition_of
    text = " ".join(str(comp.get(k) or "") for k in ("description", "personality", "name")).lower()
    races = sorted((e for (k, _, _), e in lib.items.items() if k == "race" and edition_of(e) == edition), key=lambda e: -len(e["name"]))
    for e in races:
        if e["name"].lower() in text.replace(",", " ").split() or f" {e['name'].lower()}" in f" {text}":
            return e
    return _find(lib, "race", "Human", edition) or _any(lib, "race", edition)


def _gear(lib, cls: dict, role: str, scores: dict, edition: str) -> list[dict]:
    sp = cls.get("startingProficiencies") or {}
    armor = {str(a).split("|")[0].lower() for a in sp.get("armor") or [] if isinstance(a, str)}
    weapons = {str(w).split("|")[0].lower() for w in sp.get("weapons") or [] if isinstance(w, str)}
    names = []
    if "heavy" in armor and scores["str"] >= 13:
        names.append("Chain Mail")
    elif "medium" in armor:
        names.append("Scale Mail")
    elif "light" in armor:
        names.append("Leather Armor")
    finesse = scores["dex"] > scores["str"]
    if "martial" in weapons:
        names.append("Rapier" if finesse else "Longsword")
        if finesse:
            names.append("Longbow")
    elif role == "caster" or not weapons:
        names.append("Quarterstaff")
    else:
        names.append("Mace")
    if "shield" in armor and not finesse and role != "caster":
        names.append("Shield")
    items = []
    for n in names:
        e = _find(lib, "baseitem", n, edition)
        if e:
            items.append({"type": "baseitem", **_ref(e), "qty": 1, "equipped": True})
    return items


def auto_build(comp: dict, hero: dict, taken: list[str], lib, role: str | None = None) -> dict:
    """One companion's 5e character: the card's class if it names one, else a class for `role`, at the hero's level."""
    from .character import new_character
    edition = (hero or {}).get("edition") or "2014"
    level = int((hero or {}).get("level") or 1)
    cls = _pick_class(lib, comp, role, taken, edition)
    char = new_character(edition)
    char["level"] = level
    if not cls:
        return char
    cname = cls["name"].lower()
    roles = roles_of(cls["name"])
    role = role if role in roles else ((comp.get("sheet") or {}).get("role") == "healer" and "healer" in roles and "healer") or \
        next((r for r in ORDER if r in roles), "front")
    char["cls"] = _ref(cls)
    char["race"] = _ref(_pick_race(lib, comp, edition))
    bg = _find(lib, "background", BACKGROUND_FOR.get(role, "Soldier"), edition) or _any(lib, "background", edition)
    char["background"] = _ref(bg)
    order = PRIORITY.get(cname, "str dex con int wis cha").split()
    char["scores"] = {k: STANDARD[order.index(k)] if k in order else 10 for k in ABILS}
    choose = next((b["choose"] for b in (cls.get("startingProficiencies") or {}).get("skills") or [] if isinstance(b, dict) and "choose" in b), None)
    if choose:
        bg_skills = {k for b in (bg or {}).get("skillProficiencies") or [] if isinstance(b, dict) for k, v in b.items() if v is True}
        opts = [s for s in choose.get("from") or [] if s in SKILLS and s not in bg_skills]
        char["picks"]["skills"] = opts[: choose.get("count", 0)]
    char["items"] = _gear(lib, cls, role, char["scores"], edition)
    styles, count, _ = _style_options(cls, level, lib)
    if count and styles:
        ranged = any(i["name"] in ("Longbow", "Shortbow") for i in char["items"])
        want = ["Archery", "Dueling", "Defense"] if ranged else ["Defense", "Dueling", "Protection"] if role == "front" else ["Dueling", "Defense"]
        picked = [s for s in want if s in styles][:count] or styles[:count]
        char["options"] = [{"type": "optionalfeature", "name": n, "source": cls.get("source", "PHB")} for n in picked]
    if level >= _subclass_level(cls):
        subs = [e for (k, _, _), e in lib.items.items() if k == "subclass" and e.get("className") == cls["name"] and e.get("classSource", "PHB") == cls.get("source")]
        if subs:
            want = SUBCLASS_FOR.get(role, [])
            sc = next((s for w in want for s in subs if s["name"] == w), None) or sorted(subs, key=lambda s: s["name"])[0]
            char["subclass"] = _ref(sc)
    return char


def auto_build_all(comps: list[dict], hero: dict, lib, only: str = "", keep: dict | None = None) -> dict:
    """Companions keyed by name. Cards that name a class go first; the others fill the roles still open.
    keep = companions that already have a sheet and stay as they are (their roles count as covered)."""
    covered = set(char_roles(hero))
    taken = [((hero or {}).get("cls") or {}).get("name", "")]
    edition = (hero or {}).get("edition") or "2014"
    built = {}
    keep = {k: v for k, v in (keep or {}).items() if v and k != only}
    for c in comps:
        if c["name"] in keep:
            covered |= char_roles(keep[c["name"]])
            taken.append((keep[c["name"]].get("cls") or {}).get("name", ""))
    comps = [c for c in comps if c["name"] not in keep]
    hinted = [c for c in comps if class_hint(lib, c, edition)]
    for c in hinted + [c for c in comps if c not in hinted]:
        open_roles = missing_roles(covered) or list(ORDER)
        char = auto_build(c, hero, taken, lib, role=None if c in hinted else open_roles[0])
        covered |= char_roles(char) if c in hinted else {open_roles[0]} | char_roles(char)
        taken.append((char.get("cls") or {}).get("name", ""))
        built[c["name"]] = char
    return {k: v for k, v in built.items() if not only or k == only}


def sync_companion(state: dict, name: str, lib) -> dict:
    """The companion's worked-out numbers for fights (party5e_sheet) and its HP into the party."""
    char = (state.get("party5e") or {}).get(name)
    if not char:
        return {}
    sheet = derive(char, lib)
    best = max(sheet["attacks"], key=lambda a: a["bonus"], default=None)
    rng = 1
    if best and "ft" in str(best.get("range")):
        try:
            rng = max(1, int(str(best["range"]).split("/")[0].split()[-2 if "reach" in best["range"] else 0]) // 5)
        except (ValueError, IndexError):
            rng = 1
    state.setdefault("party5e_sheet", {})[name] = {
        "class": sheet["class"], "subclass": sheet["subclass"], "level": sheet["level"], "ac": sheet["ac"],
        "hp_max": sheet["hp_max"], "attack_bonus": best["bonus"] if best else sheet["prof"],
        "damage": best["damage"] if best else "1d4", "weapon": best["name"] if best else "", "range": rng, "init_bonus": sheet["initiative"],
        "speed": max(1, sheet["speed"] // 5), "roles": sorted(char_roles(char)),
    }
    p = state.setdefault("party", {})
    cur = p.get(name) or {}
    hp = sheet["hp"] if (char.get("hp") or {}).get("current") is not None else sheet["hp_max"]
    p[name] = {"hp": min(hp, sheet["hp_max"]), "max_hp": sheet["hp_max"]} if cur or state.get("party_mode") == "companions" else cur
    return sheet
