"""Part 2: character boxes filled from the card, the sheet from the first answer, pictures before speech, places."""
import json
import unittest

from app import npcfill, sheetchat
from app.places import find_place, normalize_places, places_section
from app.portraits import place_before_speech
from tests.test_core import FakeLLM, collect, make_services


class FillLLM(FakeLLM):
    async def chat(self, messages, json_schema=None, **kw):
        self.chat_calls.append((messages, json_schema))
        q = messages[-1]["content"]
        if json_schema:
            return json.dumps(self.analysis)
        if "character sheet of" in q:
            return "Race: Human\nHair: silver, braided\nEyes: grey\nBuild: tall\nSkin: pale\nOutfit: black robes\nPersonality: Patient, cold.\nSpeech: Soft and formal."
        return "ok"


def lumencia(s):
    return s.scenarios.create({
        "name": "Lumencia", "mode": "gm_cast",
        "lorebook": {"entries": [{"name": "Cast", "keys": ["professor"], "content":
                                  "- Artemis (Professor): Strict knight instructor with red hair.\n- Lilia (Student): cheerful."}]},
        "npcs": [{"name": "Artemis", "in_prompt": False, "met": False, "appearance": {"hair": "red"}},
                 {"name": "Lilia", "personality": "Cheerful", "speech_style": "Bubbly",
                  "appearance": {"race": "Elf", "hair": "gold", "eyes": "green", "build": "small", "skin": "fair", "outfit": "uniform"}}],
    })


class FillTests(unittest.IsolatedAsyncioTestCase):
    def test_source_and_missing(self):
        s = make_services()
        card = lumencia(s)["data"]
        art = card["npcs"][0]
        src = npcfill.source_text(card, art)
        self.assertIn("Strict knight instructor", src)
        self.assertNotIn("cheerful", src)
        self.assertEqual(npcfill.missing(art), ["race", "eyes", "build", "skin", "outfit", "personality", "speech_style"])
        self.assertEqual(npcfill.missing(card["npcs"][1]), [])

    async def test_fill_keeps_what_the_card_says(self):
        llm = FillLLM()
        s = make_services(llm)
        card = lumencia(s)["data"]
        values = await npcfill.fill_one(llm, card, card["npcs"][0])
        self.assertNotIn("hair", values)                          # the card already says red
        merged = npcfill.merge(card["npcs"][0], values)
        self.assertEqual(merged["appearance"]["hair"], "red")
        self.assertEqual(merged["appearance"]["eyes"], "grey")
        self.assertEqual(merged["speech_style"], "Soft and formal.")
        self.assertEqual(await npcfill.fill_one(llm, card, card["npcs"][1]), {})   # nothing missing: no call


class SheetTests(unittest.IsolatedAsyncioTestCase):
    def test_detect(self):
        self.assertTrue(sheetchat.looks_like_sheet("Name: Kael\nDepartment: Knight\nAttributes: Magic 6"))
        self.assertFalse(sheetchat.looks_like_sheet("I walk to the door."))
        self.assertFalse(sheetchat.wanted({"setup": "app"}, 2, "Name: Kael\nClass: Knight"))
        self.assertFalse(sheetchat.wanted({"setup": "card", "sheet_from_chat": True}, 2, "Name: Kael\nClass: Knight"))

    async def test_first_answer_fills_the_sheet(self):
        llm = FillLLM()
        s = make_services(llm)
        sc = s.scenarios.create({"name": "Academy", "mode": "gm_world", "opening_message": "State your name, department and attributes."})
        cid = s.conversations.create(s.scenarios.get(sc["id"]), setup="card")["id"]
        llm.analysis = {"name": "Kael Thorne", "race": "Human", "class": "Knight Department", "background": "A minor noble's son.",
                        "looks": "Tall, scarred", "personality": "Stubborn", "gold": 150,
                        "attributes": [{"name": "Magic", "value": 4}, {"name": "Martial", "value": 8}],
                        "other": [{"label": "Tier", "value": "Beginner"}]}
        events = await collect(s.engine.send(cid, "Name: Kael Thorne\nOrigin: Minor Noble\nDepartment: Knight\nAttributes: Magic 4, Martial 8"))
        st = s.conversations.get_state(cid)
        self.assertEqual(st["player"]["name"], "Kael Thorne")
        self.assertEqual(st["player"]["class"], "Knight Department")
        self.assertEqual(st["player"]["stats"], {"Magic": 4, "Martial": 8})
        self.assertEqual(st["gold"], 150)
        self.assertEqual(st["card_status"]["Tier"], "Beginner")
        self.assertTrue(any("Your sheet" in " ".join(e.get("changes", [])) for e in events if e["type"] == "state"))
        n = len(llm.chat_calls)
        await collect(s.engine.send(cid, "Name: Someone else\nClass: Mage"))          # only once
        self.assertEqual(s.conversations.get_state(cid)["player"]["name"], "Kael Thorne")
        self.assertFalse(any("copy their character sheet" in c[0][-1]["content"] for c in llm.chat_calls[n:]))


class PlacementTests(unittest.TestCase):
    def test_picture_moves_before_speech(self):
        t = "[[show: Lilia | Happy]]\n\nThe bell rings.\n\nShe smiles. \"Morning!\"\n\n[[show: Lilia | Angry]]\n\n\"You are late.\""
        self.assertEqual(place_before_speech(t),
                         "The bell rings.\n\nShe smiles.\n\n[[show: Lilia | Happy]]\n\n\"Morning!\"\n\n[[show: Lilia | Angry]]\n\n\"You are late.\"")

    def test_no_speech_keeps_place(self):
        t = "Rain.\n\n[[show: Kael | Standard]]\n\nKael draws his sword."
        self.assertEqual(place_before_speech(t), t)


class PlaceTests(unittest.IsolatedAsyncioTestCase):
    def test_find(self):
        places = normalize_places([{"name": "Grand Hall", "picture": "/api/uploads/hall.png"},
                                   {"name": "The Chapel", "aliases": ["Capela"], "picture": "https://x/c.png"}, {"name": ""}])
        self.assertEqual(len(places), 2)
        self.assertEqual(find_place(places, "the Grand Hall of Lumencia")["name"], "Grand Hall")
        self.assertEqual(find_place(places, "capela")["name"], "The Chapel")
        self.assertIsNone(find_place(places, "Forest"))
        self.assertIn("- Grand Hall", places_section(places))

    async def test_place_picture_shown_without_painting(self):
        llm = FakeLLM()
        s = make_services(llm)
        sc = s.scenarios.create({"name": "Academy", "mode": "gm_world", "opening_message": "Hi.",
                                 "places": [{"name": "Grand Hall", "picture": "/api/uploads/hall.png"}]})
        cid = s.conversations.create(s.scenarios.get(sc["id"]))["id"]
        llm.analysis = {"location": "Grand Hall"}
        events = await collect(s.engine.send(cid, "I enter the hall."))
        pic = next(e["picture"] for e in events if e["type"] == "scene_picture")
        self.assertEqual(pic["url"], "/api/uploads/hall.png")
        self.assertEqual(s.cantos.gallery(cid)[0]["url"], "/api/uploads/hall.png")   # in the map bag


if __name__ == "__main__":
    unittest.main()
