"""Tests for measuring characters per token from the server's real counts."""
import unittest

from app import util
from tests.test_core import FakeLLM, collect, make_services, new_game


class CalibrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_learns_from_real_counts(self):
        llm = FakeLLM()
        s = make_services(llm)
        cid = new_game(s)
        await collect(s.engine.send(cid, "hello"))  # no usage reported: nothing changes
        self.assertEqual(s.settings.get("chars_per_token"), 3.4)
        async def stream(messages, stop=None, **kw):  # this model packs 4.2 characters into a token
            llm.stream_calls.append(messages)
            llm.last_usage = {"prompt_tokens": int(sum(len(m["content"]) for m in messages) / 4.2) + 6 * len(messages)}
            yield "Fine."
        llm.stream_chat = stream
        for _ in range(8):
            await collect(s.engine.send(cid, "hello"))
        ratio = s.settings.get("chars_per_token")
        self.assertGreater(ratio, 3.9)
        self.assertLessEqual(ratio, 4.3)
        self.assertAlmostEqual(util.CHARS_PER_TOKEN, ratio)
        self.assertLess(util.estimate_tokens("x" * 4200), 1100)
        timing = s.conversations.list_messages(cid)[-1]["meta"]["timing"]
        self.assertEqual(timing["prompt_tokens"], llm.last_usage["prompt_tokens"])
        util.set_chars_per_token(3.4)


if __name__ == "__main__":
    unittest.main()
