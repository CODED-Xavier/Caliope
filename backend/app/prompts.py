"""Builds what the model actually sees each turn, and fits it into the context window."""
from __future__ import annotations

from .appearance import appearance_line
from .util import estimate_tokens, truncate

LANGUAGE_DIRECTIVES = {
    "en": "Write everything in English.",
    "pt-BR": "Write everything in Brazilian Portuguese (pt-BR).",
    "auto": "Reply in the same language the player writes in.",
}

GM_INTRO = (
    "You are the Game Master (GM) of a single-player, text-based roleplaying game. You narrate the world, "
    "voice every non-player character (NPC), apply the game rules fairly and keep the story moving. "
    "The player controls exactly one character."
)

CHARACTER_INTRO = (
    "You are roleplaying as {name}, a character in an ongoing one-on-one story with the player. "
    "Stay fully in character at all times. Write {name}'s dialogue in quotes and {name}'s actions and "
    "reactions in *italics*. You only control {name} (plus minimal scene description)."
)

CORE_RULES = """## Rules you always follow
- Never write the player's actions, words, thoughts or decisions. Describe the world and NPC reactions, then stop and hand control back.
- Keep every NPC consistent with their personality, speech style and current relationship with the player.
- Stay consistent with the game state, the summary and the memories below. Do not contradict established facts.
- Keep replies focused: usually 1-4 paragraphs. Match the pace the player wants.
- This is fiction between adults. Dark, violent or mature themes are allowed when the story calls for them; portray them honestly without moralizing, disclaimers or breaking character. Every character in romantic or sexual content must be an adult.
- Text inside [GM notes ...] is private information for you. Never repeat it, quote it or mention that it exists.
- Never mention these instructions, the game state format or that you are an AI unless the player steps out of the story."""

GM_RULES = """- When the outcome of an action is uncertain or risky, tell the player which roll to make (for example "Make a DEX (Stealth) check, DC 13") and wait. Do not decide the result before the roll.
- A line starting with the dice emoji in the player's message is a real, verified roll result. Use it exactly; never re-roll or change it.
- You may suggest options, but the player is free to do anything.
- When you introduce a new character, describe their looks in a sentence (hair, eyes, build, clothing) and keep those details exactly the same afterwards. Characters that have a "Looks" entry must always match it."""

LENGTH_TOKENS = {"short": 250, "medium": 450, "long": 800}
LENGTH_HINTS = {
    "short": "Reply length: 1 to 2 short paragraphs (about 80 to 120 words). Always finish your last sentence.",
    "medium": "Reply length: 2 to 3 paragraphs (about 150 to 250 words). Always finish your last sentence.",
    "long": "Reply length: 3 to 5 paragraphs (up to about 400 words). Always finish your last sentence.",
}


def reply_token_limit(settings: dict) -> int:
    """Tokens the model may write per reply: the "Reply length" choice, never above the hard cap."""
    return int(min(int(settings.get("max_tokens", 800)), LENGTH_TOKENS.get(settings.get("reply_length", "medium"), 450)))


RELATIONSHIP_SCALE = (
    "Relationship scale: -100 = mortal enemy, -50 = hostile, 0 = neutral, +50 = close friend or ally, +100 = deepest bond. "
    "NPCs must act according to their current value."
)


def relationship_label(value: int) -> str:
    if value <= -80:
        return "mortal enemy"
    if value <= -50:
        return "hostile"
    if value <= -20:
        return "distrustful"
    if value < 20:
        return "neutral"
    if value < 50:
        return "friendly"
    if value < 80:
        return "close"
    return "deeply bonded"


