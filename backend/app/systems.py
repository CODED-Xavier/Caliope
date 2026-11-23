"""A card's own sheet, kept by the app (Black Sheep: Pilot Level, XP, Credits, Tier, Integrity and a mech loadout).

The card's systems (`scenario["systems"]`):
- stats: named numbers, choices or texts with ranges and starting values;
- levels: an XP stat that raises a level stat at given totals;
- loadout: slots filled from a catalog of parts, each with a point cost, weight, modifiers and a level gate; a point
  budget set by a tier stat; net modifiers; speed from the number of parts of one weight; stats derived from the
  modifiers (Integrity = 20 + 2 x Endurance).

The game keeps `state["systems"] = {"values": {...}, "loadout": {slot: part name}}`. The app does the arithmetic
and refuses what the rules don't allow; the Aedo only sees the result, and the tracker reports changes
(`system_changes`) that the app checks and applies.
"""
from __future__ import annotations

import re

from .util import as_int, truncate

KINDS = ("number", "choice", "text")
WEIGHTS = ("Light", "Medium", "Heavy")
RANGES = ("short", "medium", "long")
PRICES = ("Cheap", "Moderate", "Expensive", "Rare")
MAX_ITEMS, MAX_STATS, MAX_SLOTS = 200, 30, 16


def _s(v, n=60) -> str:
    return truncate(" ".join(str(v or "").split()), n)


def _norm_item(i: dict) -> dict | None:
    if not isinstance(i, dict) or not _s(i.get("name")):
        return None
    mods = {_s(k, 24): max(-20, min(20, as_int(v))) for k, v in (i.get("mods") or {}).items() if _s(k) and as_int(v)} \
        if isinstance(i.get("mods"), dict) else {}
    return {"name": _s(i["name"], 80), "kind": _s(i.get("kind"), 30).lower() or "other", "cost": max(0, min(99, as_int(i.get("cost")))),
            "weight": _s(i.get("weight"), 12), "range": _s(i.get("range"), 12), "mods": mods,
            "level": max(0, min(99, as_int(i.get("level")))), "effect": _s(i.get("effect"), 240), "source": _s(i.get("source"), 60),
            "price": _s(i.get("price"), 20), "start": bool(i.get("start"))}


