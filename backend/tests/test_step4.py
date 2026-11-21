"""Tests for v0.7.0: writing rules, player emphasis, weather, start screens, drafts, save points."""
import unittest

from app.writing import for_model, is_gm_message, strip_thoughts, thoughts
from tests.test_core import FakeLLM, collect, make_services, new_game


class WritingRuleTests(unittest.TestCase):
    def test_marks(self):
        t = "\"Hello,\" *I bow*. 'She looks nervous.' I don't move."
        self.assertEqual(thoughts(t), ["She looks nervous."])
        self.assertNotIn("nervous", strip_thoughts(t))
        self.assertIn("don't", strip_thoughts(t))
        self.assertIn("[thought: She looks nervous.]", for_model(t))

    def test_quotes_inside_speech_are_not_thoughts(self):
        self.assertEqual(thoughts("\"They said 'never' to me.\""), [])

    def test_apostrophes(self):
        self.assertEqual(thoughts("The guards' armor and Rena's sword."), [])
        self.assertEqual(thoughts("'I hope she's fine'"), ["I hope she's fine"])

    def test_gm_messages(self):
        self.assertTrue(is_gm_message("/how much gold do I have?"))
        self.assertFalse(is_gm_message("/roll 1d20"))
        self.assertEqual(for_model("/is it night?"), "[message to the GM: is it night?]")
        self.assertEqual(strip_thoughts("/is it night?"), "")


class PromptTests(unittest.IsolatedAsyncioTestCase):
    async def test_thoughts_reach_gm_only(self):
        llm = FakeLLM()
        s = make_services(llm)
        cid = new_game(s, "gm_world")
        llm.analysis = {"memories": [{"text": "Something happened", "importance": 3, "characters": []}]}
        await collect(s.engine.send(cid, "\"Good evening.\" 'This innkeeper is hiding something.'"))
        prompt = llm.stream_calls[-1]
        self.assertIn("[thought: This innkeeper is hiding something.]", prompt[-1]["content"])
        self.assertIn("## How the player writes", prompt[0]["content"])
        self.assertIn("## The player's character", prompt[0]["content"])
        tracker_input = llm.chat_calls[-1][0][-1]["content"]
        self.assertNotIn("hiding something", tracker_input)
        self.assertIn("Good evening", tracker_input)

    async def test_gm_message_skips_tracker(self):
        llm = FakeLLM()
        s = make_services(llm)
        cid = new_game(s, "gm_world")
        await collect(s.engine.send(cid, "/what time is it in the story?"))
        self.assertEqual(llm.chat_calls, [])
        self.assertEqual(llm.stream_calls[-1][-1]["content"], "what time is it in the story?")  # its own prompt (test_part6)

    async def test_weather_is_tracked(self):
        llm = FakeLLM()
        s = make_services(llm)
        cid = new_game(s, "gm_world")
        llm.analysis = {"weather": "heavy rain", "time": "night"}
        events = await collect(s.engine.send(cid, "I wait."))
        state = s.conversations.get_state(cid)
        self.assertEqual((state["weather"], state["time"]), ("heavy rain", "night"))
        self.assertIn("Weather: heavy rain", [e for e in events if e["type"] == "state"][0]["changes"])
        await collect(s.engine.send(cid, "I wait more."))
        self.assertIn("Weather: heavy rain.", llm.stream_calls[-1][-1]["content"])

    async def test_card_parts_stay_before_summary(self):
        llm = FakeLLM()
        s = make_services(llm)
        cid = new_game(s, "gm_world")
        s.conversations.set_summary(cid, "Old events.", 0)
        await collect(s.engine.send(cid, "Hi"))
        system = llm.stream_calls[-1][0]["content"]
        self.assertLess(system.index("## How the player writes"), system.index("## Story so far"))
        self.assertLess(system.index("## The player's character"), system.index("## Story so far"))


if __name__ == "__main__":
    unittest.main()


