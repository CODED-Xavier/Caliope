import unittest

from app import prompts


class AppWrittenTurnTest(unittest.TestCase):
    def test_combat_start_is_not_the_players_action(self):
        self.assertTrue(prompts.app_wrote("⚔️ Combat starts! Turn order: Goblin 2, Aster."))
        self.assertFalse(prompts.app_wrote("I punch the goblin. ⚔️ Aster attacks Goblin 2"))
        text = prompts.closing_rules("Aster", "en", app_turn=True)
        self.assertIn("Aster has not acted", text)
        self.assertIn("ask what Aster does", text)
        self.assertNotIn("has not acted", prompts.closing_rules("Aster", "en"))


if __name__ == "__main__":
    unittest.main()
