"""The D&D 5e library: the built-in SRD pack plus the user's own 5e.tools files, in one searchable index.

The SRD pack (`app/seed/srd5e.json`) ships with Calíope (CC-BY-4.0). The user's files stay on their PC in
`data/compendium/dnd5e/` (git-ignored) and add everything else they own. A later source wins for the same entry
(type, name, source), so the user's copy replaces the SRD one.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from .text import render, strip_tags

log = logging.getLogger("rpg.dnd5e")

TYPES = ("class", "subclass", "classFeature", "subclassFeature", "race", "subrace", "background", "feat",
         "optionalfeature", "spell", "baseitem", "item")
NEW_BOOKS = {"XPHB", "XDMG", "XMM"}
CREDIT = ("Contains material from the System Reference Document 5.1 and 5.2 by Wizards of the Coast LLC, "
          "available under the Creative Commons Attribution 4.0 International License.")


def edition_of(entry: dict) -> str:
    """"2024" for the 2024 rules (XPHB and friends), else "2014"."""
    return "2024" if entry.get("source") in NEW_BOOKS or entry.get("edition") == "one" else "2014"


def _summary(entry: dict) -> str:
    text = render(entry.get("entries") or entry.get("entry") or "")
    text = " ".join(text.split())
    return text[:180] + ("…" if len(text) > 180 else "")


class Library:
    def __init__(self, folders: list[Path]):
        self.folders = [Path(f) for f in folders]
        self.items: dict[tuple, dict] = {}
        self.info: dict = {"entries": 0, "files": 0, "errors": []}

    def _files(self) -> list[Path]:
        out: list[Path] = []
        for f in self.folders:
            if f.is_file():
                out.append(f)
            elif f.is_dir():
                out += sorted(p for p in f.rglob("*.json") if p.is_file())
        return out

    def load(self) -> dict:
        self.items = {}
        errors, files = [], 0
        for path in self._files():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                errors.append(f"{path.name}: {exc}")
                continue
            if not isinstance(data, dict):
                errors.append(f"{path.name}: not a 5e.tools data file")
                continue
            files += 1
            for kind in TYPES:
                for e in data.get(kind) or []:
                    if isinstance(e, dict) and e.get("name") and e.get("source"):
                        self.items[(kind, str(e["name"]).lower(), str(e["source"]).upper())] = e
        self.info = {"entries": len(self.items), "files": files, "errors": errors}
        return self.info

    def _card(self, kind: str, e: dict) -> dict:
        card = {"type": kind, "name": e["name"], "source": e["source"], "edition": edition_of(e),
                "srd": bool(e.get("srd") or e.get("srd52")), "summary": _summary(e)}
        if kind in ("classFeature", "subclassFeature"):
            card.update(level=e.get("level"), **{"class": e.get("className", "")})
            if e.get("subclassShortName"):
                card["subclass"] = e["subclassShortName"]
        elif kind == "subclass":
            card["class"] = e.get("className", "")
        elif kind == "spell":
            card["level"] = e.get("level", 0)
        elif kind == "subrace":
            card["race"] = e.get("raceName", "")
        elif kind == "baseitem":
            card["category"] = item_category(e)
        return card

    def search(self, kind: str, q: str = "", edition: str = "2014", limit: int = 60, category: str = "") -> list[dict]:
        q = (q or "").lower().strip()
        out = []
        for (k, name, _), e in self.items.items():
            if k != kind or edition_of(e) != edition:
                continue
            if category and item_category(e) != category:
                continue
            if q and q not in name and q not in str(e.get("className", "")).lower():
                continue
            out.append(self._card(kind, e))
            if len(out) >= limit:
                break
        return out

    def get(self, kind: str, source: str, name: str) -> dict | None:
        e = self.items.get((kind, str(name).lower(), str(source).upper()))
        if not e:
            return None
        return {**e, "text": render(e.get("entries") or e.get("entry") or ""), "title": strip_tags(e["name"])}


ITEM_CATEGORIES = {"M": "weapon", "R": "weapon", "LA": "armor", "MA": "armor", "HA": "armor", "S": "armor",
                   "A": "ammunition", "AF": "ammunition", "AT": "tools", "GS": "tools", "INS": "tools", "T": "tools",
                   "MNT": "mounts", "VEH": "mounts", "SHP": "mounts", "AIR": "mounts", "TAH": "mounts"}


def item_category(e: dict) -> str:
    """weapon, armor, ammunition, tools, mounts, or gear (everything else: packs, rope, a holy symbol…)."""
    return ITEM_CATEGORIES.get(str(e.get("type") or "").split("|")[0], "gear")


def default_library(data_dir: Path) -> Library:
    """The built-in SRD pack first, then the user's own files (which win for the same entry)."""
    seed = Path(__file__).resolve().parent.parent / "seed" / "srd5e.json"
    return Library([seed, Path(data_dir) / "compendium" / "dnd5e"])
