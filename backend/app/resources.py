"""Resources (Mana, Aura, Stamina, Ki...) and the abilities that spend them, kept by the app.

A card defines its resources and the player's abilities. The app keeps the numbers: using an ability spends the cost
(and is refused when there is not enough), rests and new days refill, enemy casters spend from their own pool in
fights. The GM only narrates; it always sees the current pools, so it can show a drained character as drained.

Regeneration per resource (a number, or -1 for "all of it"):
    round       every round of a fight
    short_rest  an hour or more of rest
    long_rest   a night's sleep (8 hours or more)
    day         each new day on the calendar
"""
from __future__ import annotations

import re
import uuid

from .dice import DiceError, DiceRoller
from .util import as_int, truncate

ABILITY_KINDS = ("attack", "heal", "effect")
REGEN_KEYS = ("round", "short_rest", "long_rest", "day")
MARK = "✨"  # ✨ starts a message that reports an ability the app resolved
MAX_RESOURCES, MAX_ABILITIES = 6, 24


class ResourceError(ValueError):
    pass


def _dice(expr: str) -> str:
    expr = re.sub(r"\s+", "", str(expr or "")).lower()
    if not expr:
        return ""
    try:
        DiceRoller().roll(expr)
        return expr
    except DiceError:
        return ""


def normalize_resources(raw) -> list[dict]:
    out = []
    for r in raw if isinstance(raw, list) else []:
        if not isinstance(r, dict) or not str(r.get("name", "")).strip():
            continue
        regen_raw = r.get("regen") if isinstance(r.get("regen"), dict) else {}
        regen = {k: max(-1, min(999, as_int(regen_raw.get(k, 0)))) for k in REGEN_KEYS}
        color = str(r.get("color") or "")
        out.append({"name": truncate(str(r["name"]).strip(), 24), "max": max(1, min(999, as_int(r.get("max", 10), 10))),
                    "regen": regen, "color": color if re.fullmatch(r"#[0-9a-fA-F]{6}", color) else ""})
        if len(out) >= MAX_RESOURCES:
            break
    return out


def normalize_abilities(raw, resources: list[dict] | None = None) -> list[dict]:
    names = {r["name"].lower(): r["name"] for r in resources or []}
    out = []
    for a in raw if isinstance(raw, list) else []:
        if not isinstance(a, dict) or not str(a.get("name", "")).strip():
            continue
        costs = {}
        for k, v in (a.get("costs") if isinstance(a.get("costs"), dict) else {}).items():
            key = names.get(str(k).lower(), str(k).strip()) if names else str(k).strip()
            if key and as_int(v) > 0:
                costs[truncate(key, 24)] = min(999, as_int(v))
        bonus = a.get("bonus")
        out.append({
            "id": str(a.get("id") or uuid.uuid4().hex[:8]),
            "name": truncate(str(a["name"]).strip(), 40),
            "kind": a.get("kind") if a.get("kind") in ABILITY_KINDS else "effect",
            "costs": costs,
            "dice": _dice(a.get("dice", "")),
            "bonus": None if bonus in (None, "") else max(-5, min(20, as_int(bonus))),
            "range": max(1, min(30, as_int(a.get("range", 1), 1))),
            "description": truncate(str(a.get("description", "")).strip(), 600),
            **({"own": True} if a.get("own") else {}),
        })
        if len(out) >= MAX_ABILITIES:
            break
    return out


def start_pools(resources: list[dict]) -> dict:
    return {r["name"]: {"current": r["max"], "max": r["max"], "regen": dict(r["regen"]), "color": r.get("color", "")} for r in resources}


def normalize_pools(raw) -> dict:
    out = {}
    for name, p in (raw.items() if isinstance(raw, dict) else []):
        if isinstance(p, dict):
            mx = max(1, min(999, as_int(p.get("max", 10), 10)))
            regen_raw = p.get("regen") if isinstance(p.get("regen"), dict) else {}
            color = str(p.get("color") or "")
            out[truncate(str(name), 24)] = {"current": max(0, min(mx, as_int(p.get("current", mx), mx))), "max": mx,
                                            "regen": {k: max(-1, min(999, as_int(regen_raw.get(k, 0)))) for k in REGEN_KEYS},
                                            "color": color if re.fullmatch(r"#[0-9a-fA-F]{6}", color) else ""}
    return dict(list(out.items())[:MAX_RESOURCES])


def pools_line(state: dict) -> str:
    pools = state.get("resources") or {}
    return ", ".join(f"{n} {p['current']}/{p['max']}" for n, p in pools.items())


def cost_text(costs: dict) -> str:
    return ", ".join(f"{v} {k}" for k, v in costs.items()) or "free"


