"""Tests for resources (Mana, Aura...) and abilities kept by the app."""
import random
import unittest

from app import resources as R
from app.combat import CombatEngine
from app.dice import DiceRoller
from app.state import new_state, normalize_state
from tests.test_core import FakeLLM, collect, make_services, new_game

CARD = {
    "resources": [{"name": "Mana", "max": 20, "regen": {"round": 1, "short_rest": 5, "long_rest": -1, "day": -1}},
                  {"name": "Aura", "max": 10, "regen": {"long_rest": -1}}],
    "abilities": [{"name": "Fire Bolt", "kind": "attack", "costs": {"mana": 5}, "dice": "2d6+2", "range": 12},
                  {"name": "Healing Light", "kind": "heal", "costs": {"Mana": 4}, "dice": "1d8+2"},
                  {"name": "Aura Shield", "kind": "effect", "costs": {"Aura": 3}, "description": "A shimmering barrier."}],
}


def player_state():
    st = new_state({"name": "Kaela", "hp": {"current": 10, "max": 20}})
    res = R.normalize_resources(CARD["resources"])
    st["resources"] = R.start_pools(res)
    st["abilities"] = R.normalize_abilities(CARD["abilities"], res)
    return st


class PoolTests(unittest.TestCase):
    def test_normalize_pay_regen(self):
        st = player_state()
        self.assertEqual(st["abilities"][0]["costs"], {"Mana": 5})  # cost names follow the card's resources
        R.pay(st, {"Mana": 18})
        self.assertIn("Not enough Mana", R.can_pay(st, {"Mana": 5}))
        with self.assertRaises(R.ResourceError):
            R.pay(st, {"Mana": 5})
        self.assertEqual(R.regenerate(st, "short_rest"), ["Mana 7/20"])
        self.assertEqual(R.regenerate(st, "round", 3), ["Mana 10/20"])
        self.assertEqual(R.regenerate(st, "long_rest"), ["Mana 20/20"])
        self.assertEqual(R.rest_kind(30), None)
        self.assertEqual(R.rest_kind(90), "short_rest")
        self.assertEqual(R.rest_kind(600), "long_rest")
        back = normalize_state(st)
        self.assertEqual(back["resources"]["Mana"]["regen"]["long_rest"], -1)
        self.assertEqual(len(back["abilities"]), 3)

    def test_outside_combat_and_tracker(self):
        st = player_state()
        heal = st["abilities"][1]
        st, line = R.use_outside_combat(st, heal, DiceRoller(random.Random(1)))
        self.assertTrue(R.is_ability(line))
        self.assertEqual(st["resources"]["Mana"]["current"], 16)
        self.assertGreater(st["player"]["hp"]["current"], 10)
        self.assertEqual(R.apply_tracker(st, [{"resource": "aura", "delta": -4, "reason": "barrier"}]), ["Aura -4 → 6/10 (barrier)"])
        self.assertEqual(R.apply_tracker(st, [{"resource": "Aura", "delta": 50}]), ["Aura +4 → 10/10"])
        self.assertIn("Out of", R.gm_notes({"resources": {"Ki": {"current": 0, "max": 5}}}, []))


class CombatTests(unittest.TestCase):
    def setUp(self):
        self.engine = CombatEngine(DiceRoller(random.Random(4)), random.Random(4))
        self.st = player_state()

    def start(self, enemies):
        st, _ = self.engine.start(self.st, "d20", enemies, player={"init_bonus": 20})
        return st

    def test_player_ability_spends_and_hits(self):
        st = self.start([{"name": "Wolf", "hp": 30, "ac": 5, "attack_bonus": 0, "damage": "1d2"}])
        wolf = next(c for c in st["combat"]["combatants"] if c["side"] == "enemy")
        st, text = self.engine.player_action(st, "ability", wolf["id"], "", st["abilities"][0]["id"])
        self.assertIn("Kaela uses Fire Bolt on Wolf", text)
        self.assertEqual(st["resources"]["Mana"]["current"], 15 + 1)  # 5 spent, then 1 back at the new round
        self.assertIn("\U0001F504 Mana 16/20", text)
        st["resources"]["Mana"]["current"] = 2
        with self.assertRaises(ValueError):
            self.engine.player_action(st, "ability", wolf["id"], "", st["abilities"][0]["id"])

    def test_enemy_caster_spends_then_falls_back(self):
        st = self.start([{"name": "Cultist", "hp": 50, "ac": 30, "attack_bonus": 30, "damage": "1d2", "range": 12, "mp": 6,
                          "spell": {"name": "Shadow Bolt", "cost": 4, "damage": "1d4", "range": 12}}])
        st["player"]["hp"] = {"current": 500, "max": 500}
        me = next(c for c in st["combat"]["combatants"] if c["side"] == "player")
        me["hp"] = me["max_hp"] = 500
        st, first = self.engine.player_action(st, "dodge")
        self.assertIn("casts Shadow Bolt at Kaela", first)
        self.assertIn("(Mana 2/6)", first)
        st, second = self.engine.player_action(st, "dodge")
        self.assertNotIn("casts Shadow Bolt", second)
        self.assertIn("no more Shadow Bolt", second)


class GameTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_game_prompt_and_rest(self):
        llm = FakeLLM()
        s = make_services(llm)
        cid = new_game(s, **CARD, calendar={"enabled": True, "preset": "fantasy"})
        st = s.conversations.get_state(cid)
        self.assertEqual(st["resources"]["Mana"]["current"], 20)
        st["resources"]["Mana"]["current"] = 3
        st["resources"]["Aura"]["current"] = 1
        s.conversations.save_state(cid, st)
        await collect(s.engine.send(cid, "I look around."))
        msgs = llm.stream_calls[-1]
        self.assertIn("Player's resources: Mana 3/20, Aura 1/10", msgs[-1]["content"])
        self.assertIn("## Resources", msgs[0]["content"])
        await collect(s.engine.send(cid, "/wait 8 hours"))
        st = s.conversations.get_state(cid)
        self.assertEqual(st["resources"]["Mana"]["current"], 20)
        self.assertEqual(st["resources"]["Aura"]["current"], 10)
        self.assertIn("Recovered", s.conversations.list_messages(cid)[-2]["content"])


if __name__ == "__main__":
    unittest.main()
