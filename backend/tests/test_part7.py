import copy
import unittest

from app import sheets, statusbook
from app.cards import resolve_features
from app.state import DEFAULT_STATE
from tests.test_core import make_services


class SheetLibraryTests(unittest.TestCase):
    def test_every_template_parses_and_fills_known_fields_from_the_game(self):
        st = copy.deepcopy(DEFAULT_STATE)
        st["player"].update(level=4, ac=15, **{"class": "Rogue"})
        st["player"]["stats"]["DEX"] = 17
        for t in sheets.library():
            self.assertTrue(statusbook.PLACEHOLDER.search(t["text"]), t["id"])
            self.assertTrue(statusbook.render(t["text"], st, []).strip(), t["id"])
        dnd = statusbook.render(sheets.by_id("dnd5e")["text"], st, [])
        self.assertIn("Level: 4", dnd)
        self.assertIn("AC: 15", dnd)
        self.assertIn("Class: Rogue", dnd)
        self.assertIn("DEX: 17", dnd)
        t20 = statusbook.render(sheets.by_id("tormenta20")["text"], st, [])
        self.assertIn("DES: 17", t20)                                         # Tormenta20's Portuguese attributes
        self.assertIn("Nível: 4", t20)
        self.assertNotIn("STR", statusbook.custom_fields(sheets.by_id("dnd5e")["text"]))

    def test_a_lone_attribute_like_label_stays_the_cards_own_field(self):
        tpl = "INFO\n- Body: [Grade] [[X]/100]\n- INT: [Grade] [[X]/100]"
        self.assertEqual(statusbook.custom_fields(tpl), ["Body", "INT"])      # Lumencia's INT is a grade, not the stat

    def test_card_info_block_wins_over_a_picked_sheet(self):
        own = {"information": {"post_history": "Rules.\n\nINFO\nTier: [Tier]"}, "sheet_template": "HP: [HP]"}
        self.assertIn("Tier", statusbook.template_of(own))
        self.assertEqual(statusbook.template_of({"sheet_template": "Mood: [Mood]"}), "Mood: [Mood]")
        self.assertIsNone(statusbook.template_of({"sheet_template": "no placeholders"}))
        self.assertIn("status", resolve_features({"mode": "character", "sheet_template": "Mood: [Mood]"})["panels"])


class GameSheetTests(unittest.TestCase):
    def test_a_game_picks_its_sheet_without_changing_the_card(self):
        svc = make_services()
        sc = svc.scenarios.create({"name": "Plain", "mode": "gm_world", "opening_message": "Hello."})
        conv = svc.conversations.create(svc.scenarios.get(sc["id"]))
        svc.conversations.set_sheet_template(conv["id"], sheets.by_id("cthulhu7")["text"])
        snap = svc.conversations.get(conv["id"])["scenario"]
        self.assertIn("Sanity", statusbook.custom_fields(statusbook.template_of(snap)))
        self.assertFalse(svc.scenarios.get(sc["id"])["data"].get("sheet_template"))
        self.assertEqual(svc.scenarios.create({"name": "S", "sheet_template": "HP: [HP]"})["data"]["sheet_template"], "HP: [HP]")


if __name__ == "__main__":
    unittest.main()