def normalize(raw) -> dict:
    """Make a card's systems safe ({} when the card has none)."""
    if not isinstance(raw, dict):
        return {}
    out: dict = {}
    stats = []
    for s in (raw.get("stats") if isinstance(raw.get("stats"), list) else [])[:MAX_STATS]:
        if not isinstance(s, dict) or not _s(s.get("key")):
            continue
        kind = s.get("kind") if s.get("kind") in KINDS else "number"
        stat = {"key": _s(s["key"], 30), "kind": kind, "note": _s(s.get("note"), 160)}
        if kind == "number":
            stat |= {"min": as_int(s.get("min"), 0) if s.get("min") not in (None, "") else None,
                     "max": as_int(s.get("max")) if s.get("max") not in (None, "") else None, "start": as_int(s.get("start"))}
            by = s.get("start_by")  # the start depends on a choice: {"stat": "Origin", "values": {"High noble": 500}}
            if isinstance(by, dict) and _s(by.get("stat")) and isinstance(by.get("values"), dict):
                stat["start_by"] = {"stat": _s(by["stat"], 30),
                                    "values": {_s(k, 30): as_int(v) for k, v in list(by["values"].items())[:12] if _s(k)}}
        elif kind == "choice":
            opts = [_s(o, 30) for o in s.get("options") or [] if _s(o)][:12]
            stat |= {"options": opts, "start": _s(s.get("start"), 30) if _s(s.get("start"), 30) in opts else (opts[0] if opts else "")}
        else:
            stat["start"] = _s(s.get("start"), 80)
        stats.append(stat)
    if stats:
        out["stats"] = stats
    lv = raw.get("levels")
    if isinstance(lv, dict) and _s(lv.get("xp")) and _s(lv.get("level")) and isinstance(lv.get("at"), list):
        out["levels"] = {"xp": _s(lv["xp"], 30), "level": _s(lv["level"], 30), "at": sorted(max(0, as_int(x)) for x in lv["at"][:30])}
    lo = raw.get("loadout")
    if isinstance(lo, dict) and isinstance(lo.get("slots"), list) and lo["slots"]:
        catalog = [x for x in (_norm_item(i) for i in (lo.get("catalog") or [])[:MAX_ITEMS]) if x]
        slots = []
        for sl in lo["slots"][:MAX_SLOTS]:
            if isinstance(sl, dict) and _s(sl.get("key")):
                slots.append({"key": _s(sl["key"], 30), "accepts": [_s(a, 30).lower() for a in sl.get("accepts") or [] if _s(a)][:6],
                              "start": _s(sl.get("start"), 80)})
        speed = lo.get("speed") if isinstance(lo.get("speed"), dict) else {}
        out["loadout"] = {
            "name": _s(lo.get("name"), 40), "points": _s(lo.get("points"), 30) or "Points", "tier": _s(lo.get("tier"), 30),
            "budgets": {_s(k, 30): max(0, as_int(v)) for k, v in (lo.get("budgets") or {}).items()} if isinstance(lo.get("budgets"), dict) else {},
            "mods": [_s(m, 24) for m in lo.get("mods") or [] if _s(m)][:8], "level_stat": _s(lo.get("level_stat"), 30),
            "slots": slots, "catalog": catalog,
            "speed": {"weight": _s(speed.get("weight"), 12), "bands": [[as_int(b[0]), _s(b[1], 20)] for b in speed.get("bands") or []
                                                                     if isinstance(b, list) and len(b) == 2][:6]} if speed else {},
            "derived": [{"stat": _s(d.get("stat"), 30), "base": as_int(d.get("base")),
                         "per": {_s(k, 24): as_int(v) for k, v in (d.get("per") or {}).items()}}
                        for d in lo.get("derived") or [] if isinstance(d, dict) and _s(d.get("stat"))][:4],
        }
    if out.get("loadout"):  # buying parts: tier words -> amounts of the money stat
        sh = raw.get("shop") if isinstance(raw.get("shop"), dict) else {}
        prices = sh.get("prices") if isinstance(sh.get("prices"), dict) else {}
        out["shop"] = {"currency": _s(sh.get("currency"), 30) or next((x["key"] for x in stats if re.search(r"credit|gold|coin|money|crown", x["key"], re.I)), ""),
                       "prices": {_s(k, 20): max(0, as_int(v)) for k, v in (prices or DEFAULT_PRICES).items() if _s(k)}}
    bd = raw.get("board")
    if isinstance(bd, dict) and isinstance(bd.get("grades"), list) and bd["grades"]:
        out["board"] = {"size": max(1, min(6, as_int(bd.get("size"), 3))), "pay_stat": _s(bd.get("pay_stat"), 30),
                        "level_stat": _s(bd.get("level_stat"), 30), "refresh_days": max(1, min(30, as_int(bd.get("refresh_days"), 7))),
                        "grades": [{"grade": _s(g.get("grade"), 8), "pay": max(0, as_int(g.get("pay"))),
                                    "min_level": max(0, as_int(g.get("min_level"))), "text": _s(g.get("text"), 160)}
                                   for g in bd["grades"][:8] if isinstance(g, dict) and _s(g.get("grade"))]}
    rk = raw.get("ranking")
    if isinstance(rk, dict) and isinstance(rk.get("names"), list) and rk["names"]:
        out["ranking"] = {"size": max(2, min(20, as_int(rk.get("size"), len(rk["names"])))), "names": [_s(n, 40) for n in rk["names"] if _s(n)][:20],
                          "protect_days": max(0, min(30, as_int(rk.get("protect_days"), 3))),
                          "step_only": bool(rk.get("step_only"))}  # challenge only the rank directly above (unranked: the last)
    sp = raw.get("steps")
    if isinstance(sp, dict) and isinstance(sp.get("labels"), list) and sp["labels"]:
        out["steps"] = {"name": _s(sp.get("name"), 30) or "Steps", "labels": [_s(x, 30) for x in sp["labels"] if _s(x)][:10],
                        "people": [_s(x, 40) for x in sp.get("people") or [] if _s(x)][:20], "per_day": max(1, as_int(sp.get("per_day"), 1))}
    return out


DEFAULT_PRICES = {"Cheap": 50, "Moderate": 150, "Expensive": 400, "Rare": 1000}
NOT_SOLD = re.compile(r"wager|reward|mission|legendar|bount|quest|apost|recompens", re.I)


# ------------------------------------------------------------------ the catalog reader
_HEADER = re.compile(r"\b([A-Z][A-Z/&' -]{1,40}[A-Z])\b(?:\s*\([^)]*\))?\s*[.:]")
_ITEM = re.compile(r"(?P<name>[A-Z][^.:;\[\]]{1,70}?(?:\([^)]*\))?)\s*:\s*(?P<cost>\d+)\s*(?:PF|FP|points?)\b(?P<rest>[^\[\]]*?)\[(?P<br>[^\]]*)\]")


def _kind_from_header(h: str) -> str:
    h = h.lower().split("/")[0].strip()
    h = re.sub(r"\b(frames?|slot|parts?)\b", "", h).strip()
    return re.sub(r"\bweapons\b", "weapon", h)


def _guess_kind(name: str, rng: str) -> str:
    low = name.lower()
    for kind, words in (("arm", r"\barm\b"), ("legs", r"\blegs\b"), ("thrusters", r"thrusters?|boosters?"),
                        ("armor", r"plating|armou?r|skirts|dampers"), ("cockpit", r"cockpit|harness|rig\b|cage|controls"),
                        ("back weapon", r"pods|launcher|mortar|autocannons?")):
        if re.search(words, low):
            return kind
    return "arm weapon" if rng else "other"


