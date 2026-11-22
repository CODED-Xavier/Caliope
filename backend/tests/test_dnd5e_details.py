import unittest

from app.dnd5e import details
from tests.dnd5e_fixture import fixture_library

LIB = fixture_library()


class ClassDetailsTest(unittest.TestCase):
    def test_fighter_levels(self):
        d = details.describe(LIB, "class", "Fighter", "PHB")
        self.assertEqual(d["hit_die"], "d10")
        self.assertEqual(d["saves"], ["STR", "CON"])
        self.assertEqual(d["levels"][0]["features"], ["Fighting Style", "Second Wind"])
        self.assertIn("Martial Archetype", d["levels"][2]["features"])
        self.assertNotIn("Martial Versatility", d["levels"][3]["features"])  # optional TCE rules are not automatic
        self.assertEqual(len(d["levels"]), 20)
        self.assertEqual(d["levels"][4]["prof"], 3)
        self.assertEqual((d["subclass_title"], d["subclass_level"], d["subclasses"]), ("Martial Archetype", 3, ["Champion"]))
        self.assertIn("Choose 2", d["skills"])
        self.assertIn("heavy", d["armor"])

    def test_cleric_spellcasting(self):
        d = details.describe(LIB, "class", "Cleric", "PHB")
        self.assertEqual(d["spellcasting"], "WIS")
        self.assertEqual(d["subclass_level"], 1)
        self.assertEqual(d["levels"][0]["slots"], {"1": 2})


class RaceAndBackgroundDetailsTest(unittest.TestCase):
    def test_elf(self):
        d = details.describe(LIB, "race", "Elf", "PHB")
        self.assertEqual((d["speed"], d["abilities"], d["darkvision"]), (30, "DEX +2", 60))
        self.assertEqual([t["name"] for t in d["traits"]], ["Darkvision", "Fey Ancestry"])

    def test_human_gets_plus_one_everywhere(self):
        self.assertEqual(details.describe(LIB, "race", "Human", "PHB")["abilities"], "+1 to every score")

    def test_acolyte(self):
        d = details.describe(LIB, "background", "Acolyte", "PHB")
        self.assertEqual(d["skills"], ["Insight", "Religion"])
        self.assertEqual(d["feature"]["name"], "Shelter of the Faithful")
        self.assertIn("holy symbol", d["equipment"])
        self.assertIn("common clothes", d["equipment"])

    def test_unknown_entry(self):
        with self.assertRaises(ValueError):
            details.describe(LIB, "class", "Nope", "PHB")


class EquipmentCategoryTest(unittest.TestCase):
    def test_categories_on_cards(self):
        cats = {c["name"]: c.get("category") for c in LIB.search("baseitem", "", "2014", limit=99)}
        self.assertEqual((cats["Longsword"], cats["Chain Mail"], cats["Shield"]), ("weapon", "armor", "armor"))
        self.assertEqual((cats["Rope, Hempen (50 feet)"], cats["Thieves' Tools"]), ("gear", "tools"))

    def test_search_by_category(self):
        names = {c["name"] for c in LIB.search("baseitem", "", "2014", limit=99, category="weapon")}
        self.assertIn("Longsword", names)
        self.assertNotIn("Chain Mail", names)


if __name__ == "__main__":
    unittest.main()


class TagCleaningTest(unittest.TestCase):
    def test_tagged_proficiency(self):
        self.assertEqual(details._clean("{@item shortsword|phb|shortswords}"), "shortswords")
        self.assertEqual(details._clean("light|phb"), "light")
