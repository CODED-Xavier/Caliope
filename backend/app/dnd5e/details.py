"""What a class, race or background gives, for the ▸ arrow on the builder's cards: a class's 20 levels, a race's
traits, a background's skills, equipment and feature. Read straight from the Library entry."""
from __future__ import annotations

from .character import _parse_ref, _slots, prof_bonus
from .text import render, strip_tags

SIZES = {"T": "Tiny", "S": "Small", "M": "Medium", "L": "Large", "H": "Huge", "G": "Gargantuan"}
ABBR = {"str": "STR", "dex": "DEX", "con": "CON", "int": "INT", "wis": "WIS", "cha": "CHA"}


def _clean(x) -> str:
    return (strip_tags(x) if "{@" in x else x.split("|")[0]) if isinstance(x, str) else strip_tags(str(x.get("proficiency") or x.get("full") or "")) if isinstance(x, dict) else ""


def _short(entries, limit: int = 320) -> str:
    text = render(entries or "")
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "…"


def _choose_text(block) -> str:
    if isinstance(block, dict) and "choose" in block:
        ch = block["choose"]
        return f"Choose {ch.get('count', 1)}: " + ", ".join(s.title() for s in ch.get("from") or [])
    if isinstance(block, dict):
        return ", ".join(k.title() for k, v in block.items() if v is True)
    return ""


def _class(lib, e: dict) -> dict:
    from .build import _subclass_level
    sp = e.get("startingProficiencies") or {}
    src = e.get("source", "PHB")
    by_level: dict[int, list[str]] = {}
    for ref in e.get("classFeatures") or []:
        name, _, _, lv, fsrc = _parse_ref(ref)
        if fsrc == src:
            by_level.setdefault(lv, []).append(name)
    levels = []
    for lv in range(1, 21):
        sl = _slots(e, lv)
        row = {"level": lv, "prof": prof_bonus(lv), "features": by_level.get(lv, [])}
        if sl["slots"]:
            row["slots"] = {str(k): v for k, v in sl["slots"].items()}
        if sl.get("pact"):
            row["pact"] = sl["pact"]
        levels.append(row)
    subs = sorted({x["name"] for (k, _, _), x in lib.items.items()
                   if k == "subclass" and x.get("className") == e["name"] and x.get("classSource", "PHB") == src})
    return {
        "kind": "class", "name": e["name"], "source": src,
        "hit_die": f"d{(e.get('hd') or {}).get('faces', 8)}",
        "saves": [ABBR.get(a, a.upper()) for a in e.get("proficiency") or []],
        "armor": [_clean(a) for a in sp.get("armor") or [] if _clean(a)],
        "weapons": [_clean(w) for w in sp.get("weapons") or [] if _clean(w)],
        "skills": "; ".join(t for t in (_choose_text(b) for b in sp.get("skills") or []) if t),
        "spellcasting": ABBR.get(str(e.get("spellcastingAbility") or ""), "") or None,
        "subclass_title": e.get("subclassTitle") or "Subclass",
        "subclass_level": _subclass_level(e),
        "subclasses": subs,
        "levels": levels,
    }


def _race(lib, e: dict) -> dict:
    bonuses = []
    for a in e.get("ability") or []:
        for k, v in a.items():
            if k in ABBR:
                bonuses.append(f"{ABBR[k]} {'+' if int(v) >= 0 else ''}{v}")
            elif k == "choose" and isinstance(v, dict):
                bonuses.append(f"+{v.get('amount', 1)} to {v.get('count', 1)} of your choice")
    if not bonuses and e.get("name") == "Human" and e.get("source") == "PHB":
        abilities = "+1 to every score"
    else:
        abilities = ", ".join(bonuses)
    speed = e.get("speed", 30)
    speed = speed.get("walk", 30) if isinstance(speed, dict) else speed
    traits = [{"name": strip_tags(x["name"]), "text": _short(x.get("entries"))}
              for x in e.get("entries") or [] if isinstance(x, dict) and x.get("name")]
    subs = sorted({x["name"] for (k, _, _), x in lib.items.items()
                   if k == "subrace" and x.get("raceName") == e["name"] and x.get("raceSource", "PHB") == e.get("source")})
    return {"kind": "race", "name": e["name"], "source": e.get("source"), "speed": speed, "abilities": abilities,
            "size": ", ".join(SIZES.get(s, s) for s in e.get("size") or []), "darkvision": e.get("darkvision"),
            "traits": traits, "subraces": subs}


def _equipment(blocks) -> list[str]:
    def one(x):
        if isinstance(x, str):
            return strip_tags(x.split("|")[0])
        if isinstance(x, dict):
            name = x.get("displayName") or x.get("special") or (x.get("item") or "").split("|")[0] or x.get("equipmentType", "")
            name = strip_tags(str(name))
            if x.get("quantity", 1) > 1:
                name = f"{x['quantity']} × {name}"
            if x.get("containsValue"):
                name += f" ({x['containsValue'] // 100} gp)"
            return name
        return ""
    out = []
    for block in blocks or []:
        if not isinstance(block, dict):
            continue
        if "_" in block:
            out += [t for t in (one(x) for x in block["_"]) if t]
        opts = [", ".join(t for t in (one(x) for x in block[k]) if t) for k in sorted(block) if k != "_"]
        if opts:
            out.append(" or ".join(o for o in opts if o))
    return out


def _background(lib, e: dict) -> dict:
    feature = None
    for x in e.get("entries") or []:
        if isinstance(x, dict) and str(x.get("name", "")).startswith("Feature:"):
            feature = {"name": strip_tags(x["name"].split(":", 1)[1].strip()), "text": _short(x.get("entries"), 500)}
    skills = []
    for b in e.get("skillProficiencies") or []:
        skills += [k.title() for k, v in b.items() if v is True] if isinstance(b, dict) else []
    tools = [t for t in (_choose_text(b) for b in e.get("toolProficiencies") or []) if t]
    langs = []
    for b in e.get("languageProficiencies") or []:
        if isinstance(b, dict):
            for k, v in b.items():
                langs.append(f"{v} of your choice" if k == "anyStandard" else k.title())
    return {"kind": "background", "name": e["name"], "source": e.get("source"), "skills": skills, "tools": tools,
            "languages": langs, "equipment": _equipment(e.get("startingEquipment")), "feature": feature}


def describe(lib, kind: str, name: str, source: str) -> dict:
    e = lib.items.get((kind, str(name).lower(), str(source).upper()))
    if not e:
        raise ValueError(f"{name} ({source}) is not in the library.")
    if kind == "class":
        return _class(lib, e)
    if kind == "race":
        return _race(lib, e)
    if kind == "background":
        return _background(lib, e)
    raise ValueError("Only classes, races and backgrounds have details.")