def parse_catalog(text: str, mods: list[str]) -> list[dict]:
    """Parts written as 'Name: 3 PF, Heavy, short; Melee +1, Handling -1 [Lv4, city market, Expensive].', grouped
    under headers like 'ARM WEAPONS' or 'LEGS.' (Black Sheep's format; other cards in the same style work too)."""
    text = text or ""
    headers = [(m.start(), m.group(1)) for m in _HEADER.finditer(text) if len(re.sub(r"[^A-Z]", "", m.group(1))) >= 3]
    mod_re = re.compile(r"\b(" + "|".join(re.escape(m) for m in mods) + r")\s*([+\-−–]\s*\d+)") if mods else None
    out, seen = [], set()
    for m in _ITEM.finditer(text):
        name = m["name"].strip()
        if name.lower() in seen:
            continue
        head = next((h for pos, h in reversed(headers) if pos < m.start()), "")
        kind = _kind_from_header(head) if head else ""
        weight = rng = ""
        found_mods: dict = {}
        effect = []
        rest_text = m["rest"]
        if mods:  # "+1 to Handling, Melee, Artillery and Endurance" -> "Handling +1, Melee +1, ..."
            alt = "|".join(re.escape(x) for x in mods)
            rest_text = re.sub(rf"([+\-−–]\s*\d+)\s+to\s+((?:{alt})(?:\s*,\s*(?:{alt}))*(?:\s*,?\s*and\s+(?:{alt}))?)",
                               lambda g: ", ".join(f"{n} {g.group(1)}" for n in re.findall(alt, g.group(2))), rest_text)
        for tok in re.split(r"[,;]", rest_text):
            tok = tok.strip()
            if not tok:
                continue
            if tok in WEIGHTS and not weight:
                weight = tok
                continue
            if tok in RANGES and not rng:
                rng = tok
                continue
            hits = list(mod_re.finditer(tok)) if mod_re else []
            for h in hits:
                found_mods[h.group(1)] = found_mods.get(h.group(1), 0) + as_int(re.sub(r"[−–\s]", lambda c: "-" if c.group() in "−–" else "", h.group(2)))
            rest = mod_re.sub("", tok).strip(" ,;") if hits else tok
            if rest and rest.lower() != "no modifier":
                effect.append(rest)
        level, start, source, price = 0, False, "", ""
        for b in (x.strip() for x in m["br"].split(",")):
            if re.fullmatch(r"(?:Lv|Level)\s*(\d+)\+?", b, re.I):
                level = as_int(re.sub(r"\D", "", b))
            elif b.lower().startswith("starting"):
                start = True
            elif b in PRICES:
                price = b
            elif b and not source:
                source = b
        if not kind or kind in ("masterwork", "legendary"):
            kind = _guess_kind(name, rng)
        seen.add(name.lower())
        out.append(_norm_item({"name": name, "kind": kind, "cost": int(m["cost"]), "weight": weight, "range": rng, "mods": found_mods,
                               "level": level, "effect": "; ".join(effect), "source": source, "price": price, "start": start}))
    return out


# ------------------------------------------------------------------ the sheet in play
def _stat(sys: dict, key: str) -> dict | None:
    low = (key or "").strip().lower()
    return next((s for s in sys.get("stats") or [] if s["key"].lower() == low), None)


def _item(sys: dict, name: str) -> dict | None:
    low = (name or "").strip().lower()
    return next((i for i in (sys.get("loadout") or {}).get("catalog") or [] if i["name"].lower() == low), None)


def start_state(sys: dict) -> dict:
    values = {s["key"]: s.get("start", "") for s in sys.get("stats") or []}
    lo = sys.get("loadout") or {}
    loadout = {sl["key"]: (_item(sys, sl["start"]) or {}).get("name", "") for sl in lo.get("slots") or []}
    st: dict = {"values": values, "loadout": loadout}
    if lo:  # parts you own: the starting ones (and what is installed)
        st["owned"] = sorted({i["name"] for i in lo.get("catalog") or [] if i["start"]} | {v for v in loadout.values() if v})
    if sys.get("board"):
        st["board"] = {"jobs": [], "log": [], "posted": None}
    if sys.get("ranking"):
        st["ranking"] = {"order": list(sys["ranking"]["names"][: sys["ranking"]["size"]]), "player": None, "protected": {}, "duels": []}
    if sys.get("steps"):
        st["steps"] = {p: 0 for p in sys["steps"]["people"]}
        st["step_days"] = {}
    return st


