"""The player's lorebook: world facts the player adds for one game (a new great house, a home village, an order).

They are canon in that game and win over the card's own lore when the two disagree. A one-line summary of each
entry is always in the prompt (so the GM never forgets they exist); the full text is added when one of the
entry's keywords comes up, like the card's lorebook.
"""
from __future__ import annotations

import re
import uuid

from .lorebook import select_entries
from .util import truncate

MAX_ENTRIES = 30
MAX_CONTENT = 2000

CANON_RULE = (
    "These are TRUE in this world, added by the player. Where the card's lore disagrees (for example it lists the great "
    "houses or the noble families), these win: count them in, treat them as long established, and weave them into "
    "the world's politics, history and rumours. Never deny or forget them."
)


def clean_entries(entries) -> list[dict]:
    """Validate and normalise what the interface sends."""
    if not isinstance(entries, list):
        raise ValueError("The player lorebook must be a list of entries.")
    if len(entries) > MAX_ENTRIES:
        raise ValueError(f"At most {MAX_ENTRIES} lore entries.")
    out = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        name = str(e.get("name", "")).strip()[:80]
        content = str(e.get("content", "")).replace("\r\n", "\n").strip()
        if not name and not content:
            continue
        if not name:
            raise ValueError("Every lore entry needs a name.")
        if len(content) > MAX_CONTENT:
            raise ValueError(f"'{name}' is too long ({len(content)} characters, the limit is {MAX_CONTENT}).")
        keys = e.get("keys") or []
        if isinstance(keys, str):
            keys = keys.split(",")
        keys = [str(k).strip()[:60] for k in keys if str(k).strip()][:10]
        out.append({"id": str(e.get("id") or uuid.uuid4().hex[:10]), "name": name, "keys": keys, "content": content,
                    "summary": str(e.get("summary", "")).strip()[:200], "enabled": bool(e.get("enabled", True))})
    return out


def summary_line(e: dict) -> str:
    s = e.get("summary") or ""
    if not s:
        first = re.split(r"(?<=[.!?])\s|\n", e.get("content", "").strip(), maxsplit=1)[0]
        s = truncate(first, 160)
    return f"- {e['name']}" + (f": {s}" if s else "")


def always_section(entries: list[dict]) -> str:
    on = [e for e in entries or [] if e.get("enabled", True)]
    if not on:
        return ""
    return "## World additions by the player (canon)\n" + CANON_RULE + "\n" + "\n".join(summary_line(e) for e in on)


def triggered(entries: list[dict], recent_texts: list[str], budget_tokens: int) -> list[dict]:
    """Entries whose name or keywords appear in the recent messages (full text), within a token budget."""
    book = {"scan_depth": 4, "entries": [
        {**e, "keys": (e.get("keys") or []) + [e["name"]], "constant": False, "priority": 100}
        for e in entries or [] if e.get("enabled", True) and e.get("content")
    ]}
    return select_entries(book, recent_texts, budget_tokens)[1]


def suggest_prompt(entry: dict, summary: str, recent: list[str]) -> str:
    story = "\n\n".join(truncate(t, 700) for t in reversed(recent[:8]))
    return (
        "The player keeps a lore entry about something they added to the world. Read the story so far and list NEW facts "
        f"about \"{entry['name']}\" that the story has established and the entry does not mention yet (people, events, "
        "places, relations). Only facts the story clearly states; no guesses. One short line each, starting with '- '. "
        "If there is nothing new, answer exactly: NOTHING\n\n"
        f"Current entry:\n{truncate(entry.get('content', ''), 1500)}\n\n"
        + (f"Story summary:\n{truncate(summary, 1200)}\n\n" if summary else "")
        + f"Recent story:\n{story}"
    )


def parse_suggestions(text: str) -> list[str]:
    if not text or text.strip().upper().startswith("NOTHING"):
        return []
    lines = [re.sub(r"^\s*[-*•\d.)]+\s*", "", ln).strip() for ln in text.splitlines()]
    return [truncate(ln, 240) for ln in lines if len(ln) > 3][:8]
