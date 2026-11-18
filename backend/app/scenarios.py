"""Scenarios: a reusable game setup (mode, rules, world, cast, player template, skills policy).

Modes
-----
gm_world : the AI is the Game Master and invents the world, places and NPCs as you go.
gm_cast  : the AI is the Game Master and runs a preset cast of NPCs you provide.
character: the AI plays ONE character; the story centres on your relationship with them.
"""
from __future__ import annotations

import json
from pathlib import Path

from .appearance import normalize_appearance
from .cards import KINDS, default_kind, normalize_features
from .db import Database
from .util import extract_json, now, slugify, truncate

MODES = ("gm_world", "gm_cast", "character")


def normalize_scenario(raw: dict, default_mode: str = "gm_world") -> dict:
    raw = raw if isinstance(raw, dict) else {}
    mode = raw.get("mode") if raw.get("mode") in MODES else default_mode

    npcs = []
    for n in raw.get("npcs", []) if isinstance(raw.get("npcs"), list) else []:
        if not isinstance(n, dict) or not str(n.get("name", "")).strip():
            continue
        try:
            rel = int(n.get("relationship", 0))
        except (TypeError, ValueError):
            rel = 0
        npcs.append(
            {
                "name": truncate(str(n["name"]).strip(), 60),
                "description": truncate(str(n.get("description", "")), 600),
                "personality": truncate(str(n.get("personality", "")), 600),
                "speech_style": truncate(str(n.get("speech_style", "")), 300),
                "appearance": normalize_appearance(n.get("appearance")),
                "relationship": max(-100, min(100, rel)),
                "active": bool(n.get("active", True)),
            }
        )

    # Skills are card add-ons: up to 3, always part of the prompt. (Older cards stored them as "pinned".)
    skills = raw.get("skills") if isinstance(raw.get("skills"), dict) else {}
    attached = skills.get("attached", skills.get("pinned", []))
    attached = [str(x) for x in attached][:3] if isinstance(attached, list) else []

    species = raw.get("species", [])
    species = [str(x).strip()[:40] for x in species[:12] if str(x).strip()] if isinstance(species, list) else []

    return {
        "name": truncate(str(raw.get("name") or "Untitled scenario").strip(), 100),
        "mode": mode,
        "kind": raw.get("kind") if raw.get("kind") in KINDS else default_kind(mode),
        "features": normalize_features(raw.get("features")),
        "description": truncate(str(raw.get("description", "")), 400),
        "language": raw.get("language") if raw.get("language") in ("en", "pt-BR", "auto") else "",
        "system_rules": str(raw.get("system_rules", "")),
        "world": str(raw.get("world", "")),
        "tone": str(raw.get("tone", "")),
        "species": species,
        "opening_message": str(raw.get("opening_message", "")),
        "player": raw.get("player") if isinstance(raw.get("player"), dict) else {},
        "npcs": npcs,
        "skills": {"attached": attached},
    }


