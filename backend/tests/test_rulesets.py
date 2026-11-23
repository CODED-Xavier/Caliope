"""World Compendium rule sets: short rules saved once, ticked on cards, sent always / in fights / on trigger words."""
import unittest

from app.rulebooks import applies_now
from tests.test_core import FakeLLM, collect, make_services, new_game

SPECTRUMS = "STRENGTH: Power Parity > Outmatched > Overpowered. SPEED: Equal Footing > Outpaced."


class AppliesTests(unittest.TestCase):
    def test_when_a_rule_set_applies(self):
        self.assertTrue(applies_now("always", "", "we talk about tea"))
        self.assertTrue(applies_now("fights", "", "I draw my sword and attack her"))
        self.assertTrue(applies_now("fights", "", "Eu ataco com um golpe rápido"))
        self.assertFalse(applies_now("fights", "", "We share tea in the garden."))
        self.assertTrue(applies_now("fights", "", "We share tea.", fighting=True))
        self.assertTrue(applies_now("fights", "aura", "Her aura flares."))
        self.assertTrue(applies_now("words", "circle, mana", "a 3-Circle spell"))
        self.assertFalse(applies_now("words", "circle, mana", "a quiet evening"))


class GameTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_fight_rule_set_reaches_the_aedo_only_in_fights(self):
        llm = FakeLLM()
        s = make_services(llm)
        rs = s.rulebooks.create_ruleset("Combat Spectrums", SPECTRUMS, "fights", "")
        self.assertEqual((rs["status"], rs["applies"]), ("ready", "fights"))
        always = s.rulebooks.create_ruleset("Tone", "Always describe the weather.", "always")
        cid = new_game(s, rulebooks=[rs["id"], always["id"]])
        await collect(s.engine.send(cid, "We drink tea and talk."))
        sent = "\n".join(m["content"] for m in llm.stream_calls[-1])
        self.assertNotIn("Power Parity", sent)
        self.assertIn("Always describe the weather.", sent)
        await collect(s.engine.send(cid, "I draw my sword and attack the bandit!"))
        sent = "\n".join(m["content"] for m in llm.stream_calls[-1])
        self.assertIn("## Rules in play right now", sent)
        self.assertIn("Power Parity", sent)

    def test_editing_when_it_applies(self):
        s = make_services()
        rs = s.rulebooks.create_ruleset("Magic", "Circles cost mana.", "always")
        got = s.rulebooks.update(rs["id"], applies="words", trigger_words="circle, mana,  circle ")
        self.assertEqual((got["applies"], got["trigger_words"]), ("words", "circle, mana"))
        self.assertEqual(s.rulebooks.update(rs["id"], applies="nonsense")["applies"], "words")


if __name__ == "__main__":
    unittest.main()
