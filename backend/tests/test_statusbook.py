"""Tests for the INFO block written by the app."""
import unittest

from app import statusbook as sb
from tests.test_core import FakeLLM, collect, make_services, new_game

TEMPLATE = """INFO
Location: [Location] | Time: [Time - Day X]
Tier: [Tier] | Rank: [Year/Title]
Attributes (1-10): Magic [1-10] | Martial [1-10]
- Body: [Grade] [[X]/100]
Combat Log: Battles Today: [N] ([Mult]) | Total: [Total]
Inventory: [Items] | [X] Crowns / [Y] Merits
Relationships: [NPC (Affinity [Score] - context)]"""

WRITTEN = """INFO
Location: Hall | Time: Morning (Day 1)
Tier: Bronze | Rank: 1st-Year
Attributes (1-10): Magic 3 | Martial -
- Body: C [40/100]
Combat Log: Battles Today: 1 (1.0x) | Total: 4
Inventory: Wand | 10 Crowns / 100 Merits
Relationships: Lilia (Friendly [+1])"""


class ParseTests(unittest.TestCase):
    def test_fields_and_round_trip(self):
        self.assertEqual(sb.custom_fields(TEMPLATE),
                         ["Tier", "Rank", "Magic", "Martial", "Body", "Battles Today", "Total", "Crowns / Merits"])
        values = sb.read_block(TEMPLATE, WRITTEN)
        self.assertEqual(values["Body"], "C [40/100]")
        self.assertEqual(values["Battles Today"], "1 (1.0x)")
        self.assertEqual(values["Crowns / Merits"], "10 Crowns / 100")
        state = {"location": "Courtyard", "date_label": "Monday, 2 Frostmoon", "inventory": [{"name": "Wand", "qty": 1}],
                 "player": {"name": "Dan", "hp": {"current": 5, "max": 9}}, "quests": [], "card_status": values}
        out = sb.render(TEMPLATE, state, [{"name": "Lilia", "relationship": 35, "met": True, "active": True}])
        self.assertIn("Location: Courtyard | Time: Monday, 2 Frostmoon", out)
        self.assertIn("Attributes (1-10): Magic 3 | Martial -", out)
        self.assertIn("- Body: C [40/100]", out)
        self.assertIn("Inventory: Wand | 10 Crowns / 100 Merits", out)
        self.assertIn("Relationships: Lilia (+35 friendly)", out)

    def test_changes_only_for_card_fields(self):
        st = {"card_status": {"Tier": "Bronze"}}
        changed = sb.apply_changes(st, TEMPLATE, [{"field": "Tier", "value": "Silver"}, {"field": "Location", "value": "x"},
                                                  {"field": "Tier", "value": "Silver"}])
        self.assertEqual(changed, ["Tier: Silver"])
        self.assertEqual(st["card_status"], {"Tier": "Silver"})
        self.assertIn("Tier = Silver", sb.tracker_lines(st, TEMPLATE))


class TrackerTests(unittest.IsolatedAsyncioTestCase):
    async def test_tracker_updates_card_fields(self):
        llm = FakeLLM()
        s = make_services(llm)
        cid = new_game(s, information={"post_history": "Rules.\n\n" + TEMPLATE, "status_every": 3})
        llm.analysis = {"status_changes": [{"field": "Battles Today", "value": "1 (1.0x)"}]}
        await collect(s.engine.send(cid, "I spar with Lilia."))
        self.assertEqual(s.conversations.get_state(cid)["card_status"]["Battles Today"], "1 (1.0x)")
        self.assertIn("status_changes", llm.chat_calls[-1][1]["required"])
        last = s.conversations.list_messages(cid)[-1]
        self.assertIn("Combat Log: Battles Today: 1 (1.0x)", last["meta"]["status"])
        self.assertIn("Battles Today: 1 (1.0x)", last["meta"]["changes"])


if __name__ == "__main__":
    unittest.main()
