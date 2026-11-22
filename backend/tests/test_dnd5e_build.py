"""Rules checks on add, the builder's steps and level-ups."""
import unittest

from app.dnd5e import build
from app.dnd5e.character import derive, new_character
from tests.dnd5e_fixture import fixture_library, ref
from tests.test_dnd5e_character import aster

LIB = fixture_library()
E = lambda kind, name: LIB.items[(kind, name.lower(), "PHB")]  # noqa: E731


class CheckTests(unittest.TestCase):
    def test_heavy_armor_master_needs_heavy_armor(self):
        self.assertEqual(build.check_add(aster(), E("feat", "Heavy Armor Master"), "feat", LIB), "")  # fighters wear heavy armour
        wiz = new_character()
        wiz.update(cls=ref("Wizard"), race=ref("Human"))
        self.assertIn("heavy armor", build.check_add(wiz, E("feat", "Heavy Armor Master"), "feat", LIB))

    def test_third_level_spell_refused_at_level1(self):
        wiz = new_character()
        wiz.update(cls=ref("Wizard"), race=ref("Human"))
        self.assertIn("level 3", build.check_add(wiz, E("spell", "Fireball"), "spell", LIB))
        self.assertEqual(build.check_add(wiz, E("spell", "Magic Missile"), "spell", LIB), "")
        wiz["level"] = 5
        self.assertEqual(build.check_add(wiz, E("spell", "Fireball"), "spell", LIB), "")

    def test_class_feature_above_level(self):
        self.assertIn("level 2", build.check_add(aster(), E("classFeature", "Action Surge"), "classFeature", LIB))


class BuilderTests(unittest.TestCase):
    def test_builder_steps_fighter(self):
        c = new_character()
        steps = {s["id"]: s for s in build.builder_steps(c, LIB)}
        self.assertFalse(steps["class"]["done"])
        c.update(cls=ref("Fighter"), race=ref("Human"), background=ref("Soldier"))
        steps = {s["id"]: s for s in build.builder_steps(c, LIB)}
        self.assertTrue(steps["class"]["done"])
        self.assertEqual(steps["skills"]["count"], 2)
        self.assertIn("perception", steps["skills"]["options"])
        self.assertNotIn("athletics", steps["skills"]["options"])  # already from Soldier
        self.assertEqual(steps["style"]["count"], 1)
        self.assertIn("Defense", steps["style"]["options"])
        self.assertEqual(build.ABILITY_METHODS["standard"], [15, 14, 13, 12, 10, 8])


class LevelUpTests(unittest.TestCase):
    def test_level3_needs_subclass(self):
        c = aster(level=2)
        plan = build.level_up_plan(c, LIB)
        self.assertEqual((plan["to_level"], plan["hp_average"]), (3, 6))
        self.assertEqual(plan["choices"][0]["kind"], "subclass")
        self.assertIn("Champion", plan["choices"][0]["options"])
        with self.assertRaises(ValueError):
            build.apply_level_up(c, {"hp": "average"}, LIB)
        up = build.apply_level_up(c, {"hp": "average", "subclass": "Champion"}, LIB)
        self.assertEqual((up["level"], up["subclass"]["name"]), (3, "Champion"))

    def test_missed_subclass_is_asked_at_the_next_level(self):
        c = aster(level=3)  # a converted sheet: level 3 but no subclass yet
        plan = build.level_up_plan(c, LIB)
        self.assertEqual(plan["to_level"], 4)
        self.assertIn("subclass", [ch["kind"] for ch in plan["choices"]])

    def test_level_up_raises_current_hp(self):
        c = aster(level=1)
        c["hp"]["current"] = 5
        up = build.apply_level_up(c, {"hp": {"roll": 9}}, LIB)
        self.assertEqual(up["hp"]["rolls"], [9])
        self.assertEqual(derive(up, LIB)["hp"], 5 + 9 + 3)

    def test_asi_at_level4(self):
        c = aster(level=3, subclass=ref("Champion"))
        plan = build.level_up_plan(c, LIB)
        self.assertEqual(plan["choices"][0]["kind"], "asi_or_feat")
        up = build.apply_level_up(c, {"hp": "average", "asi_or_feat": {"asi": {"str": 2}}}, LIB)
        self.assertEqual(derive(up, LIB)["abilities"]["str"]["score"], 20)

    def test_no_level_21(self):
        c = aster(level=20)
        with self.assertRaises(ValueError):
            build.level_up_plan(c, LIB)
