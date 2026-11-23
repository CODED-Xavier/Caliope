"""Starting equipment and the shop.

A class and a background list their starting gear as groups: some items you always get, and choices like
"(a) chain mail or (b) leather armor, a longbow and 20 arrows" (2014) or packages A / B / C (2024, where one package
is just gold). A 2014 class also offers its starting gold instead (5d4 × 10 gp for a Fighter). Some choices are a
kind of item ("a martial weapon"): the player picks which one. Money is kept in copper pieces (`char["cp"]`).
"""
from __future__ import annotations

import re

from .text import strip_tags

PICKS = {  # an "equipmentType" placeholder -> which Library items fit it
    "weaponSimple": lambda e: e.get("weaponCategory") == "simple",
    "weaponMartial": lambda e: e.get("weaponCategory") == "martial",
    "weaponSimpleMelee": lambda e: e.get("weaponCategory") == "simple" and _kind(e) == "M",
    "weaponMartialMelee": lambda e: e.get("weaponCategory") == "martial" and _kind(e) == "M",
    "instrumentMusical": lambda e: _kind(e) == "INS",
    "toolArtisan": lambda e: _kind(e) == "AT",
    "setGaming": lambda e: _kind(e) == "GS",
    "focusSpellcastingArcane": lambda e: e.get("scfType") == "arcane",
    "focusSpellcastingHoly": lambda e: e.get("scfType") == "holy",
    "focusSpellcastingDruidic": lambda e: e.get("scfType") == "druid",
}
PICK_LABELS = {"weaponSimple": "a simple weapon", "weaponMartial": "a martial weapon", "weaponSimpleMelee": "a simple melee weapon",
               "weaponMartialMelee": "a martial melee weapon", "instrumentMusical": "a musical instrument", "toolArtisan": "artisan's tools",
               "setGaming": "a gaming set", "focusSpellcastingArcane": "an arcane focus", "focusSpellcastingHoly": "a holy symbol",
               "focusSpellcastingDruidic": "a druidic focus"}


def _kind(e: dict) -> str:
    return str(e.get("type") or "").split("|")[0]


def _find(lib, ref: str) -> dict | None:
    """'chain mail|phb' -> the Library's base item (or item)."""
    name, _, rest = str(ref).partition("|")
    source = (rest.split("|")[0] or "PHB").upper()
    for kind in ("baseitem", "item"):
        e = lib.items.get((kind, name.lower(), source))
        if e:
            return {**e, "_kind": kind}
    return None


def _edition_items(lib, edition: str) -> list[dict]:
    want = {"XPHB"} if edition == "2024" else {"PHB"}
    return [e for (k, _, src), e in lib.items.items() if k == "baseitem" and src in want]


def _item(lib, x, edition: str) -> dict:
    if isinstance(x, str):
        x = {"item": x}
    if not isinstance(x, dict):
        return {}
    qty = int(x.get("quantity") or 1)
    if "value" in x and not (x.get("item") or x.get("special")):
        cp = int(x["value"])
        return {"label": f"{cp // 100} gp" if cp % 100 == 0 else f"{cp} cp", "cp": cp, "qty": 1}
    if x.get("equipmentType"):
        t = x["equipmentType"]
        fits = PICKS.get(t)
        cands = sorted({(e["name"], e["source"]) for e in _edition_items(lib, edition) if fits and fits(e)})
        label = PICK_LABELS.get(t, t)
        return {"label": f"{qty} × {label}" if qty > 1 else label, "pick": t, "qty": qty,
                "candidates": [{"name": n, "source": s} for n, s in cands]}
    if x.get("special"):
        return {"label": strip_tags(str(x.get("displayName") or x["special"])), "special": True, "qty": qty}
    e = _find(lib, x.get("item", ""))
    name = strip_tags(str(x.get("displayName") or (e or {}).get("name") or str(x.get("item", "")).split("|")[0]))
    out = {"label": f"{qty} × {name}" if qty > 1 else name, "qty": qty}
    if e:
        out.update(name=e["name"], source=e["source"], type=e["_kind"])
    else:
        out.update(name=name, special=True)
    if x.get("containsValue"):
        out["cp"] = int(x["containsValue"])
        out["label"] += f" ({out['cp'] // 100} gp)"
    return out


def _groups(lib, blocks, edition: str) -> list[dict]:
    groups = []
    for i, block in enumerate(blocks or []):
        if not isinstance(block, dict):
            continue
        fixed = [_item(lib, x, edition) for x in block.get("_") or []]
        choices = [{"key": k, "items": [_item(lib, x, edition) for x in block[k]]} for k in sorted(k for k in block if k != "_")]
        for c in choices:
            c["label"] = ", ".join(it["label"] for it in c["items"] if it)
        groups.append({"id": f"g{i}", "fixed": [f for f in fixed if f], "choices": choices})
    return groups


def _gold(text: str) -> dict | None:
    m = re.search(r"(\d+)d(\d+)(?:\s*[×x*]\s*(\d+))?", str(text or ""))  # "{@dice 5d4 × 10|…|Starting Gold}"
    if not m:
        return None
    n, s, times = int(m.group(1)), int(m.group(2)), int(m.group(3) or 1)
    return {"dice": f"{n}d{s}", "times": times, "average": int(n * (s + 1) / 2 * times), "max": n * s * times}


def _entry(lib, kind: str, ref: dict | None) -> dict | None:
    if not ref:
        return None
    return lib.items.get((kind, str(ref.get("name", "")).lower(), str(ref.get("source", "PHB")).upper()))