class StartScreenTests(unittest.IsolatedAsyncioTestCase):
    async def test_player_from_start_screen(self):
        llm = FakeLLM()
        s = make_services(llm)
        sc = s.scenarios.get(next(x["id"] for x in s.scenarios.list() if x["mode"] == "gm_world"))
        player = {"name": "Kaela", "race": "Elf", "class": "Ranger", "stats": {"STR": 12, "DEX": 16, "CON": 13, "INT": 10, "WIS": 14, "CHA": 8},
                  "background": "Raised by wolves.", "traits": "Quiet", "bogus": "x"}
        cid = s.conversations.create(sc, player=player, setup="app")["id"]
        state = s.conversations.get_state(cid)
        self.assertEqual((state["player"]["name"], state["player"]["class"], state["player"]["stats"]["DEX"]), ("Kaela", "Ranger", 16))
        self.assertNotIn("bogus", state["player"])
        await collect(s.engine.send(cid, "I look around."))
        prompt = llm.stream_calls[-1]
        self.assertIn("Name: Kaela (Elf Ranger, level 1)", prompt[0]["content"])
        self.assertIn("DEX 16 (+3)", prompt[0]["content"])
        self.assertIn("## Character creation", prompt[-1]["content"])

    async def test_drafts(self):
        from app.drafts import draft_card_field, draft_player
        llm = FakeLLM()
        llm.summary = "\"The storm breaks over the harbor.\""
        text = await draft_card_field(llm, "opening_message", {"name": "Harbor", "world": "A port town"})
        self.assertEqual(text, "The storm breaks over the harbor.")
        self.assertIn("A port town", llm.chat_calls[-1][0][0]["content"])
        with self.assertRaises(ValueError):
            await draft_card_field(llm, "npcs", {})
        llm.summary = '{"name": "Kaela", "background": "A smuggler.", "traits": "Bold", "class": 5}'
        got = await draft_player(llm, {"name": "Harbor"}, {"name": "Kaela"})
        self.assertEqual(got, {"name": "Kaela", "background": "A smuggler.", "traits": "Bold"})


class SavePointTests(unittest.IsolatedAsyncioTestCase):
    async def test_fork_copies_state_at_that_point(self):
        llm = FakeLLM()
        s = make_services(llm)
        cid = new_game(s, "gm_world")
        llm.analysis = {"gold_change": 10, "new_npcs": [{"name": "Brann", "description": "A smith", "personality": "", "appearance": {}}],
                        "memories": [{"text": "Brann forged a blade for the player", "importance": 4, "characters": ["Brann"]}]}
        await collect(s.engine.send(cid, "one"))
        llm.analysis = {"gold_change": 100, "memories": [{"text": "The player found a dragon hoard", "importance": 5, "characters": []}]}
        await collect(s.engine.send(cid, "two"))
        msgs = s.conversations.list_messages(cid)
        first_reply = msgs[2]
        new_id = s.engine.fork(cid, first_reply["id"])
        self.assertEqual(len(s.conversations.list_messages(new_id)), 3)
        self.assertEqual(s.conversations.get_state(new_id)["gold"], 25)          # after turn one, before turn two
        self.assertEqual(s.conversations.get_state(cid)["gold"], 125)            # original unchanged
        self.assertEqual([m["text"] for m in s.memory.list(new_id)], ["Brann forged a blade for the player"])
        self.assertIn("Brann", [n["name"] for n in s.conversations.list_npcs(new_id)])
        # undo data inside the copy still works and does not touch the original game's characters
        s.engine.rewind(new_id, s.conversations.list_messages(new_id)[0]["id"], inclusive=False)
        self.assertEqual(s.conversations.get_state(new_id)["gold"], 15)
        self.assertNotIn("Brann", [n["name"] for n in s.conversations.list_npcs(new_id)])
        self.assertIn("Brann", [n["name"] for n in s.conversations.list_npcs(cid)])

    async def test_export_markdown(self):
        from app.exporting import export_markdown
        llm = FakeLLM()
        s = make_services(llm)
        cid = new_game(s, "gm_world")
        llm.reply = "[[show: Brann | Happy]]\nBrann waves."
        await collect(s.engine.send(cid, "Hello"))
        md = export_markdown(s.conversations.get(cid), s.conversations.list_messages(cid), s.conversations.get_state(cid))
        self.assertIn("**Adventurer:** Hello", md)
        self.assertIn("Brann waves.", md)
        self.assertNotIn("[[show", md)
