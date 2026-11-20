"""Lorebook (world info): entries that are added to the prompt only when their keywords come up.

Entries marked "constant" are always on. The others are triggered when one of their keys appears in the
recent messages. A token budget keeps them from filling the small context window.
"""
from __future__ import annotations

import re

from .util import estimate_tokens

MAX_ENTRIES = 300


def key_matches(key: str, text: str, case_sensitive: bool = False) -> bool:
    key = (key or "").strip()
    if not key:
        return False
    flags = 0 if case_sensitive else re.IGNORECASE
    if len(key) > 2 and key.startswith("/") and key.endswith("/"):  # /regex/ keys
        try:
            return re.search(key[1:-1], text, flags) is not None
        except re.error:
            return False
    return (key in text) if case_sensitive else (key.lower() in text.lower())


def entry_triggered(entry: dict, text: str) -> bool:
    if not entry.get("enabled", True):
        return False
    cs = bool(entry.get("case_sensitive"))
    if not any(key_matches(k, text, cs) for k in entry.get("keys", [])):
        return False
    if entry.get("selective") and entry.get("secondary_keys"):
        return any(key_matches(k, text, cs) for k in entry["secondary_keys"])
    return True


def select_entries(lorebook: dict | None, recent_texts: list[str], budget_tokens: int) -> tuple[list[dict], list[dict]]:
    """(always-on entries, triggered entries). `recent_texts` are the messages to scan, newest first."""
    if not lorebook or not lorebook.get("entries"):
        return [], []
    depth = max(1, int(lorebook.get("scan_depth", 4)))
    scanned = "\n".join(recent_texts[:depth + 1])
    budget = max(0, min(int(budget_tokens), int(lorebook.get("token_budget", budget_tokens) or budget_tokens)))
    always = [e for e in lorebook["entries"] if e.get("enabled", True) and e.get("constant")]
    candidates = [e for e in lorebook["entries"] if e.get("enabled", True) and not e.get("constant") and entry_triggered(e, scanned)]
    candidates.sort(key=lambda e: (-int(e.get("priority", 0)), int(e.get("insertion_order", 0))))
    used, chosen = 0, []
    for e in candidates:
        cost = estimate_tokens(e["content"])
        if chosen and used + cost > budget:
            continue
        if not chosen and cost > budget:
            continue  # a single entry bigger than the whole budget never fits
        chosen.append(e)
        used += cost
    return always, chosen
