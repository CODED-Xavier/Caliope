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


class WikiResearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_find_list_read_and_build_a_card(self):
        from app import wikiresearch as W
        pages = {
            "Hero Saga": "'''Hero Saga''' is a series about a [[academy|magic academy]].\n== Plot ==\nStuff.",
            "Aya Kurogane": "{{Infobox|age=16}}\n'''Aya Kurogane''' is the [[protagonist]]. She wields a cursed blade.\n"
                            "== Appearance ==\nShort black hair.\n== Personality ==\nStubborn and kind.",
            "Sun Academy": "The '''Sun Academy''' is the school where sorcerers train.<ref>x</ref>",
        }
        calls = []

        async def fetch(url):
            calls.append(url)
            if "meta=siteinfo" in url:
                if "hero-saga.fandom" not in url:
                    raise OSError("no wiki")
                return {"query": {"general": {"sitename": "Hero Saga Wiki", "mainpage": "Hero Saga Wiki"}}}
            if "list=search" in url:
                return {"query": {"search": [{"title": "Hero Saga"}]}}
            if "list=categorymembers" in url:
                if "Characters" in url and "Main" not in url and "Female" not in url and "Male" not in url:
                    return {"query": {"categorymembers": [{"title": "Aya Kurogane"}, {"title": "List of characters"}]}}
                if "Locations" in url:
                    return {"query": {"categorymembers": [{"title": "Sun Academy"}]}}
                return {"query": {"categorymembers": []}}
            if "prop=info" in url:
                return {"query": {"pages": {"1": {"title": "Aya Kurogane", "length": 9000}, "2": {"title": "Sun Academy", "length": 3000}}}}
            if "action=parse" in url:
                from urllib.parse import unquote
                title = unquote(url.split("page=")[1].split("&")[0])
                return {"parse": {"wikitext": {"*": pages[title]}}}
            raise AssertionError(url)

        W.GAP = 0
        wiki = await W.find_wiki(fetch, "Hero Saga")
        self.assertEqual(wiki["api"], "https://hero-saga.fandom.com/api.php")
        self.assertEqual(wiki["work"], "Hero Saga")
        listed = await W.list_pages(fetch, wiki["api"])
        self.assertEqual([p["title"] for p in listed["characters"]], ["Aya Kurogane"])     # "List of..." skipped
        self.assertEqual([p["title"] for p in listed["lore"]], ["Sun Academy"])
        events = [e async for e in W.research(fetch, wiki["api"], wiki["sitename"], "Hero Saga", ["Aya Kurogane"], ["Sun Academy"])]
        card = events[-1]["card"]
        self.assertEqual(card["name"], "Hero Saga")
        self.assertIn("magic academy", card["world"])
        aya = card["npcs"][0]
        self.assertEqual(aya["name"], "Aya Kurogane")
        self.assertIn("cursed blade", aya["description"])
        self.assertEqual(aya["personality"], "Stubborn and kind.")
        self.assertNotIn("Infobox", aya["description"])
        names = [e["name"] for e in card["lorebook"]["entries"]]
        self.assertIn("Sun Academy", names)
        self.assertNotIn("<ref>", card["lorebook"]["entries"][0]["content"])
        self.assertIn("Aya Kurogane", events[-1]["notes"])
        from app.scenarios import normalize_scenario
        self.assertEqual(normalize_scenario(card)["npcs"][0]["name"], "Aya Kurogane")    # a valid card

    def test_nothing_found_explains_what_to_do(self):
        from app import wikiresearch as W
        with self.assertRaises(W.ResearchError):
            W.wiki_candidates("  ")


