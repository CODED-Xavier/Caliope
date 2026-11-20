"""Tests for buying, paying and quest confirmations done by the app."""
import unittest

from app.shop import buy, find_offers, is_trade, pay
from app.state import apply_state_updates, new_state, normalize_updates
from tests.test_core import FakeLLM, collect, make_services, new_game


class OfferTests(unittest.TestCase):
    def test_find_offers(self):
        got = find_offers("He shows his wares: a coil of rope (1 gold), a lantern (5 gp) and a healing potion for 50 gold.")
        self.assertEqual(got, [{"item": "coil of rope", "price": 1}, {"item": "lantern", "price": 5}, {"item": "healing potion", "price": 50}])
        self.assertEqual(find_offers("- Iron dagger: 8 crowns", "Crown"), [{"item": "Iron dagger", "price": 8}])
        self.assertEqual(find_offers("Ele oferece uma espada longa por 15 moedas de ouro."), [{"item": "espada longa", "price": 15}])
        self.assertEqual(find_offers("You pay him and leave. That costs you nothing."), [])

    def test_buy_and_pay(self):
        st = new_state({"gold": 20})
        st, line = buy(st, {"item": "Rope", "price": 3}, 2, "gold")
        self.assertEqual(st["gold"], 14)
        self.assertEqual(st["inventory"][0], {"name": "Rope", "qty": 2, "notes": ""})
        self.assertTrue(is_trade(line))
        st, _ = buy(st, {"item": "rope", "price": 1}, 1, "gold")
        self.assertEqual(st["inventory"][0]["qty"], 3)
        with self.assertRaises(ValueError):
            buy(st, {"item": "Horse", "price": 500}, 1, "gold")
        st, line = pay(st, 4, "the innkeeper", "a room", "gold")
        self.assertEqual(line, "\U0001F4B0 Paid 4 gold to the innkeeper for a room (gold left: 9).")
        with self.assertRaises(ValueError):
            pay(st, 100, "", "", "gold")

    def test_quest_end_is_a_suggestion(self):
        st = new_state()
        st, _ = apply_state_updates(st, normalize_updates({"quests": [{"title": "Find the ring", "status": "active", "notes": ""}]}))
        st, changes = apply_state_updates(st, normalize_updates({"quests": [{"title": "Find the ring", "status": "completed", "notes": ""}]}))
        q = st["quests"][0]
        self.assertEqual((q["status"], q["suggested"]), ("active", "completed"))
        self.assertIn("confirm", changes[0])


class GameTests(unittest.IsolatedAsyncioTestCase):
    async def test_offers_and_no_double_counting(self):
        llm = FakeLLM()
        s = make_services(llm)
        cid = new_game(s)
        st = s.conversations.get_state(cid)
        st["gold"] = 30
        s.conversations.save_state(cid, st)
        llm.reply = "The trader grins. A lantern (5 gold), or a sturdy rope for 2 gold?"
        await collect(s.engine.send(cid, "What do you sell?"))
        offers = s.conversations.list_messages(cid)[-1]["meta"]["offers"]
        self.assertEqual([o["item"] for o in offers], ["lantern", "sturdy rope"])
        llm.analysis = {"gold_change": -5, "inventory_add": [{"name": "Lantern", "qty": 1}]}  # the tracker would count it again
        from app import shop
        await collect(s.engine.send(cid, "", prepare=lambda st: shop.buy(st, offers[0], 1, "gold"), kind="trade"))
        st = s.conversations.get_state(cid)
        self.assertEqual(st["gold"], 25)
        self.assertEqual([i["name"] for i in st["inventory"]].count("lantern") + [i["name"] for i in st["inventory"]].count("Lantern"), 1)
        user = s.conversations.list_messages(cid)[-2]
        self.assertTrue(user["meta"]["trade"])


if __name__ == "__main__":
    unittest.main()
