"""Reputation as a system: what the player did is classified, the app decides how much it counts.

A small model is bad at numbers ("+15? +3?") but good at naming what happened. So the tracker only names the event
("defended", "mocked", "kept a promise"); this table gives the value, the same every time. Repeating the same thing to
the same person counts less each time (compliments can't be farmed), every change is capped per reply (Settings:
*Biggest relationship change per reply*), and each level of the -100..+100 meter has defined effects the characters
follow: what they share, what they do for the player, what they refuse.
"""
from __future__ import annotations

# event: (value, how it reads in the changes line)
EVENTS: dict[str, tuple[int, str]] = {
    "saved_life": (25, "saved their life"),
    "defended": (12, "defended them"),
    "helped": (8, "helped them"),
    "kept_promise": (10, "kept a promise"),
    "gift": (6, "gave a gift"),
    "shared_secret": (6, "trusted them with a secret"),
    "kind_words": (4, "kind words"),
    "respected": (4, "showed respect"),
    "flirt_welcome": (5, "flirting they enjoyed"),
    "agreed": (3, "sided with them"),
    "rude": (-5, "was rude"),
    "disagreed": (-3, "went against them"),
    "mocked": (-8, "mocked them"),
    "flirt_unwelcome": (-6, "unwelcome advances"),
    "caught_lying": (-10, "caught lying"),
    "broke_promise": (-12, "broke a promise"),
    "threatened": (-12, "threatened them"),
    "hurt_friend": (-15, "hurt someone they care about"),
    "stole": (-15, "stole from them"),
    "attacked": (-25, "attacked them"),
    "betrayed": (-30, "betrayed them"),
}

# (lowest value, label, what the character does at this level)
LEVELS: list[tuple[int, str, str]] = [
    (-100, "mortal enemy", "wants the player gone; works against them openly or in secret, never helps, never tells the truth"),
    (-79, "hostile", "refuses help and favours, insults or threatens, shares nothing, may sabotage or report the player"),
    (-49, "distrustful", "guarded and curt; helps only for a clear price or benefit, shares only what anyone knows"),
    (-19, "neutral", "polite and ordinary; normal prices and small help, keeps personal matters private"),
    (20, "friendly", "warm; small favours, rumours and advice, a little discount, hears the player out"),
    (50, "close", "trusts the player: shares personal worries and their own secrets when asked, takes risks for them"),
    (80, "deeply bonded", "fiercely loyal: would sacrifice for the player, reveals their deepest secrets, defends them anywhere"),
]
REPEAT_WINDOW = 12   # recent changes remembered per game
LOG_LIMIT = 60


def level(value: int) -> tuple[str, str]:
    """(label, effects) for a relationship value."""
    found = LEVELS[0]
    for lv in LEVELS:
        if value >= lv[0]:
            found = lv
    return found[1], found[2]


def scale_text() -> str:
    """The levels and their effects, for the card's stable prompt."""
    rows = []
    for i, (low, label, effect) in enumerate(LEVELS):
        high = LEVELS[i + 1][0] - 1 if i + 1 < len(LEVELS) else 100
        rows.append(f"  {low:+d}..{high:+d} {label}: {effect}.")
    return ("Relationships (-100..+100, kept by the app). Characters act by their level:\n" + "\n".join(rows))


def delta_for(event: str, npc: str, log: list[dict]) -> int:
    """The fixed value of an event, halved for each time the same thing happened with the same person recently."""
    base = EVENTS.get(event, (0, ""))[0]
    if not base:
        return 0
    recent = [e for e in log[-REPEAT_WINDOW:] if e.get("npc", "").lower() == npc.lower() and e.get("event") == event]
    value = base / (2 ** len(recent))
    return int(round(value)) if abs(value) >= 1 else 0


def remember(state: dict, npc: str, event: str, delta: int, reason: str) -> None:
    log = state.setdefault("rep_log", [])
    log.append({"npc": npc, "event": event, "delta": delta, "reason": reason[:140]})
    del log[:-LOG_LIMIT]


def event_label(event: str) -> str:
    return EVENTS.get(event, (0, event.replace("_", " ")))[1]


def tracker_line() -> str:
    names = ", ".join(EVENTS)
    return ("- relationship_changes: what the PLAYER did that changed how a character feels about them: npc, event (one of: "
            f"{names}), reason (the player's action, in a few words). ONLY for a character who was present AND talked with "
            "the player or saw what the player did. Never for characters only mentioned, the player's thoughts in single "
            "quotes, plans or suggestions, or a character simply being friendly (their own behaviour is not a reason). "
            "No player action toward them: no change.")
