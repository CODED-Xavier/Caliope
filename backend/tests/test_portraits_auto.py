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

    def test_mood_from_the_paragraph_for_each_speaker(self):
        story = ('Lyra glares at you. "Move."\n\nIsabel blushes. "W-what?"\n\nElara sighs. "Again?"')
        _, meta, _ = portraits.process_reply(story, CAST)
        self.assertEqual(list(meta["portraits"]), ["Lyra|Angry", "Isabel|Blushing", "Elara|Sad"])

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


    async def test_correction_redoes_the_last_reply_with_the_fact(self):
        llm = FakeLLM()
        s = make_services(llm)
        cid = new_game(s)
        llm.reply = '"Isabel, Second Princess of House Valenheart," she says.'
        await collect(s.engine.send(cid, "And your name is?"))
        before = s.conversations.list_messages(cid)
        llm.reply = '"Isabel, Second Princess of the Empire," she says. Anastasia is her older sister.'
        events = await collect(s.engine.send(cid, "/correction Isabel is the Second Princess of the Empire, not a Valenheart"))
        after = s.conversations.list_messages(cid)
        self.assertEqual(len(after), len(before))  # the wrong reply was replaced, nothing added
        self.assertEqual(after[-2]["content"], "And your name is?")  # the player's line stays
        self.assertIn("Second Princess of the Empire", after[-1]["content"])
        self.assertNotIn("Valenheart,", after[-1]["content"])
        self.assertTrue(any(e.get("type") == "rolled_back" for e in events))
        prompt = "\n".join(m["content"] for m in llm.stream_calls[-1])
        self.assertIn("Isabel is the Second Princess of the Empire, not a Valenheart", prompt)
        self.assertIn("Rewrite", prompt)
        st = s.conversations.get_state(cid)
        self.assertIn("Isabel is the Second Princess of the Empire, not a Valenheart", st["corrections"])
        llm.reply = "Later."
        await collect(s.engine.send(cid, "I bow."))
        prompt = "\n".join(m["content"] for m in llm.stream_calls[-1])
        self.assertNotIn("Rewrite", prompt)  # the redo note is for one reply only; the fact stays
        self.assertIn("not a Valenheart", prompt)

    async def test_correction_with_nothing_to_redo(self):
        s = make_services(FakeLLM())
        cid = new_game(s)
        events = await collect(s.engine.send(cid, "/correction Nothing yet"))
        self.assertTrue(any(e.get("type") == "error" for e in events))


if __name__ == "__main__":
    unittest.main()
