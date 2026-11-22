"""Companions and solo play.

A card can carry up to 3 companions: characters (card NPCs marked `companion`) with a small fight sheet. In a game
started with **Play with companions** they travel with the player: the Aedo voices them, and Calíope plays them in
fights (healers heal, the others attack). In a **solo** game they are left out, and an adventure's scene enemies are
scaled to one hero (published adventures are written for 4).

Game state: `state["party_mode"]` ("solo" | "companions") and `state["party"]` = {name: {"hp", "max_hp"}}: their HP
lasts between fights, like the player's.
"""
from __future__ import annotations

import re

from .util import as_int, extract_json, truncate

MAX_COMPANIONS = 3
ROLES = ("fighter", "archer", "healer", "rogue")
# 5e level 1 numbers: hp, ac, attack bonus, damage, range (squares), speed
ROLE_DEFAULTS = {
    "fighter": {"hp": 12, "ac": 16, "attack_bonus": 5, "damage": "1d8+3", "range": 1, "speed": 6},
    "archer": {"hp": 10, "ac": 14, "attack_bonus": 5, "damage": "1d8+3", "range": 16, "speed": 6},
    "healer": {"hp": 10, "ac": 16, "attack_bonus": 4, "damage": "1d6+2", "range": 1, "speed": 5},
    "rogue": {"hp": 9, "ac": 14, "attack_bonus": 5, "damage": "1d6+3", "range": 1, "speed": 6},
}
_DICE = re.compile(r"^\d{0,2}d\d{1,3}([+-]\d{1,2})?$|^\d{1,2}$")


def _dice(value, default: str) -> str:
    v = str(value or "").replace(" ", "").lower()
    return v if _DICE.match(v) else default


def normalize_sheet(raw) -> dict:
    """A companion's fight sheet, with the role's defaults for anything missing."""
    raw = raw if isinstance(raw, dict) else {}
    role = str(raw.get("role") or "").lower().strip()
    role = role if role in ROLES else "fighter"
    d = ROLE_DEFAULTS[role]
    out = {
        "class": truncate(str(raw.get("class") or "").strip(), 40),
        "role": role,
        "hp": max(1, min(300, as_int(raw.get("hp", d["hp"]), d["hp"]))),
        "ac": max(5, min(30, as_int(raw.get("ac", d["ac"]), d["ac"]))),
        "attack_bonus": max(-2, min(15, as_int(raw.get("attack_bonus", d["attack_bonus"]), d["attack_bonus"]))),
        "damage": _dice(raw.get("damage"), d["damage"]),
        "range": max(1, min(30, as_int(raw.get("range", d["range"]), d["range"]))),
        "speed": max(1, min(12, as_int(raw.get("speed", d["speed"]), d["speed"]))),
        "init_bonus": max(-3, min(10, as_int(raw.get("init_bonus", 2), 2))),
        "heal": "",
        "heals": 0,
    }
    if role == "healer":
        out["heal"] = _dice(raw.get("heal"), "1d8+3")
        out["heals"] = max(0, min(9, as_int(raw.get("heals", 2), 2)))
    return out


def companions(scenario: dict) -> list[dict]:
    """The card's companions (at most 3), each with a normalized sheet."""
    return [n for n in (scenario or {}).get("npcs") or [] if n.get("companion")][:MAX_COMPANIONS]


def apply_companion_edits(npcs: list[dict], edits: list | None) -> list[dict]:
    """The start screen's "Set up your companions": name, background, looks, personality and pictures with moods,
    laid over the card's companions (matched by their card name, `of`). Other characters stay as they are."""
    from .appearance import normalize_appearance
    from .portraits import normalize_portraits
    out = [dict(n) for n in npcs or []]
    for e in (edits if isinstance(edits, list) else [])[:MAX_COMPANIONS]:
        if not isinstance(e, dict):
            continue
        n = next((x for x in out if x.get("companion") and x.get("name") == str(e.get("of") or "")), None)
        if not n:
            continue
        name = " ".join(str(e.get("name") or "").split())[:60]
        if name:
            n["name"] = name
        for key, cap in (("description", 2000), ("personality", 600), ("speech_style", 300)):
            if key in e:
                n[key] = str(e.get(key) or "").strip()[:cap]
        if "appearance" in e:
            n["appearance"] = normalize_appearance(e.get("appearance"))
        if "portraits" in e:
            n["portraits"] = normalize_portraits(e.get("portraits"))
    return out


