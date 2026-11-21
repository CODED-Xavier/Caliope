"""Tests for v0.6.0: card import/export, lorebook, status block, portraits."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from app.cardio import CardError, export_card, parse_card, parse_characters
from app.images import ImageError, get_image
from app.lorebook import select_entries
from app.portraits import process_reply, resolve_portraits
from app.status import split_status
from tests.test_core import FakeLLM, collect, make_services

BASE = "https://example.com/portraits/main"
LORE_CAST = (
    "Students:\n"
    f"- Lilia Valenheart (Female, 1st-Year): Gold eyes, red hair. Cheerful. Base URL: {BASE}/Lilia.png "
    "(1=Standard, 2=Happy, 3=Sad, 4=Angry, 5=Disgusted/Very Angry, 6=Blushing)\n"
    f"- Professor Artemis (Female, Teacher): Grey eyes, silver hair. Strict. Base URL: {BASE}/Artemis.png "
    "(1=Standard, 2=Happy, 3=Sad, 4=Angry, 5=Disgusted/Very Angry, 6=Blushing)\n"
    f"- Asmo (Female, 2nd-Year): Pink eyes, black hair. Base URL: {BASE}/Asmo.png (1=Standard, 2=Happy)\n"
)
CARD = {
    "spec": "chara_card_v2",
    "spec_version": "2.0",
    "data": {
        "name": "Test Academy",
        "description": "You are the Game Master of a text RPG at an academy. {{user}} is a new student.",
        "personality": "",
        "scenario": "First day at the academy.",
        "first_mes": f"![Artemis - Standard]({BASE}/Artemis/1.png)\nProfessor Artemis looks at {{{{user}}}}.\n\nINFO\nName: ?\n<END>",
        "mes_example": "<START>\n{{user}}: Hi\n{{char}}: Hello.",
        "post_history_instructions": "Use affinity from -3 to +3.\n\nINFO\nName: [Name]\nRelationships: [NPC (Affinity)]",
        "character_book": {
            "scan_depth": 3,
            "token_budget": 900,
            "entries": [
                {"keys": ["academy"], "content": "The academy floats above the sea.", "constant": True, "enabled": True},
                {"keys": ["Lilia", "Artemis", "Asmo"], "content": LORE_CAST, "enabled": True, "priority": 5},
                {"keys": ["dragon"], "content": "Dragons sleep under the mountain.", "enabled": True},
            ],
        },
    },
}


class ImportTests(unittest.TestCase):
    def test_parse_card_finds_everything(self):
        r = parse_card(json.loads(json.dumps(CARD)))
        sc = r["scenario"]
        self.assertEqual(sc["mode"], "gm_cast")
        self.assertEqual(len(sc["lorebook"]["entries"]), 3)
        self.assertEqual([n["name"] for n in sc["npcs"]], ["Lilia Valenheart", "Professor Artemis", "Asmo"])
        lilia = sc["npcs"][0]
        self.assertFalse(lilia["in_prompt"])
        self.assertFalse(lilia["met"])
        self.assertEqual(lilia["appearance"].get("hair"), "red")
        self.assertEqual(lilia["portraits"]["moods"][1]["url"], f"{BASE}/Lilia/2.png")
        self.assertEqual(sc["information"]["status_every"], 3)
        self.assertIn("status", sc["features"]["panels"])
        self.assertTrue(any("-100 to +100" in w for w in r["warnings"]))

    def test_round_trip_is_exact(self):
        first = parse_card(json.loads(json.dumps(CARD)))["scenario"]
        again = parse_card(json.loads(json.dumps(export_card(first))))
        self.assertEqual(again["format"], "rpg_app")
        self.assertEqual(again["scenario"], first)

    def test_plain_character_card(self):
        r = parse_card({"name": "Mira", "description": "A shy librarian.", "first_mes": "Hello."})
        self.assertEqual(r["scenario"]["mode"], "character")
        self.assertEqual(r["scenario"]["npcs"][0]["name"], "Mira")

    def test_rejects_non_cards(self):
        with self.assertRaises(CardError):
            parse_card([1, 2])
        with self.assertRaises(CardError):
            parse_card({"foo": "bar"})

    def test_parse_characters_without_urls(self):
        chars = parse_characters([{"content": "- Bob (Male): Blue eyes.\n- Ann (Female): Short."}])
        self.assertEqual([c["name"] for c in chars], ["Bob", "Ann"])
        self.assertEqual(chars[0]["portraits"]["default"], "")


class LoreAndStatusTests(unittest.TestCase):
    def test_lorebook_selection(self):
        book = parse_card(json.loads(json.dumps(CARD)))["scenario"]["lorebook"]
        always, hit = select_entries(book, ["I wave at Lilia", "old dragon talk", "x", "y", "z"], 800)
        self.assertEqual(len(always), 1)
        self.assertEqual(len(hit), 2)
        self.assertIn("Lilia", hit[0]["content"])  # higher priority first
        _, old = select_entries(book, ["a", "b", "c", "d", "the dragon"], 800)
        self.assertEqual(old, [])  # beyond the scan depth
        _, none = select_entries(book, ["nothing here"], 800)
        self.assertEqual(none, [])
        _, tiny = select_entries(book, ["Lilia and the dragon"], 20)
        self.assertEqual([e["content"] for e in tiny], ["Dragons sleep under the mountain."])

    def test_split_status(self):
        text, block = split_status("Story here.\n\n**INFO**\nName: Dan\nHP: 3\n<END>")
        self.assertEqual(text, "Story here.")
        self.assertTrue(block.startswith("**INFO**"))
        self.assertNotIn("<END>", block)
        self.assertEqual(split_status("No block")[1], None)


class PortraitTests(unittest.TestCase):
    def setUp(self):
        self.npcs = parse_card(json.loads(json.dumps(CARD)))["scenario"]["npcs"]
        for i, n in enumerate(self.npcs):
            n["id"] = i + 1

    def test_garbled_links_are_fixed_and_limited(self):
        text = (f"![Lilia – happy](https://bad.link/x.png)\n\"Hi!\"\n\n[[show: Artemis | furious]]\nShe glares.\n\n"
                f"![Asmo - Happy]({BASE}/Asmo/2.png)\nAsmo grins.")
        out, shown = resolve_portraits(text, self.npcs)
        self.assertIn("[[show: Lilia Valenheart | Happy]]", out)
        self.assertIn("[[show: Professor Artemis | Disgusted/Very Angry]]", out)
        self.assertNotIn("Asmo |", out)  # third character: no picture
        self.assertNotIn("http", out)
        self.assertEqual(shown["Lilia Valenheart|Happy"], f"{BASE}/Lilia/2.png")

    def test_guess_from_url(self):
        out, shown = resolve_portraits(f"![]({BASE}/Asmo/2.png)\nAsmo waves.", self.npcs)
        self.assertEqual(list(shown), ["Asmo|Happy"])

    def test_process_reply_marks_met(self):
        story, meta, met = process_reply("Lilia waves at you.\n\nINFO\nName: Dan", self.npcs)
        self.assertEqual(story, "Lilia waves at you.")
        self.assertEqual(meta["status"], "INFO\nName: Dan")
        self.assertEqual(met, [1])


class ImageCacheTests(unittest.TestCase):
    def test_download_once_and_type_check(self):
        calls = []

        async def fetch(url):
            calls.append(url)
            return b"\x89PNG....", "image/png"

        tmp = Path(tempfile.mkdtemp())
        p1 = asyncio.run(get_image("https://x.org/a.png", tmp, fetch, check=lambda u: u))
        p2 = asyncio.run(get_image("https://x.org/a.png", tmp, fetch, check=lambda u: u))
        self.assertEqual(p1, p2)
        self.assertEqual(len(calls), 1)

        async def html(url):
            return b"<html>", "text/html"

        with self.assertRaises(ImageError):
            asyncio.run(get_image("https://x.org/b.png", tmp, html, check=lambda u: u))


class CardGameTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.llm = FakeLLM()
        self.s = make_services(self.llm)
        data = parse_card(json.loads(json.dumps(CARD)))["scenario"]
        data["features"] = {**data["features"], "tracker": "off"}
        sc = self.s.scenarios.create(data)
        self.cid = self.s.conversations.create(sc, player_name="Dan")["id"]

    async def test_opening_is_cleaned(self):
        msgs = self.s.conversations.list_messages(self.cid)
        self.assertNotIn("INFO", msgs[0]["content"])
        self.assertIn("[[show: Professor Artemis | Standard]]", msgs[0]["content"])
        self.assertIn("Dan", msgs[0]["content"])
        npcs = {n["name"]: n for n in self.s.conversations.list_npcs(self.cid)}
        self.assertTrue(npcs["Professor Artemis"]["met"])
        self.assertFalse(npcs["Lilia Valenheart"]["met"])

    async def test_prompt_uses_card_lore_and_status(self):
        self.llm.reply = "Lilia runs up to you. INFO is not here."
        await collect(self.s.engine.send(self.cid, "Who is Lilia?"))
        prompt = self.llm.stream_calls[-1]
        system, last = prompt[0]["content"], prompt[-1]["content"]
        self.assertIn("floats above the sea", system)          # always-on lore, stable part
        self.assertIn("Gold eyes, red hair", last)              # triggered lore, per-turn notes
        self.assertNotIn("Gold eyes", system)                   # lorebook-only characters stay out of the fixed part
        self.assertIn("-100 to +100", system)
        self.assertIn("[[show: Name | Mood]]", system)
        self.assertIn("Status (kept by the app; do not write it)", last)
        self.assertIn("Never write the INFO status block", system)
        self.assertIn("Dan is a new student", system)           # {{user}} replaced
        npcs = {n["name"]: n for n in self.s.conversations.list_npcs(self.cid)}
        self.assertTrue(npcs["Lilia Valenheart"]["met"])

    async def test_status_by_app(self):
        self.llm.reply = "Story.\n\nINFO\nName: Dan the Bold\nRelationships: Artemis (+5)"
        await collect(self.s.engine.send(self.cid, "turn 1"))
        msgs = self.s.conversations.list_messages(self.cid)
        self.assertEqual(msgs[-1]["content"], "Story.")
        block = msgs[-1]["meta"]["status"]
        self.assertTrue(block.startswith("INFO"))
        self.assertIn("Relationships: Professor Artemis (+0 neutral)", block)  # from the app, not the model's "+5"
        await collect(self.s.engine.send(self.cid, "turn 2"))
        history = "\n".join(m["content"] for m in self.llm.stream_calls[-1][1:-1])
        self.assertNotIn("INFO", history)  # no old blocks in the history: the model is not taught to write them

    async def test_status_every_third_reply(self):
        data = self.s.conversations.get(self.cid)["scenario"]
        data["features"] = {**data["features"], "status_by": "ai"}
        sc = self.s.scenarios.create({**data, "name": "AI status"})
        self.cid = self.s.conversations.create(sc, player_name="Dan")["id"]
        self.llm.reply = "Story.\n\nINFO\nName: Dan\nRelationships: Artemis (+5)"
        for i in range(3):
            await collect(self.s.engine.send(self.cid, f"turn {i}"))
        third = self.llm.stream_calls[-1][-1]["content"]
        self.assertIn("End THIS reply with the status block", third)
        msgs = self.s.conversations.list_messages(self.cid)
        self.assertEqual(msgs[-1]["content"], "Story.")
        self.assertIn("Relationships", msgs[-1]["meta"]["status"])
        # The model sees only the newest status block in the history.
        await collect(self.s.engine.send(self.cid, "turn 4"))
        history = "\n".join(m["content"] for m in self.llm.stream_calls[-1][1:-1])
        self.assertEqual(history.count("Relationships: Artemis"), 1)


if __name__ == "__main__":
    unittest.main()


class ContinueTests(unittest.IsolatedAsyncioTestCase):
    async def test_continue_appends_to_last_reply(self):
        llm = FakeLLM()
        s = make_services(llm)
        sc = s.scenarios.get(next(x["id"] for x in s.scenarios.list() if x["mode"] == "gm_world"))
        cid = s.conversations.create(sc)["id"]
        events = await collect(s.engine.continue_reply(cid))
        self.assertEqual(events[0]["type"], "error")  # the opening scene cannot be continued
        llm.reply = "The door creaks open."
        await collect(s.engine.send(cid, "I knock."))
        llm.reply = "A cold wind follows the stranger inside."
        events = await collect(s.engine.continue_reply(cid))
        self.assertEqual(events[-1]["type"], "done")
        last = s.conversations.list_messages(cid)[-1]
        self.assertEqual(last["content"], "The door creaks open.\n\nA cold wind follows the stranger inside.")
        self.assertTrue(last["meta"]["continued"])
        self.assertIn("Continue your last reply", llm.stream_calls[-1][-1]["content"])
        self.assertEqual(len(s.conversations.list_messages(cid)), 3)


class UploadTests(unittest.TestCase):
    def test_save_upload_checks_real_type(self):
        from app.images import save_upload
        tmp = Path(tempfile.mkdtemp())
        png = b"\x89PNG\r\n\x1a\n" + b"x" * 20
        name = save_upload(png, tmp)
        self.assertTrue(name.endswith(".png"))
        self.assertEqual(save_upload(png, tmp), name)  # same picture, same file
        with self.assertRaises(ImageError):
            save_upload(b"<script>alert(1)</script>", tmp)
        with self.assertRaises(ImageError):
            save_upload(b"", tmp)

    def test_player_portraits_and_local_links(self):
        from app.state import new_state
        st = new_state({"portraits": {"default": "/api/uploads/abc.png", "moods": [{"n": 2, "label": "Happy", "url": "javascript:x"}]}})
        self.assertEqual(st["player"]["portraits"], {"default": "/api/uploads/abc.png", "moods": []})

    def test_character_mode_emotion_rule(self):
        from app.portraits import portrait_instructions
        npcs = [{"name": "Mira", "is_main": True, "active": True, "portraits": {"default": "https://x/m.png", "moods": []}}]
        self.assertIn("Start EVERY reply with a line  [[show: Mira | Mood]]", portrait_instructions(npcs, "character"))
        self.assertIn("At most 2 characters with portraits", portrait_instructions(npcs, "gm_cast"))


class CoverTests(unittest.TestCase):
    def test_card_list_has_covers(self):
        s = make_services(FakeLLM())
        data = parse_card(json.loads(json.dumps(CARD)))["scenario"]
        sc = s.scenarios.create(data)
        item = next(x for x in s.scenarios.list() if x["id"] == sc["id"])
        self.assertEqual(item["covers"][0], f"{BASE}/Lilia/1.png")
        self.assertLessEqual(len(item["covers"]), 3)
