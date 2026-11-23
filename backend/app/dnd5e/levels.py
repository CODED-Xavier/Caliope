"""What each level gives: the class table's own columns (Rages, Sneak Attack, Ki Points…), spells known and prepared,
spell slots, and the resources that grow (Lay on Hands, Channel Divinity…). Read from the Library's class entry.

How many spells a class has, by level:
- known (Bard, Ranger, Sorcerer, Warlock in 2014 rules): spellsKnownProgression; the sheet's spells are what you know.
- prepared (Cleric, Druid, Paladin): level (or half level) + the spellcasting modifier, at least 1, or the 2024
  table's preparedSpellsProgression; the sheet's spells are what you have prepared today.
- spellbook (Wizard): 6 spells at level 1 and 2 more each level; you prepare level + INT modifier of them (spells
  marked `"prepared": false` stay in the book only).
"""
from __future__ import annotations

import re

from .text import strip_tags

# a feature with uses that the class table already shows as a column
COVERED = {"Rage": "Rages", "Ki": "Ki Points", "Monk's Focus": "Focus Points", "Font of Magic": "Sorcery Points"}
OWN_COLUMNS = {"cantrips known", "spells known", "spell slots", "slot level", "prepared spells"}


def _cell(v) -> str:
    if isinstance(v, bool):
        return "✓" if v else "–"
    if isinstance(v, (int, float)):
        return str(int(v)) if float(v).is_integer() else str(v)
    if isinstance(v, str):
        return strip_tags(v) if "{@" in v else v
    if isinstance(v, dict):
        kind = v.get("type")
        if kind == "dice":
            return "+".join(f"{d.get('number', 1)}d{d.get('faces', 6)}" for d in v.get("toRoll") or []) or "–"
        if kind == "bonus":
            return f"+{v.get('value', 0)}"
        if kind == "bonusSpeed":
            return f"+{v['value']} ft" if v.get("value") else "–"
        if "value" in v:
            return _cell(v["value"])
    return "–"


def table_columns(cls: dict | None) -> list[dict]:
    """The class table's columns besides slots and spell counts: [{label, values: 20 strings}]."""
    out = []
    groups = (cls or {}).get("classTableGroups")
    for group in groups if isinstance(groups, list) else []:  # homebrew files can hold anything: skip what isn't a table
        if not isinstance(group, dict) or "spell slots" in str(group.get("title") or "").lower():
            continue
        labels = [strip_tags(x) if isinstance(x, str) else str(x) for x in group.get("colLabels") or [] if isinstance(group.get("colLabels"), list)]
        rows = group.get("rows") or group.get("rowsSpellProgression") or []
        rows = rows if isinstance(rows, list) else []
        for i, label in enumerate(labels):
            if label.lower() in OWN_COLUMNS:
                continue
            values = [_cell(r[i]) if isinstance(r, list) and i < len(r) else "–" for r in rows[:20]]
            out.append({"label": label, "values": values + ["–"] * (20 - len(values))})
    return out


def _formula(text: str, level: int, mods: dict) -> int:
    """5e.tools' "<$level$> / 2 + <$cha_mod$>": whole numbers with + - * / and brackets only (division rounds down)."""
    import ast
    expr = str(text).replace("<$level$>", str(level))
    expr = re.sub(r"<\$(\w+)_mod\$>", lambda m: f"({int(mods.get(m.group(1), 0))})", expr)
    if len(expr) > 80 or not re.fullmatch(r"[\d\s+\-*/()]+", expr) or "**" in expr:
        return 0
    ops = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b,
           ast.Div: lambda a, b: a // b, ast.FloorDiv: lambda a, b: a // b}

    def calc(n):
        if isinstance(n, ast.Expression):
            return calc(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, int):
            return n.value
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            return -calc(n.operand) if isinstance(n.op, ast.USub) else calc(n.operand)
        if isinstance(n, ast.BinOp) and type(n.op) in ops:
            return ops[type(n.op)](calc(n.left), calc(n.right))
        raise ValueError("not arithmetic")

    try:
        return int(calc(ast.parse(expr, mode="eval")))
    except (SyntaxError, ZeroDivisionError, ValueError, RecursionError):
        return 0


def counts(char: dict, cls: dict | None, sub: dict | None, level: int, mods: dict, has_magic: bool, lib) -> dict | None:
    """Cantrips, spells known / prepared / in the spellbook for this level, and what the sheet has."""
    src = cls if cls and (cls.get("casterProgression") or cls.get("cantripProgression")) else sub
    if not src or not (src.get("casterProgression") or src.get("cantripProgression") or src.get("spellsKnownProgression")):
        return None
    i = level - 1

    def at(key):
        v = src.get(key)
        return _int(v[i]) if isinstance(v, list) and len(v) > i else None

    known = at("spellsKnownProgression")
    prepared = _formula(src["preparedSpells"], level, mods) if src.get("preparedSpells") else at("preparedSpellsProgression")
    fixed = src.get("spellsKnownProgressionFixed")
    book = sum(_int(x) or 0 for x in fixed[:level]) if isinstance(fixed, list) else None
    if prepared is not None:
        prepared = max(1, prepared) if has_magic else 0
    if known is not None and not has_magic:
        known = 0
    mode = "spellbook" if book is not None else "known" if known is not None else "prepared" if prepared is not None else None
    if mode is None:
        return None
    have = {"cantrips": 0, "spells": 0, "prepared": 0}
    for sp in char.get("spells") or []:
        e = lib.items.get(("spell", str(sp.get("name", "")).lower(), str(sp.get("source", "PHB")).upper()))
        lv = int((e or {}).get("level", 1))
        if lv == 0:
            have["cantrips"] += 1
        else:
            have["spells"] += 1
            have["prepared"] += sp.get("prepared") is not False
    return {"mode": mode, "cantrips": at("cantripProgression") or 0, "known": known if mode == "known" else None,
            "prepared": prepared if mode != "known" else None, "spellbook": book,
            "have_cantrips": have["cantrips"], "have_spells": have["spells"], "have_prepared": have["prepared"],
            "arcanum": arcanum_at(src)}


