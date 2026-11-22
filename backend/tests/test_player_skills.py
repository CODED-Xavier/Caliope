"""Your own skills (Lumencia: Soul Forge, Mana Sense Eyes...): made on the start screen, always in front of the Aedo,
and used in the story just by naming them ("I use my soul forge")."""
import unittest

from app import resources
from tests.test_card_sheet import LUMENCIA, OPENING
from tests.test_core import FakeLLM, collect, make_services, new_game

FORGE = {"name": "Soul Forge", "description": "Forges a weapon of pure soul energy that lasts one scene.", "costs": {"Mana": 3}}
EYES = {"name": "Mana Sense Eyes", "description": "Sees mana flows and hidden spells nearby."}


class FindTests(unittest.TestCase):
    def test_named_in_the_text(self):
        skills = resources.normalize_abilities([FORGE, EYES, {"name": "Go"}])
        found = resources.skills_in_text("I use my soul forge ability and strike!", skills)
        self.assertEqual([a["name"] for a in found], ["Soul Forge"])
        self.assertEqual(resources.skills_in_text("I look around.", skills), [])
        self.assertEqual(resources.skills_in_text("I go home.", skills), [])  # too short a name to spot by chance
        self.assertEqual(len(resources.skills_in_text("Mana sense eyes on, then soul-forge!", skills)), 2)

    def test_long_descriptions_kept(self):
        long = {"name": "X skill", "description": "a" * 500}
        self.assertEqual(len(resources.normalize_abilities([long])[0]["description"]), 500)

    def test_prompt_section(self):
        skills = resources.normalize_abilities([FORGE, EYES])
        text = resources.skills_section(skills)
        self.assertIn("Soul Forge", text)
        self.assertIn("pure soul energy", text)
        self.assertIn("3 Mana", text)
        self.assertEqual(resources.skills_section([]), "")


class GameTests(unittest.IsolatedAsyncioTestCase):
    def _game(self, s, **extra):
        base = s.conversations.get(new_game(s, information={"post_history": "Rules.\n\n" + LUMENCIA}, opening_message=OPENING,
                                            resources=[{"name": "Mana", "max": 10}], **extra))
        card = s.scenarios.get(base["scenario_id"])
        return s.conversations.create(card, setup="app", abilities=[FORGE, EYES], card_status={"Tier": "3-Circle"})["id"]

    async def test_start_screen_skills_reach_the_sheet_and_the_aedo(self):
        llm = FakeLLM()
        s = make_services(llm)
        cid = self._game(s)
        st = s.conversations.get_state(cid)
        own = [a for a in st["abilities"] if a.get("own")]
        self.assertEqual([a["name"] for a in own], ["Soul Forge", "Mana Sense Eyes"])
        self.assertEqual(st["card_status"]["Skills"], "Soul Forge / Mana Sense Eyes")  # the card's Skills field follows
        await collect(s.engine.send(cid, "I look at the hall."))
        system = "\n".join(m["content"] for m in llm.stream_calls[-1])
        self.assertIn("Soul Forge", system)
        self.assertIn("pure soul energy", system)

    async def test_naming_a_skill_uses_it(self):
        llm = FakeLLM()
        s = make_services(llm)
        cid = self._game(s)
        await collect(s.engine.send(cid, "I use my soul forge ability against the golem."))
        st = s.conversations.get_state(cid)
        self.assertEqual(st["resources"]["Mana"]["current"], 7)  # the cost is paid
        user = [m for m in s.conversations.list_messages(cid) if m["role"] == "user"][-1]
        self.assertEqual(user["meta"]["skills_used"][0]["name"], "Soul Forge")
        prompt = "\n".join(m["content"] for m in llm.stream_calls[-1])
        self.assertIn("uses a skill this turn", prompt)
        st["resources"]["Mana"]["current"] = 1
        s.conversations.save_state(cid, st)
        await collect(s.engine.send(cid, "Soul forge again!"))
        self.assertEqual(s.conversations.get_state(cid)["resources"]["Mana"]["current"], 1)  # not enough: nothing paid
        prompt = "\n".join(m["content"] for m in llm.stream_calls[-1])
        self.assertIn("Not enough Mana", prompt)


class PictureTests(unittest.TestCase):
    def test_your_picture_from_the_start_screen(self):
        s = make_services(FakeLLM())
        card = s.scenarios.get(s.conversations.get(new_game(s))["scenario_id"])
        cid = s.conversations.create(card, setup="app", player={"name": "Aster", "portraits": {"default": "/api/uploads/aster.png", "moods": []}})["id"]
        self.assertEqual(s.conversations.get_state(cid)["player"]["portraits"]["default"], "/api/uploads/aster.png")


if __name__ == "__main__":
    unittest.main()
