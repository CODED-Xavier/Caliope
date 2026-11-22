"""5e actions like Foundry: every option sorted by what it costs (action, bonus action, reaction, free), read from the
rules and from each feature's own text; the fight holds what was spent until the turn ends."""
import unittest

from app.combat import CombatError
from app.dnd5e import actions
from app.dnd5e.character import new_character
from tests.dnd5e_fixture import fixture_library, ref
from tests.test_action_economy import ready

LIB = fixture_library()


class CostTest(unittest.TestCase):
    def test_costs_from_the_text(self):
        self.assertEqual(actions.cost_of("On your turn, you can use a bonus action to regain hit points"), "bonus")
        self.assertEqual(actions.cost_of("When an attacker hits you, you can use your reaction to halve the damage"), "reaction")
        self.assertEqual(actions.cost_of("When you hit a creature with a melee weapon attack, you can expend one spell slot"), "free")
        self.assertEqual(actions.cost_of("On your turn, you can take one additional action."), "free")
        self.assertEqual(actions.cost_of("As an action, you can present your holy symbol"), "action")
        self.assertIsNone(actions.cost_of("You gain proficiency with heavy armor."))


class OptionsTest(unittest.TestCase):
    def fighter(self):
        c = new_character("2014")
        c.update(cls=ref("Fighter"), race=ref("Human"), level=2)
        return c

    def test_standard_actions_and_features(self):
        opts = actions.options(self.fighter(), LIB)
        names = {k: [o["name"] for o in v] for k, v in opts.items()}
        for n in ("Attack", "Dash", "Disengage", "Dodge", "Help", "Hide", "Ready", "Search", "Use an Object", "Grapple", "Shove"):
            self.assertIn(n, names["action"])
        self.assertIn("Second Wind", names["bonus"])
        self.assertIn("Action Surge", names["free"])
        self.assertIn("Opportunity Attack", names["reaction"])
        sw = next(o for o in opts["bonus"] if o["name"] == "Second Wind")
        self.assertEqual((sw["kind"], sw["uses_left"]), ("feature", 1))

    def test_monk_has_one_martial_arts_button(self):
        c = new_character("2014")
        c.update(cls=ref("Monk"), level=1)
        lib_monk_text = LIB.items[("classFeature", "martial arts", "PHB")]
        lib_monk_text["entries"] = ["You can make one unarmed strike as a bonus action."]
        names = [o["name"] for o in actions.options(c, LIB)["bonus"]]
        self.assertEqual(sum("Martial Arts" in n for n in names), 1)

    def test_spells_by_casting_time(self):
        c = new_character("2014")
        c.update(cls=ref("Wizard"), level=1, spells=[{"type": "spell", **ref(n)} for n in ("Magic Missile", "Shield", "Healing Word", "Fire Bolt")])
        opts = actions.options(c, LIB)
        self.assertIn("Magic Missile", [o["name"] for o in opts["action"]])
        self.assertIn("Fire Bolt", [o["name"] for o in opts["action"]])
        self.assertIn("Shield", [o["name"] for o in opts["reaction"]])
        self.assertIn("Healing Word", [o["name"] for o in opts["bonus"]])


class SpendingTest(unittest.TestCase):
    def test_a_bonus_option_spends_the_bonus_action(self):
        eng, state, me, rat = ready()
        state, line = eng.use_option(state, {"id": "feature:Second Wind", "name": "Second Wind", "cost": "bonus", "kind": "feature"}, "")
        self.assertTrue(state["combat"]["spent"]["bonus"])
        self.assertIn("Second Wind", line)
        with self.assertRaises(CombatError):
            eng.use_option(state, {"id": "spell:Healing Word", "name": "Healing Word", "cost": "bonus", "kind": "spell"}, "")

    def test_reaction_once_per_round(self):
        eng, state, me, rat = ready()
        state, _ = eng.use_option(state, {"id": "spell:Shield", "name": "Shield", "cost": "reaction", "kind": "spell"}, "")
        with self.assertRaises(CombatError):
            eng.use_option(state, {"id": "rules:opportunity", "name": "Opportunity Attack", "cost": "reaction", "kind": "opportunity"}, rat["id"])

    def test_dash_doubles_movement(self):
        eng, state, me, rat = ready()
        state, _ = eng.use_option(state, {"id": "rules:dash", "name": "Dash", "cost": "action", "kind": "dash"}, "")
        self.assertEqual(state["combat"]["moved"], -me["speed"])
        with self.assertRaises(CombatError):  # the action is spent
            eng.use_option(state, {"id": "rules:dodge", "name": "Dodge", "cost": "action", "kind": "dodge"}, "")

    def test_grapple_is_a_contest(self):
        eng, state, me, rat = ready()
        state, line = eng.use_option(state, {"id": "rules:grapple", "name": "Grapple", "cost": "action", "kind": "grapple"}, rat["id"])
        self.assertIn("Athletics", line)
        self.assertEqual("grappled" in rat["conditions"], "GRAPPLED" in line)

    def test_free_options_cost_nothing(self):
        eng, state, me, rat = ready()
        state, _ = eng.use_option(state, {"id": "feature:Action Surge", "name": "Action Surge", "cost": "free", "kind": "feature", "grants": "action"}, "")
        state, _ = eng.player_step(state, "attack", rat["id"])
        state, _ = eng.player_step(state, "dodge")  # Action Surge gave a second action
        with self.assertRaises(CombatError):
            eng.player_step(state, "dodge")


if __name__ == "__main__":
    unittest.main()
