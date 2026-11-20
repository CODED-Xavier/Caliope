"""How the player writes, and what each mark means.

    "speech"        what the character says out loud
    'thought'       what the character thinks: only the GM knows it, NPCs never do
    *action*        what the character does
    /message        a direct message to the GM, outside the story (except /roll, which rolls dice)
    no mark         the GM decides how to read it (usually an action or intention)

Thoughts are kept out of everything that could leak them into the world: the tracker never reads them
and memories never store them. In the prompt they are rewritten into an explicit private tag, because a
small model easily misses a pair of single quotes.
"""
from __future__ import annotations

import re

# A single-quoted span that is not an apostrophe: it cannot open right after a letter ("don't")
# and cannot close right before one ("she's" inside the thought is fine).
THOUGHT = re.compile(r"(?<![\w'])'(?=\S)((?:[^'\n]|(?<=\w)'(?=\w))*?[^\s'])'(?!\w)")

RULES = """## How the player writes
- Text in "double quotes" is what the player's character says out loud.
- Text in *asterisks* is what the player's character does.
- [thought: ...] is what the player's character silently thinks. ONLY YOU know it. NPCs can never hear, read, guess or react to a thought, unless the character says or shows it. You may use thoughts to understand the player's intentions and, now and then, to give a subtle hint through the narration (something the character notices), never through an NPC knowing it.
- [message to the GM: ...] is the player talking to YOU outside the story. Answer it directly and briefly, out of character, and do not advance the story unless asked.
- Text without marks: decide what fits best, usually an action or an intention of the character."""


_SPEECH = re.compile(r'"[^"\n]*"|\u201c[^\u201d\n]*\u201d')


def _outside_speech(text: str, fn) -> str:
    """Apply fn only outside "speech", so 'quotes' inside dialogue are never taken for thoughts."""
    out, last = [], 0
    for m in _SPEECH.finditer(text):
        out.append(fn(text[last:m.start()]))
        out.append(m.group(0))
        last = m.end()
    out.append(fn(text[last:]))
    return "".join(out)


def is_gm_message(text: str) -> bool:
    t = (text or "").lstrip()
    return t.startswith("/") and not t.lower().startswith("/roll")


def strip_thoughts(text: str) -> str:
    """The text without the character's thoughts (for the tracker, memories and anything NPCs could see)."""
    if is_gm_message(text):
        return ""
    out = _outside_speech(text or "", lambda part: THOUGHT.sub("", part))
    return re.sub(r"[ \t]{2,}", " ", out).strip()


def thoughts(text: str) -> list[str]:
    found: list[str] = []
    _outside_speech(text or "", lambda part: found.extend(m.group(1).strip() for m in THOUGHT.finditer(part)) or part)
    return found


def for_model(text: str) -> str:
    """The player's message as the model sees it: thoughts and GM messages become explicit tags."""
    t = text or ""
    if is_gm_message(t):
        return f"[message to the GM: {t.lstrip()[1:].strip()}]"
    return _outside_speech(t, lambda part: THOUGHT.sub(lambda m: f"[thought: {m.group(1).strip()}]", part))