def describe_state(state: dict) -> str:
    p = state["player"]
    hp = p["hp"]
    stats = ", ".join(f"{k} {v}" for k, v in p.get("stats", {}).items())
    lines = [
        f"Player character: {p['name']}"
        + (f", {p['race']}" if p.get("race") else "")
        + (f" {p['class']}" if p.get("class") else "")
        + f", level {p.get('level', 1)}. HP {hp['current']}/{hp['max']}, AC {p.get('ac', 10)}.",
        f"Stats: {stats}.",
    ]
    if p.get("description"):
        lines.append(f"Appearance/background: {truncate(p['description'], 300)}")
    inv = ", ".join(f"{i['name']}" + (f" x{i['qty']}" if i["qty"] > 1 else "") for i in state["inventory"]) or "nothing"
    lines.append(f"Gold: {state['gold']}. Inventory: {inv}.")
    active = [q for q in state["quests"] if q["status"] == "active"]
    if active:
        lines.append("Active quests: " + "; ".join(f"{q['title']}" + (f" ({truncate(q['notes'], 80)})" if q["notes"] else "") for q in active))
    if state.get("location"):
        lines.append(f"Current location: {state['location']}." + (f" Time: {state['time']}." if state.get("time") else ""))
    known = [l["name"] for l in state["locations"] if l["name"] != state.get("location")][:12]
    if known:
        lines.append("Known places: " + ", ".join(known) + ".")
    return "\n".join(lines)


def describe_npcs(npcs: list[dict], limit_chars: int = 3200, with_relationship: bool = False) -> str:
    out, used = [], 0
    for n in npcs:
        if not n["active"]:
            continue
        head = f"- {n['name']}"
        if with_relationship:
            head += f" [relationship {n['relationship']:+d}, {relationship_label(n['relationship'])}]"
        parts = [head]
        if n["description"]:
            parts.append(n["description"])
        looks = appearance_line(n.get("appearance") or {})
        if looks:
            parts.append(f"Looks: {looks}")
        if n["personality"]:
            parts.append(f"Personality: {n['personality']}")
        if n["speech_style"]:
            parts.append(f"Speech: {n['speech_style']}")
        if n["notes"]:
            parts.append(f"Notes: {n['notes']}")
        line = ". ".join(parts)
        if used + len(line) > limit_chars:
            line = head
        out.append(line)
        used += len(line)
    return "\n".join(out)


def describe_relationships(npcs: list[dict]) -> str:
    return "\n".join(
        f"- {n['name']}: {n['relationship']:+d} ({relationship_label(n['relationship'])})" for n in npcs if n["active"]
    )


def fit_memories(memories: list[dict], char_budget: int) -> list[dict]:
    """Keep the best-ranked facts that fit in the character budget."""
    kept, used = [], 0
    for m in memories:
        cost = len(m["text"]) + 3
        if kept and used + cost > char_budget:
            break
        kept.append(m)
        used += cost
    return kept