def compute(sys: dict, st: dict) -> dict:
    """The numbers the app works out: points used and budget, net modifiers, heavy parts and speed, stat maximums."""
    lo = sys.get("loadout") or {}
    values = (st or {}).get("values") or {}
    items = {slot: _item(sys, name) for slot, name in ((st or {}).get("loadout") or {}).items()}
    parts = [i for i in items.values() if i]
    used = sum(i["cost"] for i in parts)
    budgets = lo.get("budgets") or {}
    budget = budgets.get(str(values.get(lo.get("tier"), ""))) if budgets else None
    if budget is None and budgets:
        budget = min(budgets.values())
    mods = {m: sum(i["mods"].get(m, 0) for i in parts) for m in lo.get("mods") or []}
    sp = lo.get("speed") or {}
    heavy = sum(1 for i in parts if sp.get("weight") and i["weight"] == sp["weight"])
    speed = next((label for n, label in sp.get("bands") or [] if heavy <= n), "") if sp else ""
    mx = {s["key"]: s.get("max") for s in sys.get("stats") or [] if s["kind"] == "number" and s.get("max") is not None}
    for d in lo.get("derived") or []:
        mx[d["stat"]] = d["base"] + sum(mods.get(k, 0) * v for k, v in d["per"].items())
    return {"used": used, "budget": budget, "mods": mods, "heavy": heavy, "speed": speed, "max": mx,
            "items": {slot: i for slot, i in items.items()}}


def set_part(sys: dict, st: dict, slot: str, name: str) -> str:
    """Install a part in a slot. '' when done, else why not (wrong slot, level gate, not enough points)."""
    lo = sys.get("loadout") or {}
    sl = next((x for x in lo.get("slots") or [] if x["key"].lower() == (slot or "").lower()), None)
    if not sl:
        return f"There is no {slot} slot."
    item = _item(sys, name)
    if not item:
        return f"{name} is not in the catalog."
    if sl["accepts"] and item["kind"] not in sl["accepts"]:
        return f"{sl['key']} takes {' or '.join(sl['accepts'])} parts, not {item['kind']}."
    level = as_int((st.get("values") or {}).get(lo.get("level_stat") or ""), 0)
    if item["level"] and not item["start"] and lo.get("level_stat") and level < item["level"]:
        return f"{item['name']} needs Level {item['level']} ({lo['level_stat']} {level} now)."
    if "owned" in st and item["name"] not in st["owned"] and not item["start"]:
        return f"Not owned yet: {item['name']}. Buy it or earn it first."
    before = compute(sys, st)
    old = before["items"].get(sl["key"])
    used = before["used"] - (old["cost"] if old else 0) + item["cost"]
    if before["budget"] is not None and used > before["budget"]:
        return f"Not enough {lo.get('points') or 'points'}: {used} of {before['budget']}."
    st.setdefault("loadout", {})[sl["key"]] = item["name"]
    return ""


def _set_value(sys: dict, st: dict, stat: dict, value, maxes: dict):
    values = st.setdefault("values", {})
    if stat["kind"] == "number":
        v = as_int(value, as_int(values.get(stat["key"])))
        if stat.get("min") is not None:
            v = max(stat["min"], v)
        top = maxes.get(stat["key"])
        if top is not None:
            v = min(top, v)
        values[stat["key"]] = v
    elif stat["kind"] == "choice":
        if str(value) in stat.get("options", []):
            values[stat["key"]] = str(value)
    else:
        values[stat["key"]] = _s(value, 80)


def _level_up(sys: dict, st: dict) -> list[str]:
    lv = sys.get("levels")
    if not lv:
        return []
    values = st["values"]
    xp = as_int(values.get(lv["xp"]))
    new = max(1, sum(1 for t in lv["at"] if xp >= t))
    stat = _stat(sys, lv["level"])
    if stat and stat.get("max") is not None:
        new = min(stat["max"], new)
    if new > as_int(values.get(lv["level"]), 1):
        values[lv["level"]] = new
        return [f"{lv['level']} {new} (level up!)"]
    return []


def apply_changes(sys: dict, st: dict, changes: list) -> list[str]:
    """Changes the tracker reported ({stat, delta} or {stat, value}), checked against the sheet's rules."""
    lines = []
    for ch in changes if isinstance(changes, list) else []:
        if not isinstance(ch, dict):
            continue
        if ch.get("buy") or ch.get("gain"):  # a part bought in the story, or earned (wager, reward)
            name = str(ch.get("buy") or ch.get("gain"))
            item = _item(sys, name)
            if item and item["name"] not in st.get("owned", []):
                err = buy(sys, st, name, story=True) if ch.get("buy") else gain(sys, st, name)
                if not err:
                    lines.append(f"{'Bought' if ch.get('buy') else 'Got'}: {item['name']}")
            continue
        if ch.get("step"):
            if not step(sys, st, str(ch["step"]), as_int(ch.get("delta"), 1), day=as_int(ch.get("day"), 0)):
                lines.append(f"{sys['steps']['name']}: {ch['step']} {st['steps'].get(_person(sys, str(ch['step'])) or '', 0)}")
            continue
        stat = _stat(sys, str(ch.get("stat", "")))
        if not stat:
            continue
        before = st.setdefault("values", {}).get(stat["key"])
        maxes = compute(sys, st)["max"]
        if stat["kind"] == "number" and ch.get("delta") not in (None, ""):
            _set_value(sys, st, stat, as_int(before) + as_int(ch["delta"]), maxes)
        elif ch.get("value") not in (None, ""):
            _set_value(sys, st, stat, ch["value"], maxes)
        after = st["values"].get(stat["key"])
        if after != before:
            lines.append(f"{stat['key']} {as_int(after) - as_int(before):+d} → {after}" if stat["kind"] == "number"
                         else f"{stat['key']}: {after}")
            lines += _level_up(sys, st)
    return lines