def can_pay(state: dict, costs: dict) -> str:
    """'' when the pools cover the cost, else the reason."""
    pools = state.get("resources") or {}
    for name, amount in costs.items():
        have = (pools.get(name) or {}).get("current", 0)
        if name not in pools:
            return f"You have no {name}."
        if have < amount:
            return f"Not enough {name}: {amount} needed, you have {have}."
    return ""


def pay(state: dict, costs: dict) -> None:
    why = can_pay(state, costs)
    if why:
        raise ResourceError(why)
    for name, amount in costs.items():
        state["resources"][name]["current"] -= amount


def change(state: dict, name: str, delta: int) -> int:
    """Add (or take) some of a resource, kept between 0 and the maximum. Returns the real change."""
    pools = state.get("resources") or {}
    key = next((k for k in pools if k.lower() == (name or "").strip().lower()), None)
    if not key:
        return 0
    p = pools[key]
    before = p["current"]
    p["current"] = max(0, min(p["max"], before + int(delta)))
    return p["current"] - before


def regenerate(state: dict, when: str, times: int = 1) -> list[str]:
    """Refill after a round, a rest, a night or a new day (each pool has its own rule). Lines like 'Mana 20/20'."""
    out = []
    for name, p in (state.get("resources") or {}).items():
        amount = (p.get("regen") or {}).get(when, 0)
        if not amount or p["current"] >= p["max"] or times <= 0:
            continue
        p["current"] = p["max"] if amount < 0 else min(p["max"], p["current"] + amount * times)
        out.append(f"{name} {p['current']}/{p['max']}")
    from .party import rest as party_rest
    if state.get("character5e") and when in ("short_rest", "long_rest"):  # 5e features come back on rests
        from .dnd5e.store import pull_hp, rest as char_rest, sync_player
        pull_hp(state, "")
        state["character5e"] = char_rest(state["character5e"], when, _library())
        sync_player(state, _library())
        out.append("features refreshed")
    out += party_rest(state, when)
    if state.get("party5e") and when in ("short_rest", "long_rest"):  # companions' 5e sheets: HP from the party, uses refilled
        from .dnd5e.party5e import sync_companion
        from .dnd5e.store import pull_hp, rest as char_rest
        for name in list(state["party5e"]):
            pull_hp(state, name)
            state["party5e"][name] = char_rest(state["party5e"][name], when, _library())
            hp = (state.get("party") or {}).get(name, {}).get("hp")
            if hp is not None and when == "short_rest":
                state["party5e"][name]["hp"] = {**state["party5e"][name].get("hp", {}), "current": hp}
            sync_companion(state, name, _library())
    return out


def _library():
    from .main import library5e
    return library5e()


def rest_kind(minutes: int) -> str | None:
    """A skip of 8 hours or more is a night's sleep; an hour or more is a short rest."""
    return "long_rest" if minutes >= 8 * 60 else "short_rest" if minutes >= 60 else None


def use_outside_combat(state: dict, ability: dict, dice: DiceRoller) -> tuple[dict, str]:
    """Use an ability from the sheet (no fight going on): pay, roll, heal, and tell the GM."""
    pay(state, ability["costs"])
    name = state["player"].get("name") or "You"
    paid = f" (−{cost_text(ability['costs'])}; {pools_line(state)})" if ability["costs"] else ""
    line = f"{MARK} **{name} uses {ability['name']}**{paid}"
    if ability["dice"] and ability["kind"] == "heal":
        r = dice.roll(ability["dice"])
        hp = state["player"]["hp"]
        before = hp["current"]
        hp["current"] = min(hp["max"], hp["current"] + max(0, r.total))
        line += f"\n\U0001F49A heals {r.total} ({ability['dice']}) → HP {hp['current']}/{hp['max']}" + (
            "" if hp["current"] > before or r.total <= 0 else " (already full)")
    elif ability["dice"]:
        r = dice.roll(ability["dice"])
        line += f"\n\U0001F4A5 power {r.total} ({ability['dice']})"
    if ability["description"]:
        line += f"\n_{ability['description']}_"
    return state, line


def is_ability(text: str) -> bool:
    return (text or "").lstrip().startswith(MARK)


def gm_notes(state: dict, abilities: list[dict]) -> str:
    pools = pools_line(state)
    if not pools:
        return ""
    lines = [f"Player's resources: {pools}."]  # the abilities themselves are in "The player's skills"
    empty = [n for n, p in (state.get("resources") or {}).items() if p["current"] == 0]
    if empty:
        lines.append(f"Out of {', '.join(empty)}: the player is drained and cannot use abilities that cost it; show the exhaustion.")
    return "\n".join(lines)


def _key(text: str) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", (text or "").lower()).split())