def starting_options(lib, char: dict) -> dict:
    """The class's and background's starting gear, as groups to choose from, plus the class's gold instead."""
    edition = char.get("edition", "2014")
    out = {}
    cls = _entry(lib, "class", char.get("cls"))
    if cls:
        se = cls.get("startingEquipment") or {}
        out["class"] = {"name": cls["name"], "groups": _groups(lib, se.get("defaultData"), edition), "gold": _gold(se.get("goldAlternative"))}
    bg = _entry(lib, "background", char.get("background"))
    if bg:
        se = bg.get("startingEquipment")
        out["background"] = {"name": bg["name"], "groups": _groups(lib, se if isinstance(se, list) else (se or {}).get("defaultData"), edition)}
    out["coins"] = int(char.get("cp") or 0)
    return out


def _take(groups: list[dict], picks: dict, chosen_items: dict, what: str) -> tuple[list[dict], int]:
    items, cp = [], 0
    for g in groups:
        bundle = list(g["fixed"])
        if g["choices"]:
            key = (picks or {}).get(g["id"]) or g["choices"][0]["key"]
            choice = next((c for c in g["choices"] if c["key"] == key), None)
            if not choice:
                raise ValueError(f"Choose one of the {what}'s options.")
            for n, it in enumerate(choice["items"]):
                if it.get("pick"):
                    ref = (chosen_items or {}).get(f"{g['id']}.{key}.{n}") or ""
                    name, _, source = str(ref).partition("|")
                    cand = next((c for c in it["candidates"] if c["name"].lower() == name.lower() and (not source or c["source"].upper() == source.upper())), None)
                    if not cand:
                        raise ValueError(f"Pick which {PICK_LABELS.get(it['pick'], 'item')} you take.")
                    it = {**it, "name": cand["name"], "source": cand["source"], "type": "baseitem"}
                bundle.append(it)
        for it in bundle:
            cp += int(it.get("cp") or 0) * (1 if "name" in it or it.get("special") else int(it.get("qty") or 1))
            if it.get("name"):
                items.append({"type": it.get("type", "special"), "name": it["name"], **({"source": it["source"]} if it.get("source") else {}),
                              "qty": int(it.get("qty") or 1), "equipped": False, "from": "start"})
    return items, cp


def apply_start(char: dict, lib, choice: dict) -> dict:
    """Your starting gear: the packages you chose (or the class's gold), replacing an earlier choice."""
    opts = starting_options(lib, char)
    items, cp = [], 0
    gold = choice.get("class_gold")
    if "class" in opts:
        if gold not in (None, ""):
            g = opts["class"].get("gold")
            gp = int(gold)
            if not g:
                raise ValueError("This class has no starting gold to take instead; pick a package.")
            if not g["times"] <= gp <= g["max"] or gp % g["times"]:
                raise ValueError(f"Starting gold is {g['dice']} × {g['times']} gp: between {g['times']} and {g['max']}.")
            cp += gp * 100
        else:
            got, money = _take(opts["class"]["groups"], choice.get("class"), choice.get("class_picks"), "class")
            items += got
            cp += money
    if "background" in opts:
        got, money = _take(opts["background"]["groups"], choice.get("background"), choice.get("background_picks"), "background")
        items += got
        cp += money
    kept = [i for i in char.get("items") or [] if i.get("from") != "start"]
    old_start = int(char.get("start_cp") or 0)
    return {**char, "items": kept + items, "start_cp": cp, "cp": max(0, int(char.get("cp") or 0) - old_start + cp)}


def price_cp(lib, name: str, source: str) -> int | None:
    for kind in ("baseitem", "item"):
        e = lib.items.get((kind, str(name).lower(), str(source).upper()))
        if e:
            return int(e["value"]) if e.get("value") else None
    return None


def buy(char: dict, lib, name: str, source: str, qty: int = 1) -> dict:
    e = next((lib.items.get((k, str(name).lower(), str(source).upper())) for k in ("baseitem", "item")
              if lib.items.get((k, str(name).lower(), str(source).upper()))), None)
    if not e:
        raise ValueError(f"{name} ({source}) is not in the library.")
    price = price_cp(lib, name, source)
    if price is None:
        raise ValueError(f"{e['name']} has no price in the Library.")
    qty = max(1, int(qty or 1))
    have = int(char.get("cp") or 0)
    if have < price * qty:
        raise ValueError(f"Not enough money: {e['name']} costs {money_text(price * qty)}, you have {money_text(have)}.")
    kind = "baseitem" if lib.items.get(("baseitem", e["name"].lower(), e["source"].upper())) else "item"
    item = {"type": kind, "name": e["name"], "source": e["source"], "qty": qty, "equipped": False, "bought": price * qty}
    return {**char, "items": list(char.get("items") or []) + [item], "cp": have - price * qty}


def refund(char: dict, index: int) -> dict:
    items = list(char.get("items") or [])
    if not 0 <= index < len(items) or not items[index].get("bought"):
        raise ValueError("Only things you bought can be returned.")
    back = int(items.pop(index)["bought"])
    return {**char, "items": items, "cp": int(char.get("cp") or 0) + back}


def money_text(cp: int) -> str:
    gp, sp, c = cp // 100, (cp % 100) // 10, cp % 10
    return " ".join(x for x in (f"{gp} gp" if gp else "", f"{sp} sp" if sp else "", f"{c} cp" if c else "") if x) or "0 gp"
