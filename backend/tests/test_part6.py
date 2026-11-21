"""Beta feedback: the Aedo answers "/questions" outside the story; the story keeps its own memory slot."""
import unittest

from app.aedo_desk import without_ooc
from app.llm import LLMClient
from app.runtime import build_command
from tests.test_core import FakeLLM, collect, make_services


class AedoDeskTests(unittest.IsolatedAsyncioTestCase):
    async def test_question_is_answered_outside_the_story(self):
        llm = FakeLLM()
        s = make_services(llm)
        sc = s.scenarios.create({"name": "Academy", "mode": "gm_world", "opening_message": "The gates open."})
        cid = s.conversations.create(s.scenarios.get(sc["id"]))["id"]
        st = s.conversations.get_state(cid)
        st["player"].update(name="Aster", background="Born in the Sengo house, raised by a soul forge.")
        s.conversations.save_state(cid, st)

        llm.reply = "Your background: Born in the Sengo house, raised by a soul forge."
        events = await collect(s.engine.send(cid, "/give me the background I wrote"))
        answer = next(e["message"] for e in events if e["type"] == "assistant_message")
        self.assertTrue(answer["meta"]["ooc"])
        system = llm.stream_calls[-1][0]["content"]
        self.assertIn("OUTSIDE the story", system)
        self.assertIn("soul forge", system)                      # the sheet is in its prompt
        self.assertEqual(llm.stream_calls[-1][-1]["content"], "give me the background I wrote")
        self.assertFalse(any(e["type"] == "analysis_start" for e in events))   # no tracker for it
        self.assertFalse(llm.stream_kwargs[-1].get("story"))   # helper slot, the story's memory stays

        llm.reply = "The bell rings."
        await collect(s.engine.send(cid, "*I walk in*"))
        story = "\n".join(m["content"] for m in llm.stream_calls[-1])
        self.assertNotIn("background I wrote", story)            # the question and answer are not in the story
        self.assertNotIn("Your background:", story)
        self.assertTrue(llm.stream_kwargs[-1].get("story"))

    def test_without_ooc_also_drops_old_answers(self):
        h = [{"role": "assistant", "content": "Opening", "meta": {}},
             {"role": "user", "content": "/what time is it?", "meta": {}},
             {"role": "assistant", "content": "(answered in character)", "meta": {}},
             {"role": "user", "content": "I go.", "meta": {}}]
        self.assertEqual([m["content"] for m in without_ooc(h)], ["Opening", "I go."])


class SlotTests(unittest.TestCase):
    def test_engine_has_a_story_slot_and_a_helper_slot(self):
        cmd = build_command("llama-server", "m.gguf", 8192, 8091, "auto")
        self.assertEqual(cmd[cmd.index("-np") + 1], "2")
        self.assertEqual(cmd[cmd.index("-c") + 1], "16384")   # each slot keeps the whole context

    def test_payload_picks_the_slot_only_for_the_builtin_engine(self):
        base = {"temperature": 0.8, "top_p": 0.9, "max_tokens": 500}
        builtin = LLMClient(lambda: dict(base, ai_engine="builtin"))
        self.assertEqual(builtin._payload([], "m", True, None, {"story": True})["id_slot"], 0)
        self.assertEqual(builtin._payload([], "m", False, None, {})["id_slot"], 1)
        lm = LLMClient(lambda: dict(base, ai_engine="lmstudio"))
        p = lm._payload([], "m", True, None, {"story": True})
        self.assertNotIn("id_slot", p)
        self.assertNotIn("story", p)


if __name__ == "__main__":
    unittest.main()
