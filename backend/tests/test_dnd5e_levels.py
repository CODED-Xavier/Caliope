"""Level-up: spells known and prepared by class and level, the class table (what each level gives), resources that
grow, and the new spells chosen when levelling up."""
import unittest
from pathlib import Path

from app.dnd5e import actions, build, levels, store
from app.dnd5e.character import derive, new_character
from app.dnd5e.library import Library

SEED = Path(__file__).resolve().parents[1] / "app/seed/srd5e.json"
LIB = Library([SEED])
LIB.load()


def hero(cls, level, scores=None, spells=()):
    c = new_character("2014")
    c["cls"] = {"name": cls, "source": "PHB"}
    c["level"] = level
    c["scores"] = {**c["scores"], **(scores or {})}
    c["spells"] = [{"type": "spell", "name": s, "source": "PHB"} for s in spells]
    return c


ASI = {"asi": {"cha": 2}}  # Bard 4 also gets an Ability Score Improvement


def with_sub(c, name):
    c["subclass"] = {"name": name, "source": "PHB"}
    return c


def ref(name):
    return {"name": name, "source": "PHB"}


class CountTests(unittest.TestCase):
    def test_known_casters(self):
        c = levels.spell_counts(hero("Bard", 3, {"cha": 16}), LIB)
        self.assertEqual((c["mode"], c["cantrips"], c["known"], c["prepared"]), ("known", 2, 6, None))
        w = levels.spell_counts(hero("Warlock", 5, {"cha": 16}), LIB)
        self.assertEqual((w["cantrips"], w["known"]), (3, 6))

    def test_prepared_casters_use_level_and_modifier(self):
        c = levels.spell_counts(hero("Cleric", 3, {"wis": 16}), LIB)
        self.assertEqual((c["mode"], c["cantrips"], c["prepared"]), ("prepared", 3, 6))
        self.assertEqual(levels.spell_counts(hero("Paladin", 5, {"cha": 14}), LIB)["prepared"], 4)  # 5 / 2 + 2
        self.assertEqual(levels.spell_counts(hero("Paladin", 1, {"cha": 14}), LIB)["prepared"], 0)  # no magic yet
        self.assertEqual(levels.spell_counts(hero("Cleric", 1, {"wis": 8}), LIB)["prepared"], 1)  # at least one

    def test_wizard_spellbook(self):
        c = levels.spell_counts(hero("Wizard", 3, {"int": 16}, ["Fire Bolt", "Magic Missile", "Shield"]), LIB)
        self.assertEqual((c["mode"], c["cantrips"], c["spellbook"], c["prepared"]), ("spellbook", 3, 10, 6))
        self.assertEqual((c["have_cantrips"], c["have_spells"], c["have_prepared"]), (1, 2, 2))

    def test_no_magic(self):
        self.assertIsNone(levels.spell_counts(hero("Fighter", 3), LIB))
        self.assertIsNone(levels.spell_counts(hero("Barbarian", 5), LIB))

    def test_too_many_prepared_is_a_warning(self):
        c = hero("Cleric", 1, {"wis": 16}, ["Bless", "Cure Wounds", "Guiding Bolt", "Healing Word", "Command", "Sanctuary"])
        self.assertTrue(any("prepare" in w for w in derive(c, LIB)["warnings"]))


