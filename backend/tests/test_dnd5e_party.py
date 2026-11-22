import unittest

from app import party
from app.dnd5e import party5e, store
from app.dnd5e.character import derive, new_character
from app.state import normalize_state
from tests.dnd5e_fixture import fixture_library, ref

LIB = fixture_library()


def hero(cls="Fighter", level=1):
    c = new_character("2014")
    c.update(cls=ref(cls), race=ref("Human"), level=level)
    return c


class RolesTest(unittest.TestCase):
    def test_roles_are_blurry(self):
        self.assertEqual(party5e.roles_of("Fighter"), {"front"})
        self.assertIn("healer", party5e.roles_of("Cleric"))
        self.assertIn("support", party5e.roles_of("Cleric"))
        self.assertIn("front", party5e.roles_of("Cleric", "War Domain"))
        self.assertIn("front", party5e.roles_of("Wizard", "Bladesinging"))
        self.assertIn("caster", party5e.roles_of("Wizard"))

    def test_missing_roles_around_the_hero(self):
        self.assertEqual(party5e.missing_roles({"front"}), ["healer", "caster", "support"])
        self.assertEqual(party5e.missing_roles({"healer", "support", "caster"}), ["front"])


class AutoBuildTest(unittest.TestCase):
    def test_the_cards_class_wins(self):
        c = party5e.auto_build({"name": "Dorna", "description": "A dwarf cleric.", "sheet": {"class": "Cleric"}}, hero("Wizard"), [], LIB)
        self.assertEqual(c["cls"]["name"], "Cleric")

    def test_the_description_names_the_class(self):
        c = party5e.auto_build({"name": "Pip", "description": "A halfling monk with quick fists.", "sheet": {"role": "fighter"}}, hero("Fighter"), [], LIB, role="caster")
        self.assertEqual(c["cls"]["name"], "Monk")

    def test_fills_the_gaps_around_a_fighter(self):
        comps = [{"name": n, "sheet": {}} for n in ("A", "B", "C")]
        built = party5e.auto_build_all(comps, hero("Fighter"), LIB)
        classes = [built[n]["cls"]["name"] for n in ("A", "B", "C")]
        self.assertEqual(classes[:2], ["Cleric", "Wizard"])
        self.assertIn(classes[2], ("Cleric", "Paladin"))

    def test_rebuilding_one_counts_the_others_roles(self):
        comps = [{"name": n, "sheet": {}} for n in ("A", "B")]
        keep = {"A": hero("Wizard")}  # A is already the spellcaster
        built = party5e.auto_build_all(comps, hero("Fighter"), LIB, only="B", keep=keep)
        self.assertEqual(list(built), ["B"])
        self.assertEqual(built["B"]["cls"]["name"], "Cleric")
        keep = {"A": hero("Cleric")}  # now A heals: B becomes the spellcaster
        self.assertEqual(party5e.auto_build_all(comps, hero("Fighter"), LIB, only="B", keep=keep)["B"]["cls"]["name"], "Wizard")

    def test_same_level_scores_race_and_gear(self):
        c = party5e.auto_build({"name": "Faelar", "description": "An elf scholar.", "sheet": {"class": "Wizard"}}, hero("Fighter", level=3), [], LIB)
        self.assertEqual(c["level"], 3)
        self.assertEqual(c["race"]["name"], "Elf")
        self.assertEqual(max(c["scores"], key=c["scores"].get), "int")
        sheet = derive(c, LIB)
        self.assertTrue(sheet["attacks"])  # a weapon in hand

    def test_cleric_wears_armour_and_picks_a_healing_domain(self):
        c = party5e.auto_build({"name": "Dorna", "sheet": {"class": "Cleric", "role": "healer"}}, hero("Fighter"), [], LIB)
        self.assertEqual(c["subclass"]["name"], "Life Domain")
        sheet = derive(c, LIB)
        self.assertGreaterEqual(sheet["ac"], 16)  # scale mail + shield
        self.assertEqual(len((c.get("picks") or {}).get("skills") or []), 2)


