"""✨ Correct my text: the model fixes spelling and grammar of the player's message without changing it otherwise."""
from __future__ import annotations

import re

PROMPT = """Correct the spelling, grammar and punctuation of the text below{lang}. Rules:
- Keep the meaning, the words, the tone and the length. Do not add or remove ideas. Do not answer it.
- Keep every writing mark exactly: text in "double quotes" is speech, *asterisks* is action, 'single quotes' is a
  thought, a line starting with / is a message to the game master. Keep names as they are.
- Write ONLY the corrected text, nothing before or after it.

Text:
{text}"""

LANGS = {"pt-BR": " in Brazilian Portuguese", "en": " in English"}


async def correct(llm, text: str, language: str) -> str:
    raw = await llm.chat([{"role": "user", "content": PROMPT.format(lang=LANGS.get(language, ""), text=text)}],
                         max_tokens=min(1200, 60 + len(text) // 2), temperature=0.1)
    out = (raw or "").strip()
    out = re.sub(r"^(corrected text|texto corrigido)\s*:\s*", "", out, flags=re.I).strip()
    if out.startswith("```"):
        out = out.strip("`").strip()
    # a reply that is wildly different in length is not a correction: keep the player's text
    if not out or len(out) > len(text) * 1.6 + 40 or len(out) < len(text) * 0.5:
        return text
    return out
