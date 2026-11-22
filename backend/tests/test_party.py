"""Companions, solo play and death saves (docs/superpowers/specs/2026-11-22-companions-and-solo-design.md)."""
import random
import unittest

from app import party
from app.combat import CombatEngine
from app.dice import DiceRoller
from app.scenarios import normalize_scenario
from app.state import new_state, normalize_state

CARD = {"name": "Cragmaw", "mode": "gm_world", "npcs": [
    {"name": "Dorna Ironhand", "companion": True, "personality": "gruff", "sheet": {"class": "Cleric", "role": "healer"}},
    {"name": "Faelar Quickbow", "companion": True, "sheet": {"class": "Ranger", "role": "archer", "hp": 11}},
    {"name": "Pip Thistledown", "companion": True, "sheet": {"class": "Rogue", "role": "rogue"}},
    {"name": "Extra One", "companion": True, "sheet": {"role": "fighter"}},
    {"name": "Sildar Hallwinter"}]}


def hero(hp=12):
    return new_state({"name": "Aster", "class": "Fighter", "stats": {"STR": 16, "DEX": 14, "CON": 14, "INT": 10, "WIS": 10, "CHA": 8},
                      "hp": {"current": hp, "max": hp}, "ac": 18, "level": 1})


class SheetTests(unittest.TestCase):
    def test_sheet_defaults_by_role(self):
        h = party.normalize_sheet({"role": "healer"})
        self.assertEqual((h["heal"], h["heals"], h["hp"], h["ac"]), ("1d8+3", 2, 10, 16))
        self.assertEqual(party.normalize_sheet({"role": "wizard"})["role"], "fighter")
        self.assertEqual(party.normalize_sheet({"role": "archer"})["range"], 16)

    def test_card_keeps_companions(self):
        data = normalize_scenario(CARD)
        comps = party.companions(data)
        self.assertEqual([c["name"] for c in comps], ["Dorna Ironhand", "Faelar Quickbow", "Pip Thistledown"])
        self.assertEqual(comps[1]["sheet"]["hp"], 11)
        self.assertFalse(next(n for n in data["npcs"] if n["name"] == "Extra One").get("companion"))  # only 3

    def test_start_party_solo_and_companions(self):
        data = normalize_scenario(CARD)
        st = hero()
        party.start_party(st, data, "companions")
        self.assertEqual(st["party_mode"], "companions")
        self.assertEqual(st["party"]["Faelar Quickbow"], {"hp": 11, "max_hp": 11})
        self.assertEqual(party.party_size(st), 4)
        st2 = hero()
        party.start_party(st2, data, "solo")
        self.assertEqual((st2["party_mode"], st2["party"], party.party_size(st2)), ("solo", {}, 1))

    def test_state_keeps_party(self):
        st = hero()
        party.start_party(st, normalize_scenario(CARD), "companions")
        again = normalize_state(st)
        self.assertEqual(again["party_mode"], "companions")
        self.assertEqual(again["party"]["Dorna Ironhand"]["max_hp"], 10)



class ScaleTests(unittest.TestCase):
    def test_scale(self):
        foes = [{"name": "Goblin", "count": 4}, {"name": "Bugbear", "count": 1}, {"name": "Wolf", "count": 6}]
        self.assertEqual([e["count"] for e in party.scale_enemies(foes, 1)], [1, 1, 2])
        self.assertEqual([e["count"] for e in party.scale_enemies(foes, 4)], [4, 1, 6])
        self.assertEqual(party.scale_enemies([{"name": "Wolf", "count": 6}], 2)[0]["count"], 3)
        self.assertEqual(party.scale_enemies(foes, 1)[0]["scaled_for"], 1)
        self.assertNotIn("scaled_for", party.scale_enemies(foes, 1)[1])  # unchanged

    def test_combat_enemies_uses_party(self):
        from app import adventure
        adv = adventure.normalize_adventure({"scenes": [{"id": "amb", "name": "Goblin Ambush", "enemies": [{"name": "Goblin", "count": 4}]}]})
        st = hero()
        st["adventure"] = {"scene": "amb", "visited": ["amb"], "xp_given": []}
        st["party_mode"] = "solo"
        self.assertEqual(adventure.combat_enemies(adv, st)[0]["count"], 1)
        st["party_mode"] = "companions"
        st["party"] = {"A": {"hp": 5, "max_hp": 5}, "B": {"hp": 5, "max_hp": 5}, "C": {"hp": 0, "max_hp": 5}}
        self.assertEqual(adventure.combat_enemies(adv, st)[0]["count"], 3)



def eng(seed=1):
    return CombatEngine(DiceRoller(random.Random(seed)), random.Random(seed))


def party_state(mode="companions"):
    st = hero()
    party.start_party(st, normalize_scenario(CARD), mode)
    return st


