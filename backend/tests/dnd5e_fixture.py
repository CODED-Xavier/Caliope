"""A tiny 5e library in the real 5e.tools shapes, for the character engine tests."""
import json
import tempfile
from pathlib import Path

from app.dnd5e.library import Library

DATA = {
    "Classes/class-fighter.json": {
        "class": [{"name": "Fighter", "source": "PHB", "hd": {"number": 1, "faces": 10}, "proficiency": ["str", "con"],
                   "startingProficiencies": {"skills": [{"choose": {"from": ["acrobatics", "athletics", "history", "insight", "intimidation", "perception", "survival"], "count": 2}}],
                                             "weapons": ["simple", "martial"], "armor": ["light", "medium", "heavy", "shield"]},
                   "optionalfeatureProgression": [{"name": "Fighting Style", "featureType": ["FS:F"], "progression": {"1": 1}}],
                   "subclassTitle": "Martial Archetype",
                   "classFeatures": ["Fighting Style|Fighter||1", "Second Wind|Fighter||1", "Action Surge|Fighter||2",
                                     {"classFeature": "Martial Archetype|Fighter||3", "gainSubclassFeature": True},
                                     "Ability Score Improvement|Fighter||4", "Martial Versatility|Fighter||4|TCE", "Extra Attack|Fighter||5"]}],
        "subclass": [{"name": "Champion", "shortName": "Champion", "source": "PHB", "className": "Fighter", "classSource": "PHB"}],
        "classFeature": [{"name": n, "source": "PHB", "className": "Fighter", "classSource": "PHB", "level": l, "entries": [t]} for n, l, t in [
            ("Fighting Style", 1, "Adopt a style."), ("Second Wind", 1, "Regain {@dice 1d10} + your fighter level."),
            ("Action Surge", 2, "One more action."), ("Martial Archetype", 3, "Choose an archetype."),
            ("Ability Score Improvement", 4, "Increase scores."), ("Extra Attack", 5, "Attack twice.")]]
        + [{"name": "Martial Versatility", "source": "TCE", "className": "Fighter", "classSource": "PHB", "level": 4, "entries": ["Optional."]}],
        "subclassFeature": [{"name": "Improved Critical", "source": "PHB", "className": "Fighter", "classSource": "PHB", "subclassShortName": "Champion",
                             "subclassSource": "PHB", "level": 3, "entries": ["Crit on 19-20."]}],
    },
    "Classes/class-barbarian.json": {"class": [{"name": "Barbarian", "source": "PHB", "hd": {"number": 1, "faces": 12}, "proficiency": ["str", "con"],
                                                "startingProficiencies": {"weapons": ["simple", "martial"], "armor": ["light", "medium", "shield"]},
                                                "classFeatures": ["Rage|Barbarian||1", "Unarmored Defense|Barbarian||1"]}],
                                     "classFeature": [{"name": "Rage", "source": "PHB", "className": "Barbarian", "classSource": "PHB", "level": 1, "entries": ["Rage."]},
                                                      {"name": "Unarmored Defense", "source": "PHB", "className": "Barbarian", "classSource": "PHB", "level": 1, "entries": ["AC."]}]},
    "Classes/class-wizard.json": {"class": [{"name": "Wizard", "source": "PHB", "hd": {"number": 1, "faces": 6}, "proficiency": ["int", "wis"],
                                             "casterProgression": "full", "spellcastingAbility": "int", "classFeatures": ["Arcane Recovery|Wizard||1"]}],
                                  "classFeature": [{"name": "Arcane Recovery", "source": "PHB", "className": "Wizard", "classSource": "PHB", "level": 1, "entries": ["Recover."]}]},
    "Classes/class-paladin.json": {"class": [{"name": "Paladin", "source": "PHB", "hd": {"number": 1, "faces": 10}, "proficiency": ["wis", "cha"],
                                              "casterProgression": "1/2", "spellcastingAbility": "cha", "classFeatures": []}]},
    "Races/races.json": {"race": [{"name": "Human", "source": "PHB", "speed": 30},
                                  {"name": "Dwarf", "source": "PHB", "speed": 25, "ability": [{"con": 2}]}],
                         "subrace": [{"name": "Hill", "source": "PHB", "raceName": "Dwarf", "raceSource": "PHB", "ability": [{"wis": 1}]}]},
    "Backgrounds/backgrounds.json": {"background": [{"name": "Soldier", "source": "PHB", "skillProficiencies": [{"athletics": True, "intimidation": True}]}]},
    "Optional Features/optionalfeatures.json": {"optionalfeature": [{"name": n, "source": "PHB", "featureType": ["FS:F"], "entries": ["Style."]} for n in ("Defense", "Archery", "Dueling")]},
    "Feats/feats.json": {"feat": [{"name": "Alert", "source": "PHB", "entries": ["+5 initiative."]},
                                  {"name": "Heavy Armor Master", "source": "PHB", "prerequisite": [{"proficiency": [{"armor": "heavy"}]}], "entries": ["DR 3."]}]},
    "Equipment/items-base.json": {"baseitem": [
        {"name": "Longsword", "source": "PHB", "type": "M", "weaponCategory": "martial", "dmg1": "1d8", "dmg2": "1d10", "dmgType": "S", "property": ["V"]},
        {"name": "Rapier", "source": "PHB", "type": "M", "weaponCategory": "martial", "dmg1": "1d8", "dmgType": "P", "property": ["F"]},
        {"name": "Longbow", "source": "PHB", "type": "R", "weaponCategory": "martial", "dmg1": "1d8", "dmgType": "P", "property": ["A", "H", "2H"], "range": "150/600"},
        {"name": "Chain Mail", "source": "PHB", "type": "HA", "ac": 16, "strength": "13"},
        {"name": "Leather Armor", "source": "PHB", "type": "LA", "ac": 11},
        {"name": "Scale Mail", "source": "PHB", "type": "MA", "ac": 14},
        {"name": "Shield", "source": "PHB", "type": "S", "ac": 2}]},
    "Spells/spells-phb.json": {"spell": [{"name": "Fireball", "source": "PHB", "level": 3, "entries": ["Boom."]},
                                         {"name": "Magic Missile", "source": "PHB", "level": 1, "entries": ["Darts."]}]},
}


def fixture_library():
    tmp = tempfile.mkdtemp()
    for rel, data in DATA.items():
        p = Path(tmp) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data), encoding="utf-8")
    lib = Library([Path(tmp)])
    lib.load()
    return lib


def ref(name, source="PHB"):
    return {"name": name, "source": source}
