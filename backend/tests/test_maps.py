"""Tests for battle maps and terrain rules."""
import random
import unittest

from app.combat import CombatEngine, CombatError, suggest_fight
from app.dice import DiceRoller
from app.maps import TYPES, MapError, clean_tiles, generate, has_cover, largest_region, open_cells, path_step
from tests.test_combat import GOBLINS, tough
from tests.test_core import FakeLLM, make_services


class GeneratorTests(unittest.TestCase):
    def test_every_type_is_connected_and_sized(self):
        for kind in TYPES:
            for seed in range(5):
                tiles = generate(kind, 14, 9, seed=seed, features=["rocks", "barrels"])
                self.assertEqual((len(tiles), len(tiles[0])), (9, 14), kind)
                cells = open_cells(tiles)
                region = largest_region([list(r) for r in tiles])
                walkable = sum(1 for r in tiles for ch in r if ch in '.,"D:')
                self.assertEqual(len(region), walkable, f"{kind} seed {seed} has unreachable pockets")
                self.assertGreaterEqual(len(cells), 12, kind)

    def test_same_seed_same_map(self):
        self.assertEqual(generate("cave", 12, 8, seed=7), generate("cave", 12, 8, seed=7))

    def test_clean_tiles(self):
        self.assertEqual(clean_tiles(["#x#", "."], 6, 4), ["#.#...", "......", "......", "......"])
        with self.assertRaises(MapError):
            clean_tiles([])


class TerrainRuleTests(unittest.TestCase):
    MAP = ["............",
           "....R.......",
           "....R.......",
           "....R.......",
           '..........".',
           "............"]

    def test_cover(self):
        self.assertTrue(has_cover(self.MAP, 1, 2, 8, 2))       # rock between
        self.assertFalse(has_cover(self.MAP, 1, 5, 8, 5))      # open line
        self.assertTrue(has_cover(self.MAP, 1, 4, 10, 4))      # target in bushes

    def test_path_goes_around(self):
        end = path_step(self.MAP, (1, 2), (8, 2), set(), 30)
        self.assertLessEqual(max(abs(end[0] - 8), abs(end[1] - 2)), 1)
        self.assertNotIn(self.MAP[end[1]][end[0]], "R#~TB")

    def test_combat_on_a_map(self):
        eng = CombatEngine(DiceRoller(random.Random(2)), random.Random(2))
        tiles = generate("forest", 12, 8, seed=4)
        state, _ = eng.start(tough(), "d20", GOBLINS, battle_map={"tiles": tiles, "name": "Woods"})
        c = state["combat"]
        self.assertEqual(c["grid"]["tiles"], tiles)
        for f in c["combatants"]:
            self.assertIn(tiles[f["y"]][f["x"]], '.,"D')               # nobody starts inside a tree
        blocked_spot = next((x, y) for y, row in enumerate(tiles) for x, ch in enumerate(row) if ch == "T")
        me = next(f for f in c["combatants"] if f["side"] == "player")
        with self.assertRaises(CombatError):
            eng.edit(state, me["id"], x=blocked_spot[0], y=blocked_spot[1])
        target = next(f for f in c["combatants"] if f["side"] == "enemy")
        state, line = eng.player_action(state, "attack", target["id"])
        self.assertIn("**Kaela attacks", line)


class SuggestAndLibraryTests(unittest.IsolatedAsyncioTestCase):
    async def test_suggest_fight_picks_a_map(self):
        llm = FakeLLM()
        llm.summary = ('{"enemies": [{"name": "Archer", "count": 2, "hp": 9, "ac": 12, "attack_bonus": 4, "damage": "1d8+2", "range": 16}],'
                       ' "map": {"type": "forest", "features": ["rocks", "lava"]}}')
        got = await suggest_fight(llm, "d20", "Archers hide in the trees.")
        self.assertEqual(got["map"], {"type": "forest", "features": ["rocks"]})
        self.assertEqual(got["enemies"][0]["range"], 16)
        llm.summary = '{"enemies": [{"name": "Thug"}], "map": {"type": "moon"}}'
        self.assertEqual((await suggest_fight(llm, "d20", "x"))["map"]["type"], "field")

    async def test_map_library(self):
        s = make_services(FakeLLM())
        m = s.maps.save({"name": "Crypt", "tiles": ["######", "#....#", "#....#", "######"], "background": "javascript:alert(1)"})
        self.assertEqual((m["w"], m["h"], m["background"]), (6, 4, ""))
        m2 = s.maps.save({"name": "Crypt 2", "tiles": m["tiles"], "background": "/api/uploads/abc.png"}, m["id"])
        self.assertEqual((m2["name"], m2["background"]), ("Crypt 2", "/api/uploads/abc.png"))
        s.maps.delete(m["id"])
        self.assertEqual(s.maps.list(), [])


if __name__ == "__main__":
    unittest.main()
