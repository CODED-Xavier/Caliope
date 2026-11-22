"""Fights by the rules: faster enemies act at once, you move on your turn within your speed, typed attacks are rolled
by the app, one check per round, and every check shows its DC before the roll."""
import unittest

from app.checks import find_checks
from app.combat import CombatError, combat_intent, find_target
from tests.test_combat import GOBLINS, beside, engine, tough
from tests.test_core import FakeLLM, collect, make_services, new_game

FAST = [{"name": "Goblin", "count": 2, "hp": 7, "ac": 13, "attack_bonus": 4, "damage": "1d6+2", "init_bonus": 15}]


def me_of(state):
    return next(c for c in state["combat"]["combatants"] if c["side"] == "player")


class TurnTests(unittest.TestCase):
    def test_faster_enemies_act_at_the_start(self):
        st = tough()
        st["player"]["stats"]["DEX"] = 1
        state, line = engine(3).start(st, "d20", FAST)
        self.assertIn("Goblin", line.split("⚔️ Combat starts!")[1])
        self.assertTrue("attacks" in line or "closes in" in line)   # their turns were played, with real rolls
        self.assertIn("Kaela's turn", line)
        self.assertEqual(engine(3).current(state["combat"])["side"], "player")

    def test_move_on_your_turn_within_speed(self):
        eng = engine(5)
        st = tough()
        st["player"]["stats"]["DEX"] = 30
        state, _ = eng.start(st, "d20", [{"name": "Rat", "hp": 3, "ac": 5, "init_bonus": -5}], grid={"w": 20, "h": 10})
        me = me_of(state)
        self.assertEqual(eng.current(state["combat"])["id"], me["id"])
        x0, y0 = me["x"], me["y"]
        tx = x0 + 3 if x0 + 3 < 20 else x0 - 3
        state = eng.move_player(state, tx, y0)
        self.assertEqual((me["x"], state["combat"]["moved"]), (tx, 3))
        with self.assertRaises(CombatError):  # 3 more squares away would be 6 + 3 > 6
            eng.move_player(state, tx + (4 if tx > x0 else -4), y0)
        rat = next(c for c in state["combat"]["combatants"] if c["side"] == "enemy")
        beside(state, rat)
        state, _ = eng.player_action(state, "dodge")
        if state["combat"]["active"]:
            self.assertEqual(state["combat"]["moved"], 0)  # a new turn: full speed again

    def test_not_your_turn(self):
        eng = engine(2)
        state, _ = eng.start(tough(), "d20", GOBLINS)
        combat = state["combat"]
        combat["turn"] = next(i for i, cid in enumerate(combat["order"]) if cid != me_of(state)["id"])
        with self.assertRaises(CombatError):
            eng.move_player(state, 0, 0)

    def test_far_target_means_a_dash(self):
        eng = engine(4)
        state, _ = eng.start(tough(), "d20", [{"name": "Rat", "hp": 3, "ac": 5, "init_bonus": -5}], grid={"w": 40, "h": 6})
        me, rat = me_of(state), next(c for c in state["combat"]["combatants"] if c["side"] == "enemy")
        me["x"], me["y"], rat["x"], rat["y"] = 0, 2, 30, 2
        state, line = eng.player_action(state, "attack", rat["id"])
        self.assertIn("dashes", line)
        self.assertNotIn("Kaela attacks", line)
        me["x"], me["y"], rat["x"], rat["y"] = 0, 2, 4, 2
        state["combat"]["turn"] = state["combat"]["order"].index(me["id"])
        state["combat"]["moved"] = 0
        state, line = eng.player_action(state, "attack", rat["id"])
        self.assertIn("moves 3 squares", line)
        self.assertIn("**Kaela attacks Rat**", line)

    def test_one_check_per_round(self):
        state, _ = engine(1).start(tough(), "d20", GOBLINS)
        eng = engine(1)
        eng.use_reaction(state)
        with self.assertRaises(CombatError):
            eng.use_reaction(state)
        state["combat"]["round"] += 1
        eng.use_reaction(state)


