"""The 5e character engine: every number worked out from the character's references and choices."""
import unittest

from app.dnd5e.character import derive, new_character
from tests.dnd5e_fixture import fixture_library, ref

LIB = fixture_library()


def item(name, equipped=True, qty=1):
    return {"type": "baseitem", "name": name, "source": "PHB", "qty": qty, "equipped": equipped}


def aster(level=1, **over):
    c = new_character()
    c.update(cls=ref("Fighter"), level=level, race=ref("Human"), background=ref("Soldier"),
             scores={"str": 17, "dex": 14, "con": 16, "int": 10, "wis": 13, "cha": 12})
    c["options"] = [{"type": "optionalfeature", **ref("Defense")}]
    c["items"] = [item("Chain Mail"), item("Shield"), item("Longsword")]
    c["picks"]["skills"] = ["perception", "survival"]
    c.update(over)
    return c


class BasicsTests(unittest.TestCase):
    def test_fighter_aster(self):
        s = derive(aster(), LIB)
        self.assertEqual((s["abilities"]["str"]["score"], s["abilities"]["str"]["mod"]), (18, 4))  # Human +1
        self.assertEqual(s["prof"], 2)
        self.assertEqual(s["ac"], 19)
        self.assertIn("Chain Mail 16", s["ac_how"])
        self.assertEqual(s["hp_max"], 13)  # d10 + CON 17 (+3)
        self.assertEqual(s["saves"]["str"], 6)
        self.assertEqual(s["saves"]["dex"], 2)
        self.assertTrue(s["skills"]["athletics"]["proficient"])  # from Soldier
        self.assertEqual(s["skills"]["perception"]["bonus"], 2 + 2)  # WIS 13+1 = 14 (+2), proficient +2
        self.assertEqual(s["speed"], 30)
        self.assertEqual(s["passive_perception"], 10 + s["skills"]["perception"]["bonus"])

    def test_medium_armor_dex_cap(self):
        c = aster(scores={"str": 10, "dex": 18, "con": 10, "int": 10, "wis": 10, "cha": 10})
        c["items"] = [item("Scale Mail")]
        c["options"] = []
        self.assertEqual(derive(c, LIB)["ac"], 14 + 2)

    def test_unarmored_defense_barbarian(self):
        c = new_character()
        c.update(cls=ref("Barbarian"), level=1, race=ref("Dwarf"), subrace=ref("Hill"),
                 scores={"str": 15, "dex": 14, "con": 14, "int": 8, "wis": 10, "cha": 10})
        s = derive(c, LIB)
        self.assertEqual(s["abilities"]["con"]["score"], 16)  # Dwarf +2
        self.assertEqual(s["abilities"]["wis"]["score"], 11)  # Hill +1
        self.assertEqual(s["ac"], 10 + 2 + 3)
        self.assertEqual(s["speed"], 25)

    def test_hp_with_rolls_and_average(self):
        c = aster(level=3)
        c["hp"]["rolls"] = [8]  # level 2 rolled 8, level 3 takes the average (6)
        self.assertEqual(derive(c, LIB)["hp_max"], 10 + 3 + 8 + 3 + 6 + 3)

    def test_missing_entry_is_a_warning(self):
        c = aster()
        c["items"].append(item("Vorpal Spoon"))
        s = derive(c, LIB)
        self.assertTrue(any("Vorpal Spoon" in w for w in s["warnings"]))
        self.assertEqual(s["ac"], 19)

    def test_two_armours_best_counts(self):
        c = aster()
        c["items"].append(item("Leather Armor"))
        s = derive(c, LIB)
        self.assertEqual(s["ac"], 19)
        self.assertTrue(any("Leather Armor" in w for w in s["warnings"]))



class CombatNumbersTests(unittest.TestCase):
    def test_longsword_versatile_and_shield(self):
        att = derive(aster(), LIB)["attacks"]
        self.assertEqual((att[0]["name"], att[0]["bonus"], att[0]["damage"]), ("Longsword", 6, "1d8+4"))
        c = aster()
        c["items"] = [item("Chain Mail"), item("Longsword")]
        self.assertEqual(derive(c, LIB)["attacks"][0]["damage"], "1d10+4")

    def test_finesse_uses_dex(self):
        c = aster(scores={"str": 10, "dex": 16, "con": 12, "int": 10, "wis": 10, "cha": 10})
        c["items"] = [item("Rapier")]
        a = derive(c, LIB)["attacks"][0]
        self.assertEqual((a["ability"], a["bonus"], a["damage"]), ("dex", 3 + 2, "1d8+3"))

    def test_archery_and_dueling(self):
        c = aster(options=[{"type": "optionalfeature", "name": "Archery", "source": "PHB"}])
        c["items"] = [item("Longbow")]
        self.assertEqual(derive(c, LIB)["attacks"][0]["bonus"], 2 + 2 + 2)  # DEX +2, proficient +2, Archery +2
        c = aster(options=[{"type": "optionalfeature", "name": "Dueling", "source": "PHB"}])
        self.assertEqual(derive(c, LIB)["attacks"][0]["damage"], "1d8+6")

    def test_second_wind_uses(self):
        c = aster()
        c["uses"] = {"Second Wind": 1}
        f = {x["name"]: x for x in derive(c, LIB)["features"]}
        self.assertEqual((f["Second Wind"]["uses_max"], f["Second Wind"]["used"], f["Second Wind"]["per"]), (1, 1, "short"))
        self.assertIn("Defense", f)
        self.assertNotIn("Action Surge", f)  # level 2

    def test_features_by_level_and_subclass(self):
        c = aster(level=5, subclass={"name": "Champion", "source": "PHB"})
        names = [x["name"] for x in derive(c, LIB)["features"]]
        self.assertIn("Improved Critical", names)
        self.assertIn("Extra Attack", names)
        self.assertNotIn("Martial Versatility", names)  # an optional TCE feature is not automatic

    def test_rage_by_level(self):
        c = new_character()
        c.update(cls=ref("Barbarian"), level=6, race=ref("Human"))
        f = {x["name"]: x for x in derive(c, LIB)["features"]}
        self.assertEqual(f["Rage"]["uses_max"], 4)

    def test_wizard_slots_level5(self):
        c = new_character()
        c.update(cls=ref("Wizard"), level=5, race=ref("Human"))
        self.assertEqual(derive(c, LIB)["slots"], {1: 4, 2: 3, 3: 2})

    def test_paladin_half_caster_level1_has_no_slots(self):
        c = new_character()
        c.update(cls=ref("Paladin"), level=1, race=ref("Human"))
        self.assertEqual(derive(c, LIB)["slots"], {})
        c["level"] = 5
        self.assertEqual(derive(c, LIB)["slots"], {1: 4, 2: 2})


if __name__ == "__main__":
    unittest.main()
