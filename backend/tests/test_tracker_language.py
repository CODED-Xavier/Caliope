"""A Portuguese game: the tracker writes its reasons and notes (the update lines under replies) in Portuguese."""
import unittest

from app.prompts import PromptBuilder


class TrackerLanguageTest(unittest.TestCase):
    def test_reasons_in_the_story_language(self):
        pb = PromptBuilder()
        base = dict(scenario={"mode": "gm_world"}, state={"player": {"name": "Aster", "hp": {"current": 5, "max": 5}}, "inventory": [],
                    "quests": [], "gold": 0}, npcs=[], exchanges=[("Oi", "Olá")])
        pt = "\n".join(m["content"] for m in pb.analysis_messages(**base, language="pt-BR"))
        self.assertIn("Brazilian Portuguese", pt)
        en = "\n".join(m["content"] for m in pb.analysis_messages(**base))
        self.assertNotIn("Brazilian Portuguese", en)


if __name__ == "__main__":
    unittest.main()
