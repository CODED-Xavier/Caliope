"""Cheap checks done by code that decide whether the tracker (a second, slower AI call) is needed this turn.

The tracker looks for changes: gold, items, wounds, quests, travel, new characters, time. A turn of pure talk
almost never has any, so on such turns the app skips it (the reply is ready seconds sooner) and lets the tracker
read those exchanges together a turn or two later, so memories and relationships are still caught.
"""
from __future__ import annotations

import re

from .util import STOPWORDS

CHANGE_WORDS = re.compile(
    r"\b("
    # money and trade
    r"gold|coins?|silver|copper|platinum|gp|sp|cp|pay|pays|paid|buy|buys|bought|sell|sells|sold|price|costs?|reward|bribe|"
    r"ouro|moedas?|prata|cobre|pag[aoue]\w*|compr\w*|vend\w*|preço|custa|recompensa|suborno|"
    # items
    r"gives?|gave|hands? (?:you|over)|takes?|took|receive[sd]?|picks? up|loot\w*|steals?|stole|drops?|dropped|potions?|"
    r"scrolls?|inventory|equips?|wields?|drinks?|consumes?|"
    r"entreg\w*|receb\w*|peg[aoue]\w*|saque\w*|roub\w*|poções?|pergaminho|inventário|bebe\w*|"
    # harm and healing
    r"damage|wound\w*|hurt|bleed\w*|injur\w*|heal\w*|poison\w*|stabs?|slash\w*|bitten|burn(?:s|ed)?|"
    r"dano|ferid\w*|machuc\w*|sangr\w*|cura\w*|veneno|envenen\w*|"
    # quests
    r"quests?|missions?|tasks?|jobs?|bounty|contract|missão|missões|tarefa|contrato|"
    # travel and places
    r"arriv\w*|enter\w*|leav\w*|travel\w*|journey\w*|reach\w*|head(?:s|ed)? (?:to|for|toward)|walk(?:s|ed)? (?:to|into)|"
    r"chega\w*|entr[ao]\w*|sa[ií]\w*|viaj\w*|parte\w* para|"
    # time
    r"hours? later|next (?:morning|day)|sleeps?|slept|nightfall|dawn|sunrise|sunset|horas depois|dormi\w*|amanhecer|anoitecer"
    r")\b", re.I)
NAMED = re.compile(r"\b(?:named|called|calls? (?:himself|herself|themselves)|introduces? (?:himself|herself)|chamad[oa]|se apresenta)\b", re.I)
CAPITAL = re.compile(r"\b([A-Z\u00C0-\u00DD][a-z\u00E0-\u00FF]{2,})\b")
COMMON = STOPWORDS | {"not", "yes", "now", "then", "still", "just", "even", "only", "but", "well", "perhaps", "maybe", "why",
                      "how", "after", "before", "behind", "there", "here", "while", "suddenly", "finally", "instead",
                      "lord", "lady", "sir", "master", "mistress", "god", "gods", "não", "sim", "então",
                      "ainda", "depois", "antes", "aqui", "ali", "talvez", "senhor", "senhora", "deus"}


def needs_tracking(player_text: str, reply: str, known: list[str], resources: list[str] | None = None) -> bool:
    """True when the exchange probably changed something the tracker records."""
    text = f"{player_text}\n{reply}"
    if CHANGE_WORDS.search(text) or NAMED.search(reply or ""):
        return True
    low = text.lower()
    if any(re.search(rf"\b{re.escape(r.lower())}\b", low) for r in resources or []):
        return True  # the story mentions the player's Mana, Aura...
    names = {w.lower() for n in known for w in re.findall(r"\w+", n)}
    unknown = [w for w in CAPITAL.findall(reply or "") if w.lower() not in names and w.lower() not in COMMON]
    counts: dict[str, int] = {}
    for w in unknown:
        counts[w] = counts.get(w, 0) + 1
    return any(c >= 2 for c in counts.values())  # a new name used twice: probably a new character or place


def quiet_minutes(player_text: str, reply: str) -> int:
    """How long a turn of talk takes in the story when the tracker did not run (about 40 spoken words a minute)."""
    words = len(re.findall(r"\w+", f"{player_text} {reply}"))
    return max(2, min(15, round(words / 40)))