class TableTests(unittest.TestCase):
    def test_class_columns(self):
        cols = {c["label"]: c["values"] for c in levels.table_columns(build._cls(hero("Barbarian", 1), LIB))}
        self.assertEqual((cols["Rages"][0], cols["Rage Damage"][0], cols["Rage Damage"][8]), ("2", "+2", "+3"))
        cols = {c["label"]: c["values"] for c in levels.table_columns(build._cls(hero("Rogue", 1), LIB))}
        self.assertEqual(cols["Sneak Attack"][4], "3d6")
        cols = {c["label"]: c["values"] for c in levels.table_columns(build._cls(hero("Monk", 1), LIB))}
        self.assertEqual((cols["Martial Arts"][4], cols["Unarmored Movement"][1]), ("1d6", "+10 ft"))
        cols = {c["label"] for c in levels.table_columns(build._cls(hero("Warlock", 1), LIB))}
        self.assertIn("Invocations Known", cols)
        self.assertNotIn("Cantrips Known", cols)  # counted by the app itself (its own row)
        self.assertFalse(any(c.startswith("1st") or c == "Slot Level" for c in cols))  # slots have their own column

    def test_odd_tables_are_skipped(self):
        for bad in (None, 3, [1, "x", None], [{"colLabels": "x", "rows": 5}], [{"colLabels": ["A"], "rows": [[{"type": "dice"}], 7]}]):
            levels.table_columns({"classTableGroups": bad})
        cols = levels.table_columns({"classTableGroups": [{"colLabels": ["A"], "rows": [[{"type": "dice"}], 7]}]})
        self.assertEqual(cols[0]["values"][:3], ["–", "–", "–"])

    def test_odd_spell_tables_do_not_break_the_sheet(self):
        cls = {"name": "Odd", "casterProgression": "full", "cantripProgression": ["x", None, 3],
               "spellsKnownProgression": "nope", "preparedSpells": "<$level$> + <$cha_mod$> + __import__", "spellsKnownProgressionFixedByLevel": {"a": 1, "2": {"6": "y"}, "3": {"6": 1}}}
        got = levels.counts({"spells": []}, cls, None, 1, {"cha": 2}, True, LIB)
        self.assertEqual(got["cantrips"], 0)
        self.assertEqual(got["prepared"], 1)  # a formula with anything but numbers is not run (at least 1)
        self.assertEqual(got["arcanum"], {3: {6: 1}})

    def test_formula_is_arithmetic_only(self):
        self.assertEqual(levels._formula("<$level$> / 2 + <$cha_mod$>", 5, {"cha": 2}), 4)
        self.assertEqual(levels._formula("(<$level$> + 1) * 2 - <$wis_mod$>", 3, {"wis": -1}), 9)
        for bad in ("9**9**9**9", "<$level$> ** 99", "__import__('os')", "1 if 1 else 2", "[1]*999999999", "1/0"):
            self.assertEqual(levels._formula(bad, 5, {}), 0, bad)

    def test_progression_rows(self):
        rows = levels.progression(hero("Paladin", 5, {"cha": 14}), LIB)
        self.assertEqual(len(rows["levels"]), 20)
        r5 = rows["levels"][4]
        self.assertEqual(r5["uses"]["Lay on Hands"], 25)
        self.assertEqual(r5["prepared"], 4)
        self.assertIn("Extra Attack", r5["features"])
        self.assertEqual(rows["current"], 5)


class PlanTests(unittest.TestCase):
    def changes(self, plan):
        return {c["label"]: (c["before"], c["after"]) for c in plan["changes"]}

    def test_bard_learns_a_spell_and_a_cantrip(self):
        plan = build.level_up_plan(hero("Bard", 3, {"cha": 16}), LIB)
        ch = {c["id"]: c for c in plan["choices"]}
        self.assertEqual((ch["spells"]["count"], ch["spells"]["max_level"], ch["spells"]["list"]), (1, 2, "Bard"))
        self.assertEqual(ch["cantrips"]["count"], 1)
        got = self.changes(plan)
        self.assertEqual(got["Cantrips known"], ("2", "3"))
        self.assertEqual(got["Spells known"], ("6", "7"))

    def test_wizard_adds_two_to_the_spellbook(self):
        plan = build.level_up_plan(hero("Wizard", 2, {"int": 16}), LIB)
        ch = {c["id"]: c for c in plan["choices"]}
        self.assertEqual((ch["spells"]["count"], ch["spells"]["max_level"]), (2, 2))
        got = self.changes(plan)
        self.assertEqual(got["Level 2 slots"], ("0", "2"))
        self.assertEqual(got["Level 1 slots"], ("3", "4"))

    def test_cleric_prepares_more_but_chooses_no_spells(self):
        plan = build.level_up_plan(hero("Cleric", 3, {"wis": 16}), LIB)
        ids = [c["id"] for c in plan["choices"]]
        self.assertNotIn("spells", ids)
        self.assertIn("cantrips", ids)
        self.assertEqual(self.changes(plan)["Prepared spells"], ("6", "7"))

    def test_resources_and_proficiency_grow(self):
        got = self.changes(build.level_up_plan(hero("Barbarian", 2, {"str": 16}), LIB))
        self.assertEqual(got["Rages"], ("2", "3"))
        self.assertNotIn("Rage", got)  # the table's column is enough
        got = self.changes(build.level_up_plan(hero("Paladin", 4, {"cha": 14}), LIB))
        self.assertEqual(got["Proficiency bonus"], ("+2", "+3"))
        self.assertEqual(got["Lay on Hands"], ("20", "25"))

    def test_warlock_mystic_arcanum(self):
        ch = {c["id"]: c for c in build.level_up_plan(hero("Warlock", 10, {"cha": 16}), LIB)["choices"]}
        self.assertEqual((ch["arcanum"]["count"], ch["arcanum"]["exact_level"]), (1, 6))


