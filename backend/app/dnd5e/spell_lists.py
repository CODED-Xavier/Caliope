"""Which classes can learn a spell.

The SRD 5.1 class spell lists ship with Calíope (seed/spell_lists_srd.json, CC BY 4.0). When your 5e.tools files
include the spell sources file (Spells/sources.json), its lists are used instead and cover every book. A spell
neither knows stays open (None): the sheet doesn't block what it can't check.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

SEED = Path(__file__).resolve().parent.parent / "seed" / "spell_lists_srd.json"
# PHB names for spells the SRD renamed
ALIASES = {"bigby's hand": "arcane hand", "mordenkainen's sword": "arcane sword", "nystul's magic aura": "arcanist's magic aura"}


def _norm(name: str) -> str:
    n = re.sub(r"\s+", " ", str(name or "").strip().lower())
    n = ALIASES.get(n, n)
    return re.sub(r"^[a-z]+'s ", "", n)  # "Tasha's Hideous Laughter" -> "hideous laughter"


@lru_cache(maxsize=1)
def srd_lists() -> dict[str, set[str]]:
    data = json.loads(SEED.read_text(encoding="utf-8"))["lists"]
    out: dict[str, set[str]] = {}
    for cls, names in data.items():
        for n in names:
            out.setdefault(_norm(n), set()).add(cls)
    return out


def load_sources(path: Path) -> dict[str, set[str]]:
    """5e.tools spells/sources.json: {source: {spell: {"class": [{"name": ...}], "classVariant": [...]}}}."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: dict[str, set[str]] = {}
    for spells in raw.values() if isinstance(raw, dict) else []:
        for name, info in (spells or {}).items() if isinstance(spells, dict) else []:
            for key in ("class", "classVariant"):
                for c in (info or {}).get(key) or []:
                    if isinstance(c, dict) and c.get("name"):
                        out.setdefault(_norm(name), set()).add(str(c["name"]))
    return out


def classes_for(spell_name: str, lib=None) -> set[str] | None:
    """The classes whose list has this spell, or None when no list knows it."""
    extra = getattr(lib, "spell_classes", None) or {}
    key = _norm(spell_name)
    return extra.get(key) or srd_lists().get(key)


def on_list(spell_name: str, class_name: str, lib=None) -> bool | None:
    got = classes_for(spell_name, lib)
    return None if got is None else class_name in got