def arcanum_at(src: dict) -> dict[int, dict[int, int]]:
    """A Warlock's Mystic Arcanum: {class level: {spell level: how many}} (bad entries in a homebrew file are skipped)."""
    raw = src.get("spellsKnownProgressionFixedByLevel")
    out: dict[int, dict[int, int]] = {}
    for k, v in raw.items() if isinstance(raw, dict) else []:
        if _int(k) and isinstance(v, dict):
            got = {_int(a): _int(b) for a, b in v.items() if _int(a) and _int(b)}
            if got:
                out[_int(k)] = got
    return out


def _int(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def warnings(c: dict | None, level: int, class_name: str) -> list[str]:
    if not c:
        return []
    out = []
    who = f"a level {level} {class_name}"
    if c["cantrips"] and c["have_cantrips"] > c["cantrips"]:
        out.append(f"You know {c['have_cantrips']} cantrips; {who} knows {c['cantrips']}.")
    if c["mode"] == "known" and c["have_spells"] > (c["known"] or 0):
        out.append(f"You know {c['have_spells']} spells; {who} knows {c['known']}.")
    if c["mode"] == "prepared" and c["have_spells"] > (c["prepared"] or 0):
        out.append(f"You have {c['have_spells']} spells prepared; {who} prepares {c['prepared']}.")
    if c["mode"] == "spellbook" and c["have_prepared"] > (c["prepared"] or 0):
        out.append(f"You have {c['have_prepared']} spells prepared; {who} prepares {c['prepared']}.")
    return out


def spell_counts(char: dict, lib) -> dict | None:
    from .character import derive
    return derive(char, lib).get("spell_counts")


def progression(char: dict, lib) -> dict:
    """The 20 levels for this character's class: features, proficiency, slots, the class's columns, spells and uses."""
    from .build import _cls
    from .character import derive
    cls = _cls(char, lib)
    if not cls:
        raise ValueError("Choose a class first.")
    cols = table_columns(cls)
    rows = []
    for lv in range(1, 21):
        sh = derive({**char, "level": lv}, lib)
        c = sh.get("spell_counts") or {}
        row = {"level": lv, "prof": sh["prof"], "features": [f["name"] for f in sh["features"] if f.get("level") == lv],
               "columns": [col["values"][lv - 1] for col in cols],
               "uses": {f["name"]: f["uses_max"] for f in sh["features"] if f.get("uses_max") and f["name"] not in COVERED}}
        if sh.get("slots"):
            row["slots"] = {str(k): v for k, v in sh["slots"].items()}
        if sh.get("pact"):
            row["pact"] = sh["pact"]
        for key in ("cantrips", "known", "prepared", "spellbook"):
            if c.get(key):
                row[key] = c[key]
        rows.append(row)
    return {"class": cls["name"], "columns": [c["label"] for c in cols], "levels": rows, "current": int(char.get("level") or 1)}


def changes(char: dict, to: int, lib) -> tuple[list[dict], dict, dict]:
    """What changes from this level to `to` (only what really changes), and both sheets' spell counts."""
    from .build import _cls
    from .character import derive
    cls = _cls(char, lib)
    level = int(char.get("level") or 1)
    before, after = derive(char, lib), derive({**char, "level": to}, lib)
    out: list[dict] = []
    sig = lambda n: f"+{n}" if n >= 0 else str(n)  # noqa: E731

    def add(label, b, a):
        if str(b) != str(a):
            out.append({"label": label, "before": str(b), "after": str(a)})

    add("Proficiency bonus", sig(before["prof"]), sig(after["prof"]))
    add("Hit points (with the average)", before["hp_max"], after["hp_max"])
    bs = {str(k): v for k, v in (before.get("slots") or {}).items()}
    as_ = {str(k): v for k, v in (after.get("slots") or {}).items()}
    for lv in sorted(set(bs) | set(as_), key=int):
        add(f"Level {lv} slots", bs.get(lv, 0), as_.get(lv, 0))
    pact = lambda s: f"{s['pact']['count']} × level {s['pact']['level']}" if s.get("pact") else "–"  # noqa: E731
    add("Pact slots", pact(before), pact(after))
    for col in table_columns(cls):
        add(col["label"], col["values"][level - 1], col["values"][to - 1])
    bu = {f["name"]: f["uses_max"] for f in before["features"] if f.get("uses_max")}
    au = {f["name"]: f["uses_max"] for f in after["features"] if f.get("uses_max")}
    for name in list(dict.fromkeys([*bu, *au])):
        if name not in COVERED:
            add(name, bu.get(name, 0), au.get(name, 0))
    bc, ac = before.get("spell_counts") or {}, after.get("spell_counts") or {}
    if ac:
        add("Cantrips known", bc.get("cantrips") or 0, ac.get("cantrips") or 0)
        if ac["mode"] == "known":
            add("Spells known", bc.get("known") or 0, ac.get("known") or 0)
        if ac["mode"] == "spellbook":
            add("Spells in your spellbook", bc.get("spellbook") or 0, ac.get("spellbook") or 0)
        if ac["mode"] in ("prepared", "spellbook"):
            add("Prepared spells", bc.get("prepared") or 0, ac.get("prepared") or 0)
    return out, bc, ac
