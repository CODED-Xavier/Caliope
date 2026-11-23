"""Builds what the model actually sees each turn, and fits it into the context window."""
from __future__ import annotations

import re

from .appearance import appearance_line
from .combat import COMBAT_RULES, describe_combat
from .jukebox import MOODS
from .portraits import portrait_instructions
from .status import split_template
from .util import estimate_tokens, render_macros, truncate
from .writing import RULES as WRITING_RULES
from .writing import for_model
from .playerlore import always_section, triggered
from .worldtime import CALENDAR_RULES, gm_notes
from .resources import RESOURCE_RULES
from .resources import gm_notes as resource_notes
from .routes import planned_scene, route_section
from .places import places_section
from . import reputation
from .reputation import level, scale_text
from .adventure import adventure_background, scene_section

LANGUAGE_DIRECTIVES = {
    "en": "Write everything in English.",
    "pt-BR": "Write everything in Brazilian Portuguese (pt-BR).",
    "auto": "Reply in the same language the player writes in.",
}

LANGUAGE_REMINDERS = {
    "en": "Write in English: the narration AND every character's spoken lines.",
    "pt-BR": "Escreva em português do Brasil: a narração E todas as falas dos personagens, mesmo que mensagens anteriores "
             "estejam em inglês. (Write in Brazilian Portuguese: narration and every character's dialogue.)",
    "auto": "Write in the language of the player's last message: the narration AND every character's spoken lines.",
}


END_MARK = "THE END"


def story_sections(scenario: dict, macro=lambda t: t) -> dict[str, str]:
    """The card's own story frame: what the player knows, facts that never change, secrets, and how it ends."""
    from .scenarios import STORY_LENGTHS  # noqa: PLC0415
    out = {}
    if str(scenario.get("known_at_start") or "").strip():
        out["known_at_start"] = ("## What the player's character knows from the start\n" + macro(scenario["known_at_start"]).strip()
                                 + "\nAnything beyond this and what happened in the story so far, the character does not know.")
    if str(scenario.get("fixed_facts") or "").strip():
        out["fixed_facts"] = ("## Fixed facts (always true; never contradict them)\n" + macro(scenario["fixed_facts"]).strip())
    if str(scenario.get("secrets") or "").strip():
        out["secrets"] = ("## Secrets (the player discovers these only through play)\n" + macro(scenario["secrets"]).strip()
                          + "\nNever reveal a secret directly or hint at it unasked. If the player asks about one, characters refuse, "
                            "lie or truly don't know, according to who they are. Never invent a sudden event just to change the subject; "
                            "a secret is revealed only when the player earns it in the story (evidence, a confession, a clever question).")
    length = STORY_LENGTHS.get(str(scenario.get("length") or "open"), "")
    ending = str(scenario.get("ending") or "").strip()
    if length or ending:
        out["ending"] = ("## How the story ends\n" + (f"This is {length}. " if length else "")
                         + (f"It ends when: {macro(ending)}. " if ending else "")
                         + f"Move the story toward that ending at a fitting pace. When the ending happens, write the final scene and "
                           f"finish that reply with a last line that says only: {END_MARK}")
    return out


APP_TURNS = ("\u2694\ufe0f Combat starts",)


def app_wrote(content: str) -> bool:
    """The newest "player" message was written by the app (a fight starting), not typed by the player."""
    return str(content or "").lstrip().startswith(APP_TURNS)


def closing_rules(player: str, language: str, app_turn: bool = False) -> str:
    """Sent with every message, last: never act for the player, and the story's language for every voice."""
    out = ("## Always\n"
           f"- {player} belongs to the player. Never write {player}'s words, actions, thoughts, feelings or decisions, not "
           "even small ones (a nod, a smile, an answer). The narrator and every character react only to what the player "
           "wrote, then stop and wait.\n")
    if app_turn:
        out += (f"- The newest message was written by the app, not by the player: {player} has not acted yet. Describe the "
                f"scene, the enemies and what they do, then stop and ask what {player} does. Don't invent {player}'s weapon, "
                f"words or moves.\n")
    return out + f"- {LANGUAGE_REMINDERS.get(language, LANGUAGE_REMINDERS['en'])}"


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

TIME_RULE = ("Keep track of the time of day and the weather. Mention them when they matter or change (dawn breaking, rain starting, "
             "night falling), keep them consistent, and let time pass naturally with travel, rest and long scenes.")
