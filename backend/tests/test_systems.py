"""A card's own sheet kept by the app (Black Sheep: Pilot Level, XP, Credits, a mech loadout with Frame Points, weights
and modifiers), read from the card's lorebook, filled on the start screen and kept up to date in play."""
import json
import unittest
from pathlib import Path

from app import systems as sy
from tests.test_core import FakeLLM, collect, make_services, new_game

ARMS = ("ARM FRAMES (fit either arm). Format: name, PF, weight, effect, [unlock level, source, price].\n"
        "Restored original arm: 1 PF, Medium, no modifier [Lise's workshop, Moderate]. Léon's reinforced arm: 2 PF, Heavy, "
        "Melee +1, Handling -1 [starting part]. Light servo arm: 2 PF, Light, Handling +1, cannot hold Heavy weapons [city market, "
        "Cheap]. Hydraulic brawler arm: 4 PF, Heavy, Melee +2, Handling -1 [Lv4, city market, Expensive].\n"
        "ARM WEAPONS (Light 2 / Medium 4 / Heavy 6 damage). Hand's mace: 3 PF, Heavy, short; Melee +1, Handling -1 [starting]. "
        "War sword: 2 PF, Medium, short, no modifier [city market, Cheap]. Long rifle (two-handed): 5 PF, Heavy, long; Artillery +1, "
        "Handling -1 [Lv4, duel wagers, Expensive].")
LEGS = ("LEGS. Original manual legs: 1 PF, Heavy, Endurance +1, Handling -1 [starting]. Sprinter legs: 3 PF, Light, Handling +2, "
        "Endurance -1 [Lv3, market, Moderate].\nTHRUSTERS. Outdated war-era thrusters: 2 PF, Medium, Handling -1 [starting]. "
        "Overhauled thrusters: 2 PF, Medium, no modifier [Lise, Cheap].")
BACK = ("BACK SLOT holds ONE item: armor OR a back weapon/utility. ARMOR: None (tattered heraldic tabard): 0 PF [starting]. "
        "Reactive skirts: 1 PF, Light, -1 damage from short-range hits [market, Cheap].\nCOCKPIT (weightless, no speed effect). "
        "Original manual cockpit: 2 PF [starting]. Pilot harness: 1 PF, Endurance +1 [missions, Cheap].")


def black_sheep() -> dict:
    """The sheet as the reader builds it from Black Sheep's entries (catalog parsed, the rest stated)."""
    catalog = sy.parse_catalog("\n".join([ARMS, LEGS, BACK]), ["Handling", "Melee", "Artillery", "Endurance"])
    catalog.append({"name": "Torn left arm", "kind": "arm", "cost": 0, "weight": "", "mods": {"Handling": -1}, "level": 0,
                    "effect": "cannot hold a weapon", "start": True})
    return sy.normalize({
        "stats": [{"key": "Pilot Level", "kind": "number", "min": 1, "max": 10, "start": 1},
                  {"key": "XP", "kind": "number", "min": 0, "max": 30, "start": 0},
                  {"key": "Credits", "kind": "number", "min": 0, "start": 0},
                  {"key": "Tier", "kind": "choice", "options": ["Relic", "Restored", "Reborn"], "start": "Relic"},
                  {"key": "Integrity", "kind": "number", "min": 0, "start": 22}],
        "levels": {"xp": "XP", "level": "Pilot Level", "at": [0, 3, 6, 9, 12, 15, 18, 21, 24, 27]},
        "loadout": {"name": "Brise-Lames", "points": "Frame Points", "tier": "Tier", "budgets": {"Relic": 10, "Restored": 20, "Reborn": 30},
                    "mods": ["Handling", "Melee", "Artillery", "Endurance"], "level_stat": "Pilot Level",
                    "slots": [{"key": "Left arm", "accepts": ["arm"], "start": "Torn left arm"},
                              {"key": "Right arm", "accepts": ["arm"], "start": "Léon's reinforced arm"},
                              {"key": "Right-arm weapon", "accepts": ["arm weapon"], "start": "Hand's mace"},
                              {"key": "Legs", "accepts": ["legs"], "start": "Original manual legs"},
                              {"key": "Thrusters", "accepts": ["thrusters"], "start": "Outdated war-era thrusters"},
                              {"key": "Back", "accepts": ["armor", "back weapon"], "start": "None (tattered heraldic tabard)"},
                              {"key": "Cockpit", "accepts": ["cockpit"], "start": "Original manual cockpit"}],
                    "catalog": catalog,
                    "speed": {"weight": "Heavy", "bands": [[1, "Fast"], [3, "Average"], [99, "Slow"]]},
                    "derived": [{"stat": "Integrity", "base": 20, "per": {"Endurance": 2}}]},
    })


class CatalogTests(unittest.TestCase):
    def test_parse_parts(self):
        cat = {c["name"]: c for c in sy.parse_catalog(ARMS + "\n" + LEGS, ["Handling", "Melee", "Artillery", "Endurance"])}
        arm = cat["Léon's reinforced arm"]
        self.assertEqual((arm["kind"], arm["cost"], arm["weight"], arm["mods"], arm["level"], arm["start"]),
                         ("arm", 2, "Heavy", {"Melee": 1, "Handling": -1}, 0, True))
        self.assertEqual(cat["Hydraulic brawler arm"]["level"], 4)
        self.assertEqual(cat["Hydraulic brawler arm"]["price"], "Expensive")
        self.assertEqual(cat["Hand's mace"]["kind"], "arm weapon")
        self.assertEqual(cat["Long rifle (two-handed)"]["mods"], {"Artillery": 1, "Handling": -1})
        self.assertEqual(cat["Sprinter legs"]["kind"], "legs")
        self.assertEqual(cat["Overhauled thrusters"]["kind"], "thrusters")
        self.assertIn("cannot hold Heavy weapons", cat["Light servo arm"]["effect"])

    def test_back_and_cockpit(self):
        cat = {c["name"]: c for c in sy.parse_catalog(BACK, ["Handling", "Endurance"])}
        self.assertEqual(cat["None (tattered heraldic tabard)"]["kind"], "armor")
        self.assertEqual(cat["Original manual cockpit"]["kind"], "cockpit")
        self.assertEqual(cat["Pilot harness"]["mods"], {"Endurance": 1})