def merge_state(sys: dict, raw) -> dict:
    """The start screen's sheet laid over the card's start: values checked, parts installed only when they fit."""
    st = start_state(sys)
    if not isinstance(raw, dict):
        return st
    maxes = compute(sys, st)["max"]
    for k, v in (raw.get("values") or {}).items() if isinstance(raw.get("values"), dict) else []:
        stat = _stat(sys, k)
        if stat:
            _set_value(sys, st, stat, v, maxes)
    for stat in sys.get("stats") or []:  # "Origin: High noble" sets the starting gold, unless the player typed another
        by = stat.get("start_by")
        if by and str(raw.get("values", {}).get(stat["key"], stat.get("start")) if isinstance(raw.get("values"), dict) else stat.get("start")) == str(stat.get("start")):
            pick = str(st["values"].get(by["stat"], ""))
            if pick in by["values"]:
                _set_value(sys, st, stat, by["values"][pick], maxes)
    _level_up(sys, st)
    for slot, name in (raw.get("loadout") or {}).items() if isinstance(raw.get("loadout"), dict) else []:
        if name and name != st["loadout"].get(slot) and _item(sys, name):
            st.setdefault("owned", [])
            added = name not in st["owned"]
            if added:
                st["owned"].append(_item(sys, name)["name"])  # chosen when making the character: yours
            if set_part(sys, st, slot, name) and added:
                st["owned"].remove(_item(sys, name)["name"])
    return st


def normalize_state(sys: dict, raw) -> dict:
    """A saved game's sheet: the card's stats and slots, nothing else."""
    if not sys:
        return {}
    base = start_state(sys)
    raw = raw if isinstance(raw, dict) else {}
    values = {**base["values"], **{k: v for k, v in (raw.get("values") or {}).items() if _stat(sys, k)}}
    loadout = {**base["loadout"], **{k: v for k, v in (raw.get("loadout") or {}).items() if k in base["loadout"] and (not v or _item(sys, v))}}
    out = {"values": values, "loadout": loadout}
    for key in ("owned", "board", "ranking", "steps", "step_days"):
        if key in base:
            out[key] = raw.get(key) if isinstance(raw.get(key), type(base[key])) else base[key]
    return out


def prompt_text(sys: dict, st: dict, player_name: str = "") -> str:
    """The sheet for the Aedo, written by the app every turn."""
    if not sys or not st:
        return ""
    got = compute(sys, st)
    values = st.get("values") or {}
    parts = []
    for s in sys.get("stats") or []:
        v = values.get(s["key"], "")
        top = got["max"].get(s["key"])
        parts.append(f"{s['key']} {v}/{top}" if top is not None and s["kind"] == "number" else f"{s['key']} {v}")
    lines = [" | ".join(parts)]
    lo = sys.get("loadout")
    if lo:
        slots = "; ".join(f"{slot}: {name or 'empty'}" for slot, name in (st.get("loadout") or {}).items())
        budget = f"{got['used']}/{got['budget']}" if got["budget"] is not None else str(got["used"])
        net = ", ".join(f"{k} {v:+d}" for k, v in got["mods"].items())
        speed = f" · Speed {got['speed']} ({got['heavy']} {lo['speed'].get('weight', '')})" if got["speed"] else ""
        lines.append(f"{lo.get('name') or 'Loadout'} ({lo['points']} {budget}): {slots}.")
        if net or speed:
            lines.append(f"NET: {net}{speed}")
    jobs = [j for j in (st.get("board") or {}).get("jobs", []) if j["status"] == "active"]
    if jobs:
        lines.append("Active missions: " + "; ".join(f"{j['title']} (Grade {j['grade']}, pays {j['pay']}{', extra: ' + j['extra'] if j.get('extra') else ''})" for j in jobs))
    open_jobs = [j for j in (st.get("board") or {}).get("jobs", []) if j["status"] == "open"]
    if open_jobs:
        lines.append("Bounty board: " + "; ".join(f"{j['title']} (Grade {j['grade']}, {j['pay']})" for j in open_jobs))
    rk = st.get("ranking")
    if rk:
        order = [player_name or "the player" if n == YOU else n for n in rk["order"]]
        top = ", ".join(f"{i + 1}. {n}" for i, n in enumerate(order[: sys["ranking"]["size"]]))
        lines.append(f"Ranking: {top}" + ("" if rk.get("player") else f" · {player_name or 'the player'}: unranked"))
    if st.get("steps"):
        labels = sys["steps"]["labels"]
        lines.append(f"{sys['steps']['name']}: " + " · ".join(
            f"{p} {n}" + (f" ({labels[n - 1]})" if 0 < n <= len(labels) else "") for p, n in st["steps"].items()))
    return "\n".join(lines)


