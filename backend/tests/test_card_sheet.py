"""The card's own sheet filled on the start screen (Lumencia: Tier, Attributes, Stats with EXP), and EXP that raises grades."""
import unittest

from app import statusbook as sb
from tests.test_core import FakeLLM, collect, make_services, new_game
from tests.test_statusbook import TEMPLATE

LUMENCIA = """INFO
Location: [Location] | Time: [Time - Day X]
Tier: [Tier] | Affiliation: [Dept/House/Club] | Rank: [Year/Title]
Attributes (1-10): Magic [1-10] | Martial [1-10] | Soul [1-10] | Knowledge [1-10]
Stats (D- to SSS+ | 100 EXP/Sub-Grade):
- Body: [Grade] [[X]/100]
- Mana: [Grade] [[X]/100]
Combat Log: Battles Today: [N] ([Mult]) | Total: [Total] | Breakthrough: [Req]
Skills: [Skills/spells] | Condition: [State]
Inventory: [Items] | [X] Crowns / [Y] Merits
Relationships: [NPC (Affinity [Score] - context)]"""

OPENING = """"State your name."

Character Creation:
* Department: Knight, Magic or Theology

INFO
Location: Hall | Time: Morning (Day 1)
Tier: Unregistered | Affiliation: Unaffiliated | Rank: 1st-Year
Attributes (1-10): Magic - | Martial - | Soul - | Knowledge -
Stats (D- to SSS+ | 100 EXP/Sub-Grade):
- Body: - [0/100]
- Mana: - [0/100]
Combat Log: Battles Today: 0 (1.0x) | Total: 0 | Breakthrough: Entrance Registration
Skills: - | Condition: Stable
Inventory: Uniform | 0 Crowns / 100 Merits
Relationships: Prof. Artemis (Neutral [0])"""


class FormTests(unittest.TestCase):
    def test_groups_hints_and_progress(self):
        form = sb.sheet_form(LUMENCIA, sb.read_block(LUMENCIA, OPENING))
        titles = [g["title"] for g in form]
        self.assertEqual(titles[:3], ["", "Attributes (1-10)", "Stats (D- to SSS+ | 100 EXP/Sub-Grade)"])
        first = {f["key"]: f for f in form[0]["fields"]}
        self.assertEqual(first["Tier"]["value"], "Unregistered")
        attrs = {f["key"]: f for f in form[1]["fields"]}
        self.assertEqual(attrs["Magic"]["hint"], "1-10")
        body = form[2]["fields"][0]
        self.assertEqual((body["key"], body["progress"], body["grade"], body["exp"], body["max"]), ("Body", True, "-", 0, 100))

    def test_bump_grades(self):
        self.assertEqual(sb.bump_progress("C- [115/100]"), "C [15/100]")
        self.assertEqual(sb.bump_progress("C+ [250/100]"), "B [50/100]")
        self.assertEqual(sb.bump_progress("D [40/100]"), "D [40/100]")
        self.assertEqual(sb.bump_progress("Stable"), "Stable")
        self.assertEqual(sb.bump_progress("SSS+ [120/100]"), "SSS+ [100/100]")


class ChangeTests(unittest.TestCase):
    def test_rule_text_is_not_a_value_and_exp_rolls_over(self):
        st = {"card_status": {"Magic": "8", "Body": "C- [90/100]"}}
        out = sb.apply_changes(st, LUMENCIA, [{"field": "Magic", "value": ">=8"}, {"field": "Body", "value": "C- [120/100]"}])
        self.assertEqual(st["card_status"]["Magic"], "8")
        self.assertEqual(st["card_status"]["Body"], "C [20/100]")
        self.assertEqual(out, ["Body: C [20/100] (grade up: C- → C)"])

    def test_tracker_explains_exp(self):
        line = sb.tracker_lines({"card_status": {"Body": "C [0/100]"}}, LUMENCIA)
        self.assertIn("Body", line)
        self.assertIn("/100", line)


class StartTests(unittest.IsolatedAsyncioTestCase):
    async def test_sheet_from_the_start_screen(self):
        llm = FakeLLM()
        s = make_services(llm)
        base = s.conversations.get(new_game(s, information={"post_history": "Rules.\n\n" + LUMENCIA}, opening_message=OPENING))
        card = s.scenarios.get(base["scenario_id"])
        cid = s.conversations.create(card, setup="app", card_status={
            "Tier": "3-Circle", "Affiliation": "Magic Department", "Magic": "8", "Body": "C- [0/100]", "Location": "nope", "Unknown": "x"})["id"]
        st = s.conversations.get_state(cid)
        self.assertEqual(st["card_status"]["Tier"], "3-Circle")
        self.assertEqual(st["card_status"]["Body"], "C- [0/100]")
        self.assertEqual(st["card_status"]["Rank"], "1st-Year")  # the opening's value stays where the form left it
        self.assertNotIn("Unknown", st["card_status"])
        self.assertTrue(st["sheet_from_chat"])
        opening = s.conversations.list_messages(cid)[0]
        self.assertIn("Tier: 3-Circle", opening["meta"]["status"])
        await collect(s.engine.send(cid, "Name: Aster\nDepartment: Magic\nTier: 1-Circle\nBackground: none"))
        self.assertEqual(s.conversations.get_state(cid)["card_status"]["Tier"], "3-Circle")  # no second reading


if __name__ == "__main__":
    unittest.main()

_ = TEMPLATE


class StartSheetTests(unittest.TestCase):
    def test_start_sheet_from_the_card(self):
        out = sb.start_sheet({"information": {"post_history": "Rules.\n\n" + LUMENCIA}, "opening_message": OPENING})
        self.assertTrue(out["rules"].startswith("Character Creation:"))
        self.assertIn("Department: Knight", out["rules"])
        self.assertNotIn("INFO", out["rules"])
        self.assertEqual(out["groups"][0]["fields"][0]["value"], "Unregistered")
        self.assertEqual(sb.start_sheet({"opening_message": "Hi"}), {"groups": [], "rules": ""})