class MapGridTests(unittest.TestCase):
    def test_a_map_lined_up_with_its_squares_gives_the_battle_grid_and_fog(self):
        from app import adventure
        from app.combat import CombatEngine
        adv = adventure.normalize_adventure({
            "scenes": [{"name": "1. Yard", "map": "m"}, {"name": "2. Cellar", "map": "m"}],
            "maps": [{"id": "m", "name": "Mill", "picture": "/api/images/x.png", "markers": {"1-yard": [0.5, 0.5]},
                      "grid": {"size": 40, "ox": 10, "oy": 50, "nat_w": 2010, "nat_h": 1210}, "reveal": 5}]})
        m = adv["maps"][0]
        self.assertEqual(m["grid"]["oy"], 10)                                # offsets kept inside one square
        st = {"adventure": {"scene": "1-yard", "visited": ["1-yard"]}}
        b = adventure.battle_map(adv, st)
        self.assertEqual((b["w"], b["h"]), (50, 30))
        self.assertEqual(b["near"], [24, 14])                                # (1005-10)/40, (605-10)/40
        self.assertEqual(b["fog"][0]["r"], 5)
        self.assertAlmostEqual(b["fog"][0]["x"], 24.88, places=2)
        state, _ = CombatEngine().start({"player": {"name": "Me", "hp": {"current": 9, "max": 9}, "stats": {}}},
                                              "d20", [{"name": "Goblin", "count": 1}], grid={"w": b["w"], "h": b["h"]},
                                              battle_map=b, near=b["near"])
        grid = state["combat"]["grid"]
        self.assertEqual(grid["geom"]["size"], 40.0)
        self.assertEqual(len(grid["fog"]), 1)
        self.assertEqual((grid["w"], grid["h"]), (50, 30))


class ReputationTests(unittest.IsolatedAsyncioTestCase):
    def test_events_have_fixed_values_and_repeats_count_less(self):
        from app import reputation as R
        log = []
        self.assertEqual(R.delta_for("defended", "Lilia", log), 12)
        values = []
        for _ in range(4):
            d = R.delta_for("kind_words", "Lilia", log)
            values.append(d)
            R.remember({"rep_log": log}, "Lilia", "kind_words", d, "praised her")
        self.assertEqual(values, [4, 2, 1, 0])                              # compliments can't be farmed
        self.assertEqual(R.delta_for("kind_words", "Sera", log), 4)         # someone else: full value
        self.assertEqual(R.delta_for("nonsense", "Lilia", log), 0)
        self.assertEqual(R.level(-90)[0], "mortal enemy")
        self.assertEqual(R.level(55)[0], "close")
        self.assertIn("secrets", R.level(55)[1])
        self.assertIn("deeply bonded", R.scale_text())

    async def test_the_tracker_names_the_event_and_the_app_counts_it(self):
        from tests.test_core import FakeLLM, collect, new_game
        llm = FakeLLM()
        llm.analysis = {"relationship_changes": [{"npc": "Doran", "event": "defended", "reason": "stood up for Doran"}]}
        s = make_services(llm)
        cid = new_game(s, "gm_cast")
        events = await collect(s.engine.send(cid, "I stand between Doran and the thugs."))
        self.assertEqual(s.conversations.find_npc(cid, "Doran")["relationship"], 12)
        changes = " ".join(" ".join(e.get("changes") or []) for e in events if e["type"] == "state")
        self.assertIn("defended them", changes)
        await collect(s.engine.send(cid, "I stand up for Doran again."))
        self.assertEqual(s.conversations.find_npc(cid, "Doran")["relationship"], 18)   # 12 + 6 (a repeat)
        self.assertEqual(len(s.conversations.get_state(cid)["rep_log"]), 2)
        prompt = llm.stream_calls[-1][0]["content"]
        self.assertIn("Characters act by their level", prompt)


