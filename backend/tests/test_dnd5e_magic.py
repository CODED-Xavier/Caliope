"""Spell slots, spells that roll (attack, save, healing, upcasting, cantrip growth), Divine Smite, Rage, Sneak Attack,
Lay on Hands as a pool, and the fight using them."""
import random
import unittest
from pathlib import Path

from app.combat import CombatEngine
from app.dice import DiceRoller
from app.dnd5e import magic, store
from app.dnd5e.character import derive, new_character
from app.dnd5e.library import Library

SEED = Path(__file__).resolve().parents[1] / "app/seed/srd5e.json"
LIB = Library([SEED])
LIB.load()


def spell(name):
    return next(e for (k, n, _), e in LIB.items.items() if k == "spell" and n == name.lower())


def hero(cls, level, scores=None, spells=()):
    c = new_character("2014")
    c["cls"] = {"name": cls, "source": "PHB"}
    c["level"] = level
    c["scores"] = {**c["scores"], **(scores or {})}
    c["spells"] = [{"type": "spell", "name": s, "source": "PHB"} for s in spells]
    return c


class SpellRollTests(unittest.TestCase):
    def test_shapes_of_rolls(self):
        self.assertEqual(magic.spell_roll(spell("Fire Bolt"), 5, 0, 3), {"kind": "attack", "dice": "2d10", "dtype": "fire", "save": "", "half": False})
        fb = magic.spell_roll(spell("Fireball"), 5, 4, 3)
        self.assertEqual((fb["kind"], fb["dice"], fb["save"], fb["half"]), ("save", "8d6+1d6", "dex", True))
        cw = magic.spell_roll(spell("Cure Wounds"), 5, 2, 3)
        self.assertEqual((cw["kind"], cw["dice"]), ("heal", "1d8+1d8+3"))
        self.assertEqual(magic.smite_dice(1), "2d8")
        self.assertEqual(magic.smite_dice(2, "Zombie"), "4d8")
        self.assertEqual(magic.smite_dice(9), "5d8")


class SlotTests(unittest.TestCase):
    def test_spend_and_rest(self):
        c = hero("Wizard", 3, {"int": 16})
        sh = derive(c, LIB)
        self.assertEqual((sh["spell_dc"], sh["spell_attack"], sh["slots_left"]), (13, 5, {"1": 4, "2": 2}))
        c, lv = magic.spend_slot(c, sh, 1)
        self.assertEqual(lv, 1)
        c, lv = magic.spend_slot(c, derive(c, LIB), 2)
        self.assertEqual(derive(c, LIB)["slots_left"], {"1": 3, "2": 1})
        c = store.rest(c, "long_rest", LIB)
        self.assertEqual(derive(c, LIB)["slots_left"], {"1": 4, "2": 2})
        with self.assertRaises(ValueError):
            magic.spend_slot(c, derive(c, LIB), 3)

    def test_slots_spent_and_given_back_by_hand(self):
        c = hero("Wizard", 3, {"int": 16})
        c = store.apply_change(c, {"op": "slot", "level": "1", "delta": 1}, LIB)
        c = store.apply_change(c, {"op": "slot", "level": 2, "delta": 1}, LIB)
        self.assertEqual(derive(c, LIB)["slots_left"], {"1": 3, "2": 1})
        c = store.apply_change(c, {"op": "slot", "level": "1", "delta": -1}, LIB)
        self.assertEqual(derive(c, LIB)["slots_left"], {"1": 4, "2": 1})
        with self.assertRaises(ValueError):
            store.apply_change(c, {"op": "slot", "level": "3", "delta": 1}, LIB)
        w = hero("Warlock", 3, {"cha": 16})
        w = store.apply_change(w, {"op": "slot", "level": "pact", "delta": 1}, LIB)
        self.assertEqual(derive(w, LIB)["pact_left"], 1)


class PoolTests(unittest.TestCase):
    def test_lay_on_hands_points(self):
        c = hero("Paladin", 3, {"cha": 14})
        c["hp"] = {"current": 5, "rolls": []}
        c, line = store.use_feature(c, "Lay on Hands", LIB, amount=10)
        self.assertEqual(c["uses"]["Lay on Hands"], 10)
        self.assertIn("5/15", line)


