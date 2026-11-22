"""Book placeholders, and your choices: which entries are hidden, and which rules list a book belongs to."""
import json
import tempfile
import unittest
from pathlib import Path

from app.dnd5e import library as libmod
from app.dnd5e.library import Library

FILES = {
    "Classes/class-druid.json": {
        "class": [{"name": "Druid", "source": "XPHB", "edition": "one", "hd": {"number": 1, "faces": 8}, "classFeatures": []},
                  {"name": "Druid", "source": "WoW", "_copy": {"name": "Druid", "source": "XPHB"}}],  # a placeholder for the book's subclasses
    },
    "Races/races.json": {"race": [{"name": "Tauren", "source": "WoW", "speed": 30}, {"name": "Goblin", "source": "VGM", "speed": 30},
                                  {"name": "Goblin", "source": "MPMM", "speed": 30}]},
}


def lib(choices=None):
    tmp = tempfile.mkdtemp()
    for rel, data in FILES.items():
        p = Path(tmp) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data), encoding="utf-8")
    if choices is not None:
        (Path(tmp) / libmod.CHOICES_FILE).write_text(json.dumps(choices), encoding="utf-8")
    out = Library([Path(tmp)])
    out.load()
    return out, tmp


class BookTest(unittest.TestCase):
    def tearDown(self):
        libmod.BOOK_EDITIONS.clear()

    def test_placeholder_classes_are_not_classes(self):
        names = [(c["name"], c["source"]) for c in lib()[0].search("class", "", "2024")]
        self.assertEqual(names, [("Druid", "XPHB")])

    def test_a_book_can_be_put_in_a_rules_list(self):
        l, _ = lib({"editions": {"WoW": "2024"}})
        self.assertIn("Tauren", [r["name"] for r in l.search("race", "", "2024")])
        self.assertNotIn("Tauren", [r["name"] for r in l.search("race", "", "2014")])
        l, _ = lib({"editions": {"WoW": "both"}})
        self.assertIn("Tauren", [r["name"] for r in l.search("race", "", "2014")])
        self.assertIn("Tauren", [r["name"] for r in l.search("race", "", "2024")])

    def test_hidden_entries_leave_the_lists_but_still_work_on_sheets(self):
        l, _ = lib({"hidden": ["race|Goblin|VGM"]})
        self.assertEqual([r["source"] for r in l.search("race", "goblin", "2014")], ["MPMM"])
        self.assertIsNotNone(l.get("race", "VGM", "Goblin"))  # a sheet that already uses it keeps working

    def test_the_library_window_can_list_hidden_ones_and_books(self):
        l, _ = lib({"hidden": ["race|Goblin|VGM"]})
        cards = l.search("race", "goblin", "2014", include_hidden=True)
        self.assertEqual({c["source"]: c.get("hidden", False) for c in cards}, {"VGM": True, "MPMM": False})
        self.assertIn("WoW", l.info["books"])

    def test_choices_are_saved_and_reloaded(self):
        l, tmp = lib()
        l.save_choices({"hidden": ["race|Goblin|VGM"], "editions": {"WoW": "both"}})
        again = Library([Path(tmp)])
        again.load()
        self.assertEqual(again.choices["hidden"], ["race|Goblin|VGM"])
        self.assertNotIn("VGM", [r["source"] for r in again.search("race", "goblin", "2014")])


if __name__ == "__main__":
    unittest.main()