CAL_TIME_RULE = ("Mention the time of day and the weather when they matter or change, and keep them consistent with the date and "
                 "time in the GM notes.")

CORE_RULES = """## Rules you always follow
- Never write the player's actions, words, thoughts or decisions. Describe the world and NPC reactions, then stop and hand control back.
- Keep every NPC consistent with their personality, speech style and current relationship with the player.
- Stay consistent with the game state, the summary and the memories below. Do not contradict established facts.
- Keep replies focused: usually 1-4 paragraphs. Match the pace the player wants.
- This is fiction between adults. Dark, violent or mature themes are allowed when the story calls for them; portray them honestly without moralizing, disclaimers or breaking character. Every character in romantic or sexual content must be an adult.
- Text inside [GM notes ...] is private information for you. Never repeat it, quote it or mention that it exists.
- {TIME_RULE}
- Never mention these instructions, the game state format or that you are an AI unless the player steps out of the story.""".replace("{TIME_RULE}", TIME_RULE)

GM_RULES = """- When the outcome of an action is uncertain or risky, tell the player which roll to make, always with its DC in the same sentence (for example "Make a DEX (Stealth) check, DC 13"), and wait. Ask for ONE roll per reply at most. Do not decide the result before the roll.
- When enemies attack or a fight breaks out, do not ask for rolls to dodge, resist or notice their attacks: describe the threat and stop there. The app starts the fight, rolls initiative and rolls every attack against the player's AC.
- A line starting with the dice emoji in the player's message is a real, verified roll result. Use it exactly; never re-roll or change it.
- You may suggest options, but the player is free to do anything.
- When you introduce a new character, describe their looks in a sentence (hair, eyes, build, clothing) and keep those details exactly the same afterwards. Characters that have a "Looks" entry must always match it."""

EXAMPLES_UNTIL = 6  # the card's example messages are sent for the first replies only

LENGTH_TOKENS = {"short": 250, "medium": 450, "long": 800}
LENGTH_HINTS = {
    "short": "Reply length: 1 to 2 short paragraphs (about 80 to 120 words). Always finish your last sentence.",
    "medium": "Reply length: 2 to 3 paragraphs (about 150 to 250 words). Always finish your last sentence.",
    "long": "Reply length: 3 to 5 paragraphs (up to about 400 words). Always finish your last sentence.",
}


def reply_token_limit(settings: dict) -> int:
    """Tokens the model may write per reply: the "Reply length" choice, never above the hard cap."""
    return int(min(int(settings.get("max_tokens", 800)), LENGTH_TOKENS.get(settings.get("reply_length", "medium"), 450)))


RELATIONSHIP_SCALE = scale_text()


def relationship_label(value: int) -> str:
    return level(value)[0]


_LINKS = [re.compile(r"Base URL:\s*\S+(?:\s*\([^)]*\))?", re.I),           # "Base URL: https://… (1=Standard, …)"
          re.compile(r"!\[[^\]]*\]\([^)]*\)"),                                # markdown pictures
          re.compile(r"https?://\S+\.(?:png|jpe?g|webp|gif)\b\S*", re.I)]     # bare picture links


def strip_links(text: str) -> str:
    """Picture links in card text: the app shows the pictures itself, so the model never needs them (tokens saved)."""
    for rx in _LINKS:
        text = rx.sub("", text)
    return re.sub(r"[ \t]{2,}", " ", text)


def describe_state(state: dict, compact: bool = False) -> str:
    """`compact`: the card's own status block (sent too) already has the numbers and the bag; the player's looks are
    in the stable part of the prompt. Fewer tokens to read every turn."""
    p = state["player"]
    hp = p["hp"]
    stats = ", ".join(f"{k} {v}" for k, v in p.get("stats", {}).items())
    who = f"Player character: {p['name']}" + (f", {p['race']}" if p.get("race") else "") + (f" {p['class']}" if p.get("class") else "")
    if compact:
        lines = [who + "."]
    else:
        lines = [who + f", level {p.get('level', 1)}. HP {hp['current']}/{hp['max']}, AC {p.get('ac', 10)}.", f"Stats: {stats}."]
    if not compact:
        inv = ", ".join(f"{i['name']}" + (f" x{i['qty']}" if i["qty"] > 1 else "") for i in state["inventory"]) or "nothing"
        lines.append(f"Gold: {state['gold']}. Inventory: {inv}.")
    from .party import state_line
    if state_line(state):
        lines.append(state_line(state))
    active = [q for q in state["quests"] if q["status"] == "active"]
    if active:
        lines.append("Active quests: " + "; ".join(f"{q['title']}" + (f" ({truncate(q['notes'], 80)})" if q["notes"] else "") for q in active))
    scene = describe_scene(state)
    if scene:
        lines.append(scene)
    known = [l["name"] for l in state["locations"] if l["name"] != state.get("location")][:12]
    if known:
        lines.append("Known places: " + ", ".join(known) + ".")
    return "\n".join(lines)


