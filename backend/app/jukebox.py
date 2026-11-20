"""Jukebox: your music library and the mood of each scene.

Songs come from your PC (stored in backend/data/music) or from direct audio links. Each song has mood tags.
The tracker names the scene's mood every turn (or a quick keyword check does, when the tracker is off), and the
player in the interface fades into a song with that tag. Fights always play combat music.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .util import now, truncate

MOODS = ("calm", "tavern", "exploration", "town", "forest", "dungeon", "mystery", "tension", "combat", "boss",
         "victory", "sad", "romantic", "horror", "epic")
MAX_AUDIO_BYTES = 40 * 1024 * 1024
FILE_NAME = r"^[0-9a-f]{40}\.(mp3|ogg|wav|flac|m4a|webm)$"


class MusicError(ValueError):
    pass


def sniff_audio(data: bytes) -> str | None:
    """The real audio type from the first bytes."""
    if data[:3] == b"ID3" or (len(data) > 1 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0):
        return ".mp3"
    if data[:4] == b"OggS":
        return ".ogg"
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return ".wav"
    if data[:4] == b"fLaC":
        return ".flac"
    if data[4:8] == b"ftyp":
        return ".m4a"
    if data[:4] == b"\x1aE\xdf\xa3":
        return ".webm"
    return None


def clean_tags(tags) -> list[str]:
    out: list[str] = []
    for t in tags if isinstance(tags, list) else str(tags or "").split(","):
        t = str(t).strip().lower()
        if t in MOODS and t not in out:
            out.append(t)
    return out


# Keyword check used when the tracker is off (or did not name a mood).
_MOOD_WORDS = {
    "combat": r"\b(attack|sword|blade|fight|battle|strike|arrow|blood|charge|parry|dodge)\w*",
    "horror": r"\b(scream|corpse|rot|shadow\w* move|whisper\w* in the dark|dread|ghoul|undead|nightmare)\w*",
    "tavern": r"\b(tavern|inn|ale|mug|bartender|innkeeper|stew|bard)\w*",
    "town": r"\b(market|street|square|guard|merchant|shop|crowd|city|village)\w*",
    "forest": r"\b(forest|trees|woods|leaves|grove|path through)\w*",
    "dungeon": r"\b(dungeon|crypt|tomb|corridor|cell|torch\w* flicker|stone stairs)\w*",
    "mystery": r"\b(clue|strange|secret|riddle|hidden|mysterious|letter)\w*",
    "tension": r"\b(silence|footsteps|watch\w*|hold your breath|careful|trap|ambush)\w*",
    "sad": r"\b(tears|grief|funeral|mourn|loss|cry|weep)\w*",
    "romantic": r"\b(kiss|blush|heart\w* race|gentle touch|embrace)\w*",
    "victory": r"\b(victory|triumph|cheer|celebrat|reward)\w*",
}


def guess_mood(text: str) -> str:
    low = (text or "").lower()
    scores = {m: len(re.findall(p, low)) for m, p in _MOOD_WORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] >= 2 else ""


class MusicLibrary:
    def __init__(self, db, music_dir: Path):
        self.db = db
        self.dir = Path(music_dir)

    def list(self) -> list[dict]:
        return [self._row(r) for r in self.db.query("SELECT * FROM tracks ORDER BY name COLLATE NOCASE")]

    def get(self, track_id: int) -> dict:
        row = self.db.query_one("SELECT * FROM tracks WHERE id = ?", (track_id,))
        if not row:
            raise MusicError(f"Song {track_id} not found.")
        return self._row(row)

    @staticmethod
    def _row(r) -> dict:
        return {"id": r["id"], "name": r["name"], "url": r["url"] or f"/api/music/files/{r['file']}",
                "source": "link" if r["url"] else "file", "tags": json.loads(r["tags"] or "[]"),
                "cards": json.loads(r["cards"] or "[]")}

    def _insert(self, name: str, url: str, file: str, tags, cards) -> dict:
        cur = self.db.execute("INSERT INTO tracks(name, url, file, tags, cards, created_at) VALUES(?,?,?,?,?,?)",
                              (truncate(name.strip() or "Song", 80), url, file, json.dumps(clean_tags(tags)),
                               json.dumps(_ids(cards)), now()))
        return self.get(cur.lastrowid)

    def add_file(self, data: bytes, name: str, tags=None, cards=None) -> dict:
        if not data:
            raise MusicError("The file is empty.")
        if len(data) > MAX_AUDIO_BYTES:
            raise MusicError("The song is larger than 40 MB.")
        ext = sniff_audio(data)
        if not ext:
            raise MusicError("That file is not MP3, OGG, WAV, FLAC, M4A or WebM audio.")
        self.dir.mkdir(parents=True, exist_ok=True)
        fname = hashlib.sha1(data).hexdigest() + ext
        if not (self.dir / fname).exists():
            (self.dir / fname).write_bytes(data)
        return self._insert(name, "", fname, tags, cards)

    def add_link(self, url: str, name: str, tags=None, cards=None) -> dict:
        url = (url or "").strip()
        if not re.match(r"^https?://", url, re.I):
            raise MusicError("The link must start with http:// or https://")
        if re.search(r"(youtube\.com|youtu\.be|spotify\.com|soundcloud\.com)", url, re.I):
            raise MusicError("YouTube, Spotify and SoundCloud pages cannot be played here. Use a direct link to an audio file "
                             "(ending in .mp3 or .ogg), or download the song and add the file.")
        return self._insert(name or url.rsplit("/", 1)[-1], url[:600], "", tags, cards)

    def update(self, track_id: int, name=None, tags=None, cards=None) -> dict:
        self.get(track_id)
        if name is not None and str(name).strip():
            self.db.execute("UPDATE tracks SET name = ? WHERE id = ?", (truncate(str(name).strip(), 80), track_id))
        if tags is not None:
            self.db.execute("UPDATE tracks SET tags = ? WHERE id = ?", (json.dumps(clean_tags(tags)), track_id))
        if cards is not None:
            self.db.execute("UPDATE tracks SET cards = ? WHERE id = ?", (json.dumps(_ids(cards)), track_id))
        return self.get(track_id)

    def delete(self, track_id: int) -> None:
        row = self.db.query_one("SELECT file FROM tracks WHERE id = ?", (track_id,))
        if not row:
            raise MusicError(f"Song {track_id} not found.")
        self.db.execute("DELETE FROM tracks WHERE id = ?", (track_id,))
        if row["file"] and not self.db.query_one("SELECT id FROM tracks WHERE file = ?", (row["file"],)):
            try:
                (self.dir / row["file"]).unlink()
            except OSError:
                pass

    def file_path(self, name: str) -> Path | None:
        if not re.match(FILE_NAME, name or ""):
            return None
        p = self.dir / name
        return p if p.is_file() else None


def _ids(raw) -> list[int]:
    out: list[int] = []
    for v in raw if isinstance(raw, list) else []:
        try:
            n = int(v)
        except (TypeError, ValueError):
            continue
        if n > 0 and n not in out:
            out.append(n)
    return out
