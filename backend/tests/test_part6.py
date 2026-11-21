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


class SheetStatusTests(unittest.IsolatedAsyncioTestCase):
    async def test_sheet_in_chat_fills_the_card_status_for_a_character_made_on_the_start_screen(self):
        from app import sheetchat, statusbook
        tpl = "INFO\nTier: [Tier] | Rank: [Year]\nAttributes (1-10): Magic [1-10] | Martial [1-10]\n- Body: [Grade] [[X]/100]"
        fields = statusbook.custom_fields(tpl)
        self.assertEqual(fields, ["Tier", "Rank", "Magic", "Martial", "Body"])
        text = "Name & Origin: Aster\nDepartment: Magic\nAttributes: Magic 8 | Martial 4\nStats: Body D+"
        state = {"setup": "app", "player": {"name": "Aster", "background": "Mine.", "stats": {"STR": 10}}, "card_status": {}}
        self.assertTrue(sheetchat.wanted(state, 1, text, fields))
        self.assertFalse(sheetchat.wanted(state, 1, text, []))            # no card status and made on the start screen

        llm = FakeLLM()
        seen = {}

        async def chat(messages, json_schema=None, **kw):
            seen["schema"] = json_schema
            return ('{"name": "Someone else", "race": "", "class": "Mage", "background": "Other", "looks": "", "personality": "",'
                    ' "gold": -1, "attributes": [], "other": [], "status": [{"field": "Magic", "value": "8"},'
                    ' {"field": "Martial", "value": "4"}, {"field": "Body", "value": "D+ [0/100]"}]}')
        llm.chat = chat
        sheet = await sheetchat.read_sheet(llm, "Tell me your sheet.", text, fields, {})
        self.assertEqual(seen["schema"]["properties"]["status"]["items"]["properties"]["field"]["enum"], fields)
        got = sheetchat.apply_sheet(state, sheet, keep_existing=True)
        got += statusbook.apply_changes(state, tpl, sheet["status"])
        self.assertEqual(state["player"]["name"], "Aster")                   # what you made stays
        self.assertEqual(state["player"]["background"], "Mine.")
        self.assertEqual(state["player"]["class"], "Mage")                   # empty boxes are filled
        self.assertEqual(state["card_status"]["Magic"], "8")
        self.assertEqual(state["card_status"]["Body"], "D+ [0/100]")


class WarmTests(unittest.IsolatedAsyncioTestCase):
    async def test_warm_reads_the_story_only_with_the_builtin_engine(self):
        llm = FakeLLM()
        s = make_services(llm)
        sc = s.scenarios.create({"name": "Academy", "mode": "gm_world", "opening_message": "The gates open."})
        cid = s.conversations.create(s.scenarios.get(sc["id"]))["id"]
        self.assertFalse(await s.engine.warm(cid))                         # LM Studio mode: nothing
        s.settings.update({"ai_engine": "builtin"})
        self.assertTrue(await s.engine.warm(cid))
        self.assertTrue(llm.stream_kwargs[-1]["story"])
        self.assertEqual(llm.stream_kwargs[-1]["max_tokens"], 1)
        self.assertIn("The gates open.", "\n".join(m["content"] for m in llm.stream_calls[-1]))


class OwnModelsTests(unittest.TestCase):
    def test_lmstudio_games_move_to_the_builtin_engine_and_own_copies(self):
        import tempfile
        from pathlib import Path
        from app import modelhub, runtime
        from app.modelhub import use_own_models
        tmp = Path(tempfile.mkdtemp())
        old = runtime.DATA_DIR
        runtime.DATA_DIR = tmp
        try:
            lm = tmp / "lmstudio" / "a" / "Stheno-Q4_K_S.gguf"
            lm.parent.mkdir(parents=True)
            lm.write_bytes(b"x" * 100)
            mine = tmp / "models" / "a" / "Stheno-Q4_K_S.gguf"
            mine.parent.mkdir(parents=True)
            mine.write_bytes(b"x" * 100)
            s = make_services()
            s.settings.update({"ai_engine": "lmstudio", "engine_model_path": str(lm)})
            use_own_models(s.settings)
            self.assertEqual(s.settings.get("ai_engine"), "builtin")
            self.assertEqual(s.settings.get("engine_model_path"), str(mine))
            self.assertEqual(modelhub.own_copy(str(mine)), None)           # already Calíope's own
            s.settings.update({"ai_engine": "lmstudio", "llm_base_url": "https://openrouter.ai/api/v1"})
            use_own_models(s.settings)
            self.assertEqual(s.settings.get("ai_engine"), "lmstudio")      # an online service stays
        finally:
            runtime.DATA_DIR = old


