"""Physical descriptions of characters.

Appearance is stored as structured fields (not buried in prose) so the AI always sees the same hair,
eyes, build... and does not forget or contradict them. A random "seed" is offered to the AI each turn
for any NEW character, which avoids the usual clichés (everyone with raven hair and emerald eyes).
"""
from __future__ import annotations

import random

FIELDS = ("race", "hair", "eyes", "build", "skin", "outfit", "extra")
LABELS = {"race": "Race", "hair": "Hair", "eyes": "Eyes", "build": "Build", "skin": "Skin", "outfit": "Style / outfit", "extra": "Other details"}

HAIR_COLORS = ["auburn", "chestnut", "platinum blond", "ash grey", "copper", "jet black", "dark brown", "sandy", "white",
               "honey blond", "silver-streaked brown", "deep red", "mousy brown", "salt-and-pepper"]
HAIR_STYLES = ["short and messy", "long and straight", "tied in a braid", "in a tight bun", "shaved at the sides", "curly",
               "shoulder-length and wavy", "cropped close", "in two plaits", "slicked back", "worn loose and wild", "bald"]
EYE_COLORS = ["grey", "hazel", "dark brown", "pale blue", "amber", "green", "light brown", "steel blue", "one blue, one brown"]
BUILDS = ["tall and lean", "short and sturdy", "broad-shouldered", "slim", "athletic", "heavyset", "wiry", "average height and soft", "tall and gangly"]
FEATURES = ["freckles", "a scar across the chin", "a crooked nose", "dimples", "a gap between the front teeth", "a mole near the eye",
            "heavy eyebrows", "sharp cheekbones", "ink-stained fingers", "a missing earlobe", "laugh lines", "a chipped tooth"]


def normalize_appearance(raw) -> dict:
    """Keep only known fields, as short strings."""
    if not isinstance(raw, dict):
        return {}
    out = {}
    for key in FIELDS:
        value = " ".join(str(raw.get(key, "") or "").split())
        if value:
            out[key] = value[:200]
    return out


def appearance_line(app: dict) -> str:
    """One compact line for the prompt, e.g. 'Elf; hair: silver braid; eyes: violet; build: slim'."""
    if not app:
        return ""
    parts = []
    if app.get("race"):
        parts.append(app["race"])
    for key in ("hair", "eyes", "build", "skin", "outfit", "extra"):
        if app.get(key):
            parts.append(f"{key if key != 'outfit' else 'style'}: {app[key]}" if key != "extra" else app[key])
    return "; ".join(parts)


def appearance_seed(rng: random.Random, species: list[str] | None = None) -> str:
    """Random traits for the next new character. Without species the character is human."""
    race = rng.choice(species) if species else "human"
    hair = f"{rng.choice(HAIR_STYLES)} {rng.choice(HAIR_COLORS)} hair" if rng.random() > 0.08 else "no hair"
    return f"{race}, {hair}, {rng.choice(EYE_COLORS)} eyes, {rng.choice(BUILDS)} build, {rng.choice(FEATURES)}"
