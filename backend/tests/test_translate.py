"""Translating story text, and the story language chosen for one game ("play this card in Portuguese")."""
import importlib.util
import unittest

from app.translate import pieces, translate
from tests.test_core import FakeLLM, make_services


class EchoPT(FakeLLM):
    async def chat(self, messages, json_schema=None, **kw):
        text = messages[-1]["content"].split("TEXT:\n", 1)[1]
        return "PT: " + text


class PiecesTests(unittest.TestCase):
    def test_cut_at_paragraphs_and_nothing_lost(self):
        text = "\n\n".join(f"Paragraph {i}. " + "word " * 60 for i in range(12))
        parts = pieces(text, 700)
        self.assertGreater(len(parts), 3)
        self.assertEqual("".join(parts), text)

    def test_a_huge_paragraph_is_split_by_sentences(self):
        text = "A sentence here. " * 300
        self.assertGreater(len(pieces(text, 500)), 5)


class TranslateTests(unittest.IsolatedAsyncioTestCase):
    async def test_every_piece_is_translated(self):
        text = "The bells rang.\n\n[[show: Emily | Happy]]\n**[Emily]:** \"Welcome!\""
        out = await translate(EchoPT(), text, "pt-BR")
        self.assertTrue(out.startswith("PT: The bells rang."))

    async def test_a_failed_or_short_answer_keeps_the_original(self):
        class Bad(FakeLLM):
            async def chat(self, messages, json_schema=None, **kw):
                return "Sorry."
        text = "A long paragraph of story that must not be lost by a bad answer from the model."
        self.assertEqual((await translate(Bad(), text, "pt-BR")).strip(), text)

    @unittest.skipUnless(importlib.util.find_spec("fastapi"), "FastAPI is not installed here")
    async def test_a_game_in_portuguese_translates_its_opening(self):
        s = make_services(EchoPT())
        sc = s.scenarios.create({"name": "Academy", "mode": "gm_cast", "opening_message": "The gates open at dawn."})
        from app import main
        main.app.state.svc = s
        conv = s.conversations.create(s.scenarios.get(sc["id"]), language="pt-BR")
        await main._translate_opening(conv["id"], "pt-BR")
        first = s.conversations.list_messages(conv["id"])[0]
        self.assertTrue(first["content"].startswith("PT: The gates open"))
        self.assertEqual(first["meta"]["translated"], "pt-BR")
        self.assertEqual(s.conversations.get(conv["id"])["scenario"]["language"], "pt-BR")

    def test_restart_and_card_updates_keep_the_games_language(self):
        s = make_services()
        sc = s.scenarios.create({"name": "Academy", "mode": "gm_cast", "opening_message": "Hi.", "language": "en"})
        conv = s.conversations.create(s.scenarios.get(sc["id"]), language="pt-BR")
        s.conversations.refresh_from_card(conv["id"], s.scenarios.get(sc["id"]))
        self.assertEqual(s.conversations.get(conv["id"])["scenario"]["language"], "pt-BR")
        new = s.conversations.restart(conv["id"], s.scenarios.get(sc["id"]))
        self.assertEqual(s.conversations.get(new["id"])["scenario"]["language"], "pt-BR")


if __name__ == "__main__":
    unittest.main()


class CardTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_translated_copy_of_a_card(self):
        from app.translate import JOBS, texts_of, translate_card
        s = make_services(EchoPT())
        sc = s.scenarios.create({
            "name": "Academy", "mode": "gm_cast", "opening_message": "The gates open at dawn, and the students arrive.",
            "npcs": [{"name": "Lilia Valenheart", "description": "A proud knight of the red-haired house.",
                      "portraits": {"default": "/api/cardpics/5/lilia/1.png", "moods": []}}],
            "lorebook": {"entries": [{"name": "House Valenheart", "keys": ["Valenheart", "duchy"], "content": "A ducal house that serves the throne."}]},
            "information": {"post_history": "INFO\\nTier: [Tier] | Gold: [N]"}})
        data = s.scenarios.get(sc["id"])["data"]
        paths = [p for p, _ in texts_of(data)]
        self.assertTrue(any(p[-1] == "opening_message" for p in paths))
        self.assertFalse(any("post_history" in p or "name" in p or "portraits" in p for p in paths))
        JOBS[sc["id"]] = {"status": "running", "done": 0, "total": 0, "new_id": None, "error": ""}
        await translate_card(s, sc["id"], "pt-BR")
        job = JOBS[sc["id"]]
        self.assertEqual(job["status"], "done")
        new = s.scenarios.get(job["new_id"])
        self.assertEqual(new["name"], "Academy (Português)")
        self.assertEqual(new["data"]["language"], "pt-BR")
        self.assertTrue(new["data"]["opening_message"].startswith("PT: "))
        self.assertTrue(new["data"]["npcs"][0]["description"].startswith("PT: "))
        self.assertEqual(new["data"]["npcs"][0]["name"], "Lilia Valenheart")
        self.assertIn("Valenheart", new["data"]["lorebook"]["entries"][0]["keys"])
        self.assertIn("INFO", new["data"]["information"]["post_history"])
        self.assertTrue(s.scenarios.get(sc["id"])["data"]["opening_message"].startswith("The gates"))  # the original stays
