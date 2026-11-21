"""Daily backups of your games, and .caliope card files.

Backups: once a day (at start and while the app runs) a copy of the whole database goes to data/backups,
named by date; the newest few are kept. SQLite's own backup copies a consistent picture even while you play.
To restore: close Calíope, copy a backup over data/rpg.db (keep the old file somewhere first), start again.

.caliope files: one file with a card and its pictures inside (a zip), to share a card without GitHub or the cloud.
"""
from __future__ import annotations

import datetime as dt
import io
import json
import re
import sqlite3
import zipfile
from pathlib import Path

from .images import MAX_IMAGE_BYTES, find_cached, sniff_type

BACKUP_RE = re.compile(r"^rpg-(\d{4}-\d{2}-\d{2})\.db$")
CALIOPE_VERSION = 1
MAX_FILES = 600
MAX_CARD_JSON = 20 * 2**20  # the card text itself (a zip can pack a huge file into a small one)


# ------------------------------------------------------------------ backups
def backup_dir(db_path: str | Path) -> Path:
    return Path(db_path).parent / "backups"


def list_backups(db_path: str | Path) -> list[dict]:
    d = backup_dir(db_path)
    out = []
    for p in sorted(d.glob("rpg-*.db"), reverse=True) if d.is_dir() else []:
        if BACKUP_RE.match(p.name):
            out.append({"name": p.name, "date": BACKUP_RE.match(p.name).group(1), "size_mb": round(p.stat().st_size / 1e6, 1)})
    return out


def backup_now(conn: sqlite3.Connection, lock, db_path: str | Path, keep: int = 7, today: dt.date | None = None,
               force: bool = False) -> dict | None:
    """Copy the database to backups/rpg-<date>.db unless today's copy exists (or `force`). Old copies past `keep` go."""
    if str(db_path) == ":memory:":
        return None
    d = backup_dir(db_path)
    d.mkdir(parents=True, exist_ok=True)
    day = (today or dt.date.today()).isoformat()
    target = d / f"rpg-{day}.db"
    if target.exists() and not force:
        return None
    tmp = target.with_suffix(".tmp")
    dest = sqlite3.connect(tmp)
    try:
        with lock:
            conn.backup(dest)
    finally:
        dest.close()
    tmp.replace(target)
    for old in list_backups(db_path)[max(1, int(keep)):]:
        (d / old["name"]).unlink(missing_ok=True)
    return {"name": target.name, "date": day}


# ------------------------------------------------------------------ .caliope card files
def _local_file(url: str, roots: dict[str, Path], cache_dir: Path) -> Path | None:
    for prefix, root in roots.items():
        if url.startswith(prefix):
            p = (root / url[len(prefix):]).resolve()
            if root.resolve() in p.parents and p.is_file():
                return p
    if url.startswith(("http://", "https://", "r2:")):
        return find_cached(cache_dir, url)  # a downloaded copy, if the picture was ever shown
    return None


def pack_card(data: dict, name: str, roots: dict[str, Path], cache_dir: Path) -> bytes:
    """A .caliope file: card.json plus every picture the card uses that exists on this PC."""
    data = json.loads(json.dumps(data))
    buf = io.BytesIO()
    packed: dict[str, str] = {}
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        def pack(url: str) -> str:
            if not url:
                return url
            if url in packed:
                return packed[url]
            p = _local_file(url, roots, cache_dir)
            if not p:
                return url  # a public link stays a link
            entry = f"pictures/{len(packed) + 1}{p.suffix.lower()}"
            z.write(p, entry)
            packed[url] = f"caliope:{entry}"
            return packed[url]

        for npc in data.get("npcs", []):
            pt = npc.get("portraits") or {}
            pt["default"] = pack(pt.get("default") or "")
            for m in pt.get("moods") or []:
                m["url"] = pack(m.get("url") or "")
        for place in data.get("places") or []:
            place["picture"] = pack(place.get("picture") or "")
        z.writestr("card.json", json.dumps({"caliope": CALIOPE_VERSION, "name": name, "data": data}, ensure_ascii=False, indent=1))
    return buf.getvalue()


def unpack_card(raw: bytes, dest: Path, url_base: str) -> tuple[str, dict]:
    """Read a .caliope file: (name, card data) with its pictures saved under `dest` (served at `url_base`)."""
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise ValueError("This is not a .caliope card file.") from exc
    with z:
        names = z.namelist()
        if "card.json" not in names or len(names) > MAX_FILES:
            raise ValueError("This is not a .caliope card file.")
        if z.getinfo("card.json").file_size > MAX_CARD_JSON:
            raise ValueError("The card inside the file is damaged.")
        meta = json.loads(z.read("card.json").decode("utf-8"))
        if not isinstance(meta, dict) or not isinstance(meta.get("data"), dict):
            raise ValueError("The card inside the file is damaged.")
        saved: dict[str, str] = {}

        def unpack(url: str) -> str:
            if not str(url).startswith("caliope:"):
                return url
            entry = url[len("caliope:"):]
            if url in saved:
                return saved[url]
            if not re.fullmatch(r"pictures/\d{1,4}\.(png|jpg|jpeg|webp|gif)", entry) or entry not in names:
                return ""
            info = z.getinfo(entry)
            if info.file_size > MAX_IMAGE_BYTES:
                return ""
            data = z.read(entry)
            ext = sniff_type(data)
            if not ext:
                return ""
            dest.mkdir(parents=True, exist_ok=True)
            fname = f"{Path(entry).stem}{ext}"
            (dest / fname).write_bytes(data)
            saved[url] = f"{url_base}/{fname}"
            return saved[url]

        data = meta["data"]
        for npc in data.get("npcs", []) if isinstance(data.get("npcs"), list) else []:
            pt = npc.get("portraits") if isinstance(npc, dict) else None
            if not isinstance(pt, dict):
                continue
            pt["default"] = unpack(pt.get("default") or "")
            for m in pt.get("moods") or []:
                if isinstance(m, dict):
                    m["url"] = unpack(m.get("url") or "")
        for place in data.get("places") if isinstance(data.get("places"), list) else []:
            if isinstance(place, dict):
                place["picture"] = unpack(place.get("picture") or "")
        return str(meta.get("name") or data.get("name") or "Imported card"), data