class ScenarioRepository:
    def __init__(self, db: Database):
        self.db = db

    @staticmethod
    def _row(row: dict, full: bool) -> dict:
        data = json.loads(row["data"])
        out = {
            "id": row["id"],
            "slug": row["slug"],
            "name": row["name"],
            "mode": row["mode"],
            "kind": data.get("kind") or default_kind(row["mode"]),
            "description": data.get("description", ""),
            "npc_count": len(data.get("npcs", [])),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        if full:
            out["data"] = data
        return out

    def list(self) -> list[dict]:
        rows = self.db.query("SELECT * FROM scenarios ORDER BY name COLLATE NOCASE")
        return [self._row(r, full=False) for r in rows]

    def get(self, scenario_id: int) -> dict | None:
        row = self.db.query_one("SELECT * FROM scenarios WHERE id = ?", (scenario_id,))
        return self._row(row, full=True) if row else None

    def create(self, raw: dict) -> dict:
        data = normalize_scenario(raw)
        base = slugify(data["name"])
        slug, n = base, 2
        while self.db.query_one("SELECT 1 FROM scenarios WHERE slug = ?", (slug,)):
            slug, n = f"{base}-{n}", n + 1
        ts = now()
        cur = self.db.execute(
            "INSERT INTO scenarios(slug, name, mode, data, created_at, updated_at) VALUES(?,?,?,?,?,?)",
            (slug, data["name"], data["mode"], json.dumps(data, ensure_ascii=False), ts, ts),
        )
        return self.get(cur.lastrowid)

    def update(self, scenario_id: int, raw: dict) -> dict | None:
        if not self.get(scenario_id):
            return None
        data = normalize_scenario(raw)
        self.db.execute(
            "UPDATE scenarios SET name=?, mode=?, data=?, updated_at=? WHERE id=?",
            (data["name"], data["mode"], json.dumps(data, ensure_ascii=False), now(), scenario_id),
        )
        return self.get(scenario_id)

    def delete(self, scenario_id: int) -> bool:
        cur = self.db.execute("DELETE FROM scenarios WHERE id = ?", (scenario_id,))
        return cur.rowcount > 0

    def seed_defaults(self, seed_dir: Path) -> int:
        """Install the bundled example scenarios, only on the very first run."""
        if self.db.query_one("SELECT 1 FROM scenarios LIMIT 1"):
            return 0
        count = 0
        for path in sorted(Path(seed_dir).glob("scenarios/*.json")):
            try:
                self.create(json.loads(path.read_text(encoding="utf-8")))
                count += 1
            except (ValueError, OSError):
                continue
        return count


GENERATOR_PROMPT = """You design scenarios for a text roleplaying game. Output ONE JSON object and nothing else.

Fields:
- name: short title
- mode: "{mode}"
- kind: "{kind}" ("roleplay" = simple, focused on characters and conversation; "adventure" = rules, quests and items)
- species: list of races or species that exist in this world (for example ["Human", "Elf", "Dwarf"]), or [] if everyone is human
- description: 1-2 sentence pitch shown in the scenario picker
- system_rules: the game rules to follow (concise, under 250 words). Use the rules system the idea implies; if none, write simple rules.
- world: the setting, factions, tone of the world (under 250 words)
- tone: writing style guidance for the narrator (1-3 sentences)
- opening_message: the first message the player sees (2-4 short paragraphs, ends with a question or choice for the player)
- player: {{"name": "", "class": "", "race": "", "level": 1, "stats": {{"STR": 10, "DEX": 10, "CON": 10, "INT": 10, "WIS": 10, "CHA": 10}}, "hp": {{"current": 10, "max": 10}}, "ac": 10, "gold": 0, "inventory": [{{"name": "item", "qty": 1}}], "location": ""}}
- npcs: list of {{"name", "description", "personality", "speech_style", "relationship": number from -100 to 100, "appearance": {{"race": "", "hair": "", "eyes": "", "build": "", "skin": "", "outfit": "", "extra": ""}}}} ({npc_hint}). Give each character a DISTINCT, specific look: avoid cliché combinations such as raven hair with emerald eyes.

{mode_hint}
{language_line}
Idea from the user: {idea}
"""

MODE_HINTS = {
    "gm_world": "The AI is the Game Master and will invent most characters and places during play, so keep npcs to 0-2 starting contacts.",
    "gm_cast": "The AI is the Game Master running a preset cast: provide 3-6 distinct NPCs with clearly different personalities and voices.",
    "character": "The AI plays ONE character, the main NPC (npcs must contain exactly that one character, with rich personality, history and speech_style). The story is about the player's relationship with them.",
}
NPC_HINTS = {
    "gm_world": "0-2 entries",
    "gm_cast": "3-6 entries",
    "character": "exactly 1 entry",
}


async def generate_scenario(llm, idea: str, mode: str = "gm_world", language: str = "en", kind: str | None = None) -> dict:
    mode = mode if mode in MODES else "gm_world"
    kind = kind if kind in KINDS else default_kind(mode)
    language_line = {
        "en": "Write all text in English.",
        "pt-BR": "Write all text in Brazilian Portuguese (pt-BR).",
    }.get(language, "Write in the language of the user's idea.")
    prompt = GENERATOR_PROMPT.format(
        mode=mode, kind=kind, npc_hint=NPC_HINTS[mode], mode_hint=MODE_HINTS[mode], language_line=language_line, idea=idea.strip()
    )
    raw = await llm.chat([{"role": "user", "content": prompt}], max_tokens=2200, temperature=0.9)
    data = extract_json(raw)
    if not data:
        raise ValueError("The model did not return a valid scenario. Try again or simplify the idea.")
    data["mode"] = mode
    data["kind"] = kind
    return normalize_scenario(data, default_mode=mode)
