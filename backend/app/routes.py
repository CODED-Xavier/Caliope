"""Starts (routes) of a card: the same world entered in different ways.

A card always has its default start (its opening message). Imported cards may bring alternate openings, and
the card editor can add full starts: their own opening, a framing of the world for this route (sent to the
Aedo every turn), the characters the route focuses on (known from the start; everyone else is met in the
story), and fixed scenes the Aedo follows in order, one per reply, adapting them to what the player does.
"""
from __future__ import annotations

import re

from .util import truncate

MAX_STARTS = 8
MAX_SCENES = 6


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")[:40]


def normalize_starts(raw) -> list[dict]:
    out, seen = [], set()
    for s in raw if isinstance(raw, list) else []:
        if not isinstance(s, dict) or not str(s.get("name", "")).strip():
            continue
        sid = _slug(s.get("id") or s.get("name")) or f"start-{len(out) + 1}"
        while sid in seen or sid in ("default",) or sid.startswith("alt-"):
            sid += "-x"
        seen.add(sid)
        out.append({
            "id": sid,
            "name": truncate(str(s["name"]).strip(), 60),
            "description": truncate(str(s.get("description", "")).strip(), 300),
            "opening": str(s.get("opening", ""))[:8000],
            "setting": str(s.get("setting", ""))[:4000],
            "focus": [truncate(str(n).strip(), 60) for n in (s.get("focus") or []) if str(n).strip()][:30]
            if isinstance(s.get("focus"), list) else [],
            "scenes": [str(x)[:4000] for x in (s.get("scenes") or []) if str(x).strip()][:MAX_SCENES]
            if isinstance(s.get("scenes"), list) else [],
        })
        if len(out) == MAX_STARTS:
            break
    return out


def starts_of(data: dict) -> list[dict]:
    """Every way to begin this card: the default opening, alternate openings, then the card's own starts."""
    out = [{"id": "default", "name": "Default start", "description": "The card's own opening.",
            "opening": data.get("opening_message", ""), "setting": "", "focus": [], "scenes": []}]
    for i, text in enumerate(data.get("alternate_openings") or []):
        first = re.sub(r"[*_#>\[\]!()]", "", str(text)).strip().split("\n")[0]
        out.append({"id": f"alt-{i + 1}", "name": f"Alternate opening {i + 1}", "description": truncate(first, 140),
                    "opening": text, "setting": "", "focus": [], "scenes": []})
    out += data.get("starts") or []
    return out


def resolve(data: dict, start_id: str | None) -> dict | None:
    """The chosen start, or None for the default."""
    if not start_id or start_id == "default":
        return None
    for s in starts_of(data):
        if s["id"] == start_id:
            return s
    raise ValueError(f"This card has no start called '{start_id}'.")


def route_section(route: dict | None) -> str:
    if not route or not route.get("setting"):
        return ""
    return f"## This story's route: {route['name']}\n{route['setting'].strip()}"


def planned_scene(route: dict | None, state: dict) -> str:
    """The next fixed scene of the route for the Aedo, or ''."""
    scenes = (route or {}).get("scenes") or []
    i = int((state.get("script") or {}).get("next", 0))
    if i >= len(scenes):
        return ""
    return ("## Planned scene (write this next; keep its events, people and lines, but adapt it to what the player "
            f"just did; do not mention that it was planned)\n{scenes[i].strip()}")


def advance(state: dict, route: dict | None) -> bool:
    """Move to the next fixed scene after a reply. True when something changed."""
    scenes = (route or {}).get("scenes") or []
    script = state.setdefault("script", {"next": 0})
    if int(script.get("next", 0)) >= len(scenes):
        return False
    script["next"] = int(script.get("next", 0)) + 1
    return True
