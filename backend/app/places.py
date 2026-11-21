"""Places of a card: locations with a fixed picture chosen by the card's creator (from the PC or a link).

When the story arrives at a place the card knows, its picture is shown above the reply right away: nothing is
painted, nothing leaves the PC. Places without a picture can still be painted by the scene-picture service.
"""
from __future__ import annotations

import re
import unicodedata

from .portraits import _url
from .util import truncate

MAX_PLACES = 60


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"\b(the|a|an|o|a|os|as|de|da|do|of)\b", " ", t)
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def normalize_places(raw) -> list[dict]:
    out, seen = [], set()
    for p in raw if isinstance(raw, list) else []:
        if not isinstance(p, dict) or not str(p.get("name", "")).strip():
            continue
        name = truncate(str(p["name"]).strip(), 80)
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        aliases = [truncate(str(a).strip(), 60) for a in (p.get("aliases") or []) if str(a).strip()][:8] \
            if isinstance(p.get("aliases"), list) else []
        out.append({"name": name, "aliases": aliases, "picture": _url(p.get("picture")),
                    "description": truncate(str(p.get("description", "")), 600)})
        if len(out) == MAX_PLACES:
            break
    return out


def find_place(places: list[dict], location: str) -> dict | None:
    """The card's place for the story's current location ("Grand Hall of Lumencia" finds "Grand Hall")."""
    loc = _norm(location)
    if not loc:
        return None
    best, score = None, 0
    for p in places or []:
        for name in [p["name"], *p.get("aliases", [])]:
            n = _norm(name)
            if not n:
                continue
            s = 3 if n == loc else 2 if re.search(rf"\b{re.escape(n)}\b", loc) else 1 if re.search(rf"\b{re.escape(loc)}\b", n) else 0
            if s > score or (s == score and s and best and len(n) > len(_norm(best["name"]))):
                best, score = p, s
    return best if score else None


def place_picture(place: dict) -> dict | None:
    if not place or not place.get("picture"):
        return None
    return {"prompt": place["name"], "seed": 0, "url": place["picture"], "place": place["name"]}


def places_section(places: list[dict], limit: int = 1500) -> str:
    """The card's known places for the Aedo (names and short descriptions), so the story uses their names."""
    rows = [f"- {p['name']}" + (f": {truncate(p['description'], 160)}" if p.get("description") else "") for p in places or []]
    if not rows:
        return ""
    return truncate("## Known places (use these names when the story goes there)\n" + "\n".join(rows), limit)
