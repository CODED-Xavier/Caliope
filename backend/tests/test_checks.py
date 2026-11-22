"""Tests for GM-requested checks rolled by the app."""
import random
import unittest

from app.checks import bonus_for, find_checks, label, roll_line
from app.dice import DiceRoller
from tests.test_core import FakeLLM, collect, make_services, new_game

SHEET = {"player": {"level": 5, "stats": {"STR": 8, "DEX": 16, "CON": 12, "INT": 10, "WIS": 14, "CHA": 11},
                    "skills": ["Stealth", "Perception", "DEX save"]}}


class FindTests(unittest.TestCase):
    def test_common_phrasings(self):
        self.assertEqual(find_checks("The guard turns. Make a DEX (Stealth) check, DC 13."),
                         [{"ability": "DEX", "skill": "Stealth", "kind": "check", "dc": 13}])
        self.assertEqual(find_checks("Roll a Wisdom (Perception) check.")[0]["skill"], "Perception")
        self.assertEqual(find_checks("Give me a Constitution saving throw (DC 14)!")[0],
                         {"ability": "CON", "skill": "", "kind": "save", "dc": 14})
        self.assertEqual(find_checks("Faça um teste de Destreza (Furtividade) CD 12.")[0]["skill"], "Stealth")
        self.assertEqual(find_checks("Make an Athletics check to climb.")[0]["ability"], "STR")
        self.assertEqual(find_checks("She smiles and pours the tea. Nothing to roll here."), [])
        self.assertEqual(find_checks("The con artist checks his int pocket."), [])  # ordinary words are not abilities
        many = find_checks("Make a STR check. Make a DEX check. Make a WIS check. Make a CHA check.")
        self.assertEqual(len(many), 1)  # one roll per reply

    def test_bonus_and_roll(self):
        self.assertEqual(bonus_for(SHEET, {"ability": "DEX", "skill": "Stealth", "kind": "check"})[0], 3 + 3)
        self.assertEqual(bonus_for(SHEET, {"ability": "STR", "skill": "Athletics", "kind": "check"})[0], -1)
        self.assertEqual(bonus_for(SHEET, {"ability": "DEX", "skill": "", "kind": "save"})[0], 6)
        self.assertEqual(bonus_for({"player": {}}, {"ability": "WIS", "skill": "", "kind": "check"})[0], 0)
        check = {"ability": "DEX", "skill": "Stealth", "kind": "check", "dc": 13}
        line = roll_line(DiceRoller(random.Random(3)), SHEET, check, "advantage")
        self.assertTrue(line.startswith("\U0001F3B2 Stealth check (DEX +3, proficient +3, advantage)"))
        self.assertRegex(line, r"vs DC 13 → (✅ Success|❌ Failure)")
        self.assertEqual(label(check), "Stealth check (DC 13)")


class GameTests(unittest.IsolatedAsyncioTestCase):
    async def test_reply_keeps_the_checks(self):
        llm = FakeLLM()
        s = make_services(llm)
        cid = new_game(s)
        llm.reply = "A floorboard creaks. Make a DEX (Stealth) check, DC 13."
        await collect(s.engine.send(cid, "I sneak past."))
        last = s.conversations.list_messages(cid)[-1]
        self.assertEqual(last["meta"]["checks"][0]["dc"], 13)


if __name__ == "__main__":
    unittest.main()
