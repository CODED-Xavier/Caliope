"""The arsenal: named techniques and spells, remembered for the player and for every character.

The player names a technique in brackets, shounen style: `[Chou no Mai - Manabiki]`. The Aedo marks a character's
named move with `[[move: Lilia | Crimson Fang]]` on its own line, right before it happens; the app takes the tag out,
shows the name as a call-out (**『Crimson Fang』**) and keeps it. Each technique keeps its owner, a short description
(what it looked like the first time), the power the owner had then (Beginner, Expert (Mid), 4-Circle…) and how many
times it was used. The list goes back to the Aedo so the same move comes back with the same name and look, its
strength following its user's current power.

state["arsenal"] = {owner name: [{name, desc, tier, uses}]}
"""
from __future__ import annotations

import re

MAX_PER_OWNER = 40
DESC_LEN = 220

# Lumencia-style power words (sword aura tiers, magic circles, divinity, unholy); other cards' words pass through
TIER = re.compile(
    r"\b(Beginner|Expert\s*\((?:Low|Mid|Supreme)\)|Master\s*\((?:Initiate|Adept|Apex)\)|[1-9]\s*-\s*Circle|"
    r"Acolyte|Blessed\s*\((?:Low|Mid|High)\)|Sanctified\s*\((?:Initiate|Adept|Apex)\)|Saint(?:ess)?|Tainted|"
    r"Corrupted\s*\((?:Low|Mid|High)\)|Defiled\s*\((?:Initiate|Adept|Apex)\)|Expert\s+(?:Low|Mid|Supreme)|"
    r"Master\s+(?:Initiate|Adept|Apex)|Grade\s*[1-4]|Special Grade|Level\s*\d{1,2})(?!\w)", re.I)
NOT_A_MOVE = re.compile(r"^\s*(override|ooc|gm|note|aside|system|info|roll|/)\b|^\s*[\d\s+\-dD×x*]+\s*$", re.I)
MOVE_TAG = re.compile(r"\[\[\s*move\s*:\s*([^|\]\n]{1,60})\|\s*([^\]\n]{1,80})\]\]", re.I)

RULES = (
    "## Named techniques and spells (the app keeps each character's arsenal)\n"
    "- When a character uses a NAMED technique, signature move or spell, write  [[move: Character | Technique name]]  on "
    "its own line right before it happens, then show it. The app turns it into a call-out and remembers it.\n"
    "- Reuse a character's known techniques (listed in the GM notes) with the same name and the same look. You may "
    "create a new one for a character when the moment calls for it (a rival in a spar, a teacher's demonstration): "
    "name it in the style of the character and their land.\n"
    "- A technique's strength and flavour follow its user's CURRENT power: their tier, Circle or aura level (both, for a "
    "Dual-Pather). A novice's technique is a sharpened basic form; a master's version of the same art is devastating. "
    "As the user grows, the same move grows with them.\n"
    "- The player names their own techniques in [brackets]. Never use a technique for the player's character."
)


def _clean(text: str) -> str:
    text = re.sub(r"\[\[[^\]]*\]\]", " ", text)
    text = re.sub(r"[*_`#>]+", "", text)
    return re.sub(r"\s+", " ", text).strip(" -–—:")


def tier_in(text: str) -> str:
    m = TIER.search(text or "")
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def _book(state: dict) -> dict:
    book = state.get("arsenal")
    if not isinstance(book, dict):
        book = {}
        state["arsenal"] = book
    return book


def record(state: dict, owner: str, name: str, desc: str = "", tier: str = "") -> dict | None:
    """Add a technique, or count one more use of a known one (its first description stays)."""
    owner, name = str(owner or "").strip()[:60], str(name or "").strip()[:80]
    if not owner or not name:
        return None
    moves = _book(state).setdefault(owner, [])
    known = next((m for m in moves if m["name"].lower() == name.lower()), None)
    if known:
        known["uses"] = int(known.get("uses") or 0) + 1
        if tier:
            known["tier"] = tier
        if desc and not known.get("desc"):
            known["desc"] = desc[:DESC_LEN]
        return {**known, "owner": owner, "new": False}
    if len(moves) >= MAX_PER_OWNER:
        return None
    move = {"name": name, "desc": _clean(desc)[:DESC_LEN], "tier": tier, "uses": 1}
    moves.append(move)
    return {**move, "owner": owner, "new": True}


def player_moves(text: str) -> list[tuple[str, str]]:
    """`[Chou no Mai - Manabiki]` in the player's message: (name, what the message shows around it)."""
    out: list[tuple[str, str]] = []
    for m in re.finditer(r"(?<!\[)\[([^\[\]\n]{2,60})\](?!\])", text or ""):
        name = m.group(1).strip()
        if NOT_A_MOVE.search(name) or ":" in name or not re.search(r"[A-Za-zÀ-ÿ]", name):
            continue
        after = _clean(text[m.end():m.end() + 400])
        before = _clean(text[max(0, m.start() - 300):m.start()])
        out.append((name, after or before))
    return out[:4]


