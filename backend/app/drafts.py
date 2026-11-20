"""AI drafts for single fields: a card's opening, rules, tone or world, and the player's character.

Each call writes one field from what the card already has, so the result fits the rest of the card.
"""
from __future__ import annotations

from .util import extract_json, truncate

CARD_FIELDS = {
    "opening_message": ("the opening message of the story: 2 to 4 vivid paragraphs that set the scene, introduce the situation "
                        "and end by handing control to the player (for example with a question or a choice). Do not act for the player.",
                        600),
    "world": ("the world / setting description: places, factions, history and atmosphere in 1 to 3 short paragraphs.", 500),
    "system_rules": ("the game rules the Game Master should follow: a short bullet list (dice, checks, combat, progression, "
                     "special mechanics of this world). Keep it practical, at most 12 bullets.", 500),
    "tone": ("the tone and writing style: 2 to 4 short sentences about mood, pacing, themes and how the narration should sound.", 200),
    "description": ("a one-sentence teaser for the card picker.", 80),
}

LANG = {"en": "Write in English.", "pt-BR": "Write in Brazilian Portuguese (pt-BR)."}


def _card_context(card: dict) -> str:
    bits = [f"Card name: {card.get('name') or '(unnamed)'}",
            f"Type: {card.get('kind') or 'roleplay'}; the AI plays: {card.get('mode') or 'gm_world'}"]
    for key, label in (("description", "Teaser"), ("world", "World"), ("system_rules", "Rules"), ("tone", "Tone"),
                       ("opening_message", "Opening")):
        if (card.get(key) or "").strip():
            bits.append(f"{label}: {truncate(card[key].strip(), 900)}")
    info = card.get("information") or {}
    if (info.get("description") or "").strip():
        bits.append(f"Card description: {truncate(info['description'].strip(), 1200)}")
    names = [n.get("name") for n in card.get("npcs") or [] if n.get("name")][:12]
    if names:
        bits.append("Characters: " + ", ".join(names))
    return "\n".join(bits)


async def draft_card_field(llm, field: str, card: dict, hint: str = "", language: str = "en") -> str:
    if field not in CARD_FIELDS:
        raise ValueError(f"Cannot draft the field {field!r}.")
    what, tokens = CARD_FIELDS[field]
    prompt = (
        "You help write a card for a text roleplaying game.\n"
        f"{_card_context(card)}\n\n"
        f"Write {what}\n"
        + (f"Wishes from the author: {hint.strip()}\n" if hint.strip() else "")
        + (f"The current text (improve or rewrite it): {truncate(card.get(field) or '', 1200)}\n" if (card.get(field) or "").strip() else "")
        + f"{LANG.get(language, LANG['en'])} Output only the text itself, no title, no quotes, no comments."
    )
    text = await llm.chat([{"role": "user", "content": prompt}], max_tokens=tokens + 150, temperature=0.85)
    text = (text or "").strip().strip('"').strip()
    if not text:
        raise ValueError("The model returned nothing. Try again.")
    return text


async def draft_player(llm, card: dict, player: dict, language: str = "en") -> dict:
    """Suggest background, appearance and personality for the player's character, fitting the card."""
    known = ", ".join(f"{k}: {v}" for k, v in player.items() if isinstance(v, (str, int)) and str(v).strip())
    prompt = (
        "You help a player create their character for a text roleplaying game.\n"
        f"{_card_context(card)}\n\n"
        f"What the player chose so far: {known or 'nothing yet'}.\n"
        "Fill in what is missing and keep what the player chose. Answer with ONE JSON object with the keys "
        "name, race, class, background (2-3 sentences), description (looks: hair, eyes, build, clothes; 1-2 sentences), "
        "traits (personality, 1 sentence). Fit the world of the card. Avoid clichés. "
        f"{LANG.get(language, LANG['en'])}"
    )
    raw = await llm.chat([{"role": "user", "content": prompt}], max_tokens=500, temperature=0.9)
    data = extract_json(raw)
    if not isinstance(data, dict):
        raise ValueError("The model did not return a character. Try again.")
    out = {}
    for key in ("name", "race", "class", "background", "description", "traits"):
        if isinstance(data.get(key), str) and data[key].strip():
            out[key] = truncate(data[key].strip(), 600)
    return out