class WindowStepTests(unittest.TestCase):
    def test_history_start_moves_in_steps(self):
        from app.config import DEFAULT_SETTINGS
        from app.prompts import WINDOW_STEP, PromptBuilder
        from app.state import new_state
        settings = dict(DEFAULT_SETTINGS, context_window=4096)
        sc = {"name": "X", "mode": "gm_world"}
        firsts = []
        for n in range(40, 52, 2):  # one round more each turn
            hist = [{"id": i + 1, "role": "user" if i % 2 == 0 else "assistant", "content": f"Line {i} " + "word " * 60, "meta": {}}
                    for i in range(n)]
            msgs, _ = PromptBuilder().build(scenario=sc, state=new_state(), npcs=[], summary="", memories=[], skills=[],
                                            history=hist, settings=settings)
            first = next(m["content"] for m in msgs[1:] if m["content"].startswith("Line"))
            firsts.append(first.split(" ")[1])
        starts = [int(x) for x in firsts]
        self.assertGreater(starts[-1], 0)                                   # the window did move
        self.assertTrue(all(s % WINDOW_STEP == 0 for s in starts))         # always on a step
        self.assertLess(len(set(starts)), len(starts))                      # the same start for several turns


class SheetButtonTests(unittest.IsolatedAsyncioTestCase):
    async def test_use_a_message_as_the_sheet(self):
        llm = FakeLLM()
        s = make_services(llm)
        sc = s.scenarios.create({"name": "Academy", "mode": "gm_world", "opening_message": "Tell me your sheet."})
        cid = s.conversations.create(s.scenarios.get(sc["id"]))["id"]
        llm.reply = "Welcome."
        await collect(s.engine.send(cid, "Hi."))
        mine = next(m for m in s.conversations.list_messages(cid) if m["role"] == "user")

        async def chat(messages, json_schema=None, **kw):
            return ('{"name": "Aster", "race": "Human", "class": "Mage", "background": "A branch noble.", "looks": "",'
                    ' "personality": "", "gold": -1, "attributes": [], "other": []}')
        llm.chat = chat
        r = await s.engine.sheet_from_message(cid, mine["id"])
        self.assertEqual(r["state"]["player"]["class"], "Mage")
        self.assertTrue(r["changes"][0].startswith("Your sheet:"))
        assistant = next(m for m in s.conversations.list_messages(cid) if m["role"] == "assistant")
        with self.assertRaises(ValueError):
            await s.engine.sheet_from_message(cid, assistant["id"])


class AdoptTests(unittest.TestCase):
    def test_model_from_another_folder_is_copied_in(self):
        import tempfile
        from pathlib import Path
        from app import modelhub
        tmp = Path(tempfile.mkdtemp())
        old = modelhub.download_root
        modelhub.download_root = lambda: tmp / "mine"
        try:
            src = tmp / "lmstudio" / "Lewdiculous" / "Stheno-GGUF" / "Stheno-Q4_K_S.gguf"
            src.parent.mkdir(parents=True)
            src.write_bytes(b"x" * 1000)
            s = make_services()
            s.settings.update({"engine_model_path": str(src)})
            modelhub.adopt_models(s.settings)
            new = Path(s.settings.get("engine_model_path"))
            self.assertEqual(new, tmp / "mine" / "Lewdiculous" / "Stheno-GGUF" / "Stheno-Q4_K_S.gguf")
            self.assertEqual(new.read_bytes(), src.read_bytes())
            self.assertTrue(src.exists())                                   # LM Studio's file is left alone
            self.assertIsNone(modelhub.adopt_model(str(new)))               # already Calíope's
        finally:
            modelhub.download_root = old


class CardFolderTests(unittest.TestCase):
    def test_import_a_pictures_folder_into_the_cards_own(self):
        import tempfile
        from pathlib import Path
        from app import cardpics
        from tests.test_cards2 import PNG
        tmp = Path(tempfile.mkdtemp())
        src = tmp / "Downloads" / "lumencia art"
        (src / "Lyra Moonwhisper").mkdir(parents=True)
        (src / "Lyra Moonwhisper" / "1.png").write_bytes(PNG)
        (src / "Lyra Moonwhisper" / "notes.txt").write_text("not a picture")
        (src / "Elara.png").write_bytes(PNG)
        home = cardpics.card_folder(tmp / "Pictures", 'Lumencia: "Academy"')
        self.assertEqual(home.name, "Lumencia Academy")
        self.assertEqual(cardpics.card_folder(tmp / "Pictures", "Renamed", home.name), home)   # renaming keeps it
        got = cardpics.import_folder(str(src), home)
        self.assertEqual(got, {"characters": 2, "pictures": 2})
        self.assertTrue((home / "Lyra Moonwhisper" / "1.png").is_file())
        self.assertFalse((home / "Lyra Moonwhisper" / "notes.txt").exists())
        found = cardpics.scan(str(home), ["Lyra Moonwhisper", "Elara"])
        self.assertEqual(sorted(c["character"] for c in found["characters"]), ["Elara", "Lyra Moonwhisper"])
        self.assertEqual(cardpics.import_folder(str(home), home), {"characters": 0, "pictures": 0})  # itself


