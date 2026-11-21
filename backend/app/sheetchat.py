"""Cards that create your character in the story (Lumencia asks for name, origin, department, attributes...):
when you answer with your sheet in the chat, the app reads it once and fills the Sheet tab.
"""
from __future__ import annotations

import re

from .util import as_int, extract_json, truncate

SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "race": {"type": "string"},
        "class": {"type": "string"},
        "background": {"type": "string"},
        "looks": {"type": "string"},
        "personality": {"type": "string"},
        "gold": {"type": "integer"},
        "attributes": {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}, "value": {"type": "integer"}}, "required": ["name", "value"]}},
        "other": {"type": "array", "items": {"type": "object", "properties": {"label": {"type": "string"}, "value": {"type": "string"}}, "required": ["label", "value"]}},
    },
    "required": ["name", "race", "class", "background", "looks", "personality", "gold", "attributes", "other"],
}

PROMPT = """The game asked the player to create their character, and the player answered. Read the player's answer
and copy their character sheet into JSON. Copy ONLY what the player wrote (use "" , 0 or [] for anything missing).
- name: the character's name. race: species or people. class: class, department, path or profession.
- background: origin and history, in a sentence or two. looks: appearance. personality: traits.
- gold: starting money if the player or the game's rules state it for their choice, else -1.
- attributes: every numbered attribute or stat (name and number), for example Magic 6, Martial 4.
- other: other sheet fields with a value, for example Tier: Beginner, Origin: Minor Noble, Body: C.

What the game asked:
{asked}

The player's answer:
{answer}"""

SHEET_HINT = re.compile(r"(name|nome|origin|department|class|classe|race|ra[cç]a|attribute|atributo|stat|tier|background)\s*[:\-]", re.I)


def looks_like_sheet(text: str) -> bool:
    """A message that is (probably) the player's character sheet: several "Field: value" lines, or a long answer
    naming sheet fields."""
    hits = len(SHEET_HINT.findall(text or ""))
    return hits >= 2 or (hits >= 1 and len(text) > 250)


def wanted(state: dict, user_count: int, text: str) -> bool:
    return state.get("setup") == "card" and not state.get("sheet_from_chat") and user_count <= 4 and looks_like_sheet(text)


async def read_sheet(llm, asked: str, answer: str) -> dict | None:
    raw = await llm.chat([{"role": "user", "content": PROMPT.format(asked=truncate(asked, 3000), answer=truncate(answer, 3000))}],
                         json_schema=SCHEMA, max_tokens=500, temperature=0.1)
    data = extract_json(raw or "")
    return data if isinstance(data, dict) else None


def apply_sheet(state: dict, data: dict) -> list[str]:
    """Write the sheet into the game state. Returns what changed (for the 'changes' line)."""
    p = state["player"]
    changes = []
    for key, field in (("name", "name"), ("race", "race"), ("class", "class"), ("background", "background"),
                       ("looks", "description"), ("personality", "traits")):
        val = truncate(str(data.get(key) or "").strip(), 900 if key == "background" else 300)
        if val and val != p.get(field):
            p[field] = val
            changes.append(f"{field}: {truncate(val, 40)}")
    stats = {}
    for a in data.get("attributes") or []:
        if isinstance(a, dict) and str(a.get("name", "")).strip():
            stats[truncate(str(a["name"]).strip(), 20)] = max(0, min(999, as_int(a.get("value"), 0)))
    if len(stats) >= 2:
        p["stats"] = stats
        changes.append("attributes: " + ", ".join(f"{k} {v}" for k, v in stats.items()))
    gold = as_int(data.get("gold"), -1)
    if gold >= 0 and not state.get("gold"):
        state["gold"] = gold
        changes.append(f"money: {gold}")
    other = {truncate(str(o.get("label", "")).strip(), 30): truncate(str(o.get("value", "")).strip(), 80)
             for o in data.get("other") or [] if isinstance(o, dict) and str(o.get("label", "")).strip() and str(o.get("value", "")).strip()}
    if other:
        state.setdefault("card_status", {}).update(other)
        changes.append("sheet: " + ", ".join(f"{k} {v}" for k, v in list(other.items())[:4]))
    if changes:
        state["sheet_from_chat"] = True
    return changes