STATBLOCK = """# Appendix B: Monsters

# Cave Rat

___
>## Cave Rat
>*Small Beast, Unaligned*
>___
>- **Armor Class** 12 (natural armor)
>- **Hit Points** 9 (2d6 + 2)
>- **Speed** 30 ft.
>- **Initiative** +2 (12)
>___
>|STR|DEX|CON|INT|WIS|CHA|
>|:---:|:---:|:---:|:---:|:---:|:---:|
>|7 (-2)|15 (+2)|12 (+1)|2 (-4)|10 (+0)|4 (-3)|
>___
>- **Senses** Darkvision 30 ft., Passive Perception 10
>- **Challenge** 1/8 (XP 1.100; PB +2)
>___
>***Pack Tactics.*** The rat has advantage when an ally is near.
>
>### Actions
>***Bite.*** *Melee Weapon Attack:*  +4 to hit, reach 5 ft., one target. *Hit:* 4 (1d4 + 2) piercing damage.
"""

MDBOOK = """# Introduction

### Background
An old mine was lost.

# The Road

Read the boxed text when you're ready to start.

>>You walk the muddy road toward the hills.
>>
>>Crows watch you from the trees.
>>

### Rat Den

>>A low cave that smells of wet fur.
>>

Three cave rats are hiding here. Klarg will build a throne from your bones, says a goblin.

**Developments**

If the rats flee, award each character 25 XP.

#### 1. Burrow

>>A narrow burrow.
>>

#### Treasure

A copper ring.

# Appendix B: Monsters
"""


class BestiaryTests(unittest.TestCase):
    def test_stat_blocks_become_sheets_and_fights_use_them(self):
        import tempfile
        from pathlib import Path
        from app import bestiary as B
        found = B.parse_statblocks(STATBLOCK)
        self.assertEqual(len(found), 1)
        rat = found[0]
        self.assertEqual((rat["name"], rat["ac"], rat["hp"], rat["hp_dice"], rat["init_bonus"]), ("Cave Rat", 12, 9, "2d6+2", 2))
        self.assertEqual(rat["stats"]["DEX"], 15)
        self.assertEqual(rat["xp"], 1100)
        self.assertEqual(rat["actions"][0]["attack_bonus"], 4)
        self.assertEqual(rat["actions"][0]["damage"], "1d4+2")
        self.assertIn("Pack Tactics", rat["traits"])
        with tempfile.TemporaryDirectory() as d:
            book = B.Bestiary(Path(d))
            book.save(rat)
            self.assertTrue((Path(d) / "cave-rat.json").is_file())
            self.assertEqual(book.find("Cave Rats")["name"], "Cave Rat")
            enemies = book.enrich([{"name": "Cave Rats", "count": 3}, {"name": "Cave Rat", "hp": 20}, {"name": "Ghost"}])
            self.assertEqual((enemies[0]["hp"], enemies[0]["ac"], enemies[0]["attack_bonus"], enemies[0]["damage"]), (9, 12, 4, "1d4+2"))
            self.assertEqual(enemies[1]["hp"], 20)                                 # what the fight sets stays
            self.assertNotIn("hp", enemies[2])
            book.save({**rat, "name": "Big Cave Rat"}, old_id="cave-rat")          # renamed
            self.assertEqual([m["name"] for m in book.list()], ["Big Cave Rat"])


class MarkdownBookTests(unittest.TestCase):
    def test_a_markdown_book_uses_its_headings_and_boxes(self):
        from app import adventure
        r = adventure.split_adventure(MDBOOK)
        self.assertEqual([p["title"] for p in r["parts"]], ["The Road"])
        self.assertIn("old mine", r["background"])
        names = [s["name"] for s in r["scenes"]]
        self.assertEqual(names, ["The Road: the start", "Rat Den", "1. Burrow"])
        start, den, burrow = r["scenes"]
        self.assertEqual(start["read_aloud"], "You walk the muddy road toward the hills.\n\nCrows watch you from the trees.")
        self.assertEqual(den["read_aloud"], "A low cave that smells of wet fur.")      # the dialogue with "your" is not read aloud
        self.assertEqual(den["xp"], 25)
        self.assertIn("Developments:", den["notes"])
        self.assertIn("copper ring", burrow["treasure"])
        self.assertEqual(burrow["group"], "Rat Den")
