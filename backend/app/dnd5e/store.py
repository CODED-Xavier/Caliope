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
    elif op == "slot":  # a spell slot spent (or given back) by hand on the sheet
        from .magic import pact_left, slots_left
        sheet = derive(char, lib)
        lv, delta = str(change.get("level", "")), int(change.get("delta", 1))
        if lv == "pact":
            if delta > 0 and not pact_left(sheet, char):
                raise ValueError("No pact slots left.")
            char["pact_used"] = max(0, int(char.get("pact_used") or 0) + delta)
        else:
            total = {str(k): int(v) for k, v in (sheet.get("slots") or {}).items()}  # the sheet's levels are numbers
            if lv not in total:
                raise ValueError("You have no slots of that level.")
            if delta > 0 and not slots_left(sheet, char).get(lv):
                raise ValueError(f"No level {lv} slots left.")
            used = dict(char.get("slots_used") or {})
            used[lv] = max(0, min(total[lv], int(used.get(lv, 0)) + delta))
            char["slots_used"] = used
    elif op == "prepare":  # a spellbook spell prepared today, or left in the book
        i = int(change.get("index", -1))
        if not 0 <= i < len(char.get("spells") or []):
            raise ValueError("That spell is not on the sheet.")
        char["spells"] = [dict(x) for x in char["spells"]]
        char["spells"][i]["prepared"] = bool(change.get("on"))
    elif op == "start_gear":  # the class's and background's packages, or the class's gold instead
        from .equipment import apply_start
        char = apply_start(char, lib, change.get("choice") or {})
    elif op == "buy":
        from .equipment import buy
        char = buy(char, lib, str(change.get("name", "")), str(change.get("source", "PHB")), int(change.get("qty") or 1))
    elif op == "refund":
        from .equipment import refund
        char = refund(char, int(change.get("index", -1)))
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


POOLS = ("lay on hands", "ki", "monk's focus", "font of magic", "sorcery points")  # spent by points, not one use


def use_feature(char: dict, name: str, lib, rng: random.Random | None = None, amount: int | None = None) -> tuple[dict, str]:
    sheet = derive(char, lib)
    f = next((x for x in sheet["features"] if x["name"].lower() == name.lower()), None)
    if f is None or "uses_max" not in f:
        raise ValueError(f"{name} has no uses to spend.")
    if f["used"] >= f["uses_max"]:
        raise ValueError(f"No uses of {f['name']} left until a {f['per']} rest.")
    left = f["uses_max"] - f["used"]
    if f["name"].lower() in POOLS:  # a pool of points: spend as many as asked
        if f["name"].lower() == "lay on hands":
            missing = max(0, sheet["hp_max"] - sheet["hp"])
            pts = max(1, min(left, int(amount) if amount else missing or 1))
            new_hp = min(sheet["hp_max"], sheet["hp"] + pts)
            char = {**char, "uses": {**(char.get("uses") or {}), f["name"]: f["used"] + pts},
                    "hp": {**(char.get("hp") or {}), "current": new_hp}}
            return char, f"✨ Lay on Hands: +{new_hp - sheet['hp']} HP → {new_hp}/{sheet['hp_max']} ({left - pts}/{f['uses_max']} points left)"
        pts = max(1, min(left, int(amount or 1)))
        char = {**char, "uses": {**(char.get("uses") or {}), f["name"]: f["used"] + pts}}
        return char, f"✨ {f['name']}: {pts} spent ({left - pts}/{f['uses_max']} left)"
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
    from .magic import restore_slots
    return restore_slots(char, when)


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
    state["character5e_sheet"] = {k: sheet[k] for k in ("ac", "attacks", "saves", "skills", "prof", "initiative", "speed", "hp_max", "level",
                                                         "class", "slots_left", "pact_left") if k in sheet}
    state["character5e_sheet"]["martial_arts"] = sheet["class"] == "Monk"  # an Unarmed Strike as a bonus action after attacking
    # the sheet owns the hero's numbers and gear: the Aedo reads these notes and the bag, not an old free-form sheet
    if "notes_before_5e" not in p and p.get("notes"):
        p["notes_before_5e"] = p["notes"]
    p["notes"] = sheet_summary(sheet)
    _sync_bag(state, char, lib)
    if "cp" in char:  # the sheet's money is the game's money (the Bag shows it)
        state["gold"] = int(char["cp"]) // 100
    return sheet


