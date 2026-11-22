"""The card's INFO status block, written by the app instead of the AI.

Cards like Lumencia ask the AI to end replies with a status block (place, time, stats, items, relationships).
Writing it costs the model 100-300 tokens of output each time, and it often gets the numbers wrong.
Now the app fills it from the template:

- fields the app already knows (place, date and time, items, money, HP, quests, relationships) come straight
  from the game state;
- the card's own fields (Tier, EXP, Crowns...) are kept by the app in `state["card_status"]`, and the tracker
  only reports the ones that changed. A block the AI still writes by habit is read to update them.
"""
from __future__ import annotations

import re

from .status import split_status, split_template
from .util import truncate

KNOWN = [
    ("name", re.compile(r"^(name|nome|character|personagem)$", re.I)),
    ("location", re.compile(r"^(location|place|where|local|lugar)$", re.I)),
    ("time", re.compile(r"^(time|date|day|hora|data|dia|tempo)$", re.I)),
    ("inventory", re.compile(r"^(inventory|items|bag|inventário|inventario|itens|mochila)$", re.I)),
    ("relationships", re.compile(r"^(relationships?|affinity|bonds?|relações|relacoes|relacionamentos?|afinidade)$", re.I)),
    ("hp", re.compile(r"^(hp|health|vida|pv|hit points)$", re.I)),
    ("quests", re.compile(r"^(quests?|missions?|missões|missoes|objectives?|objetivos?|jobs)$", re.I)),
    ("gold", re.compile(r"^(gold|coins|money|ouro|dinheiro|tibares|t\$|eurobucks|eddies)$", re.I)),
    ("level", re.compile(r"^(level|lvl|nível|nivel)$", re.I)),
    ("ac", re.compile(r"^(ac|armou?r class|defesa|ca)$", re.I)),
    ("class", re.compile(r"^(class|classe)$", re.I)),
    ("race", re.compile(r"^(race|raça|raca|ancestry|ancestralidade)$", re.I)),
]
# Attribute labels -> the player's stats (Tormenta20's Portuguese ones too).
STATS = {"STR": "STR", "DEX": "DEX", "CON": "CON", "INT": "INT", "WIS": "WIS", "CHA": "CHA",
         "FOR": "STR", "DES": "DEX", "SAB": "WIS", "CAR": "CHA"}
PLACEHOLDER = re.compile(r"\[(?:[^\[\]]|\[[^\[\]]*\])*\]")  # [Grade], [[X]/100], [NPC (Affinity [Score])]


def _parse_segment(seg: str) -> dict | None:
    """'- Body: [Grade] [[X]/100]' -> key Body, prefix '- Body: ', suffix ''. None when the text has no placeholder."""
    found = list(PLACEHOLDER.finditer(seg))
    if not found:
        return None
    end = found[-1].end()
    middle = seg[found[0].start(): end]
    if middle.count("(") > middle.count(")") and seg[end:].startswith(")"):
        end += 1  # "[N] ([Mult])": the closing bracket belongs to the value
    prefix, suffix = seg[: found[0].start()], seg[end:]
    label = prefix.strip().lstrip("-").strip().rstrip(":").strip()
    if ":" in label:
        label = label.rsplit(":", 1)[1].strip()  # "Combat Log: Battles Today: [N]" -> Battles Today
    outer = prefix.strip().lstrip("-").strip().split(":")[0].strip()
    if not label:  # "[X] Crowns / [Y] Merits"
        label = re.sub(r"\s+", " ", PLACEHOLDER.sub(" ", seg)).strip(" /")
    return {"key": label, "prefix": prefix, "suffix": suffix, "known": _known(label) or _known(outer),
            "middle": middle, "outer": outer if outer != label else ""}


