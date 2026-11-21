"""The Aedo outside the story: answers to "/your question" messages.

A message that starts with "/" is the player talking to the game master, not to the story. Small roleplay models
keep narrating when such a question sits inside the story's prompt, so it gets its own short prompt here: the
player's sheet, where the story stands, the last few exchanges, and an order to answer plainly, out of character.
These exchanges are kept in the chat but left out of the story the model reads later.
"""
from __future__ import annotations

from .util import truncate
from .writing import gm_question, is_gm_message

LANGS = {"pt-BR": "Answer in Brazilian Portuguese.", "en": "Answer in English.",
         "auto": "Answer in the language of the player's question."}

SYSTEM = """You are the Aedo, the game master of a roleplay story, talking with the player OUTSIDE the story.
The player asked you a question or gave you an instruction about the game. Rules:
- Answer it directly and clearly, as a helpful game master talking to a friend. Out of character.
- Do NOT continue the story, do NOT narrate scenes, do NOT speak as any character, no dialogue in quotes.
- Use the information below. When the player asks for something written there (their background, their sheet, what
  happened in the story), give it to them in full, as written.
- Answer only with what the player's character could know: their own background, what they saw and heard in the story,
  and common knowledge of the world. Other characters' private lives, hidden motives and the story's secrets are not
  handed out here: say plainly that the character doesn't know that yet and could find out in the story (ask someone,
  search, investigate). Never invent facts to fill the gap.
- Keep it short unless the player asks for everything. {lang}"""


def without_ooc(history: list[dict]) -> list[dict]:
    """The story's messages only: questions to the Aedo and his answers outside the story are left out."""
    out, skip_answer = [], False
    for m in history:
        if m["role"] == "user" and is_gm_message(m["content"]):
            skip_answer = True
            continue
        if m["role"] == "assistant" and ((m.get("meta") or {}).get("ooc") or skip_answer):
            skip_answer = False
            continue
        skip_answer = False
        out.append(m)
    return out


def _sheet(state: dict) -> str:
    p = state.get("player") or {}
    lines = []
    for key, label in (("name", "Name"), ("race", "Race"), ("class", "Class"), ("background", "Background"),
                       ("description", "Appearance"), ("traits", "Personality"), ("notes", "Player's notes")):
        if str(p.get(key) or "").strip():
            lines.append(f"{label}: {str(p[key]).strip()}")
    stats = p.get("stats") or {}
    if stats:
        lines.append("Attributes: " + ", ".join(f"{k} {v}" for k, v in stats.items()))
    if state.get("gold"):
        lines.append(f"Money: {state['gold']}")
    inv = [i.get("name", "") if isinstance(i, dict) else str(i) for i in state.get("inventory") or []]
    if inv:
        lines.append("Inventory: " + ", ".join(x for x in inv if x))
    status = state.get("card_status") or {}
    if status:
        lines.append("Sheet: " + "; ".join(f"{k}: {v}" for k, v in status.items()))
    return "\n".join(lines) or "(empty)"


def build_messages(*, scenario: dict, state: dict, npcs: list[dict], summary: str, history: list[dict],
                   question: str, language: str, player_lore: list | None = None) -> list[dict]:
    parts = [f"## The card\n{scenario.get('name', '')}: {truncate(scenario.get('description') or '', 800)}"]
    for key, label in (("known_at_start", "What the player's character knows from the start"), ("fixed_facts", "Fixed facts")):
        if str(scenario.get(key) or "").strip():
            parts.append(f"## {label}\n{truncate(scenario[key], 1500)}")
    parts += [
             f"## The player's character\n{truncate(_sheet(state), 4000)}"]
    lore = [e for e in player_lore or [] if isinstance(e, dict) and e.get("enabled", True) and e.get("name")]
    if lore:
        parts.append("## The player's world additions\n" + "\n".join(
            f"- {e['name']}: {truncate(e.get('content', ''), 400)}" for e in lore[:12]))
    where = ", ".join(x for x in (state.get("location"), state.get("date_label") or state.get("time_of_day")) if x)
    if where:
        parts.append(f"## Now\n{where}")
    met = [n for n in npcs if n.get("met", True)]
    if met:
        parts.append("## Characters met\n" + "\n".join(
            f"- {n['name']}: {truncate(n.get('description') or '', 160)} (relationship {n.get('relationship', 0)})"
            for n in met[:20]))
    if summary:
        parts.append(f"## The story so far\n{truncate(summary, 1500)}")
    story = without_ooc(history)[-6:]
    if story:
        parts.append("## The last moments of the story\n" + "\n\n".join(
            f"{'Player' if m['role'] == 'user' else 'Story'}: {truncate(m['content'], 700)}" for m in story))
    system = SYSTEM.format(lang=LANGS.get(language, LANGS["en"])) + "\n\n" + "\n\n".join(parts)
    q = gm_question(question) or question
    return [{"role": "system", "content": system}, {"role": "user", "content": q}]