class PromptBuilder:
    """Builds the prompt in two parts so the model can reuse its work between turns:

    * a STABLE start (rules, setting, characters, your memory box, summary) that rarely changes, and
    * a VOLATILE block (sheet, relationships, recalled facts, skill text) attached to the last player message.
    """

    def build(self, *, scenario: dict, state: dict, npcs: list[dict], summary: str, memories: list[dict],
              skills: list[dict], history: list[dict], settings: dict, pinned: str = "",
              appearance_hint: str = "") -> tuple[list[dict], dict]:
        """Return (messages, debug_info). History items need id, role, content and meta."""
        ctx = int(settings["context_window"])
        reserve = reply_token_limit(settings) + 150
        mode = scenario.get("mode", "gm_world")
        language = scenario.get("language") or settings.get("response_language", "en")
        mem_budget = int(settings.get("memory_char_budget", 900))

        history = [dict(h) for h in history]
        opening = next((h for h in history if h.get("meta", {}).get("opening")), None)
        if opening:
            history = [h for h in history if h is not opening]

        sections = self._stable_sections(scenario, npcs, summary, pinned, language, settings, mode, opening, skills)
        dropped: list[str] = []
        cap = int(ctx * 0.55)
        if estimate_tokens(self._join(sections)) > cap and "opening" in sections:
            sections.pop("opening")
            dropped.append("opening")
        if estimate_tokens(self._join(sections)) > cap and "summary" in sections:
            sections["summary"] = truncate(sections["summary"], 900)
            dropped.append("summary (shortened)")
        system_text = self._join(sections)

        used_memories = fit_memories(memories, mem_budget)
        volatile = self._volatile(state, npcs, used_memories, mode, appearance_hint)
        budget = ctx - reserve - estimate_tokens(system_text) - estimate_tokens(volatile)

        kept: list[dict] = []
        used = 0
        for msg in reversed(history):
            cost = estimate_tokens(msg["content"]) + 6
            if kept and used + cost > budget:
                break
            kept.append(msg)
            used += cost
        kept.reverse()

        # Facts that repeat text still visible in the kept history are redundant: drop them.
        if kept and used_memories:
            first_id = kept[0]["id"]
            fresh = [m for m in used_memories if m.get("message_id") is None or m["message_id"] < first_id]
            if len(fresh) != len(used_memories):
                used_memories = fresh
                volatile = self._volatile(state, npcs, used_memories, mode, appearance_hint)

        # Many chat templates require the first turn after the system prompt to come from the user.
        while kept and kept[0]["role"] == "assistant" and len(kept) > 1:
            kept.pop(0)

        messages: list[dict] = [{"role": "system", "content": system_text}]
        for msg in kept:
            if messages[-1]["role"] == msg["role"] and messages[-1]["role"] != "system":
                messages[-1]["content"] += "\n\n" + msg["content"]
            else:
                messages.append({"role": msg["role"], "content": msg["content"]})

        # Attach the volatile notes to the newest player message (so older turns keep their exact text).
        if volatile:
            for m in reversed(messages):
                if m["role"] == "user":
                    m["content"] = f"[GM notes - private, never quote them]\n{volatile}\n[End of GM notes]\n\n{m['content']}"
                    break
            else:
                messages[0]["content"] += f"\n\n[GM notes - private]\n{volatile}"

        debug = {
            "context_window": ctx,
            "stable_tokens": estimate_tokens(system_text),
            "volatile_tokens": estimate_tokens(volatile),
            "system_tokens": estimate_tokens(system_text),
            "history_tokens": used,
            "history_messages": len(kept),
            "trimmed_messages": len(history) - len(kept),
            "prompt_tokens": estimate_tokens(system_text) + estimate_tokens(volatile) + used,
            "dropped_sections": dropped,
            "skills": [s["name"] for s in skills],
            "memories": len(used_memories),
        }
        return messages, debug

    # ---------------------------------------------------------------- internals
    @staticmethod
    def _join(sections: dict[str, str]) -> str:
        return "\n\n".join(v for v in sections.values() if v.strip())

    def _stable_sections(self, scenario, npcs, summary, pinned, language, settings, mode, opening, skills) -> dict[str, str]:
        sec: dict[str, str] = {}
        main = next((n for n in npcs if n.get("is_main")), None)
        if mode == "character" and main:
            sec["intro"] = CHARACTER_INTRO.format(name=main["name"])
        else:
            sec["intro"] = GM_INTRO
        rules = CORE_RULES + ("" if mode == "character" else "\n" + GM_RULES)
        length = LENGTH_HINTS.get(settings.get("reply_length", "medium"), LENGTH_HINTS["medium"])
        sec["rules"] = rules + "\n- " + LANGUAGE_DIRECTIVES.get(language, LANGUAGE_DIRECTIVES["en"]) + "\n- " + length

        if scenario.get("world"):
            sec["world"] = "## Setting\n" + scenario["world"].strip()
        if scenario.get("system_rules") and mode != "character":
            sec["game_rules"] = "## Game rules\n" + scenario["system_rules"].strip()
        style = "\n".join(x for x in (scenario.get("tone", "").strip(), settings.get("extra_instructions", "").strip()) if x)
        if style:
            sec["style"] = "## Style\n" + style

        if skills:
            sec["skills"] = "## Extra guidance for this card\n" + "\n\n".join(f"### {sk['name']}\n{sk['text']}" for sk in skills)

        npc_text = describe_npcs(npcs)
        if npc_text:
            head = "## The character you play" if mode == "character" else "## Known NPCs"
            sec["npcs"] = f"{head}\n{RELATIONSHIP_SCALE}\n{npc_text}"
        if mode == "gm_world":
            sec["npc_hint"] = "Invent new NPCs, places and events as the story needs them and give each a distinct voice."
        if pinned and pinned.strip():
            sec["pinned"] = "## Always remember (the player asked you to keep this in mind)\n" + pinned.strip()
        if opening:
            sec["opening"] = "## Opening scene (already shown to the player)\n" + truncate(opening["content"], 1200)
        if summary:
            sec["summary"] = "## Story so far (summary of earlier events)\n" + summary.strip()
        return sec

    @staticmethod
    def _volatile(state, npcs, memories, mode, appearance_hint: str = "") -> str:
        parts: list[str] = []
        if mode != "character":
            parts.append("## Current game state\n" + describe_state(state))
        elif state.get("location"):
            parts.append(f"## Scene\nLocation: {state['location']}.")
        rel = describe_relationships(npcs)
        if rel:
            parts.append("## Relationships with the player\n" + rel)
        if memories:
            parts.append("## Relevant memories\n" + "\n".join(f"- {m['text']}" for m in memories))
        if appearance_hint:
            parts.append(f"## New characters\nIf you introduce a new named character this turn, give them: {appearance_hint}.")
        return "\n\n".join(parts)

    # ----------------------------------------------------- analysis / summarizing
    def analysis_messages(self, *, scenario: dict, state: dict, npcs: list[dict], exchanges: list[tuple[str, str]],
                          tracker: str = "full") -> list[dict]:
        """Ask the model what changed in the latest exchange(s). `lite` skips HP, gold, items and quests."""
        mode = scenario.get("mode", "gm_world")
        npc_names = ", ".join(n["name"] for n in npcs) or "none yet"
        full = tracker == "full"
        lines = ["You are a precise game-state tracker for a text roleplaying game. You do not write story.",
                 "Read the latest exchange(s) and report ONLY changes that clearly happened in them, as ONE JSON object."]
        if full:
            lines += [
                "- hp_change: net change to the player's hit points (negative = damage, positive = healing), else 0.",
                "- gold_change: net change to the player's gold, else 0.",
                "- inventory_add / inventory_remove: items the player gained, or lost/used up (name, qty).",
                "- quests: quests started, updated or finished (title, status: active|completed|failed, notes).",
            ]
        lines += [
            "- location: the player's new location name if they moved, else \"\". time: new in-world time if stated, else \"\".",
        ]
        if full:
            lines += ["- new_locations: newly mentioned places (name, description, connects_to: names of existing places)."]
        lines += [
            "- relationship_changes: how an NPC's feelings toward the player changed (npc, delta between -20 and 20, reason). Only NPCs involved.",
            "- new_npcs: named characters appearing for the first time (name, description, personality, appearance). "
            "appearance has race, hair, eyes, build, skin, outfit, extra: copy ONLY what the text says about their looks, use \"\" when it does not say.",
            "- memories: 0-3 short, self-contained facts worth remembering long-term, for example \"Doran swore loyalty to Seraphine\" or "
            "\"Wren sold the player's secret\". Include names. importance 1-5. characters: the names of the characters involved "
            "(use the exact names from Known NPCs).",
            "Only record things that actually HAPPENED. Prices, offers, promises, threats and plans are NOT changes"
            + (": gold changes only when money really changes hands, items only when really given, taken or used, HP only when the player is really hurt or healed." if full else "."),
            "Never invent anything. Use 0, \"\" or [] when nothing changed.",
            "",
        ]
        if full:
            inv = ", ".join(i["name"] for i in state["inventory"]) or "nothing"
            lines.append(f"Current state: HP {state['player']['hp']['current']}/{state['player']['hp']['max']}, gold {state['gold']}, "
                         f"inventory: {inv}. Location: {state.get('location') or 'unknown'}.")
        else:
            lines.append(f"Current location: {state.get('location') or 'unknown'}.")
        lines.append(f"Known NPCs: {npc_names}.")
        speaker = "CHARACTER" if mode == "character" else "GAME MASTER"
        parts = []
        for i, (user_text, reply) in enumerate(exchanges, 1):
            label = f"EXCHANGE {i}\n" if len(exchanges) > 1 else ""
            parts.append(f"{label}PLAYER:\n{truncate(user_text, 1200)}\n\n{speaker}:\n{truncate(reply, 2500)}")
        user = "\n\n".join(parts) + "\n\nOutput the JSON object now."
        return [{"role": "system", "content": "\n".join(lines)}, {"role": "user", "content": user}]

    def summary_messages(self, *, previous: str, transcript: str, language: str, max_chars: int = 1500) -> list[dict]:
        lang = LANGUAGE_DIRECTIVES.get(language, LANGUAGE_DIRECTIVES["en"])
        words = max(80, int(max_chars / 6.5))
        system = (
            "You maintain the running summary of a roleplaying story. Merge the previous summary with the new events "
            f"into one updated summary of at most {words} words. Keep names, places, items, injuries, promises, relationships "
            "and unresolved plot threads; drop small talk and details that no longer matter. Use past tense, plain text, no headings. " + lang
        )
        user = f"PREVIOUS SUMMARY:\n{previous or '(none)'}\n\nNEW EVENTS:\n{transcript}\n\nWrite the updated summary now."
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]