def _parse(template: str) -> list:
    """Template lines: a plain string (kept as it is) or a list of segments."""
    out: list = []
    for line in template.splitlines():
        segs = [_parse_segment(x) for x in re.split(r"(?<=\S)\s+\|\s+(?=\S)", line)] if PLACEHOLDER.search(line) else []
        if segs and all(segs):
            if sum(1 for x in segs if str(x["known"]).startswith("stat:")) < 3:  # a lone "INT: [Grade]" is the card's own
                for x in segs:
                    if str(x["known"]).startswith("stat:"):
                        x["known"] = None
            out.append(segs)
        else:
            out.append(line)
    return out


def template_of(scenario: dict) -> str | None:
    """The card's own INFO block first; otherwise the sheet picked from the library (app/sheets.py) for the card or game."""
    info = scenario.get("information") or {}
    own = split_template(info.get("post_history") or "")[1]
    if own:
        return own
    picked = str(scenario.get("sheet_template") or "").strip()
    return picked if PLACEHOLDER.search(picked) else None


def custom_fields(template: str) -> list[str]:
    """The card's own fields (everything the app does not know by itself)."""
    names: list[str] = []
    for line in _parse(template):
        if isinstance(line, list):
            names += [s["key"] for s in line if not s["known"] and s["key"] not in names]
    return names


def _known(label: str) -> str | None:
    base = re.sub(r"\s*\(.*?\)", "", label or "").strip()
    if base.upper() in STATS and base.isupper():
        return "stat:" + STATS[base.upper()]
    for key, rx in KNOWN:
        if rx.match(base):
            return key
    return None


def read_block(template: str, block: str) -> dict[str, str]:
    """Values of the card's own fields in a block the AI wrote (to keep them up to date)."""
    lines = [ln.replace("**", "").strip() for ln in (block or "").splitlines()]
    values: dict[str, str] = {}
    for tline in _parse(template):
        if not isinstance(tline, list):
            continue
        head = tline[0]["prefix"].strip()
        match = next((ln for ln in lines if head and ln.startswith(head)), None)
        if not match:
            continue
        parts = re.split(r"(?<=\S)\s+\|\s+(?=\S)", match)
        for seg, text in zip(tline, parts):
            if seg["known"]:
                if seg["known"] in ("location", "time"):  # used only to fill an empty place or time at the start
                    pre, suf = seg["prefix"].strip(), seg["suffix"].strip()
                    if text.startswith(pre) and text.endswith(suf):
                        v = text[len(pre): len(text) - len(suf) if suf else None].strip()
                        if v and not PLACEHOLDER.fullmatch(v):
                            values["@" + seg["known"]] = truncate(v, 80)
                continue
            pre, suf = seg["prefix"].strip(), seg["suffix"].strip()
            if text.startswith(pre) and text.endswith(suf):
                value = text[len(pre): len(text) - len(suf) if suf else None].strip()
                if value and not PLACEHOLDER.fullmatch(value) and value != "?":
                    values[seg["key"]] = truncate(value, 160)
    return values


def _known_value(key: str, state: dict, npcs: list[dict]) -> str:
    if key == "name":
        return state["player"].get("name") or "?"
    if key == "location":
        return state.get("location") or "?"
    if key == "time":
        return state.get("date_label") or state.get("time") or "?"
    if key == "inventory":
        return ", ".join(i["name"] + (f" x{i['qty']}" if i.get("qty", 1) > 1 else "") for i in state.get("inventory", [])) or "nothing"
    if key == "gold":
        return str(state.get("gold", 0))
    if key == "hp":
        hp = state["player"].get("hp") or {}
        return f"{hp.get('current', '?')}/{hp.get('max', '?')}"
    if key in ("level", "ac", "class", "race"):
        return str(state["player"].get(key) or "?")
    if key.startswith("stat:"):
        stats = state["player"].get("stats") or {}
        return str(stats.get(key[5:], "?"))
    if key == "quests":
        return "; ".join(q["title"] for q in state.get("quests", []) if q.get("status") == "active") or "none"
    if key == "relationships":
        from .prompts import relationship_label
        met = [n for n in npcs if n.get("met", True) and n.get("active", True)]
        met.sort(key=lambda n: -abs(n.get("relationship", 0)))
        return ", ".join(f"{n['name']} ({n['relationship']:+d} {relationship_label(n['relationship'])})" for n in met[:8]) or "none yet"
    return "?"


