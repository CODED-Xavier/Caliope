"""Tests for scene pictures."""
import asyncio
import time
import unittest
from urllib.parse import unquote

from app import scenes
from app.scenes import clean_prompt, is_pollinations, picture_url, polite_fetch, write_prompt
from tests.test_core import FakeLLM, collect, make_services, new_game


class PromptTests(unittest.IsolatedAsyncioTestCase):
    async def test_prompt_hides_names_and_adds_style(self):
        llm = FakeLLM()
        llm.summary = 'Prompt: "Rena stands in a misty harbor at dawn, gulls over broken masts"'
        text = await write_prompt(llm, "Rena walks to the docks.", {"location": "Harbor", "time": "dawn"}, "oil painting", ["Rena"])
        self.assertNotIn("Rena", text)
        self.assertTrue(text.startswith("a figure stands in a misty harbor"))
        self.assertIn(", oil painting, ", text)
        self.assertTrue(text.endswith("rich background"))
        ask = llm.chat_calls[-1][0][0]["content"]
        self.assertIn("Where/when: Harbor, dawn", ask)
        self.assertIn("never a plain or white background", ask)                  # the place, in detail

    async def test_scene_prompt_uses_the_characters_looks(self):
        llm = FakeLLM()
        llm.summary = "Lyra Moonwhisper leans on the railing while Aster watches"
        text = await write_prompt(llm, "Lyra leans on the railing.", {}, "", ["Lyra Moonwhisper", "Aster"], kind="scene",
                                  people=[("Lyra Moonwhisper", "Elf; hair: silver; eyes: violet")])
        ask = llm.chat_calls[-1][0][0]["content"]
        self.assertIn("pose, gesture", ask)
        self.assertIn("- Lyra Moonwhisper: Elf; hair: silver; eyes: violet", ask)
        self.assertNotIn("Lyra", text)
        self.assertNotIn("Moonwhisper", text)
        self.assertNotIn("Aster", text)

    def test_url(self):
        url = picture_url("a dark forest, rain", 42)
        self.assertTrue(is_pollinations(url))
        self.assertIn("width=768&height=432&seed=42", url)
        self.assertIn("a dark forest, rain", unquote(url))
        self.assertFalse(is_pollinations("https://evil.example/image.pollinations.ai"))
        self.assertEqual(clean_prompt('  "image prompt: a tower"  '), "a tower")

    async def test_polite_fetch_waits_between_pictures(self):
        scenes.MIN_GAP_SECONDS = 0.3
        scenes._last_request = 0.0
        calls = []

        async def fetch(url):
            calls.append(time.monotonic())
            return b"x", "image/jpeg"

        await asyncio.gather(polite_fetch("a", fetch), polite_fetch("b", fetch))
        self.assertGreaterEqual(calls[1] - calls[0], 0.28)
        scenes.MIN_GAP_SECONDS = 46


class EngineTests(unittest.IsolatedAsyncioTestCase):
    async def test_off_by_default_then_on_first_scene_and_new_place(self):
        llm = FakeLLM()
        s = make_services(llm)
        cid = new_game(s, "gm_world")
        events = await collect(s.engine.send(cid, "I look around."))
        self.assertFalse(any(e["type"] == "scene_picture" for e in events))      # off by default
        s.settings.update({"scene_pictures": True})
        llm.summary = "a smoky tavern with a roaring fire"
        events = await collect(s.engine.send(cid, "I sit down."))
        pics = [e for e in events if e["type"] == "scene_picture"]
        self.assertEqual(len(pics), 1)                                           # the first picture of the game
        self.assertTrue(pics[0]["picture"]["url"].startswith("https://image.pollinations.ai/prompt/"))
        events = await collect(s.engine.send(cid, "I drink."))
        self.assertFalse(any(e["type"] == "scene_picture" for e in events))      # same place: no new picture
        llm.analysis = {"location": "The old mill"}
        events = await collect(s.engine.send(cid, "I walk to the old mill."))
        self.assertTrue(any(e["type"] == "scene_picture" for e in events))       # new place: new picture

    async def test_paint_and_reroll(self):
        llm = FakeLLM()
        s = make_services(llm)
        cid = new_game(s, "gm_world")
        await collect(s.engine.send(cid, "Hello"))
        mid = s.conversations.list_messages(cid)[-1]["id"]
        llm.summary = "a quiet road under stars"
        first = (await s.engine.paint_scene(cid, mid))["meta"]["scene_picture"]
        again = (await s.engine.paint_scene(cid, mid, reroll=True))["meta"]["scene_picture"]
        self.assertEqual(first["prompt"], again["prompt"])
        self.assertNotEqual(first["seed"], again["seed"])


if __name__ == "__main__":
    unittest.main()