def sheet_summary(sheet: dict) -> str:
    sig = lambda n: f"+{n}" if n >= 0 else str(n)  # noqa: E731
    head = f"{sheet['class']} {sheet['level']}" + (f" ({sheet['subclass']})" if sheet["subclass"] else "")
    parts = [f"{head}. AC {sheet['ac']} ({sheet['ac_how']}). Proficiency {sig(sheet['prof'])}.",
             "Saving throws: " + (", ".join(a.upper() for a in sheet["save_prof"]) or "none") + "."]
    if sheet["attacks"]:
        parts.append("Attacks: " + "; ".join(f"{a['name']} {sig(a['bonus'])}, {a['damage']} {a['dtype']}".strip() for a in sheet["attacks"]) + ".")
    feats = [f["name"] + (f" ({f['uses_max'] - f['used']}/{f['uses_max']} per {f['per']} rest)" if f.get("uses_max") else "") for f in sheet["features"]]
    if feats:
        parts.append("Features: " + ", ".join(feats) + ".")
    if sheet.get("spell_dc"):
        parts.append(f"Spell save DC {sheet['spell_dc']}, spell attack {sig(sheet.get('spell_attack', 0))}.")
    if sheet.get("slots"):
        left = sheet.get("slots_left") or {}
        parts.append("Spell slots left: " + ", ".join(f"level {k}: {left.get(str(k), v)}/{v}" for k, v in sheet["slots"].items()) + ".")
    if sheet.get("pact"):
        parts.append(f"Pact slots left: {sheet.get('pact_left', 0)}/{sheet['pact']['count']} (level {sheet['pact']['level']}).")
    return " ".join(parts)


def _sync_bag(state: dict, char: dict, lib) -> None:
    """Weapons and armour in the bag follow the sheet; everything else in the bag (packs, potions, loot) stays."""
    from .library import item_category
    bag = [dict(i) for i in state.get("inventory") or [] if isinstance(i, dict)]
    on_sheet = {i["name"].lower() for i in char.get("items") or []}

    def gear(name: str) -> bool:
        n = name.lower()
        return any(k == "baseitem" and key == n and item_category(e) in ("weapon", "armor") for (k, key, _), e in lib.items.items())

    bag = [i for i in bag if not (gear(str(i.get("name", ""))) and str(i.get("name", "")).lower() not in on_sheet)]
    have = {str(i.get("name", "")).lower() for i in bag}
    for it in char.get("items") or []:
        if it["name"].lower() not in have:
            bag.append({"name": it["name"], "qty": int(it.get("qty", 1)), "notes": ""})
            have.add(it["name"].lower())
    state["inventory"] = bag


def pull_hp(state: dict, who: str = "") -> None:
    """HP changed by the game (a fight, the Aedo, a rest) goes into the 5e character before the sheet is touched."""
    char = char_of(state, who)
    if not char:
        return
    if not who:
        cur = ((state.get("player") or {}).get("hp") or {}).get("current")
    else:
        cur = ((state.get("party") or {}).get(who) or {}).get("hp")
    if cur is not None:
        char["hp"] = {**(char.get("hp") or {}), "current": max(0, int(cur))}


def char_of(state: dict, who: str = "") -> dict | None:
    """The hero's 5e character (who = "") or a companion's (who = their name)."""
    return state.get("character5e") if not who else (state.get("party5e") or {}).get(who)


def put_char(state: dict, who: str, char: dict, lib) -> dict:
    """Store a 5e character and work its numbers into the game (the player, or the companion's fight sheet)."""
    if not who:
        state["character5e"] = char
        return sync_player(state, lib)
    from . import party5e
    state.setdefault("party5e", {})[who] = char
    return party5e.sync_companion(state, who, lib)


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