SYSTEM_RULES = ("The app keeps the player's sheet (stats, loadout, points, net modifiers): use these numbers, never invent or "
                "recalculate them; report changes (XP, damage, money) for the app to apply.")


def tracker_line(sys: dict, st: dict) -> str:
    if not sys or not sys.get("stats"):
        return ""
    keys = ", ".join(s["key"] for s in sys["stats"])
    return ("- system_changes: the player's sheet stats that changed in these exchanges, as {stat, delta} for numbers "
            f"(XP gained, damage taken, money) or {{stat, value}} for others. Stats: {keys}. Also {{buy: part}} when the "
            "player buys a catalog part, {gain: part} when they win or are given one, and {step: name, delta: 1} when "
            "someone on the card's ladder clearly moves up. Follow the card's rules; leave empty when nothing changed.")


# ------------------------------------------------------------------ the card reader (🔍 Find systems)
READER_SCHEMA = {
    "type": "object",
    "properties": {
        "stats": {"type": "array", "items": {"type": "object", "properties": {
            "key": {"type": "string"}, "kind": {"type": "string", "enum": list(KINDS)}, "min": {"type": "integer"},
            "max": {"type": "integer"}, "start": {"type": "string"}, "options": {"type": "array", "items": {"type": "string"}}},
            "required": ["key", "kind", "start"]}},
        "xp_stat": {"type": "string"}, "level_stat": {"type": "string"},
        "xp_for_levels": {"type": "array", "items": {"type": "integer"}},
        "loadout_name": {"type": "string"}, "points_name": {"type": "string"}, "tier_stat": {"type": "string"},
        "budgets": {"type": "array", "items": {"type": "object", "properties": {"tier": {"type": "string"}, "points": {"type": "integer"}},
                                                "required": ["tier", "points"]}},
        "modifiers": {"type": "array", "items": {"type": "string"}},
        "slots": {"type": "array", "items": {"type": "object", "properties": {
            "slot": {"type": "string"}, "accepts": {"type": "array", "items": {"type": "string"}}, "start_part": {"type": "string"}},
            "required": ["slot", "accepts", "start_part"]}},
        "speed_weight": {"type": "string"},
        "speed_bands": {"type": "array", "items": {"type": "object", "properties": {"up_to": {"type": "integer"}, "speed": {"type": "string"}},
                                                    "required": ["up_to", "speed"]}},
    },
    "required": ["stats", "xp_stat", "level_stat", "xp_for_levels", "loadout_name", "points_name", "tier_stat", "budgets",
                 "modifiers", "slots", "speed_weight", "speed_bands"],
}

READER_PROMPT = """You read a role-play card's rules and copy the player's character sheet into JSON. Copy ONLY numbers and
names the text states; use "" , 0 or [] for anything it doesn't state (never invent).
- stats: the player's sheet stats (level, XP, money, hit points, tier...) with their range and starting value. kind is
  "number", "choice" (with options) or "text".
- xp_stat, level_stat, xp_for_levels: the XP stat, the level stat, and the total XP needed for each level from level 1 up
  (level 1 = 0).
- If the player has equipment slots with point costs (a mech, a ship, a loadout): loadout_name, points_name (what the
  points are called), tier_stat and budgets (points allowed per tier), modifiers (the stats the parts add to, like
  Handling or Melee), slots (each slot, which kinds of parts it takes, written like the catalog's section names in
  lower case, and its starting part's exact name), speed_weight and speed_bands (speed from the number of parts of
  that weight) when stated.
Part kinds already found in the catalog: {kinds}

THE CARD:
{text}"""


def _card_text(card: dict) -> str:
    book = card.get("lorebook") or card.get("character_book") or []
    entries = book.get("entries") if isinstance(book, dict) else book
    parts = [str(card.get("description") or ""), str(card.get("scenario") or "")]
    parts += [str(e.get("content") or "") for e in entries or [] if isinstance(e, dict)]
    return "\n\n".join(p for p in parts if p.strip())


