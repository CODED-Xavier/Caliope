"""Part 1: character notes (the player's and the Aedo's), personas."""
import unittest

from app.engine import add_note
from app.prompts import AEDO_MARK, notes_section
from tests.test_core import FakeLLM, collect, make_services, new_game


class NotesTests(unittest.IsolatedAsyncioTestCase):
    async def test_aedo_adds_notes_once(self):
        llm = FakeLLM()
        s = make_services(llm)
        cid = new_game(s, "gm_world")
        s.conversations.add_npc(cid, "Kael", met=True)
        llm.analysis = {"character_notes": [{"npc": "Kael", "note": "Promised to meet the player at the chapel on Sunday."}]}
        await collect(s.engine.send(cid, "Kael, meet me Sunday?"))
        kael = s.conversations.find_npc(cid, "Kael")
        self.assertEqual(kael["notes"], AEDO_MARK + "Promised to meet the player at the chapel on Sunday.")
        await collect(s.engine.send(cid, "See you then."))                       # the same note is not added twice
        self.assertEqual(s.conversations.find_npc(cid, "Kael")["notes"].count("chapel"), 1)
        s.engine.undo(cid)
        s.engine.undo(cid)                                                         # undo takes the note back
        self.assertEqual(s.conversations.find_npc(cid, "Kael")["notes"], "")

    def test_player_notes_kept_when_long(self):
        s = make_services()
        cid = new_game(s, "gm_world")
        npc = s.conversations.add_npc(cid, "Lilia", notes="My own note: she lied about the key.")
        for i in range(40):
            npc = s.conversations.find_npc(cid, "Lilia")
            add_note(s.conversations, npc, f"Event number {i} that changed how she sees the player a lot")
        notes = s.conversations.find_npc(cid, "Lilia")["notes"]
        self.assertTrue(notes.startswith("My own note"))                          # the player's line is never dropped
        self.assertIn("Event number 39", notes)
        self.assertLessEqual(len(notes), 1500)

    def test_notes_section_for_lorebook_characters(self):
        npcs = [{"name": "Artemis Valen", "in_prompt": False, "notes": AEDO_MARK + "Owes the player a favour."},
                {"name": "Lilia", "in_prompt": False, "notes": "Hates bells."},
                {"name": "Kael", "in_prompt": True, "notes": "Already in the prompt."}]
        text = notes_section(npcs, ["Artemis walks in.", "Kael nods."])
        self.assertIn("Artemis Valen: Owes the player a favour.", text)
        self.assertNotIn("Lilia", text)
        self.assertNotIn("Kael", text)
        self.assertEqual(notes_section(npcs, ["Nobody here."]), "")


class PersonaTests(unittest.TestCase):
    def test_save_list_update_delete(self):
        s = make_services()
        p = s.personas.save({"player": {"name": "Seraphine", "background": "A disgraced knight."},
                             "lore": [{"name": "House Vael", "content": "A sixth great house."}]})
        self.assertEqual(p["name"], "Seraphine")
        self.assertEqual(s.personas.list()[0]["lore"][0]["name"], "House Vael")
        s.personas.save({"name": "Seraphine the Grey", "player": {"name": "Seraphine"}}, p["id"])
        self.assertEqual(s.personas.get(p["id"])["name"], "Seraphine the Grey")
        with self.assertRaises(ValueError):
            s.personas.save({"player": {}})
        s.personas.delete(p["id"])
        self.assertEqual(s.personas.list(), [])


if __name__ == "__main__":
    unittest.main()