class AllyTests(unittest.TestCase):
    def test_allies_skip_the_fallen(self):
        st = party_state()
        st["party"]["Pip Thistledown"]["hp"] = 0
        al = party.allies(st, normalize_scenario(CARD))
        self.assertEqual([a["name"] for a in al], ["Dorna Ironhand", "Faelar Quickbow"])
        self.assertEqual((al[0]["role"], al[0]["heal"], al[0]["heals"]), ("healer", "1d8+3", 2))
        self.assertEqual(party.allies(party_state("solo"), normalize_scenario(CARD)), [])

    def test_ally_hp_goes_back_to_party(self):
        st = party_state()
        e = eng()
        state, _ = e.start(st, "d20", [{"name": "Rat", "hp": 1, "ac": 1, "init_bonus": -9}], allies=party.allies(st, normalize_scenario(CARD)))
        faelar = next(c for c in state["combat"]["combatants"] if c["name"] == "Faelar Quickbow")
        self.assertEqual(faelar["role"], "archer")
        faelar["hp"] = 4
        e._sync_player(state)
        self.assertEqual(state["party"]["Faelar Quickbow"]["hp"], 4)



def fight(st, foes=None, seed=1, with_allies=True):
    e = eng(seed)
    state, line = e.start(st, "d20", foes or [{"name": "Rat", "hp": 50, "ac": 30, "attack_bonus": -9, "damage": "1", "init_bonus": -9}],
                          allies=party.allies(st, normalize_scenario(CARD)) if with_allies else [], grid={"w": 12, "h": 8})
    return e, state


def who(state, name):
    return next(c for c in state["combat"]["combatants"] if c["name"] == name)


class DeathSaveTests(unittest.TestCase):
    def test_healer_heals_lowest_first(self):
        st = party_state()
        e, state = fight(st)
        me, pip = who(state, "Aster"), who(state, "Pip Thistledown")
        me["hp"], me["dying"], me["death"] = 0, True, {"ok": 0, "fail": 0}
        pip["hp"] = 2
        dorna = who(state, "Dorna Ironhand")
        line = e._companion_heal(state["combat"], dorna)
        self.assertIn("Aster", line)
        self.assertGreater(me["hp"], 0)
        self.assertFalse(me.get("dying"))
        self.assertEqual(dorna["heals_left"], 1)

    def test_heals_run_out(self):
        st = party_state()
        e, state = fight(st)
        dorna, pip = who(state, "Dorna Ironhand"), who(state, "Pip Thistledown")
        dorna["heals_left"] = 0
        pip["hp"] = 1
        self.assertEqual(e._companion_heal(state["combat"], dorna), "")

    def test_drop_to_zero_means_dying(self):
        st = party_state()
        e, state = fight(st)
        me = who(state, "Aster")
        line = e._hurt(state["combat"], me, 99)
        self.assertTrue(me["dying"])
        self.assertIn("dying", line)
        self.assertTrue(state["combat"]["active"])
        self.assertEqual(e._finished(state["combat"]), "")  # the companions still stand

    def test_three_failures_dead_and_nat20_back_up(self):
        st = party_state()
        e, state = fight(st)
        me = who(state, "Aster")
        me.update(hp=0, dying=True, death={"ok": 0, "fail": 2})
        e.dice.roll = lambda expr: type("R", (), {"natural": 5, "total": 5, "terms": []})()
        e._death_save(state["combat"], me)
        self.assertTrue(me["dead"])
        me.update(hp=0, dying=True, dead=False, death={"ok": 0, "fail": 0})
        e.dice.roll = lambda expr: type("R", (), {"natural": 20, "total": 20, "terms": []})()
        e._death_save(state["combat"], me)
        self.assertEqual((me["hp"], me["dying"]), (1, False))

    def test_hit_while_dying_is_a_failure(self):
        st = party_state()
        e, state = fight(st)
        me = who(state, "Aster")
        me.update(hp=0, dying=True, death={"ok": 0, "fail": 0})
        e._hurt(state["combat"], me, 3)
        self.assertEqual(me["death"]["fail"], 1)
        e._hurt(state["combat"], me, 3, crit=True)
        self.assertEqual(me["death"]["fail"], 3)
        self.assertTrue(me["dead"])

    def test_alone_and_down_ends_the_fight_with_saves_rolled(self):
        st = party_state("solo")
        e, state = fight(st, with_allies=False)
        me = who(state, "Aster")
        e._hurt(state["combat"], me, 99)
        self.assertEqual(e._finished(state["combat"]), "you have fallen")
        line = e._fall_out(state["combat"], me)
        self.assertTrue(me.get("stable") or me.get("dead"))
        self.assertTrue("stable" in line or "dies" in line)


    def test_won_while_dying_means_stabilized(self):
        st = party_state()
        e, state = fight(st, foes=[{"name": "Rat", "hp": 1, "ac": 1, "init_bonus": -9}])
        me, rat = who(state, "Aster"), who(state, "Rat")
        me.update(hp=0, dying=True, death={"ok": 0, "fail": 1})
        rat["hp"] = 0
        state, text = e._wrap(state, ["(the companions finish the rat)"], state["combat"]["round"])
        self.assertIn("stabilize", text)
        self.assertEqual(state["player"]["hp"]["current"], 1)



