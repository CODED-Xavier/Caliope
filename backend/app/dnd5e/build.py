"""Rules checks when something is added to a 5e sheet, the builder's steps (like Roll20's Charactermancer), and
level-ups: the app adds what the class table gives and asks only for the real choices."""
from __future__ import annotations

from .character import ABILS, SKILLS, _parse_ref, derive

ABILITY_METHODS = {"standard": [15, 14, 13, 12, 10, 8], "pointbuy": 27, "roll": "4d6 drop lowest", "manual": None}
POINT_COST = {8: 0, 9: 1, 10: 2, 11: 3, 12: 4, 13: 5, 14: 7, 15: 9}


def _armor_profs(cls: dict | None) -> set:
    return {str(a).split("|")[0].lower() for a in ((cls or {}).get("startingProficiencies") or {}).get("armor") or [] if isinstance(a, str)}


def check_add(char: dict, entry: dict, kind: str, lib) -> str:
    """"" when the entry may go on the sheet, else the reason (shown to the player, with "add anyway")."""
    sheet = derive(char, lib)
    level = sheet["level"]
    if kind == "spell":
        cls = _cls(char, lib)
        if cls:
            casting = caster_list(char, lib)
            if not casting:
                return f"{cls['name']}s don't cast spells{'' if char.get('subclass') else ' (unless a subclass gives magic)'}."
            from .spell_lists import on_list
            if on_list(entry["name"], casting, lib) is False:
                return f"{entry['name']} isn't on the {casting} spell list."
        need = int(entry.get("level", 0))
        top = max([int(k) for k in sheet["slots"]] + ([sheet["pact"]["level"]] if sheet.get("pact") else []) + [0])
        if need > 0 and need > top:
            return (f"{entry['name']} is a level {need} spell; your highest spell slot is level {top}." if top
                    else f"{entry['name']} is a level {need} spell, and you have no spell slots.")
    if kind in ("classFeature", "subclassFeature") and int(entry.get("level", 1)) > level:
        return f"{entry['name']} comes at {entry.get('className', 'class')} level {entry.get('level')}; you are level {level}."
    if kind == "feat":
        cls = lib.items.get(("class", str((char.get("cls") or {}).get("name", "")).lower(), str((char.get("cls") or {}).get("source", "PHB")).upper()))
        for req in entry.get("prerequisite") or []:
            for p in req.get("proficiency") or []:
                armor = p.get("armor")
                if armor and armor.lower() not in _armor_profs(cls):
                    return f"{entry['name']} needs proficiency with {armor} armor."
            for a in req.get("ability") or []:
                for k, v in a.items():
                    if k in ABILS and sheet["abilities"][k]["score"] < int(v):
                        return f"{entry['name']} needs {k.upper()} {v} or higher."
            if req.get("level") and level < int(req["level"] if not isinstance(req["level"], dict) else req["level"].get("level", 1)):
                return f"{entry['name']} needs level {req['level']}."
            if req.get("spellcasting") and not sheet["slots"] and not sheet.get("pact"):
                return f"{entry['name']} needs the ability to cast spells."
    return ""


def caster_list(char: dict, lib) -> str:
    """The class spell list this character learns from ("" for a class without magic). Fighters and rogues whose
    subclass casts (Eldritch Knight, Arcane Trickster) learn from the Wizard list."""
    cls = _cls(char, lib)
    if not cls:
        return ""
    if cls.get("spellcastingAbility"):
        return cls["name"]
    sub = char.get("subclass") or {}
    if sub:
        e = next((v for (k, n, _), v in lib.items.items() if k == "subclass" and n == str(sub.get("name", "")).lower()
                  and v.get("className") == cls["name"]), None)
        if e and e.get("spellcastingAbility"):
            return "Wizard" if e["spellcastingAbility"] == "int" else cls["name"]
    return ""


def _cls(char: dict, lib) -> dict | None:
    c = char.get("cls") or {}
    return lib.items.get(("class", str(c.get("name", "")).lower(), str(c.get("source", "PHB")).upper()))


def _style_options(cls: dict | None, level: int, lib) -> tuple[list[str], int, list[str]]:
    """Fighting styles (and other "pick N" options) the class gives by this level."""
    names, count, types = [], 0, []
    for prog in (cls or {}).get("optionalfeatureProgression") or []:
        p = prog.get("progression") or {}
        n = max([v for k, v in p.items() if str(k).isdigit() and int(k) <= level] + [0]) if isinstance(p, dict) else 0
        if n:
            count += n
            types += prog.get("featureType") or []
    if types:
        for (kind, _, _), e in lib.items.items():
            if kind == "optionalfeature" and set(e.get("featureType") or []) & set(types) and e.get("source") == (cls or {}).get("source"):
                names.append(e["name"])
    return sorted(set(names)), count, types


