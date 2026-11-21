"""Tests for v0.11.0: combat tracked by code."""
import random
import unittest

from app.combat import CombatEngine, CombatError, describe_combat, player_defaults, suggest_enemies
from app.dice import DiceRoller
from app.state import new_state
from tests.test_core import FakeLLM, collect, make_services, new_game


def fighter():
    return new_state({"name": "Kaela", "class": "Fighter", "stats": {"STR": 16, "DEX": 14, "CON": 14, "INT": 10, "WIS": 10, "CHA": 8},
                      "hp": {"current": 12, "max": 12}, "ac": 16, "level": 1})


def tough():
    st = fighter()
    st["player"]["hp"] = {"current": 200, "max": 200}
    return st


def engine(seed=1):
    return CombatEngine(DiceRoller(random.Random(seed)), random.Random(seed))


GOBLINS = [{"name": "Goblin", "count": 2, "hp": 7, "ac": 13, "attack_bonus": 4, "damage": "1d6+2", "init_bonus": 2}]


class D20Tests(unittest.TestCase):
    def test_defaults_from_sheet(self):
        d = player_defaults(fighter(), "d20")
        self.assertEqual((d["attack_bonus"], d["damage"], d["ac"], d["init_bonus"], d["hp"]), (5, "1d8+3", 16, 2, 12))

    def test_start_orders_and_places(self):
        state, line = engine().start(fighter(), "d20", GOBLINS)
        c = state["combat"]
        self.assertTrue(c["active"])
        self.assertEqual(len(c["combatants"]), 3)
        self.assertEqual({x["name"] for x in c["combatants"]}, {"Kaela", "Goblin 1", "Goblin 2"})
        self.assertIn("Turn order", line)
        spots = {(x["x"], x["y"]) for x in c["combatants"]}
        self.assertEqual(len(spots), 3)                               # nobody shares a square
        me = next(x for x in c["combatants"] if x["side"] == "player")
        self.assertLess(me["x"], min(x["x"] for x in c["combatants"] if x["side"] == "enemy"))

    def test_attack_round_updates_hp_and_sheet(self):
        eng = engine(3)
        state, _ = eng.start(tough(), "d20", GOBLINS)
        target = next(x for x in state["combat"]["combatants"] if x["side"] == "enemy")
        state, line = eng.player_action(state, "attack", target["id"])
        self.assertTrue(line.startswith("⚔️"))
        self.assertIn("Kaela attacks", line)
        self.assertIn("Goblin", line)
        me = next(x for x in state["combat"]["combatants"] if x["side"] == "player")
        self.assertEqual(state["player"]["hp"]["current"], me["hp"])  # the sheet follows the fight
        self.assertEqual(eng.current(state["combat"])["side"], "player")  # back to the player after the enemies act

    def test_fight_ends_when_enemies_fall(self):
        eng = engine(5)
        state, _ = eng.start(fighter(), "d20", [{"name": "Rat", "hp": 1, "ac": 1, "attack_bonus": 0, "damage": "1"}])
        rat = next(x for x in state["combat"]["combatants"] if x["side"] == "enemy")
        for _ in range(10):
            if not state["combat"]["active"]:
                break
            state, line = eng.player_action(state, "attack", rat["id"])
        self.assertFalse(state["combat"]["active"])
        self.assertIn("all enemies are down", line)

    def test_dodge_and_conditions(self):
        eng = engine(2)
        state, _ = eng.start(tough(), "d20", GOBLINS)
        state, line = eng.player_action(state, "dodge")
        self.assertIn("dodges", line)
        for block in line.split("\n\n"):
            if "attacks Kaela" in block and "🎲" in block:
                self.assertIn("(disadvantage)", block)  # the Dodge works against the attacks that follow
        gob = next(x for x in state["combat"]["combatants"] if x["side"] == "enemy")
        state = eng.edit(state, gob["id"], conditions=["prone", "nonsense"], hp=3)
        self.assertEqual((gob["conditions"], gob["hp"]), (["prone"], 3))
        with self.assertRaises(CombatError):
            eng.edit(state, gob["id"], x=99, y=0)
        self.assertIn("Goblin", describe_combat(state["combat"]))

    def test_bad_input(self):
        with self.assertRaises(CombatError):
            engine().start(fighter(), "d20", [])
        state, _ = engine().start(fighter(), "d20", [{"name": "Orc", "damage": "lots", "hp": "x"}])
        orc = next(x for x in state["combat"]["combatants"] if x["side"] == "enemy")
        self.assertEqual((orc["damage"], orc["max_hp"]), ("1d6+1", 7))