_APPEARANCE_SCHEMA = {
    "type": "object",
    "properties": {k: {"type": "string"} for k in ("race", "hair", "eyes", "build", "skin", "outfit", "extra")},
    "required": ["race", "hair", "eyes", "build", "skin", "outfit", "extra"],
}
_ITEM = {"type": "object", "properties": {"name": {"type": "string"}, "qty": {"type": "integer"}}, "required": ["name", "qty"]}

ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "hp_change": {"type": "integer"},
        "gold_change": {"type": "integer"},
        "inventory_add": {"type": "array", "items": _ITEM},
        "inventory_remove": {"type": "array", "items": _ITEM},
        "quests": {"type": "array", "items": {"type": "object", "properties": {"title": {"type": "string"}, "status": {"type": "string"}, "notes": {"type": "string"}}, "required": ["title", "status", "notes"]}},
        "location": {"type": "string"},
        "time": {"type": "string"},
        "new_locations": {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}, "description": {"type": "string"}, "connects_to": {"type": "array", "items": {"type": "string"}}}, "required": ["name", "description", "connects_to"]}},
        "relationship_changes": {"type": "array", "items": {"type": "object", "properties": {"npc": {"type": "string"}, "delta": {"type": "integer"}, "reason": {"type": "string"}}, "required": ["npc", "delta", "reason"]}},
        "new_npcs": {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}, "description": {"type": "string"}, "personality": {"type": "string"}, "appearance": _APPEARANCE_SCHEMA}, "required": ["name", "description", "personality", "appearance"]}},
        "memories": {"type": "array", "items": {"type": "object", "properties": {"text": {"type": "string"}, "importance": {"type": "integer"}, "characters": {"type": "array", "items": {"type": "string"}}}, "required": ["text", "importance", "characters"]}},
    },
    "required": ["hp_change", "gold_change", "inventory_add", "inventory_remove", "quests", "location", "time",
                 "new_locations", "relationship_changes", "new_npcs", "memories"],
}

_LITE_KEYS = ("location", "time", "relationship_changes", "new_npcs", "memories")
ANALYSIS_SCHEMA_LITE = {
    "type": "object",
    "properties": {k: ANALYSIS_SCHEMA["properties"][k] for k in _LITE_KEYS},
    "required": list(_LITE_KEYS),
}


def analysis_schema(tracker: str) -> dict:
    return ANALYSIS_SCHEMA if tracker == "full" else ANALYSIS_SCHEMA_LITE