class FightTests(unittest.TestCase):
    def fight(self, char, seed=1):
        eng = CombatEngine(DiceRoller(random.Random(seed)), random.Random(seed))
        state = {"player": {"name": "Aster", "hp": {"current": 30, "max": 30}, "ac": 15}, "character5e": char}
        store.sync_player(state, LIB)
        foes = [{"name": "Zombie", "count": 2, "hp": 40, "ac": 8, "attack_bonus": 3, "damage": "1d6+1"}]
        state, _ = eng.start(state, "d20", foes, grid={"w": 10, "h": 6})
        c = state["combat"]
        me = next(x for x in c["combatants"] if x["side"] == "player")
        while eng.current(c)["side"] != "player":
            state, _ = eng.enemies_act(state)
            c = state["combat"]
        z = [x for x in c["combatants"] if x["side"] == "enemy"]
        z[0]["x"], z[0]["y"] = me["x"] + 1, me["y"]
        z[1]["x"], z[1]["y"] = me["x"] + 1, me["y"] + 1
        return eng, state, z

    def test_cast_fireball_hits_everyone_inside_and_spends_a_slot(self):
        from app.dnd5e.fight import cast_in_fight as _cast_in_fight  # the glue: sheet + fight
        char = hero("Wizard", 5, {"int": 18}, ["Fireball"])
        eng, state, z = self.fight(char)
        me = next(x for x in state["combat"]["combatants"] if x["side"] == "player")
        z[0]["x"], z[0]["y"] = me["x"] + 5, me["y"]  # 25 ft away, the second zombie beside it
        z[1]["x"], z[1]["y"] = me["x"] + 5, me["y"] + 1
        state, line = _cast_in_fight(eng, state, LIB, "spell:Fireball", z[0]["id"], "", None)
        self.assertIn("Fireball", line)
        self.assertIn("DEX save", line)
        self.assertEqual(state["character5e"]["slots_used"], {"3": 1})
        self.assertTrue(all(x["hp"] < 40 for x in z))

    def test_a_blast_that_would_hit_you_is_refused(self):
        from app.combat import CombatError
        from app.dnd5e.fight import cast_in_fight
        char = hero("Wizard", 5, {"int": 18}, ["Fireball"])
        eng, state, z = self.fight(char)  # both zombies right next to the caster
        with self.assertRaises(CombatError) as got:
            cast_in_fight(eng, state, LIB, "spell:Fireball", z[0]["id"], "", None)
        self.assertIn("inside", str(got.exception))
        self.assertNotIn("slots_used", state["character5e"])  # nothing spent
        me = next(x for x in state["combat"]["combatants"] if x["side"] == "player")
        z[0]["x"], z[0]["y"] = me["x"] + 6, me["y"]  # 30 ft away: the caster is outside the 20 ft blast
        state, line = cast_in_fight(eng, state, LIB, "spell:Fireball", z[0]["id"], "", None)
        self.assertNotIn(f"- {me['name']}:", line)

    def test_opportunity_attack_needs_reach_and_keeps_the_reaction_when_refused(self):
        from app.combat import CombatError
        eng, state, z = self.fight(hero("Fighter", 3, {"str": 16}))
        me = next(x for x in state["combat"]["combatants"] if x["side"] == "player")
        z[0]["x"], z[0]["y"] = me["x"] + 5, me["y"]
        with self.assertRaises(CombatError):
            eng.use_option(state, {"kind": "opportunity", "cost": "reaction", "name": "Opportunity Attack"}, z[0]["id"], "")
        self.assertNotEqual(state["combat"].get("reaction_round"), state["combat"]["round"])

    def test_divine_smite_listed_once(self):
        from app.dnd5e import actions
        char = hero("Paladin", 5, {"str": 16, "cha": 14})
        names = [o["name"] for g in actions.options(char, LIB).values() for o in g]
        self.assertEqual(names.count("Divine Smite"), 1)

    def test_divine_smite_after_a_hit(self):
        from app.dnd5e.fight import cast_in_fight as _cast_in_fight
        char = hero("Paladin", 2, {"str": 16, "cha": 14})
        char["items"] = [{"type": "baseitem", "name": "Longsword", "source": "PHB", "equipped": True}]
        eng, state, z = self.fight(char, seed=3)
        with self.assertRaises(Exception):
            _cast_in_fight(eng, state, LIB, "rules:divine_smite", z[0]["id"], "", None)  # no hit yet
        for _ in range(6):
            state, line = eng.player_step(state, "attack", z[0]["id"], "advantage")
            if state["combat"].get("last_hit"):
                break
            state["combat"]["spent"] = {"action": False, "bonus": False, "attacked": False}
        self.assertTrue(state["combat"].get("last_hit"))
        before = z[0]["hp"]
        state, line = _cast_in_fight(eng, state, LIB, "rules:divine_smite", "", "", None)
        self.assertIn("Divine Smite", line)
        self.assertTrue("3d8" in line or "6d8" in line)  # 2d8 + 1d8 against undead (doubled on a critical)
        self.assertLess(z[0]["hp"], before)
        self.assertNotIn("last_hit", state["combat"])  # one smite per hit
        with self.assertRaises(Exception):
            _cast_in_fight(eng, state, LIB, "rules:divine_smite", "", "", None)

    def test_shield_reaction_is_offered_and_its_slot_comes_off_the_sheet(self):
        from app.dnd5e.fight import auto_reactions, settle_auto
        char = hero("Wizard", 3, {"int": 16}, ["Shield", "Magic Missile"])
        eng, state, z = self.fight(char)
        auto_reactions(state, LIB)
        auto = state["combat"]["auto_reactions"]
        self.assertTrue(auto["shield"])
        self.assertEqual(auto["slots"], 6)  # 4 first-level + 2 second-level at Wizard 3
        self.assertIn("shield", auto["can"])
        state["combat"]["auto_spent"] = ["slot"]
        settle_auto(state, LIB)
        self.assertEqual(state["character5e"]["slots_used"], {"1": 1})
        self.assertEqual(state["combat"]["auto_spent"], [])
        self.assertEqual(state["combat"]["auto_reactions"]["slots"], 5)

    def test_no_shield_without_the_spell(self):
        from app.dnd5e.fight import auto_reactions
        eng, state, z = self.fight(hero("Fighter", 3, {"str": 16}))
        auto_reactions(state, LIB)
        self.assertFalse(state["combat"]["auto_reactions"]["shield"])
        self.assertEqual(state["combat"]["auto_reactions"]["can"], [])

    def test_rage_marks_the_fighter_and_spends_a_use(self):
        from app.dnd5e.fight import cast_in_fight
        char = hero("Barbarian", 3, {"str": 16})
        eng, state, z = self.fight(char)
        option = next(o for g in __import__("app.dnd5e.actions", fromlist=["x"]).options(char, LIB).values()
                      for o in g if o["name"] == "Rage")
        state, line = cast_in_fight(eng, state, LIB, option["id"], "", "", None)
        me = next(x for x in state["combat"]["combatants"] if x["side"] == "player")
        self.assertTrue(me["raging"])
        self.assertEqual(me["rage_bonus"], 2)
        self.assertEqual(state["character5e"]["uses"]["Rage"], 1)


if __name__ == "__main__":
    unittest.main()