class PoolTests(unittest.TestCase):
    def test_pool_successes(self):
        eng = engine(7)
        for _ in range(50):
            r = eng.roll_pool(5)
            expected = sum(1 for x in r["rolls"] if x >= 6) + (r["rolls"].count(10) // 2) * 2
            self.assertEqual(r["successes"], expected)

    def test_pool_fight(self):
        eng = engine(9)
        state, _ = eng.start(fighter(), "pool", [{"name": "Ghoul", "hp": 6, "pool": 5, "defense": 3, "damage": 1}])
        ghoul = next(x for x in state["combat"]["combatants"] if x["side"] == "enemy")
        state, line = eng.player_action(state, "attack", ghoul["id"])
        self.assertIn("successes", line)


class FlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_combat_turn_through_engine_and_undo(self):
        llm = FakeLLM()
        s = make_services(llm)
        cid = new_game(s, "gm_world")
        hp_before = s.conversations.get_state(cid)["player"]["hp"]["current"]
        prepare = lambda st: s.combat.start(st, "d20", GOBLINS)  # noqa: E731
        events = await collect(s.engine.send(cid, "", prepare=prepare))
        self.assertEqual(events[-1]["type"], "done")
        msgs = s.conversations.list_messages(cid)
        self.assertTrue(msgs[-2]["content"].startswith("⚔️ Combat starts"))
        prompt = llm.stream_calls[-1][-1]["content"]
        self.assertIn("## Combat (tracked by the app)", prompt)
        self.assertIn("Goblin 1", prompt)
        # the tracker never changes HP in a fight
        llm.analysis = {"hp_change": -5}
        target = next(x for x in s.conversations.get_state(cid)["combat"]["combatants"] if x["side"] == "enemy")
        await collect(s.engine.send(cid, "*I swing hard*", prepare=lambda st: s.combat.player_action(st, "attack", target["id"])))
        st = s.conversations.get_state(cid)
        me = next(x for x in st["combat"]["combatants"] if x["side"] == "player")
        self.assertEqual(st["player"]["hp"]["current"], me["hp"])
        self.assertIn("*I swing hard*", s.conversations.list_messages(cid)[-2]["content"])
        # rewinding to before the fight removes it and restores HP
        s.engine.rewind(cid, msgs[0]["id"], inclusive=False)
        st = s.conversations.get_state(cid)
        self.assertNotIn("combat", st)
        self.assertEqual(st["player"]["hp"]["current"], hp_before)

    async def test_errors_do_not_send(self):
        llm = FakeLLM()
        s = make_services(llm)
        cid = new_game(s, "gm_world")
        events = await collect(s.engine.send(cid, "", prepare=s.combat.enemies_act))
        self.assertEqual(events[0]["type"], "error")
        self.assertEqual(len(s.conversations.list_messages(cid)), 1)

    async def test_suggest_enemies(self):
        llm = FakeLLM()
        llm.summary = '{"enemies": [{"name": "Bandit", "count": 3, "hp": 11, "ac": 12, "attack_bonus": 3, "damage": "1d6+1"}]}'
        got = await suggest_enemies(llm, "d20", "Three bandits block the road.")
        self.assertEqual(got[0]["name"], "Bandit")
        self.assertEqual((got[0]["count"], got[0]["hp"], got[0]["ac"]), (3, 11, 12))
        llm.summary = "no idea"
        with self.assertRaises(CombatError):
            await suggest_enemies(llm, "d20", "...")


if __name__ == "__main__":
    unittest.main()


class RoundLabelTests(unittest.TestCase):
    def test_line_names_the_round_that_was_played(self):
        eng = engine(4)
        state, _ = eng.start(tough(), "d20", GOBLINS)
        target = next(x for x in state["combat"]["combatants"] if x["side"] == "enemy")
        state, line = eng.player_action(state, "attack", target["id"])
        self.assertTrue(line.startswith("⚔️ **Round 1**"))
        block = next(b for b in line.split("\n\n") if b.startswith("**Kaela attacks"))
        rows = block.split("\n")
        self.assertTrue(rows[1].startswith("🎲"))                 # header, then the roll, then the damage
        if "HIT" in rows[1]:
            self.assertTrue(rows[2].startswith("💥"))
