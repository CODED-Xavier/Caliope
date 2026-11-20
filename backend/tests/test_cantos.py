"""Step 5: Cantos (chapters), the recap button and the map bag."""
import unittest

from app.cantos import roman
from tests.test_core import FakeLLM, collect, make_services, new_game


class ChronicleLLM(FakeLLM):
    async def chat(self, messages, json_schema=None, **kw):
        self.chat_calls.append((messages, json_schema))
        q = messages[-1]["content"]
        if json_schema:
            return "{}"
        if "chronicler" in q:
            return "The hero reached the academy and made a rival of Kael."
        if "Give a title" in q:
            return '"The Gates of Asterion"'
        if "Previously, in" in q:
            return "Previously, you crossed the gates..."
        return "Summary."


class CantoTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.llm = ChronicleLLM()
        self.s = make_services(self.llm)
        self.cid = new_game(self.s, "gm_world")

    async def test_close_and_prompt(self):
        s, cid = self.s, self.cid
        self.assertEqual([c["label"] for c in s.cantos.list(cid)], ["Canto I"])
        await collect(s.engine.send(cid, "I walk to the gates."))
        with self.assertRaises(ValueError):
            await s.cantos.close(cid)            # too short
        await collect(s.engine.send(cid, "I talk to Kael."))
        out = await s.cantos.close(cid)
        self.assertEqual(out["closed"]["title"], "The Gates of Asterion")
        self.assertEqual([c["label"] for c in out["cantos"]], ["Canto I", "Canto II"])
        await collect(s.engine.send(cid, "Next morning, I train."))
        system = self.llm.stream_calls[-1][0]["content"]
        self.assertIn("Canto I, The Gates of Asterion: The hero reached the academy", system)
        cantos = s.cantos.list(cid)
        self.assertEqual(cantos[1]["messages"], 2)
        # rewinding into Canto I reopens it and drops Canto II
        first_msgs = s.conversations.list_messages(cid)
        s.engine.rewind(cid, first_msgs[2]["id"])
        cantos = s.cantos.list(cid)
        self.assertEqual(len(cantos), 1)
        self.assertIsNone(cantos[0]["closed_at"])
        self.assertEqual(cantos[0]["chronicle"], "")

    async def test_recap_is_not_saved(self):
        s, cid = self.s, self.cid
        await collect(s.engine.send(cid, "I look around."))
        n = len(s.conversations.list_messages(cid))
        text = await s.cantos.recap(cid, "My game", "", "en")
        self.assertTrue(text.startswith("Previously"))
        self.assertEqual(len(s.conversations.list_messages(cid)), n)

    async def test_map_bag(self):
        s, cid = self.s, self.cid
        await collect(s.engine.send(cid, "I look around."))
        msg = s.conversations.list_messages(cid)[-1]
        pic = {"url": "https://image.pollinations.ai/prompt/x?seed=1", "prompt": "a hall"}
        st = s.conversations.get_state(cid)
        st["location"] = "Grand Hall"
        st["date_label"] = "Day 1 of Spring"
        s.conversations.save_state(cid, st)
        kept = s.cantos.auto_keep(cid, msg["id"], pic, st)
        self.assertEqual((kept["title"], kept["location"], kept["canto"]), ("Grand Hall", "Grand Hall", 1))
        self.assertIsNone(s.cantos.auto_keep(cid, msg["id"], {**pic, "url": "https://x/2"}, st))  # same place: not again
        again = s.cantos.keep(cid, msg["id"], pic, st, "dup")
        self.assertEqual(again["id"], kept["id"])                                                  # same picture: once
        s.cantos.rename_picture(kept["id"], "The Grand Hall at dawn")
        self.assertEqual(s.cantos.gallery(cid)[0]["title"], "The Grand Hall at dawn")
        s.engine.undo(cid)                                                                        # undoing the reply drops it
        self.assertEqual(s.cantos.gallery(cid), [])

    def test_roman(self):
        self.assertEqual([roman(n) for n in (1, 4, 9, 14, 40, 99)], ["I", "IV", "IX", "XIV", "XL", "XCIX"])


if __name__ == "__main__":
    unittest.main()
