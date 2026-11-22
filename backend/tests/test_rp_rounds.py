"""The round card told by turns: each fighter's turn under a heading, your own words under your rolls (the "Want to
describe it?" window), and a line of flavour around a companion's roll."""
import unittest

from app.combat import CombatError
from tests.test_action_economy import RATS, monk, ready
from tests.test_combat import engine


class DescribeTest(unittest.TestCase):
    def test_your_words_go_under_the_header(self):
        eng, state, me, rat = ready()
        state, _ = eng.player_step(state, "attack", rat["id"])
        state = eng.describe_last(state, "I swing for the goblin's head!")
        block = state["combat"]["turn_lines"][-1].split("\n")
        self.assertTrue(block[0].startswith("**Kaela attacks"))
        self.assertEqual(block[1], '💬 "I swing for the goblin\'s head!"')
        state, card = eng.player_action(state, "end")
        self.assertLess(card.index("I swing for"), card.index("🎲"))

    def test_nothing_to_describe(self):
        eng, state, me, rat = ready()
        with self.assertRaises(CombatError):
            eng.describe_last(state, "hello")
        state, _ = eng.player_step(state, "attack", rat["id"])
        before = list(state["combat"]["turn_lines"])
        eng.describe_last(state, "   ")
        self.assertEqual(state["combat"]["turn_lines"], before)


class TurnHeadingsTest(unittest.TestCase):
    def test_each_fighter_has_a_turn_heading(self):
        eng, state, me, rat = ready()
        state, card = eng.player_action(state, "attack", rat["id"])
        self.assertIn("**Kaela's turn**", card)
        self.assertIn("'s turn**", card.split("**Kaela's turn**")[1])  # then the rats' turns
        self.assertLess(card.index("**Kaela's turn**"), card.index("Kaela attacks"))


class CompanionFlavourTest(unittest.TestCase):
    def test_flavour_around_a_companion_roll(self):
        eng = engine(7)
        st = monk()
        ally = {"name": "Dorna", "hp": 30, "ac": 18, "attack_bonus": 4, "damage": "1d6+2", "range": 1, "speed": 6, "init_bonus": 20,
                "role": "fighter", "companion": True, "weapon": "Mace"}
        state, card = eng.start(st, "d20", RATS, allies=[ally], grid={"w": 10, "h": 6})
        rat = next(c for c in state["combat"]["combatants"] if c["side"] == "enemy")
        dorna = next(c for c in state["combat"]["combatants"] if c["name"] == "Dorna")
        dorna["x"], dorna["y"] = rat["x"] - 1 if rat["x"] else rat["x"] + 1, rat["y"]
        line = eng._flavour(dorna, rat, "**Dorna attacks Rat 1**\n🎲 d20(3) +4 = 7 vs AC 5 → **HIT**\n💥 5 damage (1d6+2) → Rat 1 25/30 HP")
        parts = line.split("\n")
        self.assertTrue(parts[1].startswith("*Dorna") and "Mace" in parts[1])
        self.assertTrue(parts[-1].startswith("*") and parts[-1].endswith("*"))
        miss = eng._flavour(dorna, rat, "**Dorna attacks Rat 1**\n🎲 d20(2) +4 = 6 vs AC 7 → **MISS**")
        self.assertIn("near miss", miss.split("\n")[-1].lower())


class CompanionFaceTest(unittest.TestCase):
    def test_face_on_the_first_turn_only(self):
        eng = engine(7)
        combat = {"combatants": [{"name": "Kaela", "side": "player"}, {"name": "Dorna", "side": "ally"}, {"name": "Rat 1", "side": "enemy"}]}
        out = eng._by_turns(combat, ["**Kaela attacks Rat 1**", "**Dorna attacks Rat 1**", "**Rat 1 attacks Dorna**"])
        self.assertEqual(out[out.index("**Dorna's turn**") + 1], "[[face: Dorna]]")
        self.assertEqual(sum(1 for x in out if x.startswith("[[face:")), 1)  # not for you, not for enemies
        again = eng._by_turns(combat, ["**Dorna attacks Rat 1**"])
        self.assertNotIn("[[face: Dorna]]", again)  # once per fight


if __name__ == "__main__":
    unittest.main()


class CompanionSetupTest(unittest.TestCase):
    def test_edits_from_the_start_screen(self):
        from app.party import apply_companion_edits
        npcs = [{"name": "Dorna", "companion": True, "description": "old", "sheet": {"hp": 12}},
                {"name": "Artemis", "description": "teacher"}]
        pics = {"default": "/api/uploads/d.png", "moods": [{"n": 2, "label": "Happy", "url": "/api/uploads/h.png"}]}
        out = apply_companion_edits(npcs, [{"of": "Dorna", "name": "Dorna Ironhand", "description": "A smith's daughter.",
                                            "personality": "blunt", "appearance": {"hair": "red braid", "junk": "x"}, "portraits": pics},
                                           {"of": "Artemis", "name": "Hacked"}, {"of": "Nobody", "name": "X"}])
        self.assertEqual(out[0]["name"], "Dorna Ironhand")
        self.assertEqual(out[0]["description"], "A smith's daughter.")
        self.assertEqual(out[0]["appearance"], {"hair": "red braid"})
        self.assertEqual(out[0]["portraits"]["moods"][0]["label"], "Happy")
        self.assertEqual(out[0]["sheet"], {"hp": 12})
        self.assertEqual(out[1]["name"], "Artemis")  # only companions can be changed here
        self.assertEqual(npcs[0]["name"], "Dorna")  # the card itself is untouched

    def test_new_game_uses_them(self):
        from tests.test_core import FakeLLM, make_services, new_game
        s = make_services(FakeLLM())
        base = s.conversations.get(new_game(s, npcs=[{"name": "Dorna", "companion": True, "sheet": {"role": "fighter", "hp": 12}}]))
        card = s.scenarios.get(base["scenario_id"])
        cid = s.conversations.create(card, party_mode="companions", companions=[
            {"of": "Dorna", "name": "Dorna Ironhand", "portraits": {"default": "/api/uploads/d.png", "moods": []}}])["id"]
        npc = next(n for n in s.conversations.list_npcs(cid) if n["name"] == "Dorna Ironhand")
        self.assertEqual(npc["portraits"]["default"], "/api/uploads/d.png")
        self.assertIn("Dorna Ironhand", s.conversations.get_state(cid)["party"])