def describe_scene(state: dict) -> str:
    bits = []
    if state.get("location"):
        bits.append(f"Current location: {state['location']}.")
    if state.get("time"):
        bits.append(f"Time: {state['time']}.")
    if state.get("weather"):
        bits.append(f"Weather: {state['weather']}.")
    return " ".join(bits)


def describe_player(state: dict, numbers: bool) -> str:
    """The player's character, near the top of the prompt so the model never forgets who they are."""
    p = state["player"]
    who = " ".join(x for x in (p.get("race", ""), p.get("class", "")) if x)
    lines = [f"Name: {p['name']}" + (f" ({who}" + (f", level {p.get('level', 1)})" if numbers else ")") if who else "")]
    if numbers and p.get("stats"):
        from .util import as_int
        stats = ", ".join(f"{k} {v} ({(as_int(v, 10) - 10) // 2:+d})" for k, v in p["stats"].items())
        lines.append(f"Abilities: {stats}")
    if p.get("skills"):
        lines.append("Skills: " + ", ".join(str(s) for s in p["skills"][:12]))
    for key, label in (("background", "Background"), ("description", "Appearance"), ("traits", "Personality")):
        if p.get(key):
            lines.append(f"{label}: {truncate(p[key], 900 if key == 'background' else 400)}")
    rule = ("Always call the player's character by this name and keep these details exactly. Their "
            + ("class, skills and abilities matter: let strengths shine and weaknesses show (a low STR character struggles to lift "
               "heavy things, a wizard understands magic, a fighter reads a fight)." if numbers else
               "background and personality matter: NPCs react to who they are and how they look."))
    return "## The player's character\n" + "\n".join(lines) + "\n" + rule


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
    """Each present character's level (what each level means is in the stable part: RELATIONSHIP_SCALE)."""
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


WINDOW_STEP = 6  # messages (3 rounds): see build()

SECTION_ORDER = [
    "intro", "rules", "writing", "card_system", "world", "card_description", "card_personality", "card_scenario", "known_at_start", "fixed_facts", "secrets", "ending", "route", "adventure", "places",
    "lore_always", "player_lore", "calendar", "resources", "game_rules", "house_rules", "style", "skills", "card_examples", "card_reminders", "card_overrides", "portraits", "npcs", "companions", "npc_hint",
    "player", "pinned", "opening", "cantos", "summary",
]


