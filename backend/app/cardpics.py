"""A card's character pictures from a folder on this PC.

Layout (the one Lumencia's artists use):
    <folder>/<Character>/1.png ... 6.png      numbered moods (1=Standard ... 6=Blushing, or the card's own labels)
    <folder>/<Character>.png                  a single picture, used as that character's Standard one
Folder names match characters however they are written: case, accents and spaces don't matter, and a first name
matches a full name ("Lilia" -> "Lilia Vale") when only one character has it. The pictures are copied into the
app's own folder, so the card keeps working if the original folder moves.
"""
from __future__ import annotations

import re
import shutil
import unicodedata
from pathlib import Path

from .images import MAX_IMAGE_BYTES, sniff_type

PICTURE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif")
STANDARD_LABELS = {1: "Standard", 2: "Happy", 3: "Sad", 4: "Angry", 5: "Disgusted", 6: "Blushing"}
# A missing mood shows the closest one the character has.
FALLBACK = {1: [2, 3], 2: [1], 3: [1], 4: [5, 1], 5: [4, 1], 6: [2, 1]}


def norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def match_name(folder: str, names: list[str]) -> str | None:
    """The character a folder name belongs to, or None."""
    f = norm(folder)
    if not f:
        return None
    exact = [n for n in names if norm(n) == f]
    if exact:
        return exact[0]
    for test in (lambda n: norm(n).split(" ")[0] == f,                        # first name
                 lambda n: f in norm(n).split(" "),                           # any part of the name
                 lambda n: norm(n).startswith(f + " ") or f.startswith(norm(n) + " "),
                 lambda n: norm(n) in f.split()):                                # "Sister Maelis" -> "Maelis"
        hits = [n for n in names if test(n)]
        if len(hits) == 1:
            return hits[0]
    return None


def _number(stem: str) -> int | None:
    m = re.fullmatch(r"\s*(\d{1,2})\s*", stem)
    return int(m.group(1)) if m else None


def scan(folder: str, names: list[str]) -> dict:
    """What a folder holds, matched to the card's characters. Nothing is copied."""
    root = Path(str(folder or "").strip().strip('"')).expanduser()
    if not root.is_dir():
        raise ValueError(f"Folder not found: {folder}")
    found: dict[str, dict] = {}
    unmatched: list[dict] = []

    def entry(name: str) -> dict:
        return found.setdefault(name, {"character": name, "folder": "", "files": {}})

    for item in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if item.is_dir():
            files = {}
            for f in item.iterdir():
                n = _number(f.stem)
                if f.is_file() and f.suffix.lower() in PICTURE_EXT and n is not None and 1 <= n <= 12:
                    files[n] = str(f)
            if not files:
                continue
            who = match_name(item.name, names)
            if who:
                e = entry(who)
                e["folder"] = item.name
                e["files"].update(files)
            else:
                unmatched.append({"folder": item.name, "count": len(files)})
        elif item.is_file() and item.suffix.lower() in PICTURE_EXT:
            who = match_name(item.stem, names)
            if who:
                entry(who)["files"].setdefault(1, str(item))  # a mood folder wins over the single picture
            else:
                unmatched.append({"folder": item.name, "count": 1})
    chars = [{**e, "moods": sorted(e["files"])} for e in found.values()]
    missing = [n for n in names if n not in found]
    return {"folder": str(root), "characters": chars, "unmatched": unmatched, "missing": missing}


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", norm(name)).strip("_") or "character"


def apply(scan_result: dict, labels_of: dict[str, dict[int, str]], dest: Path, url_base: str,
          overrides: dict[str, str] | None = None) -> dict[str, dict]:
    """Copy the pictures into `dest` and return {character: portraits} ready for the card.

    `overrides` maps an unmatched folder name to a character (picked by hand in the preview).
    `labels_of` gives each character's own mood labels by number (else the standard six)."""
    root = Path(scan_result["folder"])
    chars = {c["character"]: dict(c["files"]) for c in scan_result["characters"]}
    for folder, who in (overrides or {}).items():
        if not who:
            continue
        p = root / folder
        files = {}
        if p.is_dir():
            for f in p.iterdir():
                n = _number(f.stem)
                if f.is_file() and f.suffix.lower() in PICTURE_EXT and n is not None and 1 <= n <= 12:
                    files[n] = str(f)
        elif p.is_file():
            files[1] = str(p)
        chars.setdefault(who, {}).update({int(k): v for k, v in files.items()})
    out: dict[str, dict] = {}
    for who, files in chars.items():
        folder = dest / _safe(who)
        folder.mkdir(parents=True, exist_ok=True)
        urls: dict[int, str] = {}
        for n, src in sorted(files.items()):
            data = Path(src).read_bytes()
            ext = sniff_type(data)
            if not ext or len(data) > MAX_IMAGE_BYTES:
                continue  # not a picture, or too large: skipped
            for old in folder.glob(f"{n}.*"):
                old.unlink()
            (folder / f"{n}{ext}").write_bytes(data)
            urls[int(n)] = f"{url_base}/{_safe(who)}/{n}{ext}"
        if not urls:
            continue
        labels = {**STANDARD_LABELS, **(labels_of.get(who) or {})}
        moods = []
        for n in sorted(set(labels) | set(urls)):
            url = urls.get(n) or next((urls[f] for f in FALLBACK.get(n, []) if f in urls), "") or urls[min(urls)]
            moods.append({"n": n, "label": labels.get(n, f"Mood {n}"), "url": url})
        out[who] = {"default": urls.get(1) or urls[min(urls)], "moods": moods[:12]}
    return out


def remove_card_pictures(dest: Path) -> None:
    if dest.is_dir():
        shutil.rmtree(dest, ignore_errors=True)


def card_folder(root: Path, card_name: str, existing: str = "") -> Path:
    """Calíope's own folder for a card's pictures: <Calíope>/Pictures/<card name>/ (kept if the card is renamed)."""
    clean = re.sub(r"\s+", " ", re.sub(r'[<>:"/\\|?*\x00-\x1f]+', " ", str(card_name or "Card"))).strip(" .")
    name = existing or clean[:60] or "Card"
    folder = root / name
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def import_folder(src: str, dest: Path) -> dict:
    """Copy a folder of character pictures from anywhere on the PC into the card's Calíope folder.

    Same layout as `scan` (a folder per character with numbered moods, or Name.png). Files with the same name are
    replaced, so finishing more pictures and importing again just updates them. Returns how much was copied."""
    root = Path(str(src or "").strip().strip('"')).expanduser()
    if not root.is_dir():
        raise ValueError(f"Folder not found: {src}")
    if root.resolve() == dest.resolve() or dest.resolve() in root.resolve().parents:
        return {"characters": 0, "pictures": 0}  # it already is the card's folder
    chars = pics = 0
    for item in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if item.is_dir():
            files = [f for f in item.iterdir() if f.is_file() and f.suffix.lower() in PICTURE_EXT
                     and _number(f.stem) is not None and f.stat().st_size <= MAX_IMAGE_BYTES]
            if not files:
                continue
            (dest / item.name).mkdir(parents=True, exist_ok=True)
            for f in files:
                for old in (dest / item.name).glob(f"{f.stem}.*"):  # 2.jpg replaces an older 2.png
                    old.unlink()
                shutil.copyfile(f, dest / item.name / f.name)
                pics += 1
            chars += 1
        elif item.is_file() and item.suffix.lower() in PICTURE_EXT and item.stat().st_size <= MAX_IMAGE_BYTES:
            shutil.copyfile(item, dest / item.name)
            pics += 1
            chars += 1
    return {"characters": chars, "pictures": pics}

