"""Your turn in a fight: an action, a bonus action, your movement and a reaction. It ends when you say so
(End turn), or after a typed message, which is your whole turn. Then everyone else acts."""
import unittest

from app.combat import CombatError, bonus_intent, end_intent
from tests.test_combat import beside, engine, tough

RATS = [{"name": "Rat", "count": 2, "hp": 30, "ac": 5, "attack_bonus": 0, "damage": "1", "init_bonus": -9}]


def monk():
    st = tough()
    st["player"]["stats"]["DEX"] = 30  # acts first
    st["player"]["weapon"] = "Unarmed Strike"
    st["character5e_sheet"] = {"ac": 15, "initiative": 10, "prof": 2, "martial_arts": True,
                               "attacks": [{"name": "Unarmed Strike", "bonus": 5, "damage": "1d4+3", "range": "5 ft"}]}
    return st


def ready(seed=3):
    eng = engine(seed)
    state, _ = eng.start(monk(), "d20", RATS, grid={"w": 20, "h": 10})
    me = next(c for c in state["combat"]["combatants"] if c["side"] == "player")
    rat = next(c for c in state["combat"]["combatants"] if c["side"] == "enemy")
    beside(state, rat)
    assert eng.current(state["combat"])["id"] == me["id"]
    return eng, state, me, rat


class ActionEconomyTest(unittest.TestCase):
    def test_a_step_keeps_your_turn(self):
        eng, state, me, rat = ready()
        state, line = eng.player_step(state, "attack", rat["id"])
        self.assertEqual(eng.current(state["combat"])["id"], me["id"])
        self.assertTrue(state["combat"]["spent"]["action"])
        self.assertIn("bonus action", line.lower())  # what is left is said
        with self.assertRaises(CombatError):
            eng.player_step(state, "attack", rat["id"])  # one action per turn

    def test_martial_arts_bonus_strike(self):
        eng, state, me, rat = ready()
        with self.assertRaises(CombatError):  # Martial Arts needs the Attack action first
            eng.player_step(state, "bonus_attack", rat["id"])
        state, _ = eng.player_step(state, "attack", rat["id"])
        state, line = eng.player_step(state, "bonus_attack", rat["id"])
        self.assertIn("Unarmed Strike", line)
        self.assertTrue(state["combat"]["spent"]["bonus"])
        with self.assertRaises(CombatError):
            eng.player_step(state, "bonus_attack", rat["id"])

    def test_no_bonus_strike_without_martial_arts(self):
        eng, state, me, rat = ready()
        state["character5e_sheet"]["martial_arts"] = False
        state, _ = eng.player_step(state, "attack", rat["id"])
        with self.assertRaises(CombatError):
            eng.player_step(state, "bonus_attack", rat["id"])

    def test_end_turn_tells_the_whole_turn_then_others_act(self):
        eng, state, me, rat = ready()
        state, _ = eng.player_step(state, "attack", rat["id"])
        state, _ = eng.player_step(state, "bonus_attack", rat["id"])
        state, line = eng.player_action(state, "end")
        self.assertIn("Unarmed Strike", line)  # the steps of the turn are in the message the Aedo narrates
        self.assertIn("Rat", line.split("Unarmed Strike")[-1])  # then the others acted
        self.assertFalse(state["combat"].get("turn_lines"))
        if state["combat"]["active"] and eng.current(state["combat"])["id"] == me["id"]:
            self.assertFalse(state["combat"]["spent"]["action"])  # a fresh turn
            self.assertFalse(state["combat"]["spent"]["bonus"])

    def test_typed_turn_with_a_bonus_strike(self):
        eng, state, me, rat = ready()
        state, line = eng.player_turn(state, ["attack", "bonus_attack"], rat["id"])
        self.assertEqual(line.count("Unarmed Strike"), 2)  # the attack names its weapon, then the bonus strike
        if state["combat"]["active"]:  # the others acted and a new turn began with a fresh action and bonus action
            self.assertGreater(state["combat"]["round"], 1)
            self.assertFalse(state["combat"]["spent"]["action"])

    def test_the_old_one_call_turn_still_works(self):
        eng, state, me, rat = ready()
        state, line = eng.player_action(state, "attack", rat["id"])
        self.assertIn("Kaela", line)


class TypedWordsTest(unittest.TestCase):
    def test_bonus_words(self):
        self.assertTrue(bonus_intent("I punch the goblin, then use martial arts to strike its head with my bonus action"))
        self.assertTrue(bonus_intent("Flurry of blows on the goblin"))
        self.assertFalse(bonus_intent("I punch the goblin"))

    def test_end_words(self):
        self.assertTrue(end_intent("/end"))
        self.assertTrue(end_intent("I end my turn"))
        self.assertFalse(end_intent("I punch the goblin"))


if __name__ == "__main__":
    unittest.main()


class TargetWordsTest(unittest.TestCase):
    def combat(self):
        foes = [{"id": f"g{i}", "name": f"Goblin {i}", "side": "enemy", "hp": 7, "x": i, "y": 0} for i in (1, 2, 4)]
        return {"combatants": [{"id": "p", "name": "Aster", "side": "player", "hp": 9, "x": 0, "y": 1}] + foes}

    def test_number_words(self):
        from app.combat import find_target
        c = self.combat()
        self.assertEqual(find_target(c, "I punch the goblin one"), "g1")
        self.assertEqual(find_target(c, "o goblin dois"), "g2")
        self.assertEqual(find_target(c, "goblin four"), "g4")

    def test_action_and_bonus_targets(self):
        from app.combat import split_turn
        act, bonus = split_turn("first the goblin one with my action, and with my bonus action I attack the goblin 2")
        self.assertIn("goblin one", act)
        self.assertNotIn("goblin 2", act)
        self.assertIn("goblin 2", bonus)
        self.assertEqual(split_turn("I punch the goblin"), ("I punch the goblin", ""))
