"""Import and export of character cards.

Reads the common Character Card V2 JSON (name, description, first_mes, character_book...), the older flat
V1 layout, and cards exported by this app (which keep an exact copy of everything under extensions.rpg_app).
Everything the file contains is kept in its own place: information (long texts), characters, lorebook.
"""
from __future__ import annotations

import os
import re

from .scenarios import normalize_lorebook, normalize_scenario
from .status import split_template
from .util import estimate_tokens


class CardError(ValueError):
    pass


# "- Lilia Valenheart (Female, 1st-Year): Gold eyes, red hair. ... Base URL: https://x/Lilia.png (1=Standard, 2=Happy)"
_BULLET = re.compile(
    r"^[ \t]*-[ \t]+([^\n(:]+?)[ \t]*\(([^)\n]*)\)[ \t]*:?[ \t]*(.*?)(?=^[ \t]*-[ \t]+[^\n(:]+?[ \t]*\(|\Z)", re.S | re.M
)
_URL = re.compile(r"Base URL:\s*(https?://[^\s()]+)\s*(?:\(([^)]*)\))?")
_MOOD = re.compile(r"(\d)\s*=\s*([^,)]+)")


def _looks(text: str, paren: str) -> dict:
    out: dict = {}
    eyes = re.search(r"\b([A-Za-z]+) eyes\b", text)
    hair = re.search(r"\b([A-Za-z]+) hair\b", text)
    if eyes:
        out["eyes"] = eyes.group(1).lower()
    if hair:
        out["hair"] = hair.group(1).lower()
    if paren and len(paren) <= 40:
        out["extra"] = paren.strip()
    return out


def parse_characters(entries: list[dict]) -> list[dict]:
    """Characters listed as bullet points inside lorebook entries, with their portrait links."""
    found: dict[str, dict] = {}
    for entry in entries:
        for m in _BULLET.finditer(entry.get("content", "")):
            name, paren, body = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
            if not name or len(name) > 60:
                continue
            text, portraits = body, {"default": "", "moods": []}
            u = _URL.search(body)
            if u:
                text = body[: u.start()].strip()
                url = u.group(1)
                portraits["default"] = url
                base, ext = os.path.splitext(url)
                for n, label in _MOOD.findall(u.group(2) or ""):
                    portraits["moods"].append({"n": int(n), "label": label.strip(), "url": f"{base}/{n}{ext}"})
            npc = {
                "name": name, "description": text, "personality": "", "speech_style": "",
                "appearance": _looks(text, paren), "portraits": portraits,
                "in_prompt": False,   # the lorebook already carries the profile, shown when the name comes up
                "met": False, "relationship": 0, "active": True,
            }
            key = name.lower()
            if key in found:
                if not found[key]["portraits"]["default"] and portraits["default"]:
                    found[key]["portraits"] = portraits
                continue
            found[key] = npc
    return list(found.values())


def _summary(scenario: dict) -> dict:
    info = scenario["information"]
    portraits = sum(1 for n in scenario["npcs"] if n["portraits"]["default"] or n["portraits"]["moods"])
    fixed = {
        "description": estimate_tokens(info["description"]),
        "post_history": estimate_tokens(info["post_history"]),
        "examples": estimate_tokens(info["example_messages"]),
        "opening": estimate_tokens(scenario["opening_message"]),
    }
    return {
        "lorebook_entries": len(scenario["lorebook"]["entries"]),
        "characters": len(scenario["npcs"]),
        "characters_with_portraits": portraits,
        "tokens": fixed,
        "fixed_tokens": fixed["description"] + fixed["post_history"] + fixed["examples"],
    }


