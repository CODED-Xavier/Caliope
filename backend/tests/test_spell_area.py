"""The map's 🔥 area tool gets each spell's shape: from its range (self) or its text (a point)."""
import json
import unittest
from pathlib import Path

from app.dnd5e.actions import spell_area

SRD = {e["name"]: e for e in json.loads((Path(__file__).resolve().parents[1] / "app/seed/srd5e.json").read_text())["spell"]}


class SpellAreaTest(unittest.TestCase):
    def test_shapes(self):
        self.assertEqual(spell_area(SRD["Fireball"]), {"shape": "sphere", "size": 20, "width": 5, "origin": "point"})
        self.assertEqual(spell_area(SRD["Burning Hands"]), {"shape": "cone", "size": 15, "width": 5, "origin": "self"})
        self.assertEqual(spell_area(SRD["Lightning Bolt"]), {"shape": "line", "size": 100, "width": 5, "origin": "self"})
        self.assertEqual(spell_area(SRD["Thunderwave"]), {"shape": "cube", "size": 15, "width": 5, "origin": "self"})
        self.assertIsNone(spell_area(SRD["Fire Bolt"]))
        self.assertEqual(spell_area(SRD["Shatter"])["size"], 10)


if __name__ == "__main__":
    unittest.main()
