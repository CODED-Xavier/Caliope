"""Audit leftovers: cached memory vectors, re-sending app-result messages."""
import unittest

def _has(mod: str) -> bool:
    try:
        __import__(mod)
        return True
    except ImportError:
        return False


from app.engine import strip_app_line
from tests.test_core import FakeLLM, collect, make_services, new_game


@unittest.skipUnless(_has("numpy"), "the vector cache is only used with numpy")
class MemoryCacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_cache_follows_changes(self):
        llm = FakeLLM()
        llm.embeddings = True
        s = make_services(llm)
        s.settings.update({"embedding_model": "fake-embed"})
        cid = s.conversations.create(None)["id"]
        await s.memory.add(cid, "A red dragon sleeps beneath the northern mountain")
        hits = await s.memory.search_semantic(cid, "dragon northern mountain")
        self.assertIn("dragon", hits[0]["text"])
        self.assertNotIn("embedding", hits[0])
        self.assertEqual(len(s.memory._vec_cache), 1)

        calls = []
        real_query = s.memory.db.query
        s.memory.db.query = lambda sql, *a: (calls.append(sql), real_query(sql, *a))[1]
        await s.memory.search_semantic(cid, "dragon northern mountain")
        self.assertFalse(any("embedding FROM" in q for q in calls))  # vectors came from the cache
        s.memory.db.query = real_query

        mid = await s.memory.add(cid, "The silver key opens the northern mountain gate")
        hits = await s.memory.search_semantic(cid, "silver key gate")
        self.assertIn("silver key", hits[0]["text"])
        s.memory.delete(mid)
        hits = await s.memory.search_semantic(cid, "silver key gate")
        self.assertTrue(all("silver key" not in h["text"] for h in hits))

    async def test_change_made_elsewhere_is_noticed(self):
        llm = FakeLLM()
        llm.embeddings = True
        s = make_services(llm)
        s.settings.update({"embedding_model": "fake-embed"})
        cid = s.conversations.create(None)["id"]
        await s.memory.add(cid, "A red dragon sleeps beneath the northern mountain")
        await s.memory.search_semantic(cid, "dragon")
        s.memory.db.execute("DELETE FROM memories WHERE conversation_id = ?", (cid,))  # not through MemoryManager
        self.assertEqual(await s.memory.search_semantic(cid, "dragon northern mountain"), [])


class ResendAppResultTests(unittest.IsolatedAsyncioTestCase):
    def test_strip_app_line(self):
        self.assertEqual(strip_app_line("I swing at him\n\n⚔️ Hit! 8 damage.", {"app_line": "⚔️ Hit! 8 damage."}),
                         "I swing at him")
        self.assertEqual(strip_app_line("Buy it\n\n🛒 Bought a rope.", {}), "Buy it")
        self.assertEqual(strip_app_line("⏳ Time passes.", {}), "")

    async def test_resend_undoes_the_old_result(self):
        s = make_services(FakeLLM())
        cid = new_game(s, "gm_world")
        gold0 = s.conversations.get_state(cid)["gold"]

        def prepare(st):
            st["gold"] -= 7
            return st, "💰 Paid 7 gold."

        await collect(s.engine.send(cid, "I pay the guard", prepare=prepare, kind="trade"))
        self.assertEqual(s.conversations.get_state(cid)["gold"], gold0 - 7)
        user = [m for m in s.conversations.list_messages(cid) if m["role"] == "user"][-1]
        self.assertTrue(user["meta"]["trade"])

        events = await collect(s.engine.resend(cid, user["id"], user["content"].replace("guard", "guard politely")))
        types = [e["type"] for e in events]
        self.assertIn("user_updated", types)
        self.assertEqual(types[-1], "done")
        self.assertEqual(s.conversations.get_state(cid)["gold"], gold0)  # the payment was undone
        msg = s.conversations.get_message(user["id"], with_snapshot=True)
        self.assertEqual(msg["content"], "I pay the guard politely")
        self.assertNotIn("trade", msg["meta"])
        self.assertIsNone(msg["snapshot"])

    async def test_result_only_message_is_refused(self):
        s = make_services(FakeLLM())
        cid = new_game(s, "gm_world")
        await collect(s.engine.send(cid, "", prepare=lambda st: (st, "🛌 You rest."), kind="rest"))
        user = [m for m in s.conversations.list_messages(cid) if m["role"] == "user"][-1]
        n = len(s.conversations.list_messages(cid))
        events = await collect(s.engine.resend(cid, user["id"], user["content"]))
        self.assertEqual(events[0]["type"], "error")
        self.assertEqual(len(s.conversations.list_messages(cid)), n)  # nothing was removed


if __name__ == "__main__":
    unittest.main()
