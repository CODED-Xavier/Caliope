"""Sheet templates: ready status blocks for well-known game systems.

A card (or one game) picks a template; the app then keeps that sheet itself, exactly like a card's own INFO block
(app/statusbook.py): place, time, items, money, HP, level, attributes and relationships come straight from the game
state, and the other fields (Sanity, Hunger, Spell slots...) are kept in `state["card_status"]` and changed by the
tracker when the story changes them. The sheet shows in the Status tab of the right column.

Template format: one line per row, `Label: [placeholder]`, cells separated by " | ".
"""
from __future__ import annotations

TEMPLATES: list[dict] = [
    {"id": "simple", "name": "Simple adventure", "system": "Any",
     "text": """Location: [Location] | Time: [Time]
HP: [HP] | Condition: [Condition]
Inventory: [Items] | Gold: [Gold]
Quests: [Quests]
Relationships: [People]"""},
    {"id": "dnd5e", "name": "D&D 5e", "system": "Dungeons & Dragons 5th edition",
     "text": """Location: [Location] | Time: [Time]
Class: [Class] | Level: [Level] | XP: [XP]
HP: [HP] | AC: [AC] | Hit Dice: [Hit Dice]
STR: [STR] | DEX: [DEX] | CON: [CON] | INT: [INT] | WIS: [WIS] | CHA: [CHA]
Spell slots: [Slots] | Inspiration: [Inspiration]
Conditions: [Conditions]
Inventory: [Items] | Gold: [Gold]
Quests: [Quests]
Relationships: [People]"""},
    {"id": "pf2e", "name": "Pathfinder 2e", "system": "Pathfinder 2nd edition",
     "text": """Location: [Location] | Time: [Time]
Class: [Class] | Level: [Level] | XP: [XP]
HP: [HP] | AC: [AC] | Hero Points: [Hero Points]
STR: [STR] | DEX: [DEX] | CON: [CON] | INT: [INT] | WIS: [WIS] | CHA: [CHA]
Focus Points: [Focus] | Spell slots: [Slots]
Conditions: [Conditions]
Inventory: [Items] | Gold: [Gold]
Quests: [Quests]"""},
    {"id": "tormenta20", "name": "Tormenta20", "system": "Tormenta20 (Brazilian)",
     "text": """Local: [Local] | Hora: [Hora]
Classe: [Classe] | Nível: [Nível] | XP: [XP]
PV: [PV] | PM: [PM] | Defesa: [Defesa]
FOR: [FOR] | DES: [DES] | CON: [CON] | INT: [INT] | SAB: [SAB] | CAR: [CAR]
Poderes: [Poderes] | Condições: [Condições]
Inventário: [Itens] | Tibares: [Tibares]
Missões: [Missões]
Relações: [Pessoas]"""},
    {"id": "vampire5", "name": "Vampire: the Masquerade V5", "system": "Vampire: the Masquerade 5th edition",
     "text": """Location: [Location] | Time: [Time]
Clan: [Clan] | Generation: [Generation] | Blood Potency: [Blood Potency]
Health: [Health] | Willpower: [Willpower]
Hunger: [0-5] | Humanity: [0-10]
Disciplines: [Disciplines]
Touchstones: [Touchstones] | Convictions: [Convictions]
Inventory: [Items] | Money: [Money]
Relationships: [People]"""},
    {"id": "cthulhu7", "name": "Call of Cthulhu 7e", "system": "Call of Cthulhu 7th edition",
     "text": """Location: [Location] | Time: [Time]
Occupation: [Occupation]
HP: [HP] | Sanity: [Sanity] | Luck: [Luck] | Magic Points: [MP]
Key skills: [Skills]
Phobias and manias: [None yet]
Clues: [Clues]
Inventory: [Items] | Money: [Money]
Relationships: [People]"""},
    {"id": "cyberpunk", "name": "Cyberpunk RED", "system": "Cyberpunk RED",
     "text": """Location: [Location] | Time: [Time]
Role: [Role] | Reputation: [Rep]
HP: [HP] | Humanity: [Humanity] | Armor SP: [SP]
Cyberware: [Cyberware]
Inventory: [Items] | Eurobucks: [Eddies]
Jobs: [Quests]
Relationships: [People]"""},
    {"id": "academy", "name": "Magic academy", "system": "Academy stories (Lumencia style)",
     "text": """Location: [Location] | Time: [Time]
Year: [Year] | House: [House] | Rank: [Rank]
Mana: [Grade] | Body: [Grade] | Knowledge: [Grade]
Spells: [Spells] | Condition: [Condition]
Inventory: [Items] | Money: [Money] | Merits: [Merits]
Relationships: [People]"""},
    {"id": "romance", "name": "Slice of life / romance", "system": "Character stories",
     "text": """Location: [Location] | Time: [Time]
Mood: [Mood] | Outfit: [Outfit]
Plans: [Plans]
Relationships: [People]"""},
]


def library() -> list[dict]:
    return [dict(t) for t in TEMPLATES]


def by_id(template_id: str) -> dict | None:
    return next((dict(t) for t in TEMPLATES if t["id"] == template_id), None)
