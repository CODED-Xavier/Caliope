"""The 5e library: 5e.tools text, loading the SRD pack and the user's files, search by edition."""
import json
import tempfile
import unittest
from pathlib import Path

from app.dnd5e.text import render, strip_tags


class TextTests(unittest.TestCase):
    def test_strip_tags(self):
        self.assertEqual(strip_tags("regain {@dice 1d10} + level"), "regain 1d10 + level")
        self.assertEqual(strip_tags("cast {@spell fireball|PHB}"), "cast fireball")
        self.assertEqual(strip_tags("{@atk mw} {@hit 5} to hit. {@h}7 ({@damage 1d8+3})"), "Melee Weapon Attack: +5 to hit. Hit: 7 (1d8+3)")
        self.assertEqual(strip_tags("a {@dc 13} save"), "a DC 13 save")
        self.assertEqual(strip_tags("{@item longsword|phb|a fine sword}"), "a fine sword")
        self.assertEqual(strip_tags("{@condition prone|XPHB}"), "prone")

    def test_render_nested(self):
        text = render(["Intro.", {"type": "list", "items": ["One", "Two"]},
                       {"type": "entries", "name": "Second Wind", "entries": ["Heal {@dice 1d10}."]}])
        self.assertIn("Intro.", text)
        self.assertIn("• One", text)
        self.assertIn("Second Wind: Heal 1d10.", text)


def write(folder: Path, name: str, data) -> Path:
    path = folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return path


FIGHTER = {"class": [{"name": "Fighter", "source": "PHB", "srd": True, "hd": {"number": 1, "faces": 10}},
                     {"name": "Fighter", "source": "XPHB", "edition": "one", "hd": {"number": 1, "faces": 10}}],
           "classFeature": [{"name": "Second Wind", "source": "PHB", "srd": True, "className": "Fighter", "classSource": "PHB", "level": 1,
                             "entries": ["Regain {@dice 1d10} + your fighter level."]},
                            {"name": "Action Surge", "source": "PHB", "className": "Fighter", "classSource": "PHB", "level": 2, "entries": ["One more action."]}],
           "subclass": [{"name": "Champion", "shortName": "Champion", "source": "PHB", "className": "Fighter", "classSource": "PHB", "srd": True}]}
SPELLS = {"spell": [{"name": "Fireball", "source": "PHB", "level": 3, "srd": True, "entries": ["Boom {@damage 8d6}."]},
                    {"name": "Fireball", "source": "XPHB", "level": 3, "entries": ["Boom again."]},
                    {"name": "Shield", "source": "PHB", "level": 1, "entries": ["+5 AC."]}]}


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def lib(self, *folders):
        from app.dnd5e.library import Library
        lib = Library(list(folders))
        return lib, lib.load()

    def test_loads_types_and_editions(self):
        from app.dnd5e.library import edition_of
        write(self.dir, "Classes/class-fighter.json", FIGHTER)
        lib, info = self.lib(self.dir)
        self.assertEqual(info["errors"], [])
        self.assertEqual(info["files"], 1)
        self.assertEqual(edition_of(FIGHTER["class"][1]), "2024")
        self.assertEqual(edition_of({"source": "XPHB"}), "2024")
        self.assertEqual(edition_of(FIGHTER["class"][0]), "2014")
        feats = lib.search("classFeature", "", "2014")
        self.assertEqual([f["name"] for f in feats], ["Second Wind", "Action Surge"])
        self.assertEqual((feats[0]["level"], feats[0]["class"]), (1, "Fighter"))
        self.assertIn("1d10", feats[0]["summary"])

    def test_search_by_name_and_edition(self):
        write(self.dir, "Spells/spells-phb.json", SPELLS)
        lib, _ = self.lib(self.dir)
        self.assertEqual([(x["name"], x["source"]) for x in lib.search("spell", "fire", "2014")], [("Fireball", "PHB")])
        self.assertEqual([x["source"] for x in lib.search("spell", "fire", "2024")], ["XPHB"])
        got = lib.get("spell", "PHB", "fireball")
        self.assertIn("8d6", got["text"])

    def test_bad_file_is_reported_not_fatal(self):
        write(self.dir, "Spells/spells-phb.json", SPELLS)
        write(self.dir, "Feats/feats.json", "{ not json")
        lib, info = self.lib(self.dir)
        self.assertEqual(len(info["errors"]), 1)
        self.assertIn("feats.json", info["errors"][0])
        self.assertEqual(len(lib.search("spell", "", "2014")), 2)

    def test_user_copy_wins_over_srd(self):
        pack = write(self.dir, "srd5e.json", {"_credit": "x", "spell": [{"name": "Fireball", "source": "PHB", "level": 3, "srd": True, "entries": ["SRD text."]}]})
        user = self.dir / "user"
        write(user, "Spells/spells-phb.json", SPELLS)
        lib, info = self.lib(pack, user)
        hits = lib.search("spell", "fireball", "2014")
        self.assertEqual(len(hits), 1)
        self.assertIn("8d6", lib.get("spell", "PHB", "Fireball")["text"])


class ExportTests(unittest.TestCase):
    def test_export_keeps_only_srd(self):
        from app.dnd5e.srd_export import export
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            write(d, "in/Classes/class-fighter.json", FIGHTER)
            write(d, "in/Spells/spells-phb.json", SPELLS)
            counts = export(d / "in", d / "srd5e.json")
            pack = json.loads((d / "srd5e.json").read_text(encoding="utf-8"))
            self.assertIn("Creative Commons", pack["_credit"])
            self.assertEqual([s["name"] for s in pack["spell"]], ["Fireball"])
            self.assertEqual([f["name"] for f in pack["classFeature"]], ["Second Wind"])
            self.assertEqual(counts["spell"], 1)
            self.assertNotIn("page", pack["spell"][0])


class CardSystemTests(unittest.TestCase):
    def test_card_system_normalized(self):
        from app.scenarios import normalize_scenario
        self.assertEqual(normalize_scenario({"name": "LMoP", "kind": "adventure"})["system"], "dnd5e-2014")
        self.assertEqual(normalize_scenario({"name": "X", "kind": "adventure", "system": "dnd5e-2024"})["system"], "dnd5e-2024")
        self.assertEqual(normalize_scenario({"name": "X", "kind": "adventure", "system": "nonsense"})["system"], "dnd5e-2014")
        self.assertEqual(normalize_scenario({"name": "Lumencia", "kind": "roleplay"})["system"], "")
