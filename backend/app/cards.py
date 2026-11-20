"""Card types and their feature profiles.

Roleplay cards: simple and fast (characters, relationships, conversation).
Adventure cards: rules, quests, items and (later) combat.

A card only stores the few options the player changed in `features`; everything else comes from
the profile of its type, so changing a profile later updates every card that did not override it.
"""
from __future__ import annotations

KINDS = ("roleplay", "adventure")
TRACKERS = ("off", "lite", "full")
PANELS = ("sheet", "bag", "people", "map", "dice", "journal", "status", "combat")

PROFILES = {
    "roleplay": {
        "tracker": "lite",            # relationships, new characters, memories, place and time
        "tracker_interval": 2,        # run the tracker every N replies (it then reads all N exchanges)
        "panels": ["sheet", "people", "dice", "journal"],
        "appearance_hints": True,
        "relationships": "app",       # "app": the app's -100..+100 scale wins over any scale written in the card
    },
    "adventure": {
        "tracker": "full",            # also HP, gold, items and quests
        "tracker_interval": 1,
        "panels": ["sheet", "bag", "people", "map", "combat", "dice", "journal"],
        "appearance_hints": True,
        "relationships": "app",
    },
}


def default_kind(mode: str | None) -> str:
    return "roleplay" if mode == "character" else "adventure"


def normalize_features(raw) -> dict:
    """Keep only valid overrides."""
    raw = raw if isinstance(raw, dict) else {}
    out: dict = {}
    if raw.get("tracker") in TRACKERS:
        out["tracker"] = raw["tracker"]
    try:
        interval = int(raw.get("tracker_interval"))
        if 1 <= interval <= 5:
            out["tracker_interval"] = interval
    except (TypeError, ValueError):
        pass
    if isinstance(raw.get("panels"), list):
        panels = [p for p in raw["panels"] if p in PANELS]
        if panels:
            out["panels"] = panels
    if isinstance(raw.get("appearance_hints"), bool):
        out["appearance_hints"] = raw["appearance_hints"]
    if raw.get("relationships") in ("app", "card"):
        out["relationships"] = raw["relationships"]
    return out


def resolve_features(scenario: dict, settings: dict | None = None) -> dict:
    """The features a game really uses: type profile + the card's overrides + the global kill switch."""
    kind = scenario.get("kind") if scenario.get("kind") in KINDS else default_kind(scenario.get("mode"))
    features = {**PROFILES[kind], **normalize_features(scenario.get("features"))}
    if settings is not None and not settings.get("state_tracking", True):
        features["tracker"] = "off"
    features["kind"] = kind
    return features