class CompanionSheetInGameTest(unittest.TestCase):
    def scenario(self):
        return {"npcs": [{"name": "Dorna", "companion": True, "sheet": party.normalize_sheet({"class": "Cleric", "role": "healer"})}]}

    def test_sync_feeds_the_party_and_fights(self):
        sc = self.scenario()
        st = {"player": {}}
        party.start_party(st, sc, "companions")
        store.put_char(st, "Dorna", party5e.auto_build(sc["npcs"][0], hero(), [], LIB), LIB)
        sh = st["party5e_sheet"]["Dorna"]
        self.assertEqual(st["party"]["Dorna"]["max_hp"], sh["hp_max"])
        ally = party.allies(st, sc)[0]
        self.assertEqual((ally["ac"], ally["attack_bonus"]), (sh["ac"], sh["attack_bonus"]))
        self.assertIs(store.char_of(st, "Dorna"), st["party5e"]["Dorna"])

    def test_state_keeps_companion_sheets(self):
        sc = self.scenario()
        st = normalize_state({"player": {"name": "Aster"}})
        party.start_party(st, sc, "companions")
        store.put_char(st, "Dorna", party5e.auto_build(sc["npcs"][0], hero(), [], LIB), LIB)
        again = normalize_state(st)
        self.assertIn("Dorna", again["party5e"])
        self.assertIn("Dorna", again["party5e_sheet"])

    def test_player_slot_still_works(self):
        st = {"player": {}}
        store.put_char(st, "", hero(), LIB)
        self.assertEqual(st["player"]["class"], "Fighter")
        self.assertIs(store.char_of(st, ""), st["character5e"])


if __name__ == "__main__":
    unittest.main()


class HpFollowsTheGameTest(unittest.TestCase):
    def test_damage_from_a_fight_reaches_the_sheet(self):
        st = {"player": {}}
        store.put_char(st, "", hero(), LIB)
        st["player"]["hp"]["current"] = 3  # hurt in a fight
        store.pull_hp(st, "")
        store.put_char(st, "", store.apply_change(store.char_of(st, ""), {"op": "set", "field": "xp", "value": 10}, LIB), LIB)
        self.assertEqual(st["player"]["hp"]["current"], 3)

    def test_companion_hp_from_the_party(self):
        sc = {"npcs": [{"name": "Dorna", "companion": True, "sheet": party.normalize_sheet({"class": "Cleric"})}]}
        st = {"player": {}}
        party.start_party(st, sc, "companions")
        store.put_char(st, "Dorna", party5e.auto_build(sc["npcs"][0], hero(), [], LIB), LIB)
        st["party"]["Dorna"]["hp"] = 2
        store.pull_hp(st, "Dorna")
        self.assertEqual(derive(store.char_of(st, "Dorna"), LIB)["hp"], 2)


class SheetOwnsTheGearTest(unittest.TestCase):
    def fighter_turned_monk(self):
        st = {"player": {"name": "Aster", "class": "Fighter", "notes": "Fighter 1. Handaxe x2 +5, 1d6+3."},
              "inventory": [{"name": "Chain mail", "qty": 1}, {"name": "Handaxe", "qty": 2}, {"name": "Explorer's pack", "qty": 1},
                            {"name": "Potion of healing", "qty": 1}]}
        c = hero("Monk")
        c["scores"] = {"str": 12, "dex": 16, "con": 14, "int": 10, "wis": 15, "cha": 8}
        c["items"] = [{"type": "baseitem", "name": "Quarterstaff", "source": "PHB", "qty": 1, "equipped": True}]
        store.put_char(st, "", c, LIB)
        return st

    def test_old_weapons_and_armour_leave_the_bag(self):
        names = [i["name"] for i in self.fighter_turned_monk()["inventory"]]
        self.assertNotIn("Handaxe", names)
        self.assertNotIn("Chain mail", names)
        self.assertIn("Explorer's pack", names)
        self.assertIn("Potion of healing", names)
        self.assertIn("Quarterstaff", names)

    def test_notes_come_from_the_sheet(self):
        st = self.fighter_turned_monk()
        self.assertIn("Monk 1", st["player"]["notes"])
        self.assertNotIn("Handaxe", st["player"]["notes"])
        self.assertIn("Unarmed Strike", st["player"]["notes"])
        self.assertIn("Handaxe", st["player"]["notes_before_5e"])  # the old notes are kept aside, once

    def test_monk_unarmed_strike(self):
        sheet = derive(self.fighter_turned_monk()["character5e"], LIB)
        punch = next(a for a in sheet["attacks"] if a["name"] == "Unarmed Strike")
        self.assertEqual((punch["bonus"], punch["damage"]), (5, "1d4+3"))