async def read_card(llm, card: dict) -> dict:
    """Propose a card's sheet: the catalog parsed from its text, the rest read by the AI. The player reviews it."""
    text = _card_text(card)
    rough = parse_catalog(text, [])
    kinds = sorted({i["kind"] for i in rough})
    from .util import extract_json
    raw = await llm.chat([{"role": "user", "content": READER_PROMPT.format(kinds=", ".join(kinds) or "none",
                                                                          text=truncate(text, 14000))}],
                         json_schema=READER_SCHEMA, max_tokens=1500, temperature=0.1)
    data = extract_json(raw or "") or {}
    mods = [_s(m, 24) for m in data.get("modifiers") or [] if _s(m)]
    catalog = parse_catalog(text, mods)
    out: dict = {"stats": [{**s, "start": as_int(s.get("start")) if s.get("kind") == "number" else s.get("start")}
                           for s in data.get("stats") or [] if isinstance(s, dict)]}
    at = [as_int(x) for x in data.get("xp_for_levels") or []]
    if data.get("xp_stat") and data.get("level_stat") and len(at) > 1:
        out["levels"] = {"xp": data["xp_stat"], "level": data["level_stat"], "at": at}
    if data.get("slots") and catalog:
        out["loadout"] = {
            "name": data.get("loadout_name", ""), "points": data.get("points_name", ""), "tier": data.get("tier_stat", ""),
            "budgets": {b["tier"]: b["points"] for b in data.get("budgets") or [] if isinstance(b, dict) and b.get("tier")},
            "mods": mods, "level_stat": data.get("level_stat", ""),
            "slots": [{"key": sl.get("slot"), "accepts": sl.get("accepts") or [], "start": sl.get("start_part", "")}
                      for sl in data["slots"] if isinstance(sl, dict)],
            "catalog": catalog,
            "speed": {"weight": data.get("speed_weight", ""),
                      "bands": [[b["up_to"], b["speed"]] for b in data.get("speed_bands") or [] if isinstance(b, dict)]}
            if data.get("speed_weight") else {},
        }
    return normalize(out)


# ------------------------------------------------------------------ v2.36: shop, mission board, ranking, steps
def price_of(sys: dict, item: dict | None) -> int | None:
    if not item:
        return None
    prices = (sys.get("shop") or {}).get("prices") or {}
    return prices.get(item.get("price")) if item.get("price") else None


def gain(sys: dict, st: dict, name: str) -> str:
    """A part earned (a wager, a mission reward): owned, no money."""
    item = _item(sys, name)
    if not item:
        return f"{name} is not in the catalog."
    st.setdefault("owned", [])
    if item["name"] not in st["owned"]:
        st["owned"].append(item["name"])
    return ""


def buy(sys: dict, st: dict, name: str, story: bool = False) -> str:
    """Buy a part with the money stat: sold parts only (not wagers or rewards), level gate, enough money."""
    item = _item(sys, name)
    if not item:
        return f"{name} is not in the catalog."
    if item["name"] in st.get("owned", []):
        return f"You already own {item['name']}."
    if item["source"] and NOT_SOLD.search(item["source"]) and not re.search(r"market|shop|workshop|lise", item["source"], re.I):
        return f"{item['name']} is not sold: it comes from {item['source']}."
    lo = sys.get("loadout") or {}
    level = as_int((st.get("values") or {}).get(lo.get("level_stat") or ""), 0)
    if item["level"] and lo.get("level_stat") and level < item["level"]:
        return f"{item['name']} needs Level {item['level']} ({lo['level_stat']} {level} now)."
    cost = price_of(sys, item)
    cur = (sys.get("shop") or {}).get("currency")
    if cost and cur:
        have = as_int((st.get("values") or {}).get(cur))
        if have < cost:
            return f"Not enough {cur}: {item['name']} costs {cost}, you have {have}."
        st["values"][cur] = have - cost
    return gain(sys, st, item["name"])


def _day_week(sys: dict, day: int) -> int:
    return (max(1, day) - 1) // (sys.get("board") or {}).get("refresh_days", 7)


def board_stale(sys: dict, st: dict, day: int) -> bool:
    """New jobs are due: never posted, or a new week has started (the board refreshes every Monday)."""
    b = st.get("board") or {}
    return b.get("posted") is None or _day_week(sys, day) != _day_week(sys, b["posted"])


def board_post(sys: dict, st: dict, jobs: list, day: int) -> list[dict]:
    """Jobs drafted by the Aedo, laid on the board with the card's pay for their grade."""
    grades = {g["grade"].upper(): g for g in (sys.get("board") or {}).get("grades") or []}
    b = st.setdefault("board", {"jobs": [], "log": [], "posted": None})
    kept = [j for j in b["jobs"] if j["status"] == "active"]
    new = []
    for j in jobs if isinstance(jobs, list) else []:
        g = grades.get(str((j or {}).get("grade", "")).upper().strip())
        if not g or not _s(j.get("title")):
            continue
        new.append({"id": f"j{day}-{len(new) + 1}", "title": _s(j["title"], 80), "grade": g["grade"], "pay": g["pay"],
                    "min_level": g["min_level"], "extra": _s(j.get("extra"), 80), "status": "open"})
        if len(new) >= sys["board"]["size"]:
            break
    b["jobs"] = kept + new
    b["posted"] = day
    return new