class SheetTests(unittest.TestCase):
    def test_start_matches_the_card(self):
        sys = black_sheep()
        st = sy.start_state(sys)
        got = sy.compute(sys, st)
        self.assertEqual((got["used"], got["budget"]), (10, 10))
        self.assertEqual(got["mods"], {"Handling": -5, "Melee": 2, "Artillery": 0, "Endurance": 1})
        self.assertEqual((got["heavy"], got["speed"]), (3, "Average"))
        self.assertEqual(got["max"]["Integrity"], 22)

    def test_parts_must_fit(self):
        sys = black_sheep()
        st = sy.start_state(sys)
        self.assertIn("Level 4", sy.set_part(sys, st, "Right arm", "Hydraulic brawler arm"))
        self.assertIn("arm", sy.set_part(sys, st, "Legs", "War sword"))
        self.assertIn("Not owned", sy.set_part(sys, st, "Thrusters", "Overhauled thrusters"))
        sy.gain(sys, st, "Overhauled thrusters")
        sy.gain(sys, st, "Reactive skirts")
        self.assertIn("Frame Points", sy.set_part(sys, st, "Back", "Reactive skirts"))  # 11 of 10
        self.assertEqual(sy.set_part(sys, st, "Thrusters", "Overhauled thrusters"), "")
        self.assertEqual(sy.compute(sys, st)["mods"]["Handling"], -4)
        st["values"]["Tier"] = "Restored"
        self.assertEqual(sy.set_part(sys, st, "Back", "Reactive skirts"), "")
        self.assertEqual(sy.compute(sys, st)["budget"], 20)

    def test_xp_raises_the_level(self):
        sys = black_sheep()
        st = sy.start_state(sys)
        lines = sy.apply_changes(sys, st, [{"stat": "XP", "delta": 4}, {"stat": "Credits", "delta": 100},
                                          {"stat": "Integrity", "delta": -30}, {"stat": "Nope", "delta": 3}])
        self.assertEqual(st["values"]["XP"], 4)
        self.assertEqual(st["values"]["Pilot Level"], 2)
        self.assertEqual(st["values"]["Integrity"], 0)
        self.assertIn("Pilot Level 2 (level up!)", lines)
        sy.apply_changes(sys, st, [{"stat": "Integrity", "delta": 99}])
        self.assertEqual(st["values"]["Integrity"], 22)  # never above the frame's maximum

    def test_prompt_line(self):
        sys = black_sheep()
        text = sy.prompt_text(sys, sy.start_state(sys))
        self.assertIn("Frame Points 10/10", text)
        self.assertIn("Handling -5", text)
        self.assertIn("Speed Average", text)
        self.assertIn("Hand's mace", text)


class GameTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_game_with_its_sheet_and_tracker(self):
        llm = FakeLLM()
        s = make_services(llm)
        base = s.conversations.get(new_game(s, systems=black_sheep()))
        card = s.scenarios.get(base["scenario_id"])
        self.assertTrue(card["data"]["systems"]["loadout"]["catalog"])
        mine = sy.start_state(card["data"]["systems"])
        mine["loadout"]["Thrusters"] = "Overhauled thrusters"
        mine["loadout"]["Right arm"] = "Hydraulic brawler arm"  # level 4: refused, the card's part stays
        cid = s.conversations.create(card, systems_state=mine)["id"]
        st = s.conversations.get_state(cid)
        self.assertEqual(st["systems"]["loadout"]["Thrusters"], "Overhauled thrusters")
        self.assertEqual(st["systems"]["loadout"]["Right arm"], "Léon's reinforced arm")
        llm.analysis = {"system_changes": [{"stat": "XP", "delta": 2}, {"stat": "Credits", "delta": 100}]}
        await collect(s.engine.send(cid, "I win the duel."))
        st = s.conversations.get_state(cid)
        self.assertEqual(st["systems"]["values"]["XP"], 2)
        self.assertEqual(st["systems"]["values"]["Credits"], 100)
        prompt = "\n".join(m["content"] for m in llm.stream_calls[-1])
        self.assertIn("Frame Points", prompt)


class RealCardTest(unittest.TestCase):
    def test_reader_on_the_real_card_if_present(self):
        path = Path("/mnt/user-data/attachments/78a3ceb0-00e5-5eee-96cf-73f136ce9010/d583c808-Black_sheep.json")
        if not path.exists():
            self.skipTest("Black Sheep's card file is not here")
        book = json.loads(path.read_text())["data"]["character_book"]["entries"]
        text = "\n".join(e["content"] for e in book)
        cat = sy.parse_catalog(text, ["Handling", "Melee", "Artillery", "Endurance"])
        self.assertGreaterEqual(len(cat), 45)


if __name__ == "__main__":
    unittest.main()
