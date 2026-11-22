"""Character pictures: the face follows the text when the model gives no mood, and card pictures reach running games."""
import unittest

from app.portraits import face_from_text, resolve_portraits
from tests.test_core import make_services

PICS = {"default": "/d.png", "moods": [{"n": 1, "label": "Standard", "url": "/1.png"}, {"n": 2, "label": "Happy", "url": "/2.png"},
                                       {"n": 4, "label": "Angry", "url": "/4.png"}, {"n": 6, "label": "Blushing", "url": "/6.png"}]}


class FaceTests(unittest.TestCase):
    def test_face_from_text(self):
        self.assertEqual(face_from_text("She smiles, then frowns."), "2")  # the first one wins
        self.assertEqual(face_from_text("Ela cora e desvia o olhar."), "6")
        self.assertEqual(face_from_text('"Hello."'), "")

    def test_missing_mood_is_read_from_the_text(self):
        npcs = [{"name": "Lilia Valenheart", "portraits": PICS}]
        self.assertEqual(resolve_portraits("[[show: Lilia]]\nLilia blushes.", npcs)[1], {"Lilia Valenheart|Blushing": "/6.png"})
        self.assertEqual(resolve_portraits("[[show: Lilia | Angry]]\nShe laughs.", npcs)[1], {"Lilia Valenheart|Angry": "/4.png"})


class CardSyncTests(unittest.TestCase):
    def test_card_pictures_reach_running_games(self):
        s = make_services()
        card = s.scenarios.create({"name": "Test", "mode": "gm_cast", "npcs": [{"name": "Mira"}, {"name": "Tob"}]})
        cid = s.conversations.create(card)["id"]
        tob = next(n for n in s.conversations.list_npcs(cid) if n["name"] == "Tob")
        s.conversations.update_npc(tob["id"], portraits={"default": "/mine.png", "moods": []})  # changed in the game
        new_npcs = [{"name": "Mira", "portraits": PICS}, {"name": "Tob", "portraits": PICS}]
        self.assertEqual(s.conversations.sync_card_portraits(card["id"], card["data"]["npcs"], new_npcs), 1)
        got = {n["name"]: n["portraits"]["default"] for n in s.conversations.list_npcs(cid)}
        self.assertEqual(got, {"Mira": "/d.png", "Tob": "/mine.png"})


if __name__ == "__main__":
    unittest.main()