def start_party(state: dict, scenario: dict, mode: str) -> None:
    """A new game: with companions, everyone starts at full HP; solo leaves them out."""
    comps = companions(scenario)
    mode = "companions" if mode == "companions" and comps else "solo"
    state["party_mode"] = mode
    state["party"] = {c["name"]: {"hp": c["sheet"]["hp"], "max_hp": c["sheet"]["hp"]} for c in comps} if mode == "companions" else {}


def normalize_party(raw) -> dict:
    out = {}
    for name, v in list((raw if isinstance(raw, dict) else {}).items())[:MAX_COMPANIONS]:
        if isinstance(v, dict):
            mx = max(1, as_int(v.get("max_hp", 1), 1))
            out[truncate(str(name), 60)] = {"hp": max(0, min(mx, as_int(v.get("hp", mx), mx))), "max_hp": mx}
    return out


def party_size(state: dict) -> int:
    """The player plus the companions still standing (1 in a solo game)."""
    if state.get("party_mode") != "companions":
        return 1
    return 1 + sum(1 for v in (state.get("party") or {}).values() if v.get("hp", 0) > 0)


def scale_enemies(enemies: list[dict], size: int) -> list[dict]:
    """Published adventures are written for 4 heroes: each group's count × size ÷ 4, rounded, at least 1."""
    out = []
    for e in enemies:
        e = dict(e)
        n = max(1, as_int(e.get("count", 1), 1))
        scaled = max(1, int(n * max(1, size) / 4 + 0.5))
        if scaled != n and size < 4:
            e["count"], e["scaled_for"] = scaled, size
        out.append(e)
    return out


def scaling_on(state: dict) -> bool:
    """Only games started with the solo / companions choice are scaled (older games play as they did)."""
    return state.get("party_mode") in ("solo", "companions")


def allies(state: dict, scenario: dict) -> list[dict]:
    """The companions still standing, as allies for the combat engine (their current HP from the party)."""
    if state.get("party_mode") != "companions":
        return []
    out = []
    for c in companions(scenario):
        cur = (state.get("party") or {}).get(c["name"])
        if not cur or cur["hp"] <= 0:
            continue
        sh = {**c["sheet"], **{k: v for k, v in ((state.get("party5e_sheet") or {}).get(c["name"]) or {}).items()
                               if k in ("ac", "attack_bonus", "damage", "range", "speed", "init_bonus", "weapon")}}
        out.append({"name": c["name"], "hp": cur["max_hp"], "current_hp": cur["hp"], "ac": sh["ac"],
                    "attack_bonus": sh["attack_bonus"], "damage": sh["damage"], "range": sh["range"], "speed": sh["speed"],
                    "init_bonus": sh["init_bonus"], "role": sh["role"], "heal": sh["heal"], "heals": sh["heals"], "companion": True,
                    "weapon": sh.get("weapon", "")})
    return out


