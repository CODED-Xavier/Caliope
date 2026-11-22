"""Make the built-in SRD pack from 5e.tools files: only the entries marked SRD, credited (CC-BY-4.0).

    python -m app.dnd5e.srd_export data/compendium/dnd5e

writes app/seed/srd5e.json. Everything not marked SRD stays only in the user's own files.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .library import CREDIT, TYPES, Library

DROP = ("page", "fluff", "hasFluff", "hasFluffImages", "otherSources", "reprintedAs", "referenceSources", "basicRules")


def export(folder: Path, out: Path) -> dict:
    lib = Library([folder])
    lib.load()
    pack: dict = {"_credit": CREDIT}
    counts = {}
    for (kind, _, _), e in lib.items.items():
        if e.get("srd") or e.get("srd52"):
            pack.setdefault(kind, []).append({k: v for k, v in e.items() if k not in DROP})
    for kind in TYPES:
        counts[kind] = len(pack.get(kind, []))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(pack, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return counts


if __name__ == "__main__":
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "data/compendium/dnd5e")
    print(export(src, Path(__file__).resolve().parent.parent / "seed" / "srd5e.json"))
