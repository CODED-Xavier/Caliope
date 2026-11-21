"""Fill a card's character boxes (looks, personality, speech style) from what the card says about them.

The model reads the character's own text plus every lorebook passage that names them, and writes the empty boxes.
What the card states is used as it is; what it doesn't say is invented once to fit the character's personality and
role. The result is saved in the card, so every future game has the same character, and is also written into games
already using the card (only where those boxes are still empty there). Anything can be edited by hand afterwards.
"""
from __future__ import annotations

import re

from .util import truncate

LOOK_KEYS = ("race", "hair", "eyes", "build", "skin", "outfit")
LABELS = {"race": "Race", "hair": "Hair", "eyes": "Eyes", "build": "Build", "skin": "Skin", "outfit": "Outfit",
          "personality": "Personality", "speech_style": "Speech"}

FILL_PROMPT = """You are filling the character sheet of {name} for a roleplay game, from the card's information below.

Rules:
- Use what the information says first, in its own words where possible.
- When it says nothing about a line, invent something short that fits {name}'s personality, role and world.
- Never contradict the information. Keep each line short (a few words to two sentences).
- Write exactly these labeled lines and nothing else:
{lines}

What the card says about {name}:
{source}"""


def _mentions(text: str, name: str) -> bool:
    first = name.split()[0]
    return bool(re.search(rf"\b{re.escape(name)}\b", text, re.I) or (len(first) > 2 and re.search(rf"\b{re.escape(first)}\b", text)))


def source_text(card: dict, npc: dict, limit: int = 3000) -> str:
    """The character's own fields plus every lorebook passage that names them."""
    parts = []
    for key, label in (("description", "Description"), ("personality", "Personality"), ("speech_style", "Speech")):
        if (npc.get(key) or "").strip():
            parts.append(f"{label}: {npc[key].strip()}")
    look = "; ".join(f"{k}: {v}" for k, v in (npc.get("appearance") or {}).items() if str(v).strip())
    if look:
        parts.append(f"Looks: {look}")
    name = npc["name"]
    for e in (card.get("lorebook") or {}).get("entries", []):
        content = e.get("content", "")
        if any(k.lower() == name.lower() or k.lower() == name.split()[0].lower() for k in e.get("keys", [])):
            parts.append(truncate(content, 1500))
            continue
        for block in re.split(r"\n\s*\n|\n(?=\s*[-*•])", content):
            if _mentions(block, name):
                parts.append(block.strip())
    text, seen = [], set()
    for p in parts:
        k = p[:80]
        if k not in seen:
            seen.add(k)
            text.append(p)
    return truncate("\n\n".join(text), limit) or "(The card says nothing else about them.)"


def missing(npc: dict) -> list[str]:
    looks = npc.get("appearance") or {}
    out = [k for k in LOOK_KEYS if not str(looks.get(k, "")).strip()]
    out += [k for k in ("personality", "speech_style") if not str(npc.get(k, "")).strip()]
    return out


async def fill_one(llm, card: dict, npc: dict) -> dict:
    """{field: value} for the character's empty boxes ({} when nothing is missing)."""
    need = missing(npc)
    if not need:
        return {}
    lines = "\n".join(f"{LABELS[k]}: ..." for k in need)
    raw = await llm.chat([{"role": "user", "content": FILL_PROMPT.format(name=npc["name"], lines=lines, source=source_text(card, npc))}],
                         max_tokens=360, temperature=0.6)
    found = _parse(raw)
    return {k: truncate(found[k], 400) for k in need if found.get(k)}


def _parse(raw: str) -> dict:
    out: dict[str, str] = {}
    key = None
    names = {v.lower(): k for k, v in LABELS.items()} | {"speech style": "speech_style", "clothes": "outfit", "species": "race"}
    for line in (raw or "").splitlines():
        m = re.match(r"^\s*[-*]?\s*\**\s*([A-Za-z ]{3,14}?)\s*\**\s*:\s*\**\s*(.*)$", line)
        if m and m.group(1).strip().lower() in names:
            key = names[m.group(1).strip().lower()]
            out[key] = m.group(2).strip().strip("*").strip()
        elif key and line.strip():
            out[key] = (out[key] + " " + line.strip()).strip()
    return {k: v for k, v in out.items() if v and v not in ("...", "…")}


def merge(npc: dict, values: dict) -> dict:
    """The character with `values` written into its boxes."""
    looks = dict(npc.get("appearance") or {})
    for k in LOOK_KEYS:
        if values.get(k):
            looks[k] = values[k]
    out = {**npc, "appearance": looks}
    for k in ("personality", "speech_style"):
        if values.get(k):
            out[k] = values[k]
    return out