def skills_in_text(text: str, abilities: list[dict]) -> list[dict]:
    """The player's skills named in a message ("I use my soul forge" -> Soul Forge). Names shorter than 4 letters are
    not looked for (too easy to say by chance)."""
    words = f" {_key(text)} "
    found = []
    for a in abilities or []:
        name = _key(a.get("name", ""))
        if len(name.replace(" ", "")) >= 4 and f" {name} " in words and a not in found:
            found.append(a)
    return found[:3]


def skills_section(abilities: list[dict]) -> str:
    """The player's skills, always in front of the Aedo: what each really does, its cost."""
    if not abilities:
        return ""
    lines = ["## The player's skills (real; these are the special things they can do)"]
    for a in abilities[:MAX_ABILITIES]:
        cost = f" (costs {cost_text(a['costs'])})" if a.get("costs") else ""
        lines.append(f"- {a['name']}{cost}: {a.get('description') or 'as its name says'}")
    lines.append("When the player uses one (by name, in their own words), it works as described here, within its limits; "
                 "do not give them other powers, and do not forget these.")
    return "\n".join(lines)


def use_named_skills(state: dict, found: list[dict]) -> list[dict]:
    """Skills named in the player's message: costs are paid when the pools allow it. Returns what happened."""
    out = []
    for a in found:
        why = can_pay(state, a["costs"]) if a.get("costs") else ""
        if not why and a.get("costs"):
            pay(state, a["costs"])
        out.append({"id": a["id"], "name": a["name"], "ok": not why, "why": why})
    return out


def used_section(used: list[dict], abilities: list[dict], state: dict) -> str:
    """For the turn the player names a skill: what it does, and whether it worked (paid) or falters."""
    if not used:
        return ""
    by_id = {a["id"]: a for a in abilities or []}
    lines = ["## The player uses a skill this turn (resolved by the app)"]
    for u in used:
        a = by_id.get(u["id"], {})
        if u["ok"]:
            paid = f" Paid: {cost_text(a.get('costs') or {})} (now {pools_line(state)})." if a.get("costs") else ""
            lines.append(f"- {u['name']} WORKS: {a.get('description') or 'as its name says'}.{paid} Show it happening as described.")
        else:
            lines.append(f"- {u['name']} FALTERS: {u['why']} Show the attempt failing from exhaustion.")
    return "\n".join(lines)


RESOURCE_RULES = (
    "The APP keeps the player's resources (see the GM notes). When the player uses an ability in the story without the "
    "app's ✨ line, it only works if the resources allow it; the tracker subtracts the cost. Never refill or spend "
    "resources yourself in the text with numbers; describe effort, fatigue and recovery instead."
)


def tracker_line(state: dict) -> str:
    pools = pools_line(state)
    if not pools:
        return ""
    return ("- resource_changes: resources the PLAYER spent or regained in these exchanges outside the app's ✨ lines "
            f"(resource, delta: negative = spent, reason). Current: {pools}.")


def apply_tracker(state: dict, changes: list[dict]) -> list[str]:
    out = []
    for ch in changes:
        delta = max(-999, min(999, as_int(ch.get("delta", 0))))
        real = change(state, str(ch.get("resource", "")), delta) if delta else 0
        if real:
            name = next((k for k in state["resources"] if k.lower() == str(ch.get("resource", "")).strip().lower()), "")
            p = state["resources"][name]
            out.append(f"{name} {real:+d} → {p['current']}/{p['max']}" + (f" ({ch['reason']})" if ch.get("reason") else ""))
    return out


async def suggest(llm, card_text: str) -> dict:
    """The AI proposes resources and abilities that fit a card (the player edits and confirms them)."""
    from .util import extract_json

    prompt = (
        "A tabletop roleplaying game card is below. Propose the player's RESOURCES (energy pools like Mana, Aura, Stamina, "
        "Ki - only the ones this setting really uses, 1 to 3) and 4 to 8 ABILITIES that spend them.\n"
        "Answer with ONE JSON object: {\"resources\": [{\"name\", \"max\" (a starting character), \"regen\": {\"round\", "
        "\"short_rest\", \"long_rest\", \"day\"} (numbers, -1 = refill all)}], \"abilities\": [{\"name\", \"kind\" (attack | heal | "
        "effect), \"costs\": {\"<resource>\": number}, \"dice\" (damage or healing like 2d6+2, \"\" for effects), \"range\" "
        "(squares, 1 = touch/melee), \"description\" (one short sentence)}]}. Fit the setting's words and power level.\n\n"
        f"CARD:\n{truncate(card_text, 3500)}\n\nOutput the JSON object now."
    )
    raw = await llm.chat([{"role": "user", "content": prompt}], max_tokens=900, temperature=0.5)
    data = extract_json(raw) or {}
    res = normalize_resources(data.get("resources"))
    if not res:
        raise ResourceError("The model did not suggest any resources. Add them yourself.")
    return {"resources": res, "abilities": normalize_abilities(data.get("abilities"), res)}
