"""The D&D 5e character engine: a character is references to Library entries plus the player's choices, and every
number on the sheet (AC, attacks, saves, skills, HP, uses per rest, spell slots) is worked out here, never typed.
"""
from __future__ import annotations

import math

from .text import render, strip_tags

ABILS = ("str", "dex", "con", "int", "wis", "cha")
SKILLS = {
    "acrobatics": "dex", "animal handling": "wis", "arcana": "int", "athletics": "str", "deception": "cha", "history": "int",
    "insight": "wis", "intimidation": "cha", "investigation": "int", "medicine": "wis", "nature": "int", "perception": "wis",
    "performance": "cha", "persuasion": "cha", "religion": "int", "sleight of hand": "dex", "stealth": "dex", "survival": "wis",
}
XP_LEVELS = (0, 300, 900, 2700, 6500, 14000, 23000, 34000, 48000, 64000, 85000, 100000, 120000, 140000, 165000, 195000,
             225000, 265000, 305000, 355000)
# 5e spell slots by caster level (full casters; half and third casters use a lower row)
FULL_SLOTS = [
    [2], [3], [4, 2], [4, 3], [4, 3, 2], [4, 3, 3], [4, 3, 3, 1], [4, 3, 3, 2], [4, 3, 3, 3, 1], [4, 3, 3, 3, 2],
    [4, 3, 3, 3, 2, 1], [4, 3, 3, 3, 2, 1], [4, 3, 3, 3, 2, 1, 1], [4, 3, 3, 3, 2, 1, 1], [4, 3, 3, 3, 2, 1, 1, 1],
    [4, 3, 3, 3, 2, 1, 1, 1], [4, 3, 3, 3, 2, 1, 1, 1, 1], [4, 3, 3, 3, 3, 1, 1, 1, 1], [4, 3, 3, 3, 3, 2, 1, 1, 1],
    [4, 3, 3, 3, 3, 2, 2, 1, 1]]


def new_character(edition: str = "2014") -> dict:
    return {"edition": edition, "cls": None, "subclass": None, "level": 1, "race": None, "subrace": None, "background": None,
            "scores": {k: 10 for k in ABILS}, "picks": {"race_ability": {}, "asi": [], "skills": [], "expertise": []},
            "options": [], "feats": [], "spells": [], "items": [], "hp": {"current": None, "rolls": []}, "uses": {}, "xp": 0, "extras": []}


def prof_bonus(level: int) -> int:
    return 2 + (max(1, min(20, level)) - 1) // 4


def mod(score: int) -> int:
    return (int(score) - 10) // 2


def _sig(n: int) -> str:
    return f"+{n}" if n >= 0 else str(n)


class _Lookup:
    """Finds the character's references in the Library and notes the missing ones."""

    def __init__(self, lib):
        self.lib, self.warnings = lib, []

    def get(self, kind: str, ref: dict | None, what: str = "") -> dict | None:
        if not ref or not ref.get("name"):
            return None
        e = self.lib.items.get((kind, str(ref["name"]).lower(), str(ref.get("source", "PHB")).upper()))
        if e is None:
            self.warnings.append(f"{ref['name']} ({ref.get('source', '?')}) is missing from the library{' — ' + what if what else ''}.")
        return e

    def item(self, it: dict) -> dict | None:
        e = self.get(it.get("type", "baseitem"), it) or (self.lib.items.get(("item", str(it.get("name", "")).lower(), str(it.get("source", "")).upper())))
        if e and e.get("baseItem"):  # a magic weapon or armour: the base item's numbers plus its own
            name, _, src = str(e["baseItem"]).partition("|")
            base = self.lib.items.get(("baseitem", name.lower(), (src or "PHB").upper()))
            if base:
                e = {**base, **e}
        return e


def _props(e: dict) -> set:
    return {str(p).split("|")[0] for p in e.get("property") or []}


def _bonus(e: dict, key: str) -> int:
    try:
        return int(str(e.get(key) or "0").replace("+", ""))
    except ValueError:
        return 0