def _owner(raw: str, npcs: list[dict]) -> str:
    raw = raw.strip()
    low = raw.lower()
    for n in npcs:
        name = n.get("name") or ""
        if name.lower() == low:
            return name
    for n in npcs:  # "Lilia" for "Lilia Valenheart", "Yanagi" for "Professor Yanagi"
        words = (n.get("name") or "").lower().split()
        if low in words or (words and low.split()[0] in words and len(low) > 2):
            return n["name"]
    return raw


def take_from_reply(reply: str, npcs: list[dict], player: str) -> tuple[str, list[tuple[str, str, str]]]:
    """Take the [[move: …]] tags out of the reply: (reply with call-outs, [(owner, name, desc)])."""
    found: list[tuple[str, str, str]] = []

    def swap(m):
        owner, name = _owner(m.group(1), npcs), m.group(2).strip()
        if player and owner.lower() == player.lower():
            return f"**『{name}』**"  # the Aedo never acts for the player: shown, not kept
        rest = reply[m.end():m.end() + 500]
        found.append((owner, name, _clean(rest.split("\n\n")[0] if rest.strip() else rest)))
        return f"**『{name}』**"

    reply = MOVE_TAG.sub(swap, reply)
    reply = re.sub(r"\[\[\s*move\s*:\s*([^\]|\n]{1,80})\]\]", lambda m: f"**『{m.group(1).strip()}』**", reply, flags=re.I)  # no owner
    return reply, found


def note_player(state: dict, text: str) -> list[dict]:
    player = (state.get("player") or {}).get("name") or "Player"
    tier = tier_in(" ".join(str(v) for v in (state.get("card_status") or {}).values()) if isinstance(state.get("card_status"), dict) else "")
    return [r for r in (record(state, player, name, desc, tier) for name, desc in player_moves(text)) if r]


def note_reply(state: dict, reply: str, npcs: list[dict]) -> tuple[str, list[dict]]:
    player = (state.get("player") or {}).get("name") or ""
    reply, found = take_from_reply(reply, npcs, player)
    by_name = {n["name"]: n for n in npcs}
    done = []
    for owner, name, desc in found:
        npc = by_name.get(owner) or {}
        got = record(state, owner, name, desc, tier_in(npc.get("description") or ""))
        if got:
            done.append(got)
    return reply, done


def prompt_list(state: dict, recent: list[str], player: str, limit: int = 12) -> str:
    """The arsenal of the player and of the characters named in the last messages."""
    book = state.get("arsenal") if isinstance(state.get("arsenal"), dict) else {}
    if not book:
        return ""
    text = " ".join(recent).lower()
    owners = [o for o in book if o == player or any(w in text for w in o.lower().split() if len(w) > 2)]
    lines = []
    for owner in owners:
        moves = sorted(book[owner], key=lambda m: -int(m.get("uses") or 0))[:limit]
        if not moves:
            continue
        who = f"{owner} (the player)" if owner == player else owner
        lines.append(f"- {who}: " + "; ".join(
            f"『{m['name']}』" + (f" ({m['tier']})" if m.get("tier") else "") + (f": {m['desc'][:120]}" if m.get("desc") else "")
            for m in moves))
    return ("## Known techniques of the characters here (reuse them with the same name and look)\n" + "\n".join(lines)) if lines else ""


def normalize(raw) -> dict:
    out: dict = {}
    for owner, moves in list(raw.items() if isinstance(raw, dict) else [])[:80]:
        good = []
        for m in moves if isinstance(moves, list) else []:
            if isinstance(m, dict) and str(m.get("name") or "").strip():
                try:
                    uses = max(0, int(m.get("uses") or 0))
                except (TypeError, ValueError):
                    uses = 0
                good.append({"name": str(m["name"]).strip()[:80], "desc": str(m.get("desc") or "")[:400],
                             "tier": str(m.get("tier") or "")[:40], "uses": uses})
        if good and str(owner).strip():
            out[str(owner).strip()[:60]] = good[:MAX_PER_OWNER]
    return out


def edit(state: dict, change: dict) -> dict:
    """The Arsenal tab: add, edit or forget a technique."""
    op = change.get("op")
    owner = str(change.get("owner") or "").strip()
    name = str(change.get("name") or "").strip()
    book = _book(state)
    if op == "add":
        if not owner or not name:
            raise ValueError("A technique needs its owner and a name.")
        got = record(state, owner, name, str(change.get("desc") or ""), str(change.get("tier") or ""))
        if got and not got["new"]:
            got_move = next(m for m in book[owner] if m["name"].lower() == name.lower())
            got_move["uses"] -= 1  # adding by hand is not a use
        return state
    moves = book.get(owner) or []
    move = next((m for m in moves if m["name"] == name), None)
    if move is None:
        raise ValueError(f"{owner} has no technique called {name}.")
    if op == "delete":
        moves.remove(move)
        if not moves:
            book.pop(owner, None)
    elif op == "edit":
        for key, size in (("name", 80), ("desc", 400), ("tier", 40)):
            if key in change:
                value = str(change[key] or "").strip()[:size]
                if key == "name" and not value:
                    raise ValueError("A technique needs a name.")
                move[key] = value
    else:
        raise ValueError("Unknown change.")
    return state
