"""Tests for the player's lorebook."""
import unittest

from app.playerlore import always_section, clean_entries, parse_suggestions, suggest_prompt, triggered
from tests.test_core import FakeLLM, collect, make_services, new_game

ARDENT = {"name": "House Ardent", "keys": "Ardent, burning stag", "content": "The sixth great house. Sigil: a burning stag. Seat: Emberhold.\nRivals of House Valtier."}


class CleanTests(unittest.TestCase):
    def test_clean_and_limits(self):
        out = clean_entries([ARDENT, {"name": "", "content": ""}])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["keys"], ["Ardent", "burning stag"])
        self.assertTrue(out[0]["id"])
        with self.assertRaises(ValueError):
            clean_entries([{"name": "", "content": "text"}])
        with self.assertRaises(ValueError):
            clean_entries([{"name": "x", "content": "y" * 2001}])
        with self.assertRaises(ValueError):
            clean_entries("nope")

    def test_sections(self):
        e = clean_entries([ARDENT, {"name": "Off", "content": "hidden", "enabled": False}])
        sec = always_section(e)
        self.assertIn("- House Ardent: The sixth great house.", sec)
        self.assertIn("win", sec)
        self.assertNotIn("Off", sec)
        self.assertEqual(triggered(e, ["We ride to Emberhold."], 500), [])
        self.assertEqual([x["name"] for x in triggered(e, ["A banner with a burning stag!"], 500)], ["House Ardent"])
        self.assertEqual(len(triggered(e, ["house ardent sends word"], 500)), 1)  # the name works as a keyword too

    def test_suggestions(self):
        self.assertEqual(parse_suggestions("NOTHING"), [])
        self.assertEqual(parse_suggestions("- Lord Cael leads it\n2. It owns ships\n"), ["Lord Cael leads it", "It owns ships"])
        self.assertIn("House Ardent", suggest_prompt(clean_entries([ARDENT])[0], "sum", ["newest", "older"]))


class GameTests(unittest.IsolatedAsyncioTestCase):
    async def test_prompt_storage_and_fork(self):
        llm = FakeLLM()
        s = make_services(llm)
        cid = new_game(s)
        s.conversations.set_player_lore(cid, [ARDENT])
        await collect(s.engine.send(cid, "I raise the burning stag banner."))
        msgs = llm.stream_calls[-1]
        self.assertIn("World additions by the player (canon)", msgs[0]["content"])
        self.assertIn("Seat: Emberhold", msgs[-1]["content"])  # full text because a keyword came up
        fork = s.conversations.fork(cid, s.conversations.list_messages(cid)[-1]["id"])
        self.assertEqual(s.conversations.get(fork)["player_lore"][0]["name"], "House Ardent")

        sc = s.scenarios.list()[0]
        c2 = s.conversations.create(s.scenarios.get(sc["id"]), player_lore=[ARDENT])
        self.assertEqual(len(c2["player_lore"]), 1)


if __name__ == "__main__":
    unittest.main()