def derive(char: dict, lib) -> dict:
    look = _Lookup(lib)
    level = max(1, min(20, int(char.get("level") or 1)))
    cls = look.get("class", char.get("cls"), "class")
    race = look.get("race", char.get("race"), "race")
    sub = look.get("subrace", char.get("subrace"), "subrace")
    bg = look.get("background", char.get("background"), "background")
    names = lambda key: {str(x.get("name", "")).lower() for x in char.get(key) or []}  # noqa: E731
    options, feats = names("options"), names("feats")

    # ability scores: base + race (+ subrace) + the player's picks + ASIs
    scores = {k: int((char.get("scores") or {}).get(k, 10)) for k in ABILS}
    how = {k: [str(scores[k])] for k in ABILS}
    adds: list[tuple[dict, str]] = []
    for src, label in ((race, "race"), (sub, "subrace")):
        if src:
            fixed = next((a for a in src.get("ability") or [] if isinstance(a, dict) and "choose" not in a), None)
            if fixed:
                adds.append(({k: v for k, v in fixed.items() if k in ABILS}, label))
            elif label == "race" and src.get("name") == "Human" and src.get("source") == "PHB" and not src.get("ability"):
                adds.append(({k: 1 for k in ABILS}, "race"))  # the PHB human: +1 to every score
    adds.append(((char.get("picks") or {}).get("race_ability") or {}, "race choice"))
    for asi in (char.get("picks") or {}).get("asi") or []:
        adds.append((asi, "improvement"))
    for d, label in adds:
        for k, v in d.items():
            if k in ABILS and v:
                scores[k] += int(v)
                how[k].append(f"{_sig(int(v))} {label}")
    scores = {k: min(30, v) for k, v in scores.items()}
    mods = {k: mod(v) for k, v in scores.items()}
    prof = prof_bonus(level)

    saves_prof = set((cls or {}).get("proficiency") or [])
    saves = {k: mods[k] + (prof if k in saves_prof else 0) for k in ABILS}

    skill_prof = {s.lower() for s in (char.get("picks") or {}).get("skills") or []}
    for src in (bg, race, sub):
        for block in (src or {}).get("skillProficiencies") or []:
            skill_prof |= {k for k, v in block.items() if v is True}
    expertise = {s.lower() for s in (char.get("picks") or {}).get("expertise") or []}
    skills = {}
    for name, ab in SKILLS.items():
        p = name in skill_prof
        e = p and name in expertise
        skills[name] = {"bonus": mods[ab] + (prof * (2 if e else 1) if p else 0), "proficient": p, "expertise": e, "ability": ab}

    # equipment
    worn_armor, shields, weapons = [], [], []
    for it in char.get("items") or []:
        if not it.get("equipped"):
            continue
        e = look.item(it)
        if not e:
            continue
        kind = str(e.get("type", "")).split("|")[0]
        if kind in ("LA", "MA", "HA"):
            worn_armor.append(e)
        elif kind == "S":
            shields.append(e)
        elif e.get("dmg1") and kind in ("M", "R"):
            weapons.append(e)

    def armor_ac(e: dict) -> tuple[int, str]:
        kind = str(e.get("type", "")).split("|")[0]
        base = int(e.get("ac") or 10) + _bonus(e, "bonusAc")
        dex = mods["dex"] if kind == "LA" else min(2, mods["dex"]) if kind == "MA" else 0
        return base + dex, f"{e['name']} {base}" + (f" {_sig(dex)} DEX" if kind != "HA" else "")

    cls_name = (cls or {}).get("name", "")
    if worn_armor:
        best = max(worn_armor, key=lambda e: armor_ac(e)[0])
        ac, ac_how = armor_ac(best)
        for other in worn_armor:
            if other is not best:
                look.warnings.append(f"Only one armour counts: {other['name']} is worn but {best['name']} is used.")
    elif cls_name == "Barbarian":
        ac, ac_how = 10 + mods["dex"] + mods["con"], f"Unarmored Defense 10 {_sig(mods['dex'])} DEX {_sig(mods['con'])} CON"
    elif cls_name == "Monk" and not shields:
        ac, ac_how = 10 + mods["dex"] + mods["wis"], f"Unarmored Defense 10 {_sig(mods['dex'])} DEX {_sig(mods['wis'])} WIS"
    else:
        ac, ac_how = 10 + mods["dex"], f"10 {_sig(mods['dex'])} DEX"
    if shields:
        sh = max(shields, key=lambda e: 2 + _bonus(e, "bonusAc"))
        ac += 2 + _bonus(sh, "bonusAc")
        ac_how += f" + {sh['name']} {2 + _bonus(sh, 'bonusAc')}"
        if len(shields) > 1:
            look.warnings.append("Only one shield counts.")
    if "defense" in options and worn_armor:
        ac += 1
        ac_how += " + Defense 1"

    # hit points
    faces = int(((cls or {}).get("hd") or {}).get("faces") or 8)
    rolls = list((char.get("hp") or {}).get("rolls") or [])
    hp_max = faces + mods["con"]
    for lv in range(2, level + 1):
        r = rolls[lv - 2] if lv - 2 < len(rolls) and rolls[lv - 2] else faces // 2 + 1
        hp_max += max(1, int(r) + mods["con"])
    if race and race.get("name") == "Dwarf" and sub and sub.get("name") == "Hill":
        hp_max += level  # Dwarven Toughness
    if "tough" in feats:
        hp_max += 2 * level
    hp_max = max(1, hp_max)
    cur = (char.get("hp") or {}).get("current")
    hp = hp_max if cur is None else max(0, min(hp_max, int(cur)))

    speed = (race or {}).get("speed", 30)
    speed = speed.get("walk", 30) if isinstance(speed, dict) else int(speed or 30)
    initiative = mods["dex"] + (5 if "alert" in feats else 0)

    sheet = {
        "level": level, "class": cls_name, "race": (race or {}).get("name", ""), "subrace": (sub or {}).get("name", ""),
        "background": (bg or {}).get("name", ""), "subclass": (char.get("subclass") or {}).get("name", ""),
        "abilities": {k: {"score": scores[k], "mod": mods[k], "how": " ".join(how[k])} for k in ABILS},
        "prof": prof, "saves": saves, "save_prof": sorted(saves_prof), "skills": skills,
        "passive_perception": 10 + skills["perception"]["bonus"], "ac": ac, "ac_how": ac_how,
        "hp_max": hp_max, "hp": hp, "hit_die": f"d{faces}", "initiative": initiative, "speed": speed,
        "xp": int(char.get("xp") or 0), "next_level_xp": XP_LEVELS[level] if level < 20 else None,
    }
    sheet["attacks"] = _attacks(weapons, cls, mods, prof, options, bool(shields))
    if cls_name == "Monk":  # Martial Arts: an unarmed strike with DEX or STR and the monk's die
        ab = "dex" if mods["dex"] >= mods["str"] else "str"
        die = 4 if level < 5 else 6 if level < 11 else 8 if level < 17 else 10
        sheet["attacks"].insert(0, {"name": "Unarmed Strike", "bonus": prof + mods[ab], "damage": f"1d{die}{_sig(mods[ab]) if mods[ab] else ''}",
                                    "dtype": "bludgeoning", "range": "5 ft", "properties": [], "proficient": True, "ability": ab})
    sheet["features"] = _features(char, cls, look, level, mods)
    sheet.update(_slots(cls, level))
    # spellcasting: the class's ability (or the subclass's, for an Eldritch Knight), save DC and spell attack
    sab = ((cls or {}).get("spellcastingAbility") or "")
    sub_entry = None
    if char.get("subclass"):
        sub_entry = next((v for (k, n, _), v in look.lib.items.items() if k == "subclass" and n == str(char["subclass"].get("name", "")).lower()
                          and v.get("className") == (cls or {}).get("name")), None)
    if not sab:
        sab = (sub_entry or {}).get("spellcastingAbility") or ""
    if sab in mods:
        sheet.update(spell_ability=sab, spell_dc=8 + prof + mods[sab], spell_attack=prof + mods[sab])
    from .magic import pact_left, slots_left
    sheet["slots_left"] = slots_left(sheet, char)
    sheet["pact_left"] = pact_left(sheet, char)
    if sab in mods:  # how many cantrips and spells this level knows or prepares, and what the sheet has
        from .levels import counts, warnings
        sheet["spell_counts"] = counts(char, cls, sub_entry, level, mods, bool(sheet.get("slots") or sheet.get("pact")), look.lib)
        look.warnings.extend(warnings(sheet["spell_counts"], level, (cls or {}).get("name", "")))
    cp = int(char.get("cp") or 0)  # money, kept in copper pieces
    sheet["coins"] = {"cp_total": cp, "gp": cp // 100, "sp": (cp % 100) // 10, "cp": cp % 10}
    sheet["warnings"] = look.warnings
    return sheet


def _attacks(weapons: list[dict], cls: dict | None, mods: dict, prof: int, options: set, shield: bool) -> list[dict]:
    profs = " ".join(strip_tags(str(w)).lower() for w in ((cls or {}).get("startingProficiencies") or {}).get("weapons") or [])
    out = []
    one_weapon = len([w for w in weapons if str(w.get("type", "")).split("|")[0] == "M"]) == 1
    for w in weapons:
        props = _props(w)
        ranged = str(w.get("type", "")).split("|")[0] == "R"
        ab = "dex" if ranged else ("dex" if "F" in props and mods["dex"] > mods["str"] else "str")
        proficient = (w.get("weaponCategory") or "") in profs or w["name"].lower() in profs
        bonus = mods[ab] + (prof if proficient else 0) + _bonus(w, "bonusWeapon") + _bonus(w, "bonusWeaponAttack")
        if ranged and "archery" in options:
            bonus += 2
        die = w.get("dmg2") if "V" in props and not shield and one_weapon and w.get("dmg2") else w.get("dmg1")
        dmg = mods[ab] + _bonus(w, "bonusWeapon") + _bonus(w, "bonusWeaponDamage")
        if not ranged and "dueling" in options and "2H" not in props and one_weapon:
            dmg += 2
        out.append({"name": w["name"], "bonus": bonus, "damage": f"{die}{_sig(dmg) if dmg else ''}",
                    "dtype": {"S": "slashing", "P": "piercing", "B": "bludgeoning"}.get(str(w.get("dmgType", "")), str(w.get("dmgType", ""))),
                    "range": f"{w['range']} ft" if w.get("range") else ("reach 10 ft" if "R" in props else "5 ft"),
                    "properties": sorted(props), "proficient": proficient, "ability": ab})
    return out


def uses_for(name: str, level: int, mods: dict) -> tuple[int, str] | None:
    """How many uses a feature has and when it comes back (5e SRD numbers)."""
    n = name.lower()
    if n == "second wind":
        return 1, "short"
    if n == "action surge":
        return (2 if level >= 17 else 1), "short"
    if n == "rage":
        return (6 if level >= 17 else 5 if level >= 12 else 4 if level >= 6 else 3 if level >= 3 else 2), "long"
    if n.startswith("channel divinity"):
        return (3 if level >= 18 else 2 if level >= 6 else 1), "short"
    if n == "bardic inspiration":
        return max(1, mods["cha"]), ("short" if level >= 5 else "long")
    if n in ("ki", "monk's focus"):
        return level, "short"
    if n == "wild shape":
        return 2, "short"
    if n == "lay on hands":
        return 5 * level, "long"
    if n == "arcane recovery":
        return 1, "long"
    if n in ("font of magic", "sorcery points"):
        return level, "long"
    if n == "divine sense":
        return 1 + max(0, mods["cha"]), "long"
    return None


def _parse_ref(ref) -> tuple[str, str, str, int, str]:
    s = ref.get("classFeature", "") if isinstance(ref, dict) else str(ref)
    parts = s.split("|")
    name, cname = parts[0], parts[1] if len(parts) > 1 else ""
    csrc = (parts[2] if len(parts) > 2 and parts[2] else "PHB")
    lv = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 1
    src = parts[4] if len(parts) > 4 and parts[4] else csrc
    return name, cname, csrc, lv, src


def _features(char: dict, cls: dict | None, look: _Lookup, level: int, mods: dict) -> list[dict]:
    out = []
    used = char.get("uses") or {}

    def add(name, lv, source, entry):
        f = {"name": name, "level": lv, "source": source, "text": render((entry or {}).get("entries") or "")}
        u = uses_for(name, level, mods)
        if u:
            f.update(uses_max=u[0], per=u[1], used=min(u[0], int(used.get(name, 0))))
        out.append(f)

    if cls:
        csrc = cls.get("source", "PHB")
        for ref in cls.get("classFeatures") or []:
            name, _, _, lv, src = _parse_ref(ref)
            if lv > level or src != csrc:  # optional features from other books (TCE) are not automatic
                continue
            add(name, lv, src, look.lib.items.get(("classFeature", name.lower(), src.upper())))
        sub = char.get("subclass")
        if sub:
            sc = look.get("subclass", sub, "subclass")
            short = (sc or {}).get("shortName", sub.get("name"))
            for (kind, _, _), e in look.lib.items.items():
                if (kind == "subclassFeature" and e.get("className") == cls.get("name") and e.get("subclassShortName") == short
                        and e.get("subclassSource", "PHB") == sub.get("source", "PHB") and int(e.get("level", 99)) <= level):
                    add(e["name"], int(e["level"]), e["source"], e)
    for kind, key in (("optionalfeature", "options"), ("feat", "feats")):
        for ref in char.get(key) or []:
            e = look.get(kind, ref, key[:-1])
            if e:
                add(e["name"], 0, e["source"], e)
    for x in char.get("extras") or []:
        out.append({"name": x.get("name", ""), "level": 0, "source": "homebrew", "text": x.get("text", ""), "homebrew": True})
    out.sort(key=lambda f: (f["level"] == 0, f["level"]))
    return out


def _slots(cls: dict | None, level: int) -> dict:
    prog = str((cls or {}).get("casterProgression") or "")
    if prog == "pact":
        count = 1 if level == 1 else 2 if level <= 10 else 3 if level <= 16 else 4
        return {"slots": {}, "pact": {"count": count, "level": min(5, math.ceil(level / 2))}}
    row = level if prog == "full" else (math.ceil(level / 2) if prog in ("1/2", "artificer") and level >= 2 else
                                       math.ceil(level / 3) if prog == "1/3" and level >= 3 else 0)
    if not row:
        return {"slots": {}, "pact": None}
    return {"slots": {i + 1: n for i, n in enumerate(FULL_SLOTS[row - 1])}, "pact": None}
