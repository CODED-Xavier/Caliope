"""Step 6: daily backups and .caliope card files."""
import datetime as dt
import io
import sqlite3
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path

from app import backups
from app.db import Database

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 40


class BackupTests(unittest.TestCase):
    def test_daily_copy_and_keep(self):
        root = Path(tempfile.mkdtemp())
        db = Database(root / "rpg.db")
        db.execute("INSERT INTO settings(key, value) VALUES('x', '1')")
        for day in range(1, 11):
            backups.backup_now(db.conn, db._lock, db.path, keep=7, today=dt.date(2026, 11, day))
        names = [b["name"] for b in backups.list_backups(db.path)]
        self.assertEqual(len(names), 7)
        self.assertEqual(names[0], "rpg-2026-11-10.db")
        self.assertIsNone(backups.backup_now(db.conn, db._lock, db.path, today=dt.date(2026, 11, 10)))  # once a day
        copy = sqlite3.connect(root / "backups" / "rpg-2026-11-10.db")
        self.assertEqual(copy.execute("SELECT value FROM settings WHERE key='x'").fetchone()[0], "1")
        copy.close()

    def test_memory_db_is_skipped(self):
        db = Database(":memory:")
        self.assertIsNone(backups.backup_now(db.conn, threading.RLock(), db.path))


class CaliopeFileTests(unittest.TestCase):
    def test_round_trip(self):
        root = Path(tempfile.mkdtemp())
        pics = root / "cardpics"
        (pics / "3" / "artemis").mkdir(parents=True)
        (pics / "3" / "artemis" / "1.png").write_bytes(PNG)
        data = {"name": "Lumencia", "npcs": [{"name": "Artemis", "portraits": {
            "default": "/api/cardpics/3/artemis/1.png",
            "moods": [{"n": 1, "label": "Standard", "url": "/api/cardpics/3/artemis/1.png"},
                      {"n": 2, "label": "Happy", "url": "https://example.com/happy.png"}]}}],
            "starts": [{"name": "Cult member"}]}
        raw = backups.pack_card(data, "Lumencia", {"/api/cardpics/": pics}, root / "cache")
        z = zipfile.ZipFile(io.BytesIO(raw))
        self.assertEqual(sorted(z.namelist()), ["card.json", "pictures/1.png"])  # the same picture is packed once
        name, back = backups.unpack_card(raw, root / "out", "/api/cardpics/9/imported")
        self.assertEqual(name, "Lumencia")
        p = back["npcs"][0]["portraits"]
        self.assertEqual(p["default"], "/api/cardpics/9/imported/1.png")
        self.assertEqual(p["moods"][1]["url"], "https://example.com/happy.png")   # public links stay links
        self.assertEqual(back["starts"][0]["name"], "Cult member")
        self.assertTrue((root / "out" / "1.png").is_file())

    def test_bad_files(self):
        root = Path(tempfile.mkdtemp())
        with self.assertRaises(ValueError):
            backups.unpack_card(b"not a zip", root, "/x")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("card.json", '{"data": {"npcs": [{"name": "A", "portraits": {"default": "caliope:../../evil.png"}}]}}')
        _, data = backups.unpack_card(buf.getvalue(), root / "out", "/x")
        self.assertEqual(data["npcs"][0]["portraits"]["default"], "")                 # path tricks are refused
        self.assertFalse((root / "evil.png").exists())


if __name__ == "__main__":
    unittest.main()
