"""Storing and editing the 5e character, using features, rests, and the sheet feeding fights and checks."""
import random
import unittest

from app.dnd5e import store
from app.dnd5e.character import derive
from tests.dnd5e_fixture import fixture_library
from tests.test_dnd5e_character import aster

LIB = fixture_library()


class StoreTests(unittest.TestCase):
    def test_add_item_and_equip(self):
        c = aster()
        c = store.apply_change(c, {"op": "add", "type": "baseitem", "name": "Rapier", "source": "PHB"}, LIB)
        self.assertEqual(c["items"][-1]["name"], "Rapier")
        self.assertFalse(c["items"][-1]["equipped"])
        c = store.apply_change(c, {"op": "equip", "index": len(c["items"]) - 1, "on": True}, LIB)
        self.assertTrue(c["items"][-1]["equipped"])
        c = store.apply_change(c, {"op": "add", "type": "feat", "name": "Alert", "source": "PHB"}, LIB)
        self.assertEqual(derive(c, LIB)["initiative"], 2 + 5)
        c = store.apply_change(c, {"op": "add", "type": "class", "name": "Barbarian", "source": "PHB"}, LIB)
        self.assertEqual(c["cls"]["name"], "Barbarian")
        with self.assertRaises(ValueError):
            store.apply_change(c, {"op": "add", "type": "spell", "name": "Nope", "source": "PHB"}, LIB)

    def test_use_second_wind_then_none_left(self):
        c = aster()
        c["hp"]["current"] = 5
        c, line = store.use_feature(c, "Second Wind", LIB, random.Random(3))
        self.assertIn("Second Wind", line)
        self.assertGreater(c["hp"]["current"], 5)
        self.assertEqual(c["uses"]["Second Wind"], 1)
        with self.assertRaises(ValueError) as e:
            store.use_feature(c, "Second Wind", LIB)
        self.assertIn("short rest", str(e.exception))

    def test_short_rest_refills(self):
        c = aster()
        c["uses"] = {"Second Wind": 1}
        c = store.rest(c, "short_rest", LIB)
        self.assertEqual(c["uses"].get("Second Wind", 0), 0)

    def test_sync_player_numbers(self):
        st = {"player": {"name": "Aster", "hp": {"current": 1, "max": 1}, "stats": {}}}
        st["character5e"] = aster()
        store.sync_player(st, LIB)
        p = st["player"]
        self.assertEqual((p["class"], p["level"], p["ac"], p["hp"]["max"]), ("Fighter", 1, 19, 13))
        self.assertEqual(p["stats"]["STR"], 18)
        self.assertIn("Athletics +6", p["skills"])
        self.assertEqual(st["character5e_sheet"]["ac"], 19)


class StateTests(unittest.TestCase):
    def test_state_keeps_the_character(self):
        from app.state import normalize_state, new_state
        st = new_state({"name": "Aster"})
        st["character5e"] = aster()
        store.sync_player(st, LIB)
        again = normalize_state(st)
        self.assertEqual(again["character5e"]["cls"]["name"], "Fighter")
        self.assertEqual(again["character5e_sheet"]["ac"], 19)
        self.assertEqual(again["player"]["ac"], 19)


class ConvertTests(unittest.TestCase):
    def test_convert_free_form_aster(self):
        st = {"player": {"name": "Aster", "race": "Human", "class": "Fighter", "level": 1, "background": "Soldier. Served in Neverwinter.",
                         "stats": {"STR": 17, "DEX": 14, "CON": 16, "INT": 10, "WIS": 13, "CHA": 12}, "hp": {"current": 13, "max": 13},
                         "skills": ["Athletics +5", "Perception +3", "Intimidation +3", "Survival +3"],
                         "notes": "Fighter 1. Fighting Style: Defense would raise AC to 19 (not counted)."},
              "inventory": [{"name": "Chain mail", "qty": 1}, {"name": "Shield", "qty": 1}, {"name": "Longsword", "qty": 1}, {"name": "Explorer's pack", "qty": 1}]}
        char = store.convert(st, LIB, "2014")
        self.assertEqual((char["cls"]["name"], char["race"]["name"], char["background"]["name"]), ("Fighter", "Human", "Soldier"))
        self.assertEqual(char["scores"]["str"], 16)  # 17 already had the human +1
        sheet = derive(char, LIB)
        self.assertEqual(sheet["abilities"]["str"]["score"], 17)
        self.assertEqual(sheet["ac"], 19)
        self.assertEqual(sheet["attacks"][0]["name"], "Longsword")


class SheetFeedsPlayTests(unittest.TestCase):
    def setUp(self):
        from app.state import new_state
        self.st = new_state({"name": "Aster", "hp": {"current": 13, "max": 13}})
        self.st["character5e"] = aster()
        store.sync_player(self.st, LIB)

    def test_combat_uses_longsword(self):
        from app.combat import player_defaults
        d = player_defaults(self.st, "d20")
        self.assertEqual((d["attack_bonus"], d["damage"], d["ac"], d["hp"]), (6, "1d8+4", 19, 13))
        self.assertEqual(d["weapon"], "Longsword")

    def test_check_uses_skill_bonus(self):
        from app.checks import bonus_for
        self.assertEqual(bonus_for(self.st, {"ability": "WIS", "skill": "Perception", "kind": "check", "dc": 10})[0], 4)
        self.assertEqual(bonus_for(self.st, {"ability": "STR", "skill": "", "kind": "save", "dc": 10})[0], 6)
        self.assertEqual(bonus_for(self.st, {"ability": "DEX", "skill": "Stealth", "kind": "check", "dc": 10})[0], 2)
