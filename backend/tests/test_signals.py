"""Tests for skipping the tracker on quiet turns."""
import unittest

from app.signals import needs_tracking, quiet_minutes
from tests.test_core import FakeLLM, collect, make_services, new_game


class SignalTests(unittest.TestCase):
    def test_signals(self):
        self.assertFalse(needs_tracking('"How was your day?"', 'Mira laughs. "Long, as always."', ["Mira"]))
        self.assertTrue(needs_tracking("I pay the innkeeper.", "He takes your coins.", []))
        self.assertTrue(needs_tracking("I wait.", "The stranger says he is called Doran.", []))
        self.assertTrue(needs_tracking("Hi", "Corvin waves. Behind him, Corvin's dog barks.", ["Mira"]))  # a new name, twice
        self.assertFalse(needs_tracking("Hi", "Mira waves. Mira smiles.", ["Mira"]))
        self.assertTrue(needs_tracking("Eu compro a espada.", "Ele aceita o ouro.", []))
        self.assertEqual(quiet_minutes("a " * 10, "b " * 10), 2)
        self.assertEqual(quiet_minutes("a " * 400, "b " * 400), 15)


class EngineTests(unittest.IsolatedAsyncioTestCase):
    async def test_quiet_turns_skip_then_catch_up(self):
        llm = FakeLLM()
        s = make_services(llm)
        s.settings.update({"tracker_skip": True})
        cid = new_game(s, calendar={"enabled": True, "preset": "fantasy"})
        llm.reply = 'The old man nods slowly. "Sit, sit."'
        calls = len(llm.chat_calls)
        await collect(s.engine.send(cid, '"Good evening."'))
        self.assertEqual(len(llm.chat_calls), calls)  # skipped: no tracker call
        st = s.conversations.get_state(cid)
        self.assertEqual(st["untracked"], 1)
        self.assertGreaterEqual(st["clock"]["minutes"], 2)  # the clock still moves
        await collect(s.engine.send(cid, '"Thank you."'))  # second quiet turn: the tracker catches up (interval 1 + 1)
        self.assertEqual(len(llm.chat_calls), calls + 1)
        prompt = llm.chat_calls[-1][0][1]["content"]
        self.assertIn("EXCHANGE 1", prompt)
        self.assertIn("EXCHANGE 2", prompt)
        self.assertEqual(s.conversations.get_state(cid)["untracked"], 0)

    async def test_signal_runs_at_once(self):
        llm = FakeLLM()
        s = make_services(llm)
        s.settings.update({"tracker_skip": True})
        cid = new_game(s)
        llm.reply = "The merchant takes your gold and hands you the map."
        calls = len(llm.chat_calls)
        await collect(s.engine.send(cid, "I buy the map."))
        self.assertEqual(len(llm.chat_calls), calls + 1)


if __name__ == "__main__":
    unittest.main()
