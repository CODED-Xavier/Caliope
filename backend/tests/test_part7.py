import copy
import unittest

from app import sheets, statusbook
from app.cards import resolve_features
from app.state import DEFAULT_STATE
from tests.test_core import make_services


class SheetLibraryTests(unittest.TestCase):
    def test_every_template_parses_and_fills_known_fields_from_the_game(self):
        st = copy.deepcopy(DEFAULT_STATE)
        st["player"].update(level=4, ac=15, **{"class": "Rogue"})
        st["player"]["stats"]["DEX"] = 17
        for t in sheets.library():
            self.assertTrue(statusbook.PLACEHOLDER.search(t["text"]), t["id"])
            self.assertTrue(statusbook.render(t["text"], st, []).strip(), t["id"])
        dnd = statusbook.render(sheets.by_id("dnd5e")["text"], st, [])
        self.assertIn("Level: 4", dnd)
        self.assertIn("AC: 15", dnd)
        self.assertIn("Class: Rogue", dnd)
        self.assertIn("DEX: 17", dnd)
        t20 = statusbook.render(sheets.by_id("tormenta20")["text"], st, [])
        self.assertIn("DES: 17", t20)                                         # Tormenta20's Portuguese attributes
        self.assertIn("Nível: 4", t20)
        self.assertNotIn("STR", statusbook.custom_fields(sheets.by_id("dnd5e")["text"]))

    def test_a_lone_attribute_like_label_stays_the_cards_own_field(self):
        tpl = "INFO\n- Body: [Grade] [[X]/100]\n- INT: [Grade] [[X]/100]"
        self.assertEqual(statusbook.custom_fields(tpl), ["Body", "INT"])      # Lumencia's INT is a grade, not the stat

    def test_card_info_block_wins_over_a_picked_sheet(self):
        own = {"information": {"post_history": "Rules.\n\nINFO\nTier: [Tier]"}, "sheet_template": "HP: [HP]"}
        self.assertIn("Tier", statusbook.template_of(own))
        self.assertEqual(statusbook.template_of({"sheet_template": "Mood: [Mood]"}), "Mood: [Mood]")
        self.assertIsNone(statusbook.template_of({"sheet_template": "no placeholders"}))
        self.assertIn("status", resolve_features({"mode": "character", "sheet_template": "Mood: [Mood]"})["panels"])


class GameSheetTests(unittest.TestCase):
    def test_a_game_picks_its_sheet_without_changing_the_card(self):
        svc = make_services()
        sc = svc.scenarios.create({"name": "Plain", "mode": "gm_world", "opening_message": "Hello."})
        conv = svc.conversations.create(svc.scenarios.get(sc["id"]))
        svc.conversations.set_sheet_template(conv["id"], sheets.by_id("cthulhu7")["text"])
        snap = svc.conversations.get(conv["id"])["scenario"]
        self.assertIn("Sanity", statusbook.custom_fields(statusbook.template_of(snap)))
        self.assertFalse(svc.scenarios.get(sc["id"])["data"].get("sheet_template"))
        self.assertEqual(svc.scenarios.create({"name": "S", "sheet_template": "HP: [HP]"})["data"]["sheet_template"], "HP: [HP]")


if __name__ == "__main__":
    unittest.main()


BOOK = """Part 1: The Old Road

The Toll Bridge
p5
Read the following boxed text when the heroes arrive:

Rain drums on your hood as you reach a narrow stone bridge. A rusted chain blocks the way, and a hut leans beside it.

Three bandits are hiding in the hut. They demand ten silver pieces from anyone who wants to cross.
A character who succeeds on a DC 13 Wisdom (Insight) check sees that the bandits are bluffing about the crossbows.

Developments
If the heroes pay, the bandits let them pass. Award each character 50 XP for getting across.

Mill Ruins
The road ends at a ruined mill. The keyed areas follow.

1. Yard
Weeds choke the yard. You hear the creak of the broken wheel turning in the wind.

A character who searches finds tracks leading to area 2. A DC 12 Dexterity saving throw avoids the loose boards.

2. Cellar
Stairs lead down from the yard.

The cellar is cold and smells of old flour, damp stone and something much worse beneath the floor.

Grak the bugbear sleeps here with his pet wolf, Fang.

Treasure
A locked chest holds 40 gold pieces.

Roleplaying Mara
Mara is the miller's daughter, held by the bandits. She knows the bugbear's name.
"""