def render(template: str, state: dict, npcs: list[dict]) -> str:
    """The status block, filled by the app."""
    custom = state.get("card_status") or {}
    lines = []
    for line in _parse(template):
        if not isinstance(line, list):
            lines.append(line)
            continue
        parts = []
        for seg in line:
            value = _known_value(seg["known"], state, npcs) if seg["known"] else custom.get(seg["key"], "?")
            parts.append(f"{seg['prefix']}{value}{seg['suffix']}")
        lines.append(" | ".join(parts))
    return "\n".join(lines)


def harvest(state: dict, template: str, block: str | None) -> None:
    """Keep the card's own fields from a block the AI wrote anyway (or the opening scene's)."""
    if block:
        found = read_block(template, block)
        for key in ("location", "time"):
            value = found.pop("@" + key, "")
            if value and not state.get(key) and not state.get("date_label"):
                state[key] = value
        if found:
            state["card_status"] = {**(state.get("card_status") or {}), **found}


# Grades from the weakest to the strongest (Lumencia's D- to SSS+; F and E for cards that go lower)
GRADES = [g + s for g in ("F", "E", "D", "C", "B", "A", "S", "SS", "SSS") for s in ("-", "", "+")]
PROGRESS = re.compile(r"^(?P<grade>[A-Z]{1,3}[+-]?|-)\s*\[\s*(?P<x>-?\d+)\s*/\s*(?P<max>\d+)\s*\]\s*$")
RULE_TEXT = re.compile(r"^\s*(?:[<>]=?|=<|=>|≥|≤)\s*\d")  # ">=8": the card's rule, not a value


def bump_progress(value: str) -> str:
    """'C- [115/100]' -> 'C [15/100]': each full bar of EXP raises the grade one step (the card's 100 EXP/Sub-Grade)."""
    m = PROGRESS.match(str(value or "").strip())
    if not m or m["grade"] not in GRADES:
        return value
    grade, x, top = m["grade"], int(m["x"]), max(1, int(m["max"]))
    while x >= top and GRADES.index(grade) < len(GRADES) - 1:
        grade, x = GRADES[GRADES.index(grade) + 1], x - top
    if x > top:
        x = top
    return f"{grade} [{max(0, x)}/{top}]"


def apply_changes(state: dict, template: str, changes: list[dict]) -> list[str]:
    allowed = set(custom_fields(template))
    custom = dict(state.get("card_status") or {})
    out = []
    for ch in changes:
        field, value = str(ch.get("field", "")).strip(), truncate(str(ch.get("value", "")).strip(), 160)
        if field not in allowed or not value or RULE_TEXT.match(value) or PLACEHOLDER.fullmatch(value):
            continue
        value = bump_progress(value)
        if custom.get(field) == value:
            continue
        before = PROGRESS.match(str(custom.get(field) or ""))
        after = PROGRESS.match(value)
        custom[field] = value
        up = before and after and before["grade"] != after["grade"] and before["grade"] in GRADES and after["grade"] in GRADES \
            and GRADES.index(after["grade"]) > GRADES.index(before["grade"])
        out.append(f"{field}: {value}" + (f" (grade up: {before['grade']} → {after['grade']})" if up else ""))
    state["card_status"] = custom
    return out


