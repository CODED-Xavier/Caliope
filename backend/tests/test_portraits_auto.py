"""Pictures for characters the model forgot to tag (Isabel, Elara, Lyra in Lumencia), and story facts the player
fixes with the Aedo ("/fix Aria is the Saintess, not Anastasia")."""
import unittest

from app import portraits
from tests.test_core import FakeLLM, collect, make_services, new_game


def npc(name, n=6):
    moods = [{"n": i, "label": lab, "url": f"/api/uploads/{name}{i}.png"} for i, lab in
             enumerate(["Standard", "Happy", "Sad", "Angry", "Disgusted/Very Angry", "Blushing"][:n], start=1)]
    return {"id": hash(name) % 1000, "name": name, "portraits": {"default": f"/api/uploads/{name}.png", "moods": moods}}


CAST = [npc("Isabel"), npc("Elara"), npc("Lyra"), npc("Professor Artemis"), {"id": 9, "name": "Nobody"}]


class AutoTests(unittest.TestCase):
    def test_speakers_get_their_picture(self):
        story = ('Isabel smirks, clearly unimpressed. "Isabel Reihart," she responds curtly.\n\n'
                 'Elara laughs softly beside her. "Don\'t mind her."\n\nA bell rings somewhere.')
        text, meta, _ = portraits.process_reply(story, CAST)
        self.assertEqual(list(meta["portraits"]), ["Isabel|Happy", "Elara|Happy"])
        self.assertLess(text.index("[[show: Isabel"), text.index("Isabel smirks"))

    def test_mood_from_the_paragraph_and_at_most_two(self):
        story = ('Lyra glares at you. "Move."\n\nIsabel blushes. "W-what?"\n\nElara sighs. "Again?"')
        _, meta, _ = portraits.process_reply(story, CAST)
        self.assertEqual(list(meta["portraits"]), ["Lyra|Angry", "Isabel|Blushing"])

    def test_tagged_replies_are_left_alone(self):
        _, meta, _ = portraits.process_reply('[[show: Elara | Sad]]\nElara looks down. "Sorry."\nIsabel nods. "Fine."', CAST)
        self.assertEqual(list(meta["portraits"]), ["Elara|Sad"])

    def test_a_name_in_passing_is_not_a_scene(self):
        _, meta, _ = portraits.process_reply("You think of Lyra for a moment, then walk on.", CAST)
        self.assertNotIn("portraits", meta)


class FixTests(unittest.IsolatedAsyncioTestCase):
    async def test_fix_command_and_fact_lines(self):
        llm = FakeLLM()
        s = make_services(llm)
        cid = new_game(s)
        await collect(s.engine.send(cid, "/fix Aria is the Saintess, not Anastasia"))
        st = s.conversations.get_state(cid)
        self.assertEqual(st["corrections"], ["Aria is the Saintess, not Anastasia"])
        last = s.conversations.list_messages(cid)[-1]
        self.assertIn("📌", last["content"])
        llm.reply = "Right, my mistake: Aria is the Saintess.\nFACT: The Saintess is Aria, Anastasia is a noble."
        await collect(s.engine.send(cid, "/the saintess was Aria, not Anastasia!"))
        st = s.conversations.get_state(cid)
        self.assertIn("The Saintess is Aria, Anastasia is a noble", st["corrections"])
        last = s.conversations.list_messages(cid)[-1]
        self.assertNotIn("FACT:", last["content"])
        llm.reply = "The story goes on."
        await collect(s.engine.send(cid, "I look around."))
        prompt = "\n".join(m["content"] for m in llm.stream_calls[-1])
        self.assertIn("Aria is the Saintess, not Anastasia", prompt)


if __name__ == "__main__":
    unittest.main()