class GameTests(unittest.TestCase):
    def test_rests_heal_companions(self):
        from app import resources
        st = party_state()
        st["party"]["Faelar Quickbow"]["hp"] = 2
        st["party"]["Pip Thistledown"]["hp"] = 0
        back = resources.regenerate(st, "short_rest")
        self.assertEqual(st["party"]["Faelar Quickbow"]["hp"], 2 + 6)   # half of 11, rounded up
        self.assertEqual(st["party"]["Pip Thistledown"]["hp"], 5)       # half of 9, rounded up
        self.assertTrue(any("Faelar" in b for b in back))
        resources.regenerate(st, "long_rest")
        self.assertEqual(st["party"]["Faelar Quickbow"]["hp"], 11)

    def test_prompt_lists_companions(self):
        st = party_state()
        npcs = [{"name": "Dorna Ironhand", "personality": "gruff", "speech_style": "short", "relationship": 5}]
        text = party.prompt_section(st, npcs, normalize_scenario(CARD))
        self.assertIn("Dorna Ironhand", text)
        self.assertIn("healer", text)
        self.assertIn("never speak, think or decide for the player", text)
        self.assertEqual(party.prompt_section(party_state("solo"), npcs, normalize_scenario(CARD)), "")
        self.assertIn("Dorna Ironhand 10/10", party.state_line(st))

    def test_solo_game_has_no_companion_rows(self):
        from tests.test_core import make_services
        s = make_services()
        card = s.scenarios.create(CARD)
        solo = s.conversations.create(card, party_mode="solo")
        names = {n["name"] for n in s.conversations.list_npcs(solo["id"])}
        self.assertNotIn("Dorna Ironhand", names)
        self.assertIn("Sildar Hallwinter", names)
        self.assertEqual(s.conversations.get_state(solo["id"])["party_mode"], "solo")
        both = s.conversations.create(card)  # no choice given: a card with companions plays with them
        self.assertIn("Dorna Ironhand", {n["name"] for n in s.conversations.list_npcs(both["id"])})
        self.assertEqual(s.conversations.get_state(both["id"])["party"]["Pip Thistledown"]["hp"], 9)



class RestartAndDraftTests(unittest.TestCase):
    def test_restart_keeps_party_mode(self):
        from tests.test_core import make_services
        s = make_services()
        card = s.scenarios.create(CARD)
        for mode in ("solo", "companions"):
            conv = s.conversations.create(card, party_mode=mode)
            st = s.conversations.get_state(conv["id"])
            if mode == "companions":
                st["party"]["Pip Thistledown"]["hp"] = 1
                s.conversations.save_state(conv["id"], st)
            new = s.conversations.restart(conv["id"], s.scenarios.get(card["id"]), keep=False)
            nst = s.conversations.get_state(new["id"])
            self.assertEqual(nst["party_mode"], mode)
            if mode == "companions":
                self.assertEqual(nst["party"]["Pip Thistledown"]["hp"], 9)

    def test_parse_draft_caps_and_normalizes(self):
        raw = """{"companions": [
          {"name": "Dorna", "class": "Cleric", "role": "healer", "personality": "gruff", "speech_style": "short", "hp": 10},
          {"name": "Faelar", "role": "archer"}, {"name": "Pip", "role": "rogue"}, {"name": "Too many", "role": "fighter"},
          {"name": "", "role": "fighter"}]}"""
        got = party.parse_draft(raw)
        self.assertEqual([c["name"] for c in got], ["Dorna", "Faelar", "Pip"])
        self.assertTrue(all(c["companion"] for c in got))
        self.assertEqual(got[0]["sheet"]["heal"], "1d8+3")
        self.assertEqual(got[0]["sheet"]["class"], "Cleric")
        self.assertEqual(party.parse_draft("not json"), [])


    def test_one_death_save_per_round(self):
        st = party_state()
        e, state = fight(st, foes=[{"name": "Ogre", "hp": 200, "ac": 30, "attack_bonus": -9, "damage": "1", "init_bonus": -9}])
        me = who(state, "Aster")
        me.update(hp=0, dying=True, death={"ok": 0, "fail": 0})
        who(state, "Dorna Ironhand")["heals_left"] = 0  # nobody can heal: the saves go on
        state["combat"]["turn"] = state["combat"]["order"].index(me["id"])
        e.dice.roll = lambda expr: type("R", (), {"natural": 12, "total": 12, "terms": [], "mode": "", "crit": False, "fumble": False})()
        lines = e._others_until_player(state["combat"])
        self.assertEqual(sum("death save" in x for x in lines), 1)
        state, text = e.enemies_act(state)  # "Others act": the next round, with the next save
        self.assertEqual(text.count("death save"), 1)
        self.assertEqual(me["death"]["ok"], 2)


if __name__ == "__main__":
    unittest.main()
