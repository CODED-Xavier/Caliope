"""Step 3: the Muse (writer's room) and card making."""
import unittest

from app.muse import parse_cast, parse_sheet
from tests.test_core import FakeLLM, collect, make_services


class MuseLLM(FakeLLM):
    """Answers the card maker's questions like a model would."""

    async def chat(self, messages, json_schema=None, **kw):
        self.chat_calls.append((messages, json_schema))
        q = messages[-1]["content"]
        if "Summarize this brainstorm" in q:
            return "- The Black Seminary trains cultists.\n- Bishop Corvin leads it."
        if "card's title" in q:
            return "The Black Seminary"
        if "pitch" in q:
            return "A cult academy where loyalty is tested in blood and kindness is dangerous."
        if "ONE single character" in q:
            return "GM"
        if "Describe the world" in q:
            return "Beneath Lumencia lies the Black Seminary..."
        if "tone and writing style" in q:
            return "Gothic, intimate, light-dark."
        if "List the important characters" in q or "List the characters" in q:
            return "1. **Bishop Corvin** - head of the seminary\n2. Sister Maelis: a doubting acolyte\n3. Bishop Corvin - duplicate"
        if "Write the sheet of" in q:
            return ("Description: Leads the rites.\nPersonality: Gentle and cruel.\nSpeech: Soft, formal.\n"
                    "Looks: Silver hair, black robes.\nRace: Human")
        if "opening message" in q:
            return "You wake to bells under the earth."
        return "ok"


class MuseTests(unittest.IsolatedAsyncioTestCase):
    async def test_talk_is_saved(self):
        llm = FakeLLM()
        llm.reply = "What if the academy had a hidden twin?"
        s = make_services(llm)
        t = s.muse.create()
        events = await collect(s.muse.talk(t["id"], "I want a dark route for Lumencia"))
        self.assertEqual([e["type"] for e in events][-1], "done")
        talk = s.muse.get(t["id"])
        self.assertEqual([m["role"] for m in talk["messages"]], ["user", "assistant"])
        self.assertEqual(talk["title"], "I want a dark route for Lumencia")
        self.assertIn("Muse of Calíope", llm.stream_calls[-1][0]["content"])
        s.muse.undo_last(t["id"])
        self.assertEqual(s.muse.get(t["id"])["messages"], [])

    async def test_long_talk_is_summarized(self):
        llm = MuseLLM()
        s = make_services(llm)
        s.settings.update({"context_window": 2048})
        t = s.muse.create("Seminary")
        for i in range(14):
            s.muse._add(t["id"], "user" if i % 2 == 0 else "assistant", f"Idea {i}: " + "words " * 150)
        await collect(s.muse.talk(t["id"], "Continue"))
        talk = s.muse.get(t["id"])
        self.assertIn("Black Seminary", talk["summary"])
        self.assertGreater(talk["summary_upto"], 0)
        self.assertIn("Black Seminary", llm.stream_calls[-1][0]["content"])

    async def test_make_card(self):
        llm = MuseLLM()
        s = make_services(llm)
        t = s.muse.create()
        s.muse._add(t["id"], "user", "A cult academy route")
        s.muse._add(t["id"], "assistant", "Let's call it the Black Seminary.")
        events = await collect(s.muse.make_card(t["id"]))
        card = next(e["card"] for e in events if e["type"] == "card")
        self.assertEqual(card["name"], "The Black Seminary")
        self.assertEqual(card["mode"], "gm_cast")
        self.assertEqual([n["name"] for n in card["npcs"]], ["Bishop Corvin", "Sister Maelis"])
        corvin = card["npcs"][0]
        self.assertTrue(corvin["description"].startswith("head of the seminary. Leads the rites."))
        self.assertEqual(corvin["speech_style"], "Soft, formal.")
        self.assertEqual(card["opening_message"], "You wake to bells under the earth.")
        self.assertTrue(any(e["type"] == "progress" for e in events))
        # the card can be added to Calíope as it is
        saved = s.scenarios.create(card)
        self.assertEqual(saved["name"], "The Black Seminary")

    async def test_empty_talk_cannot_make_card(self):
        s = make_services(MuseLLM())
        t = s.muse.create()
        events = await collect(s.muse.make_card(t["id"]))
        self.assertEqual(events[0]["type"], "error")

    def test_parsers(self):
        self.assertEqual(parse_cast("- Artemis — the professor\nLilia: a student\n\n3) Kael (rival)"),
                         [("Artemis", "the professor"), ("Lilia", "a student"), ("Kael", "rival")])
        sheet = parse_sheet("**Description:** A knight.\nShe hides a debt.\nSpeech style: Curt.")
        self.assertEqual(sheet["description"], "A knight. She hides a debt.")
        self.assertEqual(sheet["speech"], "Curt.")


if __name__ == "__main__":
    unittest.main()


class AddCharactersTests(unittest.IsolatedAsyncioTestCase):
    async def test_make_and_merge(self):
        from app.npcfill import merge_characters
        llm = MuseLLM()
        s = make_services(llm)
        t = s.muse.create()
        s.muse._add(t["id"], "user", "Students for the cult route: Bishop Corvin and Sister Maelis")
        events = await collect(s.muse.make_characters(t["id"]))
        npcs = next(e["npcs"] for e in events if e["type"] == "characters")
        self.assertEqual([n["name"] for n in npcs], ["Bishop Corvin", "Sister Maelis"])
        card = {"npcs": [{"name": "Maelis", "portraits": {"default": "/api/cardpics/1/maelis/1.png", "moods": []},
                          "personality": "Already written"}]}
        data, added, updated = merge_characters(card, npcs)
        self.assertEqual(added, ["Bishop Corvin"])
        self.assertEqual(updated, ["Maelis"])                       # matched the picture-folder character by name
        maelis = data["npcs"][0]
        self.assertEqual(maelis["personality"], "Already written")  # never overwritten
        self.assertEqual(maelis["speech_style"], "Soft, formal.")
        self.assertEqual(maelis["portraits"]["default"], "/api/cardpics/1/maelis/1.png")
        self.assertFalse(data["npcs"][1]["met"])