def builder_steps(char: dict, lib) -> list[dict]:
    cls = _cls(char, lib)
    level = int(char.get("level") or 1)
    sheet = derive(char, lib) if cls else None
    steps = [
        {"id": "class", "title": "Class", "done": bool(char.get("cls")), "type": "class"},
        {"id": "race", "title": "Race", "done": bool(char.get("race")), "type": "race"},
        {"id": "background", "title": "Background", "done": bool(char.get("background")), "type": "background"},
        {"id": "abilities", "title": "Ability scores", "done": any(v != 10 for v in (char.get("scores") or {}).values()), "methods": list(ABILITY_METHODS)},
    ]
    if cls:
        choose = next((b["choose"] for b in (cls.get("startingProficiencies") or {}).get("skills") or [] if isinstance(b, dict) and "choose" in b), None)
        if choose:
            already = {k for k, v in sheet["skills"].items() if v["proficient"] and k not in (char.get("picks") or {}).get("skills", [])}
            opts = [s for s in choose.get("from") or [] if s in SKILLS and s not in already]
            steps.append({"id": "skills", "title": "Skills", "done": len((char.get("picks") or {}).get("skills") or []) >= choose.get("count", 0),
                          "count": choose.get("count", 0), "options": opts})
        styles, count, _ = _style_options(cls, level, lib)
        if count:
            have = [o["name"] for o in char.get("options") or []]
            steps.append({"id": "style", "title": "Fighting style" if "Fighting Style" in str(cls.get("optionalfeatureProgression")) else "Options",
                          "done": len([h for h in have if h in styles]) >= count, "count": count, "options": styles})
        casting = caster_list(char, lib)
        if casting:  # only classes with magic get a spells step, filtered to their own list
            top = max([int(k) for k in sheet["slots"]] + ([sheet["pact"]["level"]] if sheet.get("pact") else []) + [0])
            steps.append({"id": "spells", "title": "Spells", "done": bool(char.get("spells")), "type": "spell",
                          "list": casting, "max_level": top})
    steps.append({"id": "equipment", "title": "Equipment", "done": bool(char.get("items")) or "start_cp" in char, "type": "baseitem"})
    return steps


def _subclass_level(cls: dict) -> int:
    for ref in cls.get("classFeatures") or []:
        if isinstance(ref, dict) and ref.get("gainSubclassFeature"):
            return _parse_ref(ref)[3]
    return 3


def level_up_plan(char: dict, lib) -> dict:
    cls = _cls(char, lib)
    if not cls:
        raise ValueError("Choose a class first.")
    level = int(char.get("level") or 1)
    if level >= 20:
        raise ValueError("Level 20 is the highest level.")
    to = level + 1
    faces = int((cls.get("hd") or {}).get("faces") or 8)
    gains, choices = [], []
    for ref in cls.get("classFeatures") or []:
        name, _, _, lv, src = _parse_ref(ref)
        if lv == to and src == cls.get("source"):
            gains.append(name)
            if name == "Ability Score Improvement":
                choices.append({"id": "asi_or_feat", "kind": "asi_or_feat", "options": ["asi", "feat"], "count": 2})
    if to >= _subclass_level(cls) and not char.get("subclass"):  # also a converted sheet that never chose one
        subs = sorted({e["name"] for (k, _, _), e in lib.items.items()
                       if k == "subclass" and e.get("className") == cls["name"] and e.get("classSource", "PHB") == cls.get("source")})
        choices.insert(0, {"id": "subclass", "kind": "subclass", "options": subs, "count": 1})
    before = _style_options(cls, level, lib)[1]
    styles, after, _ = _style_options(cls, to, lib)
    if after > before:
        choices.append({"id": "optionalfeature", "kind": "optionalfeature", "options": styles, "count": after - before})
    from .character import derive
    from .levels import changes
    table, bc, ac = changes(char, to, lib)
    casting = caster_list(char, lib)
    if ac and casting:  # new spells: cantrips, spells known or the spellbook, a Warlock's Mystic Arcanum
        top = _top_slot(derive({**char, "level": to}, lib))
        if (ac.get("cantrips") or 0) > (bc.get("cantrips") or 0):
            choices.append({"id": "cantrips", "kind": "cantrips", "count": ac["cantrips"] - (bc.get("cantrips") or 0),
                            "list": casting, "max_level": 0})
        key = {"known": "known", "spellbook": "spellbook"}.get(ac["mode"])
        if key and (ac.get(key) or 0) > (bc.get(key) or 0):
            choices.append({"id": "spells", "kind": "spells", "count": ac[key] - (bc.get(key) or 0), "list": casting,
                            "max_level": top, "spellbook": key == "spellbook"})
        from .levels import arcanum_at
        for spell_level, n in arcanum_at(cls).get(to, {}).items():
            choices.append({"id": "arcanum", "kind": "spells", "count": n, "list": casting,
                            "exact_level": spell_level, "max_level": spell_level})
    return {"to_level": to, "hit_die": f"d{faces}", "hp_average": faces // 2 + 1, "gains": gains, "choices": choices,
            "changes": table, "spell_mode": (ac or {}).get("mode")}