def parse_card(obj) -> dict:
    """Turn a card file (already decoded from JSON) into a card of this app, plus a summary and warnings."""
    if not isinstance(obj, dict):
        raise CardError("The file must contain a JSON object.")
    data = obj["data"] if isinstance(obj.get("data"), dict) else obj
    ext = data.get("extensions") if isinstance(data.get("extensions"), dict) else {}

    if isinstance(ext.get("rpg_app"), dict):  # exported by this app: exact restore
        scenario = normalize_scenario(ext["rpg_app"])
        return {"format": "rpg_app", "scenario": scenario, "warnings": [], "summary": _summary(scenario)}

    if not any(str(data.get(k) or "").strip() for k in ("name", "description", "first_mes")):
        raise CardError("This does not look like a character card (no name, description or first message).")

    fmt = str(obj.get("spec") or "v1")
    name = str(data.get("name") or "Imported card").strip()
    lorebook = normalize_lorebook(data.get("character_book"))
    chars = parse_characters(lorebook["entries"])
    description = str(data.get("description") or "")
    personality = str(data.get("personality") or "")
    post = str(data.get("post_history_instructions") or "")
    template = split_template(post)[1]
    is_gm = re.search(r"game master|\bGM\b|text rpg|world engine|narrator", f"{description} {personality}", re.I) is not None
    mode = ("gm_cast" if chars else "gm_world") if is_gm else "character"
    if mode == "character":  # an ordinary character card: the character is the first NPC
        chars = [{"name": name, "description": "", "personality": "", "speech_style": "", "appearance": {},
                  "portraits": {"default": "", "moods": []}, "in_prompt": True, "met": True, "relationship": 0, "active": True}] + chars

    features: dict = {}
    if template:  # the card has its own status block: show it in a side panel instead of a character sheet
        features = {"tracker": "lite", "tracker_interval": 2, "panels": ["status", "people", "journal", "dice"]}

    greetings = data.get("alternate_greetings") if isinstance(data.get("alternate_greetings"), list) else []
    scenario = normalize_scenario({
        "name": name, "mode": mode, "kind": "roleplay", "features": features,
        "description": str(data.get("creator_notes") or "")[:200],
        "opening_message": str(data.get("first_mes") or ""),
        "alternate_openings": greetings,
        "information": {
            "description": description, "scenario": data.get("scenario"), "personality": personality,
            "system_prompt": data.get("system_prompt"), "post_history": post,
            "example_messages": data.get("mes_example"), "creator_notes": data.get("creator_notes"),
            "tags": data.get("tags"), "creator": data.get("creator"), "version": data.get("character_version"),
        },
        "lorebook": lorebook, "npcs": chars,
    }, default_mode=mode)

    summary = _summary(scenario)
    warnings = []
    if chars and mode != "character":
        warnings.append(f"Found {len(chars)} characters in the lorebook. Their profiles stay in the lorebook and appear when their names come up.")
    if template:
        warnings.append(f"The card asks the AI to write an INFO status block. It is shown in the Status tab and written every {scenario['information']['status_every']} replies.")
    if re.search(r"affinity|\[-3\]|hostile \[", f"{description} {post}", re.I):
        warnings.append("The card has its own relationship scale. The app's -100 to +100 scale overrides it.")
    if summary["characters_with_portraits"]:
        warnings.append(f"{summary['characters_with_portraits']} characters have portrait links. Copies are saved on this PC the first time each one is shown.")
    if summary["fixed_tokens"] > 2500:
        warnings.append(f"The card's fixed text is about {summary['fixed_tokens']} tokens, so it leaves less room for the story. A larger context window helps.")
    return {"format": fmt, "scenario": scenario, "warnings": warnings, "summary": summary}


def export_card(data: dict) -> dict:
    """Character Card V2 JSON. The app's own data rides along in extensions.rpg_app for an exact re-import."""
    info = data.get("information") or {}
    description = info.get("description") or "\n\n".join(x for x in (data.get("world"), data.get("system_rules"), data.get("tone")) if x)
    book = data.get("lorebook") or {}
    entries = [
        {"id": e["id"], "name": e["name"], "keys": e["keys"], "secondary_keys": e["secondary_keys"], "content": e["content"],
         "enabled": e["enabled"], "constant": e["constant"], "selective": e["selective"], "case_sensitive": e["case_sensitive"],
         "priority": e["priority"], "insertion_order": e["insertion_order"], "position": "before_char", "extensions": {}}
        for e in book.get("entries", [])
    ]
    card = {
        "name": data.get("name", ""), "description": description, "personality": info.get("personality", ""),
        "scenario": info.get("scenario", ""), "first_mes": data.get("opening_message", ""), "mes_example": info.get("example_messages", ""),
        "creator_notes": info.get("creator_notes", ""), "system_prompt": info.get("system_prompt", ""),
        "post_history_instructions": info.get("post_history", ""), "alternate_greetings": data.get("alternate_openings", []),
        "tags": info.get("tags", []), "creator": info.get("creator", ""), "character_version": info.get("version", ""),
        "extensions": {"rpg_app": data},
        "character_book": {"name": book.get("name", ""), "description": book.get("description", ""),
                           "scan_depth": book.get("scan_depth", 4), "token_budget": book.get("token_budget", 800),
                           "recursive_scanning": False, "extensions": {}, "entries": entries},
    }
    return {"spec": "chara_card_v2", "spec_version": "2.0", "data": card, **{k: card[k] for k in ("name", "description", "personality", "scenario", "first_mes", "mes_example")}}