class AdventureSplitTests(unittest.TestCase):
    def test_a_book_becomes_parts_scenes_checks_enemies_and_npcs(self):
        from app import adventure
        r = adventure.split_adventure(BOOK)
        self.assertEqual(r["parts"][0]["title"], "The Old Road")
        names = [s["name"] for s in r["scenes"]]
        self.assertEqual(names, ["The Toll Bridge", "Mill Ruins", "1. Yard", "2. Cellar"])
        bridge, ruins, yard, cellar = r["scenes"]
        self.assertTrue(bridge["read_aloud"].startswith("Rain drums on your hood"))
        self.assertNotIn("Read the following", bridge["read_aloud"])
        self.assertEqual(bridge["enemies"][0]["name"], "Bandit")
        self.assertEqual(bridge["enemies"][0]["count"], 3)
        self.assertEqual(bridge["enemies"][0]["hp"], 11)                     # SRD numbers
        self.assertEqual(bridge["checks"][0]["skill"], "Wisdom (Insight)")
        self.assertEqual(bridge["checks"][0]["dc"], 13)
        self.assertEqual(bridge["xp"], 50)
        self.assertIn("Developments:", bridge["notes"])
        self.assertEqual(yard["group"], "Mill Ruins")
        self.assertEqual(yard["checks"][0]["skill"], "Dexterity save")
        self.assertEqual(yard["leads"], [cellar["id"]])
        self.assertTrue(cellar["read_aloud"].startswith("The cellar is cold"))  # boxed text without "you"
        self.assertEqual({e["name"] for e in cellar["enemies"]}, {"Grak", "Fang"})
        self.assertEqual(next(e for e in cellar["enemies"] if e["name"] == "Fang")["hp"], 11)
        self.assertIn("40 gold", cellar["treasure"])
        self.assertEqual(ruins["enemies"], [])
        self.assertEqual(r["npcs"][0]["name"], "Mara")

    def test_merge_adds_maps_per_location_and_keeps_old_scenes(self):
        from app import adventure
        r = adventure.split_adventure(BOOK)
        adv = adventure.merge({}, r, title="Mill")
        self.assertEqual([m["name"] for m in adv["maps"]], ["Mill Ruins"])
        yard = next(s for s in adv["scenes"] if s["name"] == "1. Yard")
        self.assertEqual(yard["map"], adv["maps"][0]["id"])
        more = adventure.split_adventure("Part 2: Town\n\nThe Market\nStalls everywhere, and you smell bread.\n")
        adv2 = adventure.merge(adv, more)
        self.assertEqual(len(adv2["scenes"]), len(adv["scenes"]) + 1)
        self.assertEqual([p["title"] for p in adv2["parts"]], ["The Old Road", "Town"])


class AdventurePlayTests(unittest.IsolatedAsyncioTestCase):
    async def test_scenes_are_read_followed_and_fought(self):
        from app import adventure
        from tests.test_core import FakeLLM, collect
        llm = FakeLLM()
        s = make_services(llm)
        adv = adventure.merge({}, adventure.split_adventure(BOOK))
        adv["maps"][0].update(picture="/api/images/map.png", cols=30, rows=20)
        yard_id = next(x["id"] for x in adv["scenes"] if x["name"] == "1. Yard")
        cellar_id = next(x["id"] for x in adv["scenes"] if x["name"] == "2. Cellar")
        adv["maps"][0]["markers"] = {cellar_id: [0.5, 0.5]}
        sc = s.scenarios.create({"name": "Mill", "mode": "gm_world", "opening_message": "", "adventure": adv})
        cid = s.conversations.create(s.scenarios.get(sc["id"]))["id"]
        st = s.conversations.get_state(cid)
        self.assertEqual(st["adventure"]["scene"], adv["scenes"][0]["id"])
        self.assertEqual(st["adventure"]["fresh"], adv["scenes"][0]["id"])   # no opening: the first reply reads it

        await collect(s.engine.send(cid, "I walk up to the bridge."))
        last = llm.stream_calls[-1][-1]["content"]
        self.assertIn("Rain drums on your hood", last)
        self.assertIn("close to word for word", last)
        self.assertIn("Wisdom (Insight) DC 13", last)
        self.assertIn("3x Bandit", last)
        self.assertEqual(s.conversations.get_state(cid)["adventure"]["fresh"], "")
        await collect(s.engine.send(cid, "I look at the chain."))
        self.assertNotIn("close to word for word", llm.stream_calls[-1][-1]["content"])

        llm.analysis = {"location": "Mill Ruins yard"}
        await collect(s.engine.send(cid, "We follow the road to the mill."))
        st = s.conversations.get_state(cid)
        self.assertEqual(st["adventure"]["scene"], yard_id)                  # the tracker's place found the area
        llm.analysis = {}
        await collect(s.engine.send(cid, "I climb down into the cellar."))  # a way on, named by the player
        self.assertEqual(s.conversations.get_state(cid)["adventure"]["scene"], cellar_id)
        self.assertIn("The cellar is cold", llm.stream_calls[-1][-1]["content"])
        self.assertIn(cellar_id, s.conversations.get_state(cid)["adventure"]["visited"])

        st = s.conversations.get_state(cid)
        self.assertEqual({e["name"] for e in adventure.combat_enemies(adv, st)}, {"Grak", "Fang"})
        battle = adventure.battle_map(adv, st)
        self.assertEqual(battle["near"], [15, 10])
        state, _ = s.combat.start(st, "d20", adventure.combat_enemies(adv, st), grid={"w": 30, "h": 20},
                                  battle_map={"background": battle["background"]}, near=battle["near"])
        foes = [c for c in state["combat"]["combatants"] if c["side"] == "enemy"]
        self.assertTrue(all(abs(c["x"] - 15) + abs(c["y"] - 10) <= 2 for c in foes))
        self.assertEqual(state["combat"]["grid"]["w"], 30)

    def test_state_keeps_the_adventure_and_route_progress_when_the_sheet_is_edited(self):
        from app.state import normalize_state
        st = copy.deepcopy(DEFAULT_STATE)
        st["adventure"] = {"scene": "a", "visited": ["a"], "xp_given": [], "fresh": ""}
        st["script"] = {"next": 2}
        out = normalize_state(st)
        self.assertEqual(out["adventure"]["scene"], "a")
        self.assertEqual(out["script"]["next"], 2)
