"""↺ Restart: the same card from its opening, same character with full HP; the old run kept or deleted."""
import unittest

from tests.test_cards2 import card
from tests.test_core import make_services


class RestartTests(unittest.TestCase):
    def test_restart_keeps_character_and_resets_story(self):
        s = make_services()
        sc = card(s, starts=[{"name": "Cult member", "opening": "Black candles.", "focus": ["Bishop Corvin"]}])
        conv = s.conversations.create(sc, player={"name": "Aster", "hp": {"current": 13, "max": 13}, "ac": 18},
                                      setup="app", start="cult-member")
        st = s.conversations.get_state(conv["id"])
        st["player"]["hp"]["current"] = 3
        st["gold"] = 999
        s.conversations.save_state(conv["id"], st)
        s.conversations.add_message(conv["id"], "user", "I attack.")
        new = s.conversations.restart(conv["id"], s.scenarios.get(sc["id"]), keep=True)
        nst = s.conversations.get_state(new["id"])
        self.assertEqual(nst["player"]["name"], "Aster")
        self.assertEqual(nst["player"]["hp"], {"current": 13, "max": 13})
        self.assertEqual(nst["player"]["ac"], 18)
        self.assertNotEqual(nst.get("gold"), 999)
        self.assertEqual(nst.get("setup"), "app")
        self.assertEqual(new["scenario"]["route"]["id"], "cult-member")
        msgs = s.conversations.list_messages(new["id"])
        self.assertEqual([m["role"] for m in msgs], ["assistant"])
        self.assertIn("Black candles", msgs[0]["content"])
        self.assertTrue(s.conversations.get(conv["id"])["title"].endswith("(old run)"))
        again = s.conversations.restart(conv["id"], None, keep=False)  # card gone: this game's copy; old run deleted
        self.assertEqual(s.conversations.get_state(again["id"])["player"]["name"], "Aster")
        with self.assertRaises(Exception):
            s.conversations.get(conv["id"])


if __name__ == "__main__":
    unittest.main()
