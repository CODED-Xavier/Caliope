"""Resources named in the chat are spent on the 5e sheet: "I use Lay on Hands for 5", "I rage", "I cast Cure Wounds
at 2nd level", and the same in Portuguese."""
import random
import unittest
from pathlib import Path

from app.dnd5e import chatuse, store
from app.dnd5e.character import derive, new_character
from app.dnd5e.library import Library

SEED = Path(__file__).resolve().parents[1] / "app/seed/srd5e.json"
LIB = Library([SEED])
LIB.load()


def hero(cls, level, scores=None, spells=()):
    c = new_character("2014")
    c["cls"] = {"name": cls, "source": "PHB"}
    c["level"] = level
    c["scores"] = {**c["scores"], **(scores or {})}
    c["spells"] = [{"type": "spell", "name": s, "source": "PHB"} for s in spells]
    return c


def state_of(char):
    st = {"player": {"name": "Aster"}, "character5e": char}
    store.sync_player(st, LIB)  # the game's HP comes from the sheet, as in a real game
    return st


class FindTests(unittest.TestCase):
    def test_features_need_a_verb_or_the_feature_as_the_verb(self):
        pal = hero("Paladin", 3, {"cha": 14})
        found = chatuse.found_in_text("I use Lay on Hands on myself, 5 points.", pal, LIB)
        self.assertEqual(found, [{"kind": "feature", "name": "Lay on Hands", "amount": 5}])
        self.assertEqual(chatuse.found_in_text("The priest talks about lay on hands and old saints.", pal, LIB), [])
        barb = hero("Barbarian", 2, {"str": 16})
        self.assertEqual(chatuse.found_in_text("I rage and charge the orc!", barb, LIB)[0]["name"], "Rage")
        self.assertEqual(chatuse.found_in_text("Entro em fúria e avanço.", barb, LIB)[0]["name"], "Rage")
        self.assertEqual(chatuse.found_in_text("The orc's rage is clear.", barb, LIB), [])

    def test_spells_need_cast_and_take_the_slot_level(self):
        cle = hero("Cleric", 3, {"wis": 16}, ["Cure Wounds", "Sacred Flame"])
        self.assertEqual(chatuse.found_in_text("I cast Cure Wounds at 2nd level on Lyra.", cle, LIB),
                         [{"kind": "spell", "name": "Cure Wounds", "spell_level": 1, "slot": 2, "self": False}])
        self.assertEqual(chatuse.found_in_text("Conjuro Cure Wounds em mim mesmo.", cle, LIB),
                         [{"kind": "spell", "name": "Cure Wounds", "spell_level": 1, "slot": None, "self": True}])
        self.assertEqual(chatuse.found_in_text("I cast Sacred Flame at the ghoul.", cle, LIB), [])  # cantrips cost nothing
        self.assertEqual(chatuse.found_in_text("I remember the Cure Wounds scroll.", cle, LIB), [])

    def test_smite_for_paladins(self):
        pal = hero("Paladin", 2, {"str": 16, "cha": 14})
        self.assertEqual(chatuse.found_in_text("I smite the bandit with a 1st-level slot", pal, LIB),
                         [{"kind": "smite", "slot": 1}])
        self.assertEqual(chatuse.found_in_text("I smite the bandit", hero("Fighter", 2), LIB), [])


class ApplyTests(unittest.TestCase):
    def test_lay_on_hands_heals_and_spends_points(self):
        pal = hero("Paladin", 3, {"cha": 14})
        pal["hp"] = {"current": 5, "rolls": []}
        st = state_of(pal)
        lines = chatuse.apply(st, "I use lay on hands for 4", LIB)
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0]["ok"])
        self.assertIn("Lay on Hands", lines[0]["line"])
        self.assertEqual(st["character5e"]["uses"]["Lay on Hands"], 4)
        self.assertEqual(st["player"]["hp"]["current"], 9)

    def test_spell_slot_spent_and_refused_when_empty(self):
        cle = hero("Cleric", 1, {"wis": 16}, ["Cure Wounds"])
        st = state_of(cle)
        for _ in range(2):
            lines = chatuse.apply(st, "I cast Cure Wounds on Lyra", LIB)
            self.assertTrue(lines[0]["ok"])
        self.assertEqual(st["character5e"]["slots_used"], {"1": 2})
        lines = chatuse.apply(st, "I cast Cure Wounds on Lyra", LIB)
        self.assertFalse(lines[0]["ok"])
        self.assertIn("No spell slots", lines[0]["line"])
        self.assertEqual(st["character5e"]["slots_used"], {"1": 2})

    def test_healing_yourself_rolls(self):
        cle = hero("Cleric", 1, {"wis": 16}, ["Cure Wounds"])
        cle["hp"] = {"current": 1, "rolls": []}
        st = state_of(cle)
        lines = chatuse.apply(st, "I cast Cure Wounds on myself", LIB, rng=random.Random(2))
        self.assertIn("🎲", lines[0]["line"])
        self.assertGreater(derive(st["character5e"], LIB)["hp"], 1)

    def test_nothing_named_changes_nothing(self):
        st = state_of(hero("Wizard", 3, {"int": 16}, ["Magic Missile"]))
        self.assertEqual(chatuse.apply(st, "I walk to the tavern.", LIB), [])
        self.assertNotIn("slots_used", st["character5e"])

    def test_prompt_section(self):
        text = chatuse.prompt_section([{"ok": True, "line": "✨ Rage (1/2 left)", "name": "Rage"},
                                       {"ok": False, "line": "✨ Cure Wounds: No spell slots left.", "name": "Cure Wounds"}])
        self.assertIn("Rage WORKS", text)
        self.assertIn("Cure Wounds FALTERS", text)
        self.assertEqual(chatuse.prompt_section([]), "")


if __name__ == "__main__":
    unittest.main()