class ApplyTests(unittest.TestCase):
    def test_new_spells_go_on_the_sheet(self):
        c = with_sub(hero("Bard", 3, {"cha": 16}, ["Vicious Mockery", "Healing Word"]), "College of Lore")
        new = build.apply_level_up(c, {"hp": "average", "asi_or_feat": ASI, "spells": [ref("Hold Person")], "cantrips": [ref("Dancing Lights")]}, LIB)
        names = [s["name"] for s in new["spells"]]
        self.assertIn("Hold Person", names)
        self.assertIn("Dancing Lights", names)
        self.assertEqual(new["level"], 4)

    def test_spell_choices_are_checked(self):
        c = with_sub(hero("Bard", 3, {"cha": 16}), "College of Lore")
        with self.assertRaises(ValueError):  # too high for a level 4 Bard
            build.apply_level_up(c, {"hp": "average", "asi_or_feat": ASI, "spells": [ref("Fireball")]}, LIB)
        with self.assertRaises(ValueError):  # not on the Bard list
            build.apply_level_up(c, {"hp": "average", "asi_or_feat": ASI, "spells": [ref("Magic Missile")]}, LIB)
        with self.assertRaises(ValueError):  # more than the level gives
            build.apply_level_up(c, {"hp": "average", "asi_or_feat": ASI, "spells": [ref("Hold Person"), ref("Charm Person")]}, LIB)
        with self.assertRaises(ValueError):  # a cantrip is not a levelled spell
            build.apply_level_up(c, {"hp": "average", "asi_or_feat": ASI, "spells": [ref("Vicious Mockery")]}, LIB)

    def test_spells_can_be_left_for_later(self):
        new = build.apply_level_up(with_sub(hero("Bard", 3, {"cha": 16}), "College of Lore"), {"hp": "average", "asi_or_feat": ASI}, LIB)
        self.assertEqual(new["level"], 4)

    def test_arcanum_takes_the_exact_level(self):
        c = with_sub(hero("Warlock", 10, {"cha": 16}), "Fiend Patron")
        new = build.apply_level_up(c, {"hp": "average", "arcanum": [ref("Circle of Death")]}, LIB)
        self.assertIn("Circle of Death", [s["name"] for s in new["spells"]])
        with self.assertRaises(ValueError):
            build.apply_level_up(c, {"hp": "average", "arcanum": [ref("Hold Person")]}, LIB)


class PreparedTests(unittest.TestCase):
    def test_unprepared_spellbook_spells_are_not_cast(self):
        c = hero("Wizard", 3, {"int": 16}, ["Magic Missile", "Shield"])
        c = store.apply_change(c, {"op": "prepare", "index": 1, "on": False}, LIB)
        self.assertFalse(c["spells"][1]["prepared"])
        names = [o["name"] for g in actions.options(c, LIB).values() for o in g]
        self.assertIn("Magic Missile", names)
        self.assertNotIn("Shield", names)
        self.assertEqual(levels.spell_counts(c, LIB)["have_prepared"], 1)


if __name__ == "__main__":
    unittest.main()
