"""Ability checks and saving throws asked for by the GM, rolled by the app.

When a reply says "Make a DEX (Stealth) check, DC 13", the app finds it, shows a button, takes the right bonus
from the sheet (ability modifier + proficiency when the skill is on the sheet), rolls and tells the GM the exact
result ("17 vs DC 13: success"). No maths for the player, and the GM cannot bend the result.
"""
from __future__ import annotations

import re

from .util import as_int

ABILITIES = {
    "STR": ("str", "strength", "força", "forca"),
    "DEX": ("dex", "dexterity", "destreza"),
    "CON": ("con", "constitution", "constituição", "constituicao"),
    "INT": ("int", "intelligence", "inteligência", "inteligencia"),
    "WIS": ("wis", "wisdom", "sabedoria"),
    "CHA": ("cha", "charisma", "carisma"),
}
SKILLS = {  # skill: (ability, other names)
    "Acrobatics": ("DEX", ("acrobacia",)), "Animal Handling": ("WIS", ("lidar com animais", "adestrar animais")),
    "Arcana": ("INT", ("arcanismo",)), "Athletics": ("STR", ("atletismo",)), "Deception": ("CHA", ("enganação", "enganacao")),
    "History": ("INT", ("história", "historia")), "Insight": ("WIS", ("intuição", "intuicao")),
    "Intimidation": ("CHA", ("intimidação", "intimidacao")), "Investigation": ("INT", ("investigação", "investigacao")),
    "Medicine": ("WIS", ("medicina",)), "Nature": ("INT", ("natureza",)), "Perception": ("WIS", ("percepção", "percepcao")),
    "Performance": ("CHA", ("atuação", "atuacao")), "Persuasion": ("CHA", ("persuasão", "persuasao")),
    "Religion": ("INT", ("religião", "religiao")), "Sleight of Hand": ("DEX", ("prestidigitação", "prestidigitacao")),
    "Stealth": ("DEX", ("furtividade",)), "Survival": ("WIS", ("sobrevivência", "sobrevivencia")),
}
TRIGGER = re.compile(r"\b(checks?|saving throws?|saves?|rolls?|teste|testes|salvaguarda|resistência|resistencia|rolagem|role)\b", re.I)
DC = re.compile(r"\b(?:DC|CD|difficulty|dificuldade)\s*[:=]?\s*(\d{1,2})\b", re.I)
MAX_CHECKS = 3


def _find_ability(text: str) -> str | None:
    low = text.lower()
    for abbr, names in ABILITIES.items():
        for n in names:
            if re.search(rf"(?<![\w]){re.escape(n)}(?![\w])", low):
                if n in ("int", "con") and not re.search(rf"\b{n}\b(?=\s*[\(\)/,]|\s+(?:check|save|saving|teste))", low) \
                        and not re.search(rf"\b{n.upper()}\b", text):
                    continue  # "int"/"con" as ordinary words only count when written like an ability
                return abbr
    return None


def _find_skill(text: str) -> str | None:
    low = text.lower()
    for skill, (_, other) in SKILLS.items():
        if any(re.search(rf"(?<![\w]){re.escape(n)}(?![\w])", low) for n in (skill.lower(), *other)):
            return skill
    return None


def find_checks(reply: str) -> list[dict]:
    """The rolls the GM asked for in this reply, in order (at most three)."""
    out: list[dict] = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", reply or ""):
        if not TRIGGER.search(sentence):
            continue
        skill = _find_skill(sentence)
        ability = _find_ability(sentence) or (SKILLS[skill][0] if skill else None)
        if not ability:
            continue
        save = bool(re.search(r"\b(sav(e|es|ing)|salvaguarda|resist[eê]ncia)\b", sentence, re.I)) and not skill
        dc_m = DC.search(sentence)
        check = {"ability": ability, "skill": skill or "", "kind": "save" if save else "check",
                 "dc": int(dc_m.group(1)) if dc_m else None}
        if check not in out:
            out.append(check)
        if len(out) >= MAX_CHECKS:
            break
    return out


def ability_score(stats: dict, ability: str):
    for key, value in (stats or {}).items():
        if key.upper() == ability or key.lower() in ABILITIES[ability]:
            return value
    return None


def bonus_for(state: dict, check: dict) -> tuple[int, str]:
    """(bonus, how it was made) from the player's sheet."""
    p = state.get("player") or {}
    score = ability_score(p.get("stats") or {}, check["ability"])
    mod = (as_int(score, 10) - 10) // 2 if score is not None else 0
    prof = 2 + max(0, as_int(p.get("level", 1), 1) - 1) // 4
    have = {str(s).strip().lower() for s in p.get("skills") or []}
    proficient = False
    if check["kind"] == "save":
        names = {f"{check['ability'].lower()} save", f"{check['ability'].lower()} saving throw"} | {
            f"{n} save" for n in ABILITIES[check["ability"]]} | {f"{n} saving throw" for n in ABILITIES[check["ability"]]}
        proficient = bool(have & names)
    elif check["skill"]:
        proficient = check["skill"].lower() in have or any(n in have for n in SKILLS[check["skill"]][1])
    total = mod + (prof if proficient else 0)
    how = f"{check['ability']} {mod:+d}" + (f", proficient {prof:+d}" if proficient else "")
    return total, how


def label(check: dict) -> str:
    what = check["skill"] or check["ability"]
    kind = "saving throw" if check["kind"] == "save" else "check"
    return f"{what} {kind}" + (f" (DC {check['dc']})" if check.get("dc") else "")


def roll_line(dice, state: dict, check: dict, mode: str = "") -> str:
    """The message sent to the GM: the verified roll and, with a DC, success or failure."""
    bonus, how = bonus_for(state, check)
    word = {"advantage": " advantage", "disadvantage": " disadvantage"}.get(mode, "")
    r = dice.roll(f"1d20{bonus:+d}{word}" if bonus else f"1d20{word}")
    tag = {"advantage": ", advantage", "disadvantage": ", disadvantage"}.get(r.mode, "")
    rolls = next((t["rolls"] for t in r.terms if t["kind"] == "dice"), [])
    shown = "/".join(str(x) for x in rolls)
    line = f"\U0001F3B2 {label({**check, 'dc': None})} ({how}{tag}): d20[{shown}] {bonus:+d} → **{r.total}**"
    if check.get("dc"):
        ok = r.total >= check["dc"]
        line += f" vs DC {check['dc']} → " + ("✅ Success" if ok else "❌ Failure")
    if r.crit:
        line += " (natural 20!)"
    elif r.fumble:
        line += " (natural 1!)"
    return line