SPELL_KINDS = ("spells", "cantrips")


def _top_slot(sheet: dict) -> int:
    return max([int(k) for k in sheet.get("slots") or {}] + ([int(sheet["pact"]["level"])] if sheet.get("pact") else []) + [0])


def _new_spells(ch: dict, picked, have: set, lib) -> list[dict]:
    """Spells chosen at level-up, checked: real spells, the right level, on the class's list, not already known."""
    from .spell_lists import on_list
    picked = [p for p in (picked if isinstance(picked, list) else [picked]) if isinstance(p, dict) and p.get("name")]
    if len(picked) > ch["count"]:
        raise ValueError(f"This level gives {ch['count']} new {'cantrip' if ch['kind'] == 'cantrips' else 'spell'}"
                         f"{'s' if ch['count'] > 1 else ''}.")
    out = []
    for p in picked:
        e = lib.items.get(("spell", str(p["name"]).lower(), str(p.get("source", "PHB")).upper()))
        if not e:
            raise ValueError(f"{p['name']} is not in the Library.")
        lv = int(e.get("level", 0))
        if ch["kind"] == "cantrips" and lv != 0:
            raise ValueError(f"{e['name']} is not a cantrip.")
        if ch["kind"] == "spells":
            if lv == 0:
                raise ValueError(f"{e['name']} is a cantrip, not a levelled spell.")
            if ch.get("exact_level") and lv != ch["exact_level"]:
                raise ValueError(f"Mystic Arcanum here is a level {ch['exact_level']} spell.")
            if lv > ch["max_level"]:
                raise ValueError(f"{e['name']} is level {lv}; your highest spell slot will be level {ch['max_level']}.")
        if on_list(e["name"], ch["list"], lib) is False:
            raise ValueError(f"{e['name']} is not on the {ch['list']} spell list.")
        if e["name"].lower() in have:
            raise ValueError(f"You already have {e['name']}.")
        have.add(e["name"].lower())
        out.append({"type": "spell", "name": e["name"], "source": e.get("source", "PHB")})
    return out


def apply_level_up(char: dict, answers: dict, lib) -> dict:
    plan = level_up_plan(char, lib)
    cls = _cls(char, lib)
    faces = int((cls.get("hd") or {}).get("faces") or 8)
    hp = answers.get("hp", "average")
    if isinstance(hp, dict):
        roll = int(hp.get("roll", 0))
        if not 1 <= roll <= faces:
            raise ValueError(f"A d{faces} roll is between 1 and {faces}.")
    else:
        roll = faces // 2 + 1
    new = {**char, "picks": {**(char.get("picks") or {})}, "options": list(char.get("options") or []), "feats": list(char.get("feats") or []),
           "spells": list(char.get("spells") or [])}
    have = {str(x.get("name", "")).lower() for x in new["spells"]}
    for ch in plan["choices"]:
        ans = answers.get(ch["id"])
        if ch["kind"] in SPELL_KINDS:  # optional: spells can also be added later from the Library
            new["spells"] += _new_spells(ch, ans or [], have, lib)
            continue
        if not ans:
            raise ValueError(f"Choose your {ch['kind'].replace('_', ' ')} first.")
        if ch["kind"] == "subclass":
            if ans not in ch["options"]:
                raise ValueError(f"{ans} is not a choice here.")
            sc = next(e for (k, _, _), e in lib.items.items() if k == "subclass" and e["name"] == ans and e.get("className") == cls["name"])
            new["subclass"] = {"name": sc["name"], "source": sc["source"]}
        elif ch["kind"] == "asi_or_feat":
            if "asi" in ans:
                inc = {k: int(v) for k, v in ans["asi"].items() if k in ABILS and int(v) > 0}
                if sum(inc.values()) != 2 or any(v > 2 for v in inc.values()):
                    raise ValueError("An Ability Score Improvement is +2 to one score or +1 to two.")
                new["picks"]["asi"] = list(new["picks"].get("asi") or []) + [inc]
            elif "feat" in ans:
                new["feats"].append({"type": "feat", **ans["feat"]})
        elif ch["kind"] == "optionalfeature":
            picked = ans if isinstance(ans, list) else [ans]
            for n in picked[: ch["count"]]:
                if n not in ch["options"]:
                    raise ValueError(f"{n} is not a choice here.")
                new["options"].append({"type": "optionalfeature", "name": n, "source": cls.get("source", "PHB")})
    before = derive(char, lib)
    rolls = list((char.get("hp") or {}).get("rolls") or [])
    rolls += [None] * max(0, plan["to_level"] - 2 - len(rolls))
    rolls = rolls[: plan["to_level"] - 2] + [roll]
    new["level"] = plan["to_level"]
    new["hp"] = {**(char.get("hp") or {}), "rolls": rolls}
    after = derive(new, lib)
    new["hp"]["current"] = min(after["hp_max"], before["hp"] + (after["hp_max"] - before["hp_max"]))
    return new