def rest(state: dict, when: str) -> list[str]:
    """A long rest heals the companions fully; a short rest gives back half their max HP (rounded up)."""
    if when not in ("short_rest", "long_rest") or state.get("party_mode") != "companions":
        return []
    out = []
    for name, v in (state.get("party") or {}).items():
        if v["hp"] >= v["max_hp"]:
            continue
        v["hp"] = v["max_hp"] if when == "long_rest" else min(v["max_hp"], v["hp"] + (v["max_hp"] + 1) // 2)
        out.append(f"{name} {v['hp']}/{v['max_hp']} HP")
    return out


COMPANION_RULE = ("They travel with the player. Voice them and let them speak and act on their own initiative and react to "
                  "the player, but never speak, think or decide for the player, and don't let them crowd every reply. "
                  "In fights, their actions come from the ⚔️ block only.")


def prompt_section(state: dict, npcs: list[dict], scenario: dict) -> str:
    """The Aedo's note on the companions (stable: their HP is in the game state lines instead)."""
    if state.get("party_mode") != "companions":
        return ""
    by_name = {n["name"]: n for n in npcs}
    lines = []
    for c in companions(scenario):
        n = by_name.get(c["name"], c)
        sh = c["sheet"]
        bits = [f"{sh['class'] or sh['role'].title()} ({sh['role']})"]
        if n.get("personality"):
            bits.append(truncate(n["personality"], 220))
        if n.get("speech_style"):
            bits.append("speaks: " + truncate(n["speech_style"], 120))
        lines.append(f"- {c['name']}: " + "; ".join(bits))
    return "## Your companions\n" + "\n".join(lines) + "\n" + COMPANION_RULE if lines else ""


def state_line(state: dict) -> str:
    if state.get("party_mode") != "companions" or not state.get("party"):
        return ""
    return "Companions: " + ", ".join(f"{k} {v['hp']}/{v['max_hp']} HP" + (" (down)" if v["hp"] <= 0 else "")
                                       for k, v in state["party"].items()) + "."


DRAFT_SCHEMA = {"type": "object", "properties": {"companions": {"type": "array", "items": {"type": "object", "properties": {
    "name": {"type": "string"}, "class": {"type": "string"}, "role": {"type": "string", "enum": list(ROLES)},
    "personality": {"type": "string"}, "speech_style": {"type": "string"}, "description": {"type": "string"},
    "hp": {"type": "integer"}, "ac": {"type": "integer"}, "attack_bonus": {"type": "integer"}, "damage": {"type": "string"}},
    "required": ["name", "class", "role", "personality", "speech_style", "description"]}}}, "required": ["companions"]}

DRAFT_PROMPT = """Write 3 companions who could travel with the player in this story. They are NOT characters from the story's
own cast: new people who fit its world and tone, each with a clear personality, a way of speaking and a look.
Give them different roles (one healer at most) and level 1 numbers (5e: HP 8-13, AC 13-17, attack +4 or +5).
Story: {name}
{about}
Existing characters (don't reuse them): {cast}"""


def parse_draft(raw: str) -> list[dict]:
    """The AI's companions as card characters: at most 3, with names, marked as companions, sheets normalized."""
    data = extract_json(raw or "")
    items = data.get("companions") if isinstance(data, dict) else None
    out = []
    for c in items if isinstance(items, list) else []:
        if not isinstance(c, dict) or not str(c.get("name", "")).strip():
            continue
        out.append({"name": truncate(str(c["name"]).strip(), 60), "companion": True,
                    "personality": truncate(str(c.get("personality") or ""), 600),
                    "speech_style": truncate(str(c.get("speech_style") or ""), 300),
                    "description": truncate(str(c.get("description") or ""), 600),
                    "sheet": normalize_sheet({k: c.get(k) for k in ("class", "role", "hp", "ac", "attack_bonus", "damage") if c.get(k) not in (None, "")})})
        if len(out) >= MAX_COMPANIONS:
            break
    return out


async def draft(llm, scenario: dict) -> list[dict]:
    about = truncate(" ".join(str(scenario.get(k) or "") for k in ("description", "world", "tone")), 1500)
    cast = ", ".join(n["name"] for n in scenario.get("npcs") or [] if not n.get("companion"))[:600] or "none"
    raw = await llm.chat([{"role": "user", "content": DRAFT_PROMPT.format(name=scenario.get("name", ""), about=about, cast=cast)}],
                         json_schema=DRAFT_SCHEMA, max_tokens=1100, temperature=0.8)
    return parse_draft(raw)