class PromptBuilder:
    """Builds the prompt in two parts so the model can reuse its work between turns:

    * a STABLE start (rules, setting, characters, your memory box, summary) that rarely changes, and
    * a VOLATILE block (sheet, relationships, recalled facts, skill text) attached to the last player message.
    """

    def build(self, *, scenario: dict, state: dict, npcs: list[dict], summary: str, memories: list[dict],
              skills: list[dict], history: list[dict], settings: dict, pinned: str = "",
              appearance_hint: str = "", lore: tuple[list[dict], list[dict]] = ([], []),
              status_due: bool | None = None, player_name: str = "", rules: list[dict] | None = None,
              house_rules: list[tuple[str, str]] | None = None, player_lore: list[dict] | None = None,
              app_status: str | None = None, cantos: str = "") -> tuple[list[dict], dict]:
        """Return (messages, debug_info). History items need id, role, content and meta."""
        ctx = int(settings["context_window"])
        reserve = reply_token_limit(settings) + 150
        mode = scenario.get("mode", "gm_world")
        language = scenario.get("language") or settings.get("response_language", "en")
        mem_budget = int(settings.get("memory_char_budget", 900))

        history = [dict(h) for h in history]
        for h in history:  # the round card's picture markers are for the screen only
            if "[[face:" in h.get("content", ""):
                h["content"] = re.sub(r"\n?\[\[face:[^\]\n]*\]\]", "", h["content"])
        opening = next((h for h in history if h.get("meta", {}).get("opening")), None)
        if opening:
            history = [h for h in history if h is not opening]

        # Characters only listed in the lorebook ("in_prompt" off) reach the model through their lorebook entry.
        card_name = scenario.get("name") or ""
        main = next((n for n in npcs if n.get("is_main")), None)
        macro = lambda t: render_macros(t or "", player_name or "the player", main["name"] if main else card_name)
        prompt_npcs = [n for n in npcs if n.get("in_prompt", True)]
        sections = self._stable_sections(scenario, prompt_npcs, summary, pinned, language, settings, mode, opening, skills)
        sections.update(self._card_sections(scenario, npcs, lore[0], macro, app_status is not None))
        from .party import prompt_section as companions_section
        team = companions_section(state, npcs, scenario)  # app/party.py: who travels with the player
        if team:
            sections["companions"] = team
        reminders = split_template((scenario.get("information") or {}).get("post_history") or "")[0]
        if reminders.strip():  # the same every turn: kept in the stable part, so it is read once, not every turn
            sections["card_reminders"] = "## Card reminders\n" + strip_links(macro(reminders)).strip()
        replies = sum(1 for h in history if h["role"] == "assistant" and not h.get("meta", {}).get("opening"))
        if "card_examples" in sections and (summary or replies >= EXAMPLES_UNTIL):
            sections.pop("card_examples")  # the story itself now shows the style; frees ~300-800 tokens for history
        sections["writing"] = WRITING_RULES
        cal = scenario.get("calendar") or {}
        cal_on = bool(cal.get("enabled") and cal.get("months"))
        if cal_on:
            sections["calendar"] = "## Calendar and time\n" + CALENDAR_RULES
            sections["rules"] = sections["rules"].replace(TIME_RULE, CAL_TIME_RULE)
        if player_lore:
            sections["player_lore"] = always_section(player_lore)
        if cantos:
            sections["cantos"] = cantos
        if places_section(scenario.get("places")):
            sections["places"] = places_section(scenario.get("places"))
        sections.update(story_sections(scenario, macro))
        route = scenario.get("route")
        if route_section(route):
            sections["route"] = route_section(route)
        adv = scenario.get("adventure") or {}
        if adventure_background(adv):
            sections["adventure"] = adventure_background(adv)
        if state.get("resources"):
            sections["resources"] = "## Resources\n" + RESOURCE_RULES
        if house_rules:
            sections["house_rules"] = "## House rules (they win over the rulebook)\n" + "\n\n".join(
                (f"{name}:\n" if len(house_rules) > 1 else "") + text for name, text in house_rules)
        kind = scenario.get("kind") or ("roleplay" if mode == "character" else "adventure")
        sections["player"] = describe_player(state, numbers=(kind == "adventure"))
        # Parts that change most often go last, so the model can reuse everything before them.
        sections = {k: sections[k] for k in sorted(sections, key=lambda k: SECTION_ORDER.index(k) if k in SECTION_ORDER else 50)}
        dropped: list[str] = []
        cap = int(ctx * 0.55)
        if estimate_tokens(self._join(sections)) > cap and "opening" in sections:
            sections.pop("opening")
            dropped.append("opening")
        if estimate_tokens(self._join(sections)) > cap and "cantos" in sections:
            sections["cantos"] = truncate(sections["cantos"], 1500)
            dropped.append("cantos (shortened)")
        if estimate_tokens(self._join(sections)) > cap and "summary" in sections:
            sections["summary"] = truncate(sections["summary"], 900)
            dropped.append("summary (shortened)")
        system_text = self._join(sections)

        used_memories = fit_memories(memories, mem_budget)
        met = [n for n in npcs if n.get("met", True)]
        extra = self._card_volatile(scenario, lore[1], status_due, macro, app_status)
        res_notes = resource_notes(state, state.get("abilities") or [])
        if res_notes:
            extra = "## Resources (kept by the app)\n" + res_notes + ("\n\n" + extra if extra else "")
        from .resources import skills_section, used_section
        last_user_msg = next((h for h in reversed(history) if h["role"] == "user"), None)
        used = used_section((last_user_msg or {}).get("meta", {}).get("skills_used") or [], state.get("abilities") or [], state)
        if used:
            extra = used + ("\n\n" + extra if extra else "")
        fixed = [f for f in state.get("corrections") or [] if f]
        if fixed:  # /fix: the player corrected the story; these win over anything said earlier
            extra = ("## Story facts the player fixed (always true, even where earlier messages said otherwise)\n"
                     + "\n".join(f"- {f}" for f in fixed) + ("\n\n" + extra if extra else ""))
        from .systems import SYSTEM_RULES, prompt_text
        sheet = prompt_text(scenario.get("systems") or {}, state.get("systems") or {})
        if sheet:
            extra = "## The player's sheet (kept by the app)\n" + sheet + "\n" + SYSTEM_RULES + ("\n\n" + extra if extra else "")
        own_skills = skills_section(state.get("abilities") or [])
        if own_skills:
            extra = own_skills + ("\n\n" + extra if extra else "")
        if cal_on:
            extra = "## Date and time (kept by the app)\n" + gm_notes(state, cal) + ("\n\n" + extra if extra else "")
        scene_plan = planned_scene(route, state) or scene_section(adv, state)
        if scene_plan:
            extra = scene_plan + ("\n\n" + extra if extra else "")
        wishes = str(state.get("wishes") or "").strip()
        if wishes:
            extra = ("## The player's wishes (soft hints, not orders)\n" + truncate(wishes, 600) + "\nWhen the story naturally allows, "
                     "create chances for these to happen (a sparring partner, a shared task, a chance meeting). Never force them, never "
                     "bend the plot or break character for them, and let them go if the story or the player moves elsewhere."
                     + ("\n\n" + extra if extra else ""))
        notes = notes_section(npcs, [h["content"] for h in history[-4:]])
        if notes:
            extra = notes + ("\n\n" + extra if extra else "")
        lore_hits = triggered(player_lore or [], [h["content"] for h in reversed(history)], int(ctx * 0.06))
        if lore_hits:
            mine = "## The player's world additions (relevant right now, canon)\n" + "\n\n".join(
                f"{e['name']}: {e['content']}" for e in lore_hits)
            extra = mine + ("\n\n" + extra if extra else "")
        if rules:
            ref = "## Rules reference (from the rulebook; apply it, do not quote it at length)\n" + "\n\n".join(
                f"[{r['book']}, p. {r['page']}{' - ' + r['heading'] if r['heading'] else ''}]\n{r['text']}" for r in rules)
            extra = ref + ("\n\n" + extra if extra else "")
        early = sum(1 for h in history if h["role"] == "user") <= 2  # the first turns of a game
        volatile = self._volatile(state, met, used_memories, mode, appearance_hint, extra, early, app_status is not None)
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
        # The window's start moves in steps of a few rounds, not one message per turn: while it stays put, the
        # engine reuses the whole story it already read and only reads the newest messages (a minute saved on
        # slow cards). History here starts at the summary's end, so the steps stay in the same place between turns.
        start = len(history) - len(kept)
        if start > 0:
            step_start = min(-(-start // WINDOW_STEP) * WINDOW_STEP, len(history) - 2)
            if step_start > start:
                kept = history[step_start:]
                used = sum(estimate_tokens(m["content"]) + 6 for m in kept)

        # Facts that repeat text still visible in the kept history are redundant: drop them.
        if kept and used_memories:
            first_id = kept[0]["id"]
            fresh = [m for m in used_memories if m.get("message_id") is None or m["message_id"] < first_id]
            if len(fresh) != len(used_memories):
                used_memories = fresh
                volatile = self._volatile(state, met, used_memories, mode, appearance_hint, extra, early, app_status is not None)

        # Many chat templates require the first turn after the system prompt to come from the user.
        while kept and kept[0]["role"] == "assistant" and len(kept) > 1:
            kept.pop(0)

        messages: list[dict] = [{"role": "system", "content": system_text}]
        for msg in kept:
            if msg["role"] == "user":
                msg = {**msg, "content": for_model(msg["content"])}
            if messages[-1]["role"] == msg["role"] and messages[-1]["role"] != "system":
                messages[-1]["content"] += "\n\n" + msg["content"]
            else:
                messages.append({"role": msg["role"], "content": msg["content"]})

        # The two rules small models forget most, repeated right next to the player's message (where they look most).
        last_user = next((m["content"] for m in reversed(kept) if m["role"] == "user"), "")
        volatile = (volatile + "\n\n" if volatile else "") + closing_rules(player_name or "the player's character", language,
                                                                          app_turn=app_wrote(last_user))

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
            "lore_entries": [e["name"] or (e["keys"][:1] or ["?"])[0] for e in lore[0] + lore[1]] + [e["name"] for e in lore_hits],
            "status_due": bool(status_due),
            "rules": [f"{r['book']} p.{r['page']} {r['heading']}".strip() for r in (rules or [])],
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
    def _card_sections(scenario: dict, npcs: list[dict], always_lore: list[dict], macro, app_status: bool = False) -> dict[str, str]:
        """Stable parts that come from an imported card: its long texts, always-on lore, portrait rules."""
        info = scenario.get("information") or {}
        sec: dict[str, str] = {}
        if info.get("system_prompt"):
            sec["card_system"] = "## Card instructions\n" + macro(info["system_prompt"]).strip()
        if info.get("description"):
            sec["card_description"] = "## Card\n" + macro(info["description"]).strip()
        if info.get("personality"):
            sec["card_personality"] = "## Personality\n" + macro(info["personality"]).strip()
        if info.get("scenario"):
            sec["card_scenario"] = "## Scenario\n" + macro(info["scenario"]).strip()
        if always_lore:
            sec["lore_always"] = "## World info\n" + "\n\n".join(macro(e["content"]).strip() for e in always_lore)
        if info.get("example_messages"):
            examples = macro(info["example_messages"]).replace("<START>", "").strip()
            sec["card_examples"] = "## Example of the writing style (not part of the story)\n" + truncate(examples, 3000)
        rules = []
        features = scenario.get("features") or {}
        if info and features.get("relationships", "app") == "app":
            rules.append("Relationships use the app's scale from -100 to +100 shown in the GM notes. Ignore any other "
                         "affinity scale the card mentions (for example -3 to +3) and never write affinity scores yourself.")
        if app_status:
            rules.append("Never write the INFO status block, even if the card asks for it: the app keeps it and shows it to the "
                         "player. Its current values are in the GM notes; follow the card's rules for them in the story.")
        elif info.get("status_every"):
            rules.append("Only write the INFO status block when the GM notes ask for it.")
        pics = portrait_instructions(npcs, scenario.get("mode", "gm_world"))
        if pics:
            rules.append("Use the portrait format below instead of any image-link format the card describes.")
            sec["portraits"] = pics
        if rules:
            sec["card_overrides"] = "## App rules (they win over the card)\n" + "\n".join(f"- {r}" for r in rules)
        return sec

    @staticmethod
    def _card_volatile(scenario: dict, triggered: list[dict], status_due: bool | None, macro, app_status: str | None = None) -> str:
        """Per-turn parts from a card: lorebook entries whose keywords came up, the card's reminders, the status block."""
        info = scenario.get("information") or {}
        parts: list[str] = []
        if triggered:
            parts.append("## World info (relevant right now)\n" + "\n\n".join(strip_links(macro(e["content"])).strip() for e in triggered))
        rules, template = split_template(info.get("post_history") or "")
        if app_status:
            parts.append("## Status (kept by the app; do not write it)\n" + app_status)
        elif template and status_due is not None:
            if status_due:
                parts.append("## Status block\nEnd THIS reply with the status block, exactly in this format:\n" + macro(template))
            else:
                parts.append("## Status block\nDo not write the INFO status block in this reply.")
        return "\n\n".join(parts)

    @staticmethod
    def _volatile(state, npcs, memories, mode, appearance_hint: str = "", extra: str = "", early: bool = False,
                  compact: bool = False) -> str:
        parts: list[str] = []
        fight = describe_combat(state.get("combat") or {})
        if fight:
            parts.append("## Combat (tracked by the app)\n" + fight + "\n" + COMBAT_RULES)
        if mode != "character":
            parts.append("## Current game state\n" + describe_state(state, compact))
        elif describe_scene(state):
            parts.append("## Scene\n" + describe_scene(state))
        rel = describe_relationships(npcs)
        if rel:
            parts.append("## Relationships with the player\n" + rel)
        if memories:
            parts.append("## Relevant memories\n" + "\n".join(f"- {m['text']}" for m in memories))
        if state.get("setup") == "app" and early:
            parts.append("## Character creation\nThe player already created their character (see \"The player's character\"). "
                         "Do not ask the card's character creation questions; weave their details into the scene naturally.")
        if appearance_hint:
            parts.append(f"## New characters\nIf you introduce a new named character this turn, give them: {appearance_hint}.")
        if extra:  # card reminders go last, closest to the player's message, as cards expect
            parts.append(extra)
        return "\n\n".join(parts)

    # ----------------------------------------------------- analysis / summarizing
    def analysis_messages(self, *, scenario: dict, state: dict, npcs: list[dict], exchanges: list[tuple[str, str]],
                          tracker: str = "full", calendar: dict | None = None, status_fields: str = "",
                          resource_line: str = "", language: str = "en") -> list[dict]:
        """Ask the model what changed in the latest exchange(s). `lite` skips HP, gold, items and quests."""
        mode = scenario.get("mode", "gm_world")
        npc_names = ", ".join(n["name"] for n in npcs) or "none yet"
        full = tracker == "full"
        lines = ["You are a precise game-state tracker for a text roleplaying game. You do not write story.",
                 "Read the latest exchange(s) and report ONLY changes that clearly happened in them, as ONE JSON object."]
        if language == "pt-BR":  # the update lines under each reply are read by the player
            lines.append("Write every free-text value (reasons, notes, item, quest and place names you make up) in Brazilian "
                         "Portuguese (pt-BR); keep names that already exist exactly as they are.")
        if full:
            lines += [
                "- hp_change: net change to the player's hit points (negative = damage, positive = healing), else 0.",
                "- gold_change: net change to the player's gold, else 0.",
                "- inventory_add / inventory_remove: items the player gained, or lost/used up (name, qty). Dropping an item or having it knocked away is NOT losing it: it stays unless someone takes it or it is destroyed.",
                "- quests: quests started, updated or finished (title, status: active|completed|failed, notes).",
            ]
        if calendar:
            lines += [
                "- location: the player's new location name if they moved, else \"\"."
                + ("" if calendar.get("climate", "temperate") != "none" else " weather: the new weather if it changed, else \"\"."),
                "- minutes_passed: how many in-story minutes the exchange took (a short talk 5, a meal 45, a walk across town 30, "
                "a night's sleep 480). Do not count time already stated in a line starting with \u23f3 (the app counted it).",
                "- appointments: future plans with a day that someone states (\"the festival is on Sunday\", \"meet me tomorrow at noon\"): "
                "text (what and who), when (the words used: \"Sunday\", \"tomorrow at noon\", \"in three days\"), days_from_now (your count). "
                "Only NEW ones; already planned: " + ("; ".join(e["text"] for e in state.get("events", [])[-8:]) or "none") + ".",
            ]
        else:
            lines += [
                "- location: the player's new location name if they moved, else \"\". time: the new time of day if it changed, else \"\". "
                "weather: the new weather if it changed, else \"\".",
            ]
        lines += [
            "- scene_mood: the feeling of the scene for background music, one of: " + ", ".join(MOODS) + ".",
        ]
        if status_fields:
            lines.append(status_fields)
        if resource_line:
            lines.append(resource_line)
        if full:
            lines += ["- new_locations: newly mentioned places (name, description, connects_to: names of existing places)."]
        lines += [
            reputation.tracker_line(),
            "- new_npcs: named characters appearing for the first time (name, description, personality, appearance). "
            "appearance has race, hair, eyes, build, skin, outfit, extra: copy ONLY what the text says about their looks, use \"\" when it does not say.",
            "- character_notes: 0-2 lasting things about ONE character that matter for how they treat the player: a promise made, "
            "a debt, a secret shared, a deal, a grudge or a change of heart (npc, note). Short, with the reason. Only when it really happened.",
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
        "weather": {"type": "string"},
        "scene_mood": {"type": "string", "enum": list(MOODS)},
        "new_locations": {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}, "description": {"type": "string"}, "connects_to": {"type": "array", "items": {"type": "string"}}}, "required": ["name", "description", "connects_to"]}},
        "relationship_changes": {"type": "array", "items": {"type": "object", "properties": {"npc": {"type": "string"}, "event": {"type": "string", "enum": list(reputation.EVENTS)}, "reason": {"type": "string"}}, "required": ["npc", "event", "reason"]}},
        "new_npcs": {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}, "description": {"type": "string"}, "personality": {"type": "string"}, "appearance": _APPEARANCE_SCHEMA}, "required": ["name", "description", "personality", "appearance"]}},
        "memories": {"type": "array", "items": {"type": "object", "properties": {"text": {"type": "string"}, "importance": {"type": "integer"}, "characters": {"type": "array", "items": {"type": "string"}}}, "required": ["text", "importance", "characters"]}},
        "character_notes": {"type": "array", "items": {"type": "object", "properties": {"npc": {"type": "string"}, "note": {"type": "string"}}, "required": ["npc", "note"]}},
    },
    "required": ["hp_change", "gold_change", "inventory_add", "inventory_remove", "quests", "location", "time", "weather", "scene_mood",
                 "new_locations", "relationship_changes", "new_npcs", "memories", "character_notes"],
}

