import unittest

from app import adventure
from app.maps import TYPES, generate

try:
    from app import mappaint  # needs numpy and Pillow (the app's own Python has both)
except ImportError:
    mappaint = None


@unittest.skipIf(mappaint is None, "the painter needs numpy and Pillow")
class PaintTests(unittest.TestCase):
    def test_every_type_paints_a_lined_up_picture(self):
        import io
        from PIL import Image
        for kind in TYPES:
            tiles = generate(kind, 12, 8, 3)
            im = Image.open(io.BytesIO(mappaint.paint(tiles, kind, 3)))
            g = mappaint.geometry(tiles)
            self.assertEqual(im.size, (int(g["nat_w"]), int(g["nat_h"])))
            self.assertEqual(im.size, (12 * mappaint.PX, 8 * mappaint.PX))

    def test_road_has_a_road(self):
        self.assertTrue(any(":" in r for r in generate("road", 24, 16, 1)))

    def test_pick_kind(self):
        self.assertEqual(adventure.pick_kind({"name": "Goblin Ambush", "read_aloud": "the trail", "notes": ""}), "road")
        self.assertEqual(adventure.pick_kind({"name": "Cragmaw Hideout: Cave Mouth", "read_aloud": "", "notes": ""}), "cave")
        self.assertEqual(adventure.pick_kind({"name": "Stonehill Inn", "read_aloud": "", "notes": ""}), "tavern")
        self.assertEqual(adventure.pick_kind({"name": "Somewhere", "read_aloud": "", "notes": ""}), "field")

    def test_painted_map_becomes_the_scene_battle(self):
        adv = adventure.normalize_adventure({"scenes": [{"id": "amb", "name": "Goblin Ambush"}]})
        tiles = generate("road", 24, 16, 2)
        adv = adventure.add_painted_map(adv, "amb", "road", tiles, "/api/uploads/" + "a" * 40 + ".webp", mappaint.geometry(tiles))
        self.assertEqual(adv["scenes"][0]["map"], "painted-amb")
        b = adventure.battle_map(adv, {"adventure": {"scene": "amb"}})
        self.assertEqual((b["w"], b["h"]), (24, 16))
        self.assertTrue(b["painted"])
        self.assertEqual(b["tiles"], tiles)
        x, y = b["near"]
        self.assertEqual(tiles[y][x], ":")  # the scene starts on the road
        again = adventure.add_painted_map(adv, "amb", "road", tiles, "/api/uploads/" + "b" * 40 + ".webp", mappaint.geometry(tiles))
        self.assertEqual(len(again["maps"]), 1)  # repainting replaces


if __name__ == "__main__":
    unittest.main()