class TypedAttackTests(unittest.TestCase):
    def setUp(self):
        self.combat = {"active": True, "combatants": [
            {"id": "p", "side": "player", "hp": 10, "x": 0, "y": 0, "name": "Aster"},
            {"id": "g1", "side": "enemy", "hp": 7, "x": 3, "y": 0, "name": "Goblin 1"},
            {"id": "g3", "side": "enemy", "hp": 7, "x": 1, "y": 1, "name": "Goblin 3"},
            {"id": "g2", "side": "enemy", "hp": 0, "x": 1, "y": 0, "name": "Goblin 2"}]}

    def test_intents(self):
        c = self.combat
        self.assertEqual(combat_intent(c, "I try to cut the goblin's head clean off"), ("attack", "g3", "I try to cut the goblin's head clean off"))
        self.assertEqual(combat_intent(c, "*I swing at goblin 1*")[1], "g1")
        self.assertEqual(combat_intent(c, "/attack goblin #1 overhead"), ("attack", "g1", "goblin #1 overhead"))
        self.assertEqual(combat_intent(c, "/dodge")[0], "dodge")
        self.assertEqual(combat_intent(c, "Ataco o goblin com a espada")[0], "attack")
        for quiet in ('"I will cut you!"', "What does the goblin hit?", "I look around", "/ask is it dead", "(how many HP?)"):
            self.assertIsNone(combat_intent(c, quiet), quiet)
        self.assertIsNone(combat_intent({**c, "active": False}, "I attack"))
        self.assertEqual(find_target(c, "goblin 2"), "g3")  # Goblin 2 is down: the nearest living goblin


class TypedAttackFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_typed_attack_counts(self):
        llm = FakeLLM()
        s = make_services(llm)
        cid = new_game(s, "gm_world")
        await collect(s.engine.send(cid, "", prepare=lambda st: s.combat.start(st, "d20", [{"name": "Rat", "hp": 1, "ac": 1, "init_bonus": -9}])))
        st = s.conversations.get_state(cid)
        rat = next(c for c in st["combat"]["combatants"] if c["side"] == "enemy")
        beside(st, rat)
        s.conversations.save_state(cid, st)
        move, target, words = combat_intent(st["combat"], "I cut its head clean off")
        await collect(s.engine.send(cid, words, prepare=lambda x: s.combat.player_action(x, move, target)))
        msg = s.conversations.list_messages(cid)[-2]["content"]
        self.assertIn("I cut its head clean off", msg)
        self.assertIn("Rat", msg)
        self.assertIn("🎲", msg)


class CheckDcTests(unittest.TestCase):
    def test_dc_shown_before_the_roll(self):
        self.assertEqual(find_checks("Make an DEX (Reaction) check to dodge the incoming arrows. DC 15.")[0]["dc"], 15)
        c = find_checks("Make an INT (Perception) check to assess the situation. DC 10.")[0]
        self.assertEqual((c["ability"], c["skill"], c["dc"]), ("WIS", "Perception", 10))  # Perception is WIS
        d = find_checks("Roll a CON saving throw.")[0]
        self.assertEqual((d["dc"], d.get("dc_default")), (12, True))
        self.assertEqual(find_checks("Make a hard STR (Athletics) check.")[0]["dc"], 20)
        self.assertEqual(len(find_checks("Make a STR check, DC 10. Then a DEX check, DC 12.")), 1)


if __name__ == "__main__":
    unittest.main()


class DroppedGearTests(unittest.TestCase):
    def test_only_used_up_things_leave_the_bag_in_a_fight(self):
        from app.engine import USED_UP
        kept = [n for n in ("Longsword", "Shield", "Chain mail", "Potion of healing", "Arrows", "Torch") if not USED_UP.search(n)]
        self.assertEqual(kept, ["Longsword", "Shield", "Chain mail"])


class WideGridTests(unittest.TestCase):
    def test_enemies_walk_on_grids_wider_than_24(self):
        eng = engine(6)
        state, _ = eng.start(tough(), "d20", [{"name": "Rat", "hp": 3, "ac": 5, "init_bonus": -5}], grid={"w": 40, "h": 6})
        me, rat = me_of(state), next(c for c in state["combat"]["combatants"] if c["side"] == "enemy")
        me["x"], me["y"], rat["x"], rat["y"] = 5, 2, 35, 2
        state, line = eng.player_action(state, "dodge")
        self.assertLess(rat["x"], 35)  # it walked toward the player instead of standing still