class InvolvementTests(unittest.TestCase):
    def test_only_characters_in_the_exchange_with_a_reason(self):
        from app.engine import involved_changes
        ex = [("\"Thank you,\" I tell Mira. 'Maybe Doran can help me later.'", "Mira smiles. \"Of course.\" Somewhere, Seren is mentioned.")]
        got = involved_changes([
            {"npc": "Mira Valen", "delta": 5, "reason": "the player thanked her"},
            {"npc": "Doran Hale", "delta": 3, "reason": "the player thought of him"},   # only in a thought
            {"npc": "Kael", "delta": -5, "reason": "talked about"},                   # not in the exchange
            {"npc": "Mira", "delta": 2, "reason": ""},                                  # no reason
        ], ex)
        self.assertEqual([c["npc"] for c in got], ["Mira Valen"])


class GmPrefixTests(unittest.TestCase):
    def test_mestre_prefix_is_a_question_to_the_aedo(self):
        from app.writing import gm_question, is_gm_message
        self.assertTrue(is_gm_message("mestre, qual a árvore genealógica do capitão?"))
        self.assertTrue(is_gm_message("GM: who are these three?"))
        self.assertTrue(is_gm_message("/how much gold?"))
        self.assertFalse(is_gm_message("/roll 1d20"))
        self.assertFalse(is_gm_message('"Mestre Doran, bom dia," eu digo.'))   # speech to a character called master
        self.assertFalse(is_gm_message("O mestre da guilda chega."))
        self.assertEqual(gm_question("mestre, e sua família?"), "e sua família?")
        self.assertEqual(gm_question("/what time is it?"), "what time is it?")


class StoryFrameTests(unittest.IsolatedAsyncioTestCase):
    async def test_facts_secrets_wishes_and_the_end(self):
        from app.engine import story_ended
        llm = FakeLLM()
        s = make_services(llm)
        sc = s.scenarios.create({"name": "Mystery", "mode": "gm_world", "opening_message": "Begin.",
                                 "fixed_facts": "The king is alive.", "secrets": "The chancellor did it.",
                                 "known_at_start": "You were named investigator.", "length": "short",
                                 "ending": "the poisoner is accused with proof"})
        cid = s.conversations.create(s.scenarios.get(sc["id"]))["id"]
        st = s.conversations.get_state(cid)
        st["wishes"] = "Wren and I could become close friends."
        s.conversations.save_state(cid, st)
        llm.reply = "Wren looks up."
        await collect(s.engine.send(cid, "I look around."))
        system = llm.stream_calls[-1][0]["content"]
        for text in ("Fixed facts", "The king is alive.", "Secrets", "The chancellor did it.", "knows from the start",
                     "short story", "the poisoner is accused with proof", "THE END"):
            self.assertIn(text, system)
        last = llm.stream_calls[-1][-1]["content"]
        self.assertIn("Wren and I could become close friends.", last)
        self.assertIn("Never force them", last)
        self.assertIn("Never write", last)                                   # the closing rules

        llm.reply = "The court gasps as the chancellor is led away.\n\n**THE END**"
        events = await collect(s.engine.send(cid, "I accuse the chancellor."))
        msg = next(e["message"] for e in events if e["type"] == "assistant_message")
        self.assertTrue(msg["meta"]["finished"])
        self.assertTrue(s.conversations.get_state(cid)["finished"])
        self.assertTrue(story_ended("fim"))
        self.assertFalse(story_ended("The end of the road is near."))

        # the Aedo's answers outside the story never get the secrets
        await collect(s.engine.send(cid, "/who did it?"))
        self.assertNotIn("The chancellor did it.", llm.stream_calls[-1][0]["content"])
        self.assertIn("You were named investigator.", llm.stream_calls[-1][0]["content"])

    def test_bundled_card_upgrade_only_when_untouched(self):
        import json
        import tempfile
        from pathlib import Path
        s = make_services()
        seed = Path(tempfile.mkdtemp())
        (seed / "scenarios").mkdir()
        (seed / "scenarios" / "c.json").write_text(json.dumps({"name": "Crown", "mode": "gm_world", "opening_message": "New opening.",
                                                               "secrets": "S", "upgrade_from": ["Old opening."]}))
        a = s.scenarios.create({"name": "Crown", "mode": "gm_world", "opening_message": "Old opening."})
        self.assertEqual(s.scenarios.upgrade_bundled(seed), 1)
        self.assertEqual(s.scenarios.get(a["id"])["data"]["opening_message"], "New opening.")
        self.assertEqual(s.scenarios.get(a["id"])["data"]["secrets"], "S")
        s.scenarios.update(a["id"], {**s.scenarios.get(a["id"])["data"], "name": "Crown", "opening_message": "Mine."})
        self.assertEqual(s.scenarios.upgrade_bundled(seed), 0)                # edited by you: left alone
