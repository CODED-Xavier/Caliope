"""Regression tests for the problems found in the code review (Auditoria)."""
import json
import tempfile
import unittest
from pathlib import Path

from app.db import Database, unpack_snapshot
from app.images import ImageError, get_image
from app.prompts import CAL_TIME_RULE, TIME_RULE
from app.util import as_int
from tests.test_core import FakeLLM, collect, make_services, new_game

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 50


class SnapshotStorageTests(unittest.IsolatedAsyncioTestCase):
    def test_old_databases_are_migrated(self):
        path = Path(tempfile.mkdtemp()) / "old.db"
        db = Database(path)
        db.execute("INSERT INTO conversations(title, created_at, updated_at) VALUES('x', 0, 0)")
        db.execute("INSERT INTO messages(conversation_id, role, content, meta, created_at) VALUES(1, 'assistant', 'hi', ?, 0)",
                   (json.dumps({"timing": {"a": 1}, "snapshot": {"state": {"gold": 5}, "npcs": []}}),))
        db.close()
        db = Database(path)  # opening runs the migration
        row = db.query_one("SELECT meta, snapshot FROM messages WHERE id = 1")
        self.assertEqual(json.loads(row["meta"]), {"timing": {"a": 1}})
        self.assertEqual(unpack_snapshot(row["snapshot"])["state"]["gold"], 5)

    async def test_snapshots_live_outside_meta(self):
        s = make_services(FakeLLM())
        cid = new_game(s)
        await collect(s.engine.send(cid, "hello there"))
        raw = s.db.query_one("SELECT meta, snapshot FROM messages WHERE conversation_id = ? AND role = 'assistant' ORDER BY id DESC", (cid,))
        self.assertNotIn("snapshot", json.loads(raw["meta"]))
        self.assertIsNotNone(raw["snapshot"])
        self.assertNotIn("snapshot", s.conversations.list_messages(cid)[-1])
        self.assertIn("snapshot", s.conversations.list_messages(cid, with_snapshot=True)[-1])

    async def test_fork_before_a_fight_action_does_not_include_it(self):
        s = make_services(FakeLLM())
        cid = new_game(s)
        await collect(s.engine.send(cid, "I look around."))
        point = s.conversations.list_messages(cid)[-1]["id"]
        gold_before = s.conversations.get_state(cid)["gold"]

        def prepare(st):
            st["gold"] = gold_before + 100
            return st, "⚔️ the app changed the state"

        await collect(s.engine.send(cid, "", prepare=prepare))
        fork = s.conversations.fork(cid, point)
        self.assertEqual(s.conversations.get_state(fork)["gold"], gold_before)


class SmallFixTests(unittest.IsolatedAsyncioTestCase):
    def test_as_int_never_crashes(self):
        self.assertEqual(as_int(float("inf")), 0)
        self.assertEqual(as_int("1e999", 3), 3)

    def test_find_npc_whole_words(self):
        s = make_services(FakeLLM())
        cid = new_game(s)
        s.conversations.add_npc(cid, "Albert")
        s.conversations.add_npc(cid, "Captain Varro")
        self.assertIsNone(s.conversations.find_npc(cid, "Al"))
        self.assertEqual(s.conversations.find_npc(cid, "Varro")["name"], "Captain Varro")
        self.assertEqual(s.conversations.find_npc(cid, "captain varro the bold")["name"], "Captain Varro")

    async def test_examples_dropped_and_calendar_rule(self):
        llm = FakeLLM()
        s = make_services(llm)
        cid = new_game(s, information={"example_messages": "<START>{{char}}: Example line."},
                       calendar={"enabled": True, "preset": "fantasy"})
        await collect(s.engine.send(cid, "hi"))
        system = llm.stream_calls[-1][0]["content"]
        self.assertIn("Example of the writing style", system)
        self.assertIn(CAL_TIME_RULE, system)
        self.assertNotIn(TIME_RULE, system)
        for i in range(6):
            await collect(s.engine.send(cid, f"turn {i}"))
        self.assertNotIn("Example of the writing style", llm.stream_calls[-1][0]["content"])

    async def test_images_trust_bytes_not_labels(self):
        d = Path(tempfile.mkdtemp())

        async def html(url):
            return b"<html>not an image</html>", "image/png"

        async def png_as_octet(url):
            return PNG, "application/octet-stream"

        with self.assertRaises(ImageError):
            await get_image("https://x.test/a.png", d, fetch=html, check=lambda u: u)
        path = await get_image("https://x.test/b", d, fetch=png_as_octet, check=lambda u: u)
        self.assertEqual(path.suffix, ".png")


class RulebookStartupTests(unittest.IsolatedAsyncioTestCase):
    async def test_interrupted_import_and_late_embeddings(self):
        llm = FakeLLM()
        s = make_services(llm)
        stuck = s.rulebooks.create("Stuck", "dnd5e", "a.pdf")
        s.db.execute("UPDATE rulebooks SET status = 'processing' WHERE id = ?", (stuck["id"],))
        book = s.rulebooks.create("Rules", "dnd5e", "r.md")
        s.rulebooks.import_bytes(book["id"], b"# Grappling\nA creature can grapple another creature.\n", "r.md")
        from app.rulebooks import RulebookRepository
        RulebookRepository(s.db, llm, s.settings.all)  # the app starting again
        self.assertEqual(s.rulebooks.get(stuck["id"])["status"], "error")
        self.assertEqual(await s.rulebooks.embed_missing(), 0)  # no embedding model: nothing to do
        llm.embeddings = True
        s.settings.update({"embedding_model": "nomic"})
        self.assertGreater(await s.rulebooks.embed_missing(), 0)
        found = await s.rulebooks.search_semantic([book["id"]], "grapple a creature")
        self.assertTrue(found and found[0]["heading"])


if __name__ == "__main__":
    unittest.main()