_LITE_KEYS = ("location", "time", "weather", "scene_mood", "relationship_changes", "new_npcs", "memories", "character_notes")
ANALYSIS_SCHEMA_LITE = {
    "type": "object",
    "properties": {k: ANALYSIS_SCHEMA["properties"][k] for k in _LITE_KEYS},
    "required": list(_LITE_KEYS),
}


_APPOINTMENT = {"type": "object", "properties": {"text": {"type": "string"}, "when": {"type": "string"},
                                                "days_from_now": {"type": "integer"}}, "required": ["text", "when", "days_from_now"]}


def analysis_schema(tracker: str, calendar: bool = False, status: bool = False, resources: bool = False,
                    systems: bool = False) -> dict:
    base = ANALYSIS_SCHEMA if tracker == "full" else ANALYSIS_SCHEMA_LITE
    if not calendar and not status and not resources and not systems:
        return base
    props = dict(base["properties"])
    required = list(base["required"])
    if calendar:
        props.pop("time", None)
        required.remove("time")
        props["minutes_passed"] = {"type": "integer"}
        props["appointments"] = {"type": "array", "items": _APPOINTMENT}
        required += ["minutes_passed", "appointments"]
    if status:
        props["status_changes"] = {"type": "array", "items": {"type": "object", "properties": {
            "field": {"type": "string"}, "value": {"type": "string"}}, "required": ["field", "value"]}}
        required.append("status_changes")
    if resources:
        props["resource_changes"] = {"type": "array", "items": {"type": "object", "properties": {
            "resource": {"type": "string"}, "delta": {"type": "integer"}, "reason": {"type": "string"}},
            "required": ["resource", "delta", "reason"]}}
        required.append("resource_changes")
    if systems:  # the card's own sheet kept by the app (app/systems.py)
        props["system_changes"] = {"type": "array", "items": {"type": "object", "properties": {
            "stat": {"type": "string"}, "delta": {"type": "integer"}, "value": {"type": "string"}}, "required": ["stat"]}}
        required.append("system_changes")
    return {"type": "object", "properties": props, "required": required}


AEDO_MARK = "\u2712 "  # lines the Aedo added to a character's notes start with ✒


def notes_section(npcs: list[dict], recent: list[str], limit: int = 1200) -> str:
    """Notes (the player's and the Aedo's) about characters who are in the scene right now.

    Characters that are always in the prompt already carry their notes; this covers the ones that reach the model
    only through the lorebook (big casts), so a promise or a grudge is not forgotten."""
    text = " ".join(recent).lower()
    out, used = [], 0
    for n in npcs:
        if n.get("in_prompt", True) or not (n.get("notes") or "").strip():
            continue
        first = n["name"].split()[0].lower()
        if n["name"].lower() not in text and not re.search(rf"\b{re.escape(first)}\b", text):
            continue
        line = f"{n['name']}: " + "; ".join(x.strip().lstrip("\u2712").strip() for x in n["notes"].splitlines() if x.strip())
        line = truncate(line, 400)
        if used + len(line) > limit:
            break
        out.append(line)
        used += len(line)
    return ("## Notes about characters in this scene (promises, debts, feelings: keep them in mind)\n" + "\n".join(out)) if out else ""
