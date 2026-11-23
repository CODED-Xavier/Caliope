"""Magic only for classes that have it: SRD class spell lists (or your 5e.tools sources.json), checked when a spell
goes on the sheet and used to filter the Library's spell list."""
import json
import tempfile
import unittest
from pathlib import Path

from app.dnd5e import build, spell_lists
from app.dnd5e.character import new_character
from app.dnd5e.library import Library

SEED = Path(__file__).resolve().parents[1] / "app/seed/srd5e.json"


def srd():
    lib = Library([SEED])
    lib.load()
    return lib


def char(cls, level=5, subclass=None):
    c = new_character("2014")
    c["cls"] = {"name": cls, "source": "PHB"}
    c["level"] = level
    if subclass:
        c["subclass"] = {"name": subclass, "source": "PHB"}
    return c


class ListTests(unittest.TestCase):
    def test_srd_lists_and_phb_names(self):
        self.assertEqual(spell_lists.classes_for("Fireball"), {"Sorcerer", "Wizard"})
        self.assertIn("Bard", spell_lists.classes_for("Tasha's Hideous Laughter"))
        self.assertEqual(spell_lists.classes_for("Bigby's Hand"), {"Wizard"})
        self.assertIsNone(spell_lists.classes_for("Booming Blade"))  # not SRD: unknown, not blocked

    def test_sources_file_wins(self):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "sources.json").write_text(json.dumps({"TCE": {"Booming Blade": {"class": [{"name": "Wizard", "source": "PHB"}],
                                                                                "classVariant": [{"name": "Artificer"}]}}}))
        lib = Library([SEED, tmp])
        lib.load()
        self.assertEqual(spell_lists.classes_for("Booming Blade", lib), {"Wizard", "Artificer"})


class CheckTests(unittest.TestCase):
    def setUp(self):
        self.lib = srd()

    def spell(self, name):
        return next(e for (k, n, _), e in self.lib.items.items() if k == "spell" and n == name.lower())

    def test_barbarian_gets_no_magic(self):
        self.assertIn("don't cast spells", build.check_add(char("Barbarian"), self.spell("Fire Bolt"), "spell", self.lib))

    def test_class_list(self):
        self.assertIn("isn't on the Cleric spell list", build.check_add(char("Cleric"), self.spell("Fireball"), "spell", self.lib))
        self.assertEqual(build.check_add(char("Wizard"), self.spell("Fireball"), "spell", self.lib), "")
        self.assertEqual(build.check_add(char("Cleric"), self.spell("Spirit Guardians"), "spell", self.lib), "")

    def test_library_filter(self):
        names = {r["name"] for r in self.lib.search("spell", "", "2014", 500, cls="Paladin", max_level=1)}
        self.assertIn("Bless", names)
        self.assertNotIn("Fireball", names)
        self.assertNotIn("Aid", names)  # level 2
        card = next(r for r in self.lib.search("spell", "fireball", "2014") if r["name"] == "Fireball")
        self.assertEqual(card["classes"], ["Sorcerer", "Wizard"])


if __name__ == "__main__":
    unittest.main()


class BuilderStepTest(unittest.TestCase):
    def test_spells_step_only_for_casters(self):
        lib = srd()
        ids = [s["id"] for s in build.builder_steps(char("Barbarian"), lib)]
        self.assertNotIn("spells", ids)
        wiz = next(s for s in build.builder_steps(char("Wizard", 5), lib) if s["id"] == "spells")
        self.assertEqual((wiz["list"], wiz["max_level"]), ("Wizard", 3))