def board_act(sys: dict, st: dict, job_id: str, action: str, day: int) -> str:
    """accept / done / fail a job; done pays its grade's pay; done and fail go to the mission log."""
    b = st.get("board") or {}
    job = next((j for j in b.get("jobs", []) if j["id"] == job_id), None)
    if not job:
        return "That job is not on the board."
    level_stat = sys["board"].get("level_stat")
    if action == "accept":
        level = as_int(st["values"].get(level_stat), 0) if level_stat else 99
        if job["min_level"] and level < job["min_level"]:
            return f"Grade {job['grade']} needs Level {job['min_level']}."
        job["status"] = "active"
        return ""
    if action in ("done", "fail") and job["status"] == "active":
        b["jobs"] = [j for j in b["jobs"] if j["id"] != job_id]
        reward = ""
        if action == "done" and sys["board"].get("pay_stat"):
            apply_changes(sys, st, [{"stat": sys["board"]["pay_stat"], "delta": job["pay"]}])
            reward = f"{job['pay']} {sys['board']['pay_stat']}" + (f" + {job['extra']}" if job.get("extra") else "")
        b.setdefault("log", []).insert(0, f"Day {day} · Grade {job['grade']} · {job['title']} · {'done' if action == 'done' else 'failed'}"
                                          + (f" · {reward}" if reward else ""))
        b["log"] = b["log"][:8]
        return ""
    return "Accept the job first."


YOU = "@you"


def duel(sys: dict, st: dict, opponent: str, won: bool, day: int) -> str:
    """A ranked duel: beating someone above you (or anyone, when unranked) takes their place; everyone from there
    moves down one and the last falls off. Whoever you just fought is protected from a rematch for the card's
    protection days. The last 3 duels are kept."""
    rk = st.get("ranking")
    if not rk:
        return "This card keeps no ranking."
    order = list(rk["order"])
    name = next((n for n in order if n.lower() == (opponent or "").strip().lower()), _s(opponent, 40))
    until = rk["protected"].get(name)
    if until and day <= until:
        return f"{name} is protected until day {until}."
    mine = order.index(YOU) if YOU in order else None
    if sys["ranking"].get("step_only") and name in order:
        want = (mine - 1) if mine is not None else len(order) - 1
        if mine == 0 or order.index(name) != want:
            return f"You can only challenge {order[want] if want >= 0 else 'nobody above you'} (the rank directly above you)."
    if won and name in order:
        their = order.index(name)
        if mine is None or their < mine:
            if mine is not None:
                order.remove(YOU)
            order.insert(their, YOU)
            order = order[: sys["ranking"]["size"]]
    rk["order"] = order
    rk["player"] = order.index(YOU) + 1 if YOU in order else None
    rk["protected"][name] = day + sys["ranking"]["protect_days"]
    rk["duels"] = ([{"day": day, "opponent": name, "won": bool(won)}] + rk.get("duels", []))[:3]
    return ""


def _person(sys: dict, name: str) -> str | None:
    low = (name or "").strip().lower()
    return next((p for p in (sys.get("steps") or {}).get("people", []) if p.lower() == low or p.lower().split()[0] == low), None)


def step(sys: dict, st: dict, person: str, delta: int, day: int) -> str:
    """Move someone on the step ladder (romance): at most the card's steps per day, within the ladder."""
    sp = sys.get("steps")
    if not sp:
        return "This card keeps no ladder."
    who = _person(sys, person)
    if not who:
        return f"{person} is not on the {sp['name']} ladder."
    days = st.setdefault("step_days", {})
    if delta > 0 and day and days.get(who) == day:
        return f"{who} already moved a step today."
    st.setdefault("steps", {})[who] = max(0, min(len(sp["labels"]), as_int(st["steps"].get(who)) + delta))
    if delta > 0 and day:
        days[who] = day
    return ""


BOARD_SCHEMA = {"type": "object", "properties": {"jobs": {"type": "array", "items": {"type": "object", "properties": {
    "title": {"type": "string"}, "grade": {"type": "string"}, "extra": {"type": "string"}}, "required": ["title", "grade", "extra"]}}},
    "required": ["jobs"]}


def board_messages(sys: dict, st: dict, card_text: str) -> list[dict]:
    """Ask the Aedo for this week's jobs: titles and extras only; the app sets pay and level gates from the grades."""
    b = sys["board"]
    level = as_int(st["values"].get(b.get("level_stat") or ""), 0) if b.get("level_stat") else 0
    grades = "\n".join(f"- Grade {g['grade']}: {g['text']} (pays {g['pay']}, Level {g['min_level']}+)" for g in b["grades"])
    return [{"role": "user", "content": (
        f"Write this week's bounty board for the story below: exactly {b['size']} jobs, each with a short title (what the job "
        f"is, where), its grade, and one extra reward (salvage, a part, a contact, information or prestige; not the same kind "
        f"twice). The player is Level {level}: at least one job must be a grade they can take. Grades:\n{grades}\n\n"
        f"The card's rules about missions (use their names and places; never invent noble houses or named characters):\n"
        f"{truncate(card_text, 6000)}")}]
