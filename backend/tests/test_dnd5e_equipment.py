"""Starting equipment: the class's and background's packages (or the class's starting gold), and a shop at the
Library's prices to spend it."""
import unittest
from pathlib import Path

from app.dnd5e import equipment as eq
from app.dnd5e.character import derive, new_character
from app.dnd5e.library import Library
from app.dnd5e.store import apply_change

SEED = Path(__file__).resolve().parents[1] / "app/seed/srd5e.json"


def srd():
    lib = Library([SEED])
    lib.load()
    return lib


def fighter(lib, edition="2014"):
    c = new_character(edition)
    src = "PHB" if edition == "2014" else "XPHB"
    c["cls"] = {"name": "Fighter", "source": src}
    c["background"] = {"name": "Acolyte", "source": src}
    return c


class OptionTests(unittest.TestCase):
    def setUp(self):
        self.lib = srd()

    def test_2014_fighter(self):
        opt = eq.starting_options(self.lib, fighter(self.lib))
        cls = opt["class"]
        self.assertEqual(len(cls["groups"]), 4)
        first = cls["groups"][0]["choices"]
        self.assertEqual([c["key"] for c in first], ["a", "b"])
        self.assertEqual(first[0]["items"][0]["name"], "Chain Mail")
        pick = cls["groups"][1]["choices"][0]["items"][0]
        self.assertEqual(pick["pick"], "weaponMartial")
        self.assertIn("Longsword", [x["name"] for x in pick["candidates"]])
        self.assertEqual(cls["gold"], {"dice": "5d4", "times": 10, "average": 125, "max": 200})
        bg = opt["background"]
        self.assertTrue(any(i.get("cp") == 1500 for i in bg["groups"][0]["fixed"]))  # a pouch with 15 gp

    def test_2024_packages(self):
        opt = eq.starting_options(self.lib, fighter(self.lib, "2024"))
        keys = [c["key"] for c in opt["class"]["groups"][0]["choices"]]
        self.assertEqual(keys, ["A", "B", "C"])
        c = opt["class"]["groups"][0]["choices"][2]
        self.assertEqual(c["items"], [{"label": "155 gp", "cp": 15500, "qty": 1}])


class ApplyTests(unittest.TestCase):
    def setUp(self):
        self.lib = srd()

    def test_packages_then_shop(self):
        c = fighter(self.lib)
        c = apply_change(c, {"op": "start_gear", "choice": {
            "class": {"g0": "a", "g1": "a", "g2": "b", "g3": "b"}, "class_picks": {"g1.a.0": "Longsword|PHB"},
            "background": {"g1": "a"}}}, self.lib)
        names = [i["name"] for i in c["items"]]
        self.assertIn("Chain Mail", names)
        self.assertIn("Longsword", names)
        self.assertIn("Shield", names)
        hand = next(i for i in c["items"] if i["name"] == "Handaxe")
        self.assertEqual(hand["qty"], 2)
        self.assertEqual(c["cp"], 1500)
        self.assertEqual(derive(c, self.lib)["coins"]["gp"], 15)
        c = apply_change(c, {"op": "buy", "name": "Dagger", "source": "PHB", "qty": 2}, self.lib)  # 2 gp each
        self.assertEqual(c["cp"], 1100)
        with self.assertRaises(ValueError):
            apply_change(c, {"op": "buy", "name": "Plate Armor", "source": "PHB"}, self.lib)  # 1500 gp
        i = next(n for n, it in enumerate(c["items"]) if it["name"] == "Dagger")
        c = apply_change(c, {"op": "refund", "index": i}, self.lib)
        self.assertEqual(c["cp"], 1500)
        again = apply_change(c, {"op": "start_gear", "choice": {"class": {"g0": "b", "g1": "b", "g2": "a", "g3": "a"},
                                                                    "class_picks": {"g1.b.0": "Greataxe|PHB"}, "background": {"g1": "b"}}}, self.lib)
        self.assertNotIn("Chain Mail", [i["name"] for i in again["items"]])  # the old package is replaced
        self.assertEqual(again["cp"], 1500)

    def test_gold_instead(self):
        c = apply_change(fighter(self.lib), {"op": "start_gear", "choice": {"class_gold": 130, "background": {"g1": "a"}}}, self.lib)
        self.assertEqual(c["cp"], 13000 + 1500)
        self.assertFalse(any(i.get("from") == "start" and i["name"] == "Chain Mail" for i in c["items"]))
        with self.assertRaises(ValueError):
            apply_change(fighter(self.lib), {"op": "start_gear", "choice": {"class_gold": 999}}, self.lib)  # 5d4 x 10 tops at 200


if __name__ == "__main__":
    unittest.main()