def tracker_lines(state: dict, template: str) -> str:
    fields = custom_fields(template)
    if not fields:
        return ""
    custom = state.get("card_status") or {}
    now = "; ".join(f"{f} = {custom.get(f, 'unknown')}" for f in fields)
    bars = [f for f in fields if PROGRESS.match(str(custom.get(f) or ""))]
    exp = (f" Fields written as 'Grade [EXP/100]' ({', '.join(bars)}): add the EXP the card's rules give to the number and "
           "write the new total, keeping the grade (the app raises the grade when the bar fills).") if bars else ""
    return ("- status_changes: the card's own status fields that CHANGED in these exchanges (field, new value), following the "
            f"card's rules (for example EXP gained after a fight). Current values: {now}.{exp} Write real values only, never "
            "the card's rule text (not '>=8' or '[1-10]'). Fill unknown ones once from the story.")


def sheet_form(template: str, values: dict | None = None) -> list[dict]:
    """The card's own fields as a sheet to fill on the start screen, grouped as the card's INFO block groups them.
    Each field: key, hint (the card's placeholder: '1-10', 'Tier'), value (the opening's), and for 'Grade [EXP/100]'
    fields progress=True with grade, exp and max."""
    values = values or {}
    groups: list[dict] = []
    heading = ""

    def group(title: str) -> dict:
        if not groups or groups[-1]["title"] != title:
            groups.append({"title": title, "fields": []})
        return groups[-1]

    for line in _parse(template):
        if not isinstance(line, list):
            text = line.strip()
            heading = text.rstrip(":").strip() if text and not re.fullmatch(r"\[?INFO\]?", text, re.I) else ""
            continue
        dashed = line[0]["prefix"].lstrip().startswith("-")
        for seg in line:
            if seg["known"]:
                continue
            title = seg["outer"] or line[0]["outer"] or (heading if dashed else "")
            value = str(values.get(seg["key"]) or "").strip()
            hints = [h[1:-1] for h in PLACEHOLDER.findall(seg["middle"]) if not h.startswith("[[")]
            bar = re.search(r"\[\[[^\]]*\]\s*/\s*(\d+)\]", seg["middle"])
            field = {"key": seg["key"], "hint": " ".join(hints) or seg["key"], "value": value}
            if bar and hints:
                m = PROGRESS.match(value)
                field.update(progress=True, max=int(bar[1]), grade=m["grade"] if m else (value or "-"), exp=int(m["x"]) if m else 0)
            group(title)["fields"].append(field)
        if not dashed:
            heading = ""
    return [g for g in groups if g["fields"]]


def clean_values(template: str, values: dict) -> dict[str, str]:
    """A sheet sent by the start screen: only the card's own fields, no empty or rule-text values."""
    allowed = set(custom_fields(template))
    out = {}
    for k, v in (values or {}).items():
        k, v = str(k).strip(), truncate(str(v or "").strip(), 160)
        if k in allowed and v and not RULE_TEXT.match(v):
            out[k] = bump_progress(v)
    return out


def latest_block(messages: list[dict]) -> str | None:
    for m in reversed(messages):
        if m.get("meta", {}).get("status"):
            return m["meta"]["status"]
    return None


def strip_block(text: str) -> str:
    return split_status(text)[0]


CREATION = re.compile(r"^.*(character creation|create your character|build your character|cria[cç][aã]o de personagem|crie seu personagem|ficha).*$", re.I | re.M)


def start_sheet(data: dict) -> dict:
    """For the start screen: the card's own sheet (groups of fields with the opening's values) and the opening's
    character creation rules, so the player fills the sheet like a D&D one instead of answering in the chat."""
    tpl = template_of(data)
    if not tpl:
        return {"groups": [], "rules": ""}
    story, block = split_status(str(data.get("opening_message") or ""))
    values = read_block(tpl, block) if block else {}
    m = CREATION.search(story)
    rules = re.sub(r"\*\*|(?<!\w)\*(?!\s)|(?<!\s)\*(?!\w)|`", "", story[m.start():]).strip() if m else ""
    return {"groups": sheet_form(tpl, values), "rules": truncate(rules, 2500)}
