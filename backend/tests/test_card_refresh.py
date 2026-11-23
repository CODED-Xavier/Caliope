"""⟳ Update a running game from its card: new characters, lore and calendar arrive; the story's own changes stay."""
import unittest

from tests.test_core import make_services


def card(s, **extra):
    data = {"name": "Academy", "mode": "gm_cast",
            "npcs": [{"name": "Lilia", "description": "A knight.", "personality": "Blunt.", "appearance": {"hair": "red"}},
                     {"name": "Elara", "description": "Confident", "personality": "A dark knight.", "met": False},
                     {"name": "Aria", "description": "A saintess.", "personality": "Gentle."}],
            "lorebook": {"entries": [{"name": "Valenheart", "keys": ["Valenheart"], "content": "A duchy."}]}, **extra}
    return s.scenarios.create(data)


class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.s = make_services()
        self.sc = card(self.s)
        self.cid = self.s.conversations.create(self.sc)["id"]
        self.c = self.s.conversations

    def npc(self, name):
        return next((n for n in self.c.list_npcs(self.cid) if n["name"] == name), None)

    def update_card(self, change):
        data = dict(self.s.scenarios.get(self.sc["id"])["data"])
        change(data)
        self.s.scenarios.update(self.sc["id"], {**data, "name": "Academy"})
        return self.s.scenarios.get(self.sc["id"])

    def test_new_characters_lore_and_text_arrive(self):
        def change(d):
            d["npcs"] = [dict(n) for n in d["npcs"]]
            d["npcs"][0]["description"] = "A sword prodigy of House Valenheart."
            d["npcs"].append({"name": "Yanagi Tsushima", "description": "Head of Theology, from Koga.", "relationship": 5})
            d["lorebook"] = {"entries": d["lorebook"]["entries"] + [{"name": "Koga", "keys": ["Koga"], "content": "An island realm."}]}
        done = self.c.refresh_from_card(self.cid, self.update_card(change))
        self.assertEqual(done["added"], ["Yanagi Tsushima"])
        self.assertIn("Lilia", done["updated"])
        y = self.npc("Yanagi Tsushima")
        self.assertFalse(y["met"])
        self.assertEqual(y["relationship"], 5)
        self.assertEqual(self.npc("Lilia")["description"], "A sword prodigy of House Valenheart.")
        names = [e["name"] for e in self.c.get(self.cid)["scenario"]["lorebook"]["entries"]]
        self.assertIn("Koga", names)

    def test_the_story_keeps_its_own_changes(self):
        lilia = self.npc("Lilia")
        self.c.update_npc(lilia["id"], description="Lost her arm to the wyvern.", relationship=40, notes="owes the player")

        def change(d):
            d["npcs"] = [dict(n) for n in d["npcs"]]
            d["npcs"][0]["description"] = "A sword prodigy."
            d["npcs"][0]["personality"] = "Blunt and proud."
        done = self.c.refresh_from_card(self.cid, self.update_card(change))
        n = self.npc("Lilia")
        self.assertEqual(n["description"], "Lost her arm to the wyvern.")  # changed by the story: kept
        self.assertEqual(n["personality"], "Blunt and proud.")  # untouched by the story: the card's new text
        self.assertEqual((n["relationship"], n["notes"]), (40, "owes the player"))
        self.assertIn("Lilia", done["updated"])

    def test_a_character_moved_to_another_route(self):
        aria = self.npc("Aria")
        self.c.update_npc(aria["id"], met=True)

        def change(d):
            d["npcs"] = [{**n, "route": "dark"} if n["name"] in ("Elara", "Aria") else n for n in d["npcs"]]
            d["npcs"].append({"name": "Pria", "description": "Archbishop.", "route": "dark"})
        done = self.c.refresh_from_card(self.cid, self.update_card(change))
        self.assertEqual(done["aside"], ["Elara"])  # not met yet: put aside
        self.assertFalse(self.npc("Elara")["active"])
        self.assertTrue(self.npc("Aria")["active"])  # already in the story: stays
        self.assertIsNone(self.npc("Pria"))  # belongs to the other route

    def test_calendar_and_sheet_start_and_values_stay(self):
        systems = {"stats": [{"key": "Gold", "kind": "number", "min": 0, "start": 30}]}
        done = self.c.refresh_from_card(self.cid, self.update_card(lambda d: d.update(
            calendar={"enabled": True, "climate": "rainy"}, systems=systems)))
        st = self.c.get_state(self.cid)
        self.assertIn("clock", st)
        self.assertEqual(st["systems"]["values"]["Gold"], 30)
        st["systems"]["values"]["Gold"] = 95
        self.c.save_state(self.cid, st)
        systems2 = {"stats": systems["stats"] + [{"key": "Year", "kind": "number", "min": 1, "max": 3, "start": 1}]}
        self.c.refresh_from_card(self.cid, self.update_card(lambda d: d.update(systems=systems2)))
        st = self.c.get_state(self.cid)
        self.assertEqual(st["systems"]["values"], {"Gold": 95, "Year": 1})
        self.assertEqual(done["lore"], 1)

    def test_messages_and_route_stay(self):
        before = len(self.c.list_messages(self.cid))
        self.c.add_message(self.cid, "user", "Hello")
        self.c.refresh_from_card(self.cid, self.update_card(lambda d: d.update(name="Academy")))
        self.assertEqual(len(self.c.list_messages(self.cid)), before + 1)


if __name__ == "__main__":
    unittest.main()


class StartByChoiceTests(unittest.TestCase):
    SYS = {"stats": [{"key": "Origin", "kind": "choice", "options": ["Commoner", "Minor noble", "High noble", "Foreign scholarship"], "start": "Commoner"},
                     {"key": "Gold", "kind": "number", "min": 0, "start": 30,
                      "start_by": {"stat": "Origin", "values": {"Commoner": 30, "Minor noble": 150, "High noble": 500, "Foreign scholarship": 30}}}]}

    def test_the_origin_sets_the_starting_gold(self):
        from app.systems import merge_state, normalize as normalize_systems
        sys = normalize_systems(self.SYS)
        self.assertEqual(merge_state(sys, {"values": {"Origin": "High noble"}})["values"]["Gold"], 500)
        self.assertEqual(merge_state(sys, {"values": {"Origin": "Minor noble", "Gold": 30}})["values"]["Gold"], 150)
        self.assertEqual(merge_state(sys, {"values": {"Origin": "Foreign scholarship"}})["values"]["Gold"], 30)
        self.assertEqual(merge_state(sys, {"values": {"Origin": "High noble", "Gold": 77}})["values"]["Gold"], 77)  # typed by hand
        self.assertEqual(merge_state(sys, None)["values"]["Gold"], 30)
