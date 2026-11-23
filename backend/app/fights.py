"""Narrated fights counted by the app: exchanges, and EXP by difficulty (World Compendium, part 2).

Cards like Lumencia fight in prose (no battle grid). A rule set in the Compendium can carry "Fight EXP" rules;
then the Aedo only marks where a fight starts and ends, and Calíope does the arithmetic the model kept getting wrong:

    [[fight: Lilia | spar]]              a spar, duel, battle, drill or lethal trial begins
    [[fight end: won | Body, INT]]       it ended: won / lost / draw, and the stats it trained (main first)

Each of the player's turns while a fight runs is one exchange. At the end the kind's EXP range is scaled by the
exchanges (a short spar gets the low end, a long one the high end; a spar that runs long counts as a battle),
then the card's bonus (a matching Attribute of 7+), the day's streak (1st, 2nd, 3rd+ battle) and the result
are applied, and the EXP goes into the sheet's 'Grade [EXP/100]' bars (a full bar raises the grade).
A fight the Aedo forgets to close ends by itself after a few quiet turns, with no EXP.
"""
from __future__ import annotations

import re

from .statusbook import PROGRESS, bump_progress
from .util import as_int

KINDS = ("drill", "spar", "battle", "lethal")
KIND_WORDS = {
    "drill": ("drill", "training", "practice", "study", "treino", "exercício", "exercicio", "estudo"),
    "spar": ("spar", "sparring", "skirmish", "duel", "bout", "duelo", "escaramuça", "luta curta"),
    "battle": ("battle", "fight", "brawl", "combat", "batalha", "luta", "combate"),
    "lethal": ("lethal", "deadly", "trial", "upset", "higher tier", "mortal", "letal", "prova"),
}
RESULTS = {"won": ("won", "win", "victory", "venceu", "vitória", "vitoria", "ganhou"),
           "lost": ("lost", "loss", "defeat", "perdeu", "derrota"),
           "draw": ("draw", "tie", "stopped", "interrupted", "empate", "interrompida")}
QUIET_LIMIT = 4  # player turns with no fighting words before a forgotten fight closes by itself

START_TAG = re.compile(r"\[\[\s*(?:fight|luta|duel|duelo|spar)\s*:\s*([^\]|\n]{1,60}?)\s*(?:\|\s*([^\]\n]{1,40}?)\s*)?\]\]", re.I)
END_TAG = re.compile(r"\[\[\s*(?:fight|luta)\s*(?:end|over|fim)\s*(?::\s*([^\]|\n]{0,40}?))?\s*(?:\|\s*([^\]\n]{0,80}?)\s*)?\]\]", re.I)
FIGHTING = re.compile(r"(?<!\w)(attack|strike|blow|slash|parry|dodge|block|punch|kick|lunge|swing|cast|spell|blade|sword|"
                      r"clash|counter|feint|guard|ataque|ataca|golpe|esquiva|bloqueia|defende|chute|soco|espada|lâmina|feitiço)", re.I)

# Lumencia's own numbers ("Base EXP Awards", "Daily Streak", "+5 if Attribute >= 7"): one click in the Compendium
LUMENCIA = {
    "kinds": {"drill": [5, 10], "spar": [10, 15], "battle": [20, 35], "lethal": [40, 60]},
    "long_after": 4,
    "stats": ["Body", "Mana", "INT", "Divinity"],
    "bonus": {"min": 7, "exp": 5, "links": {"Body": "Martial", "Mana": "Magic", "INT": "Knowledge", "Divinity": "Soul"}},
    "streak": [1.0, 1.25, 1.5],
    "lost": 0.75,
    "second": 0.5,
    "log": {"today": "Battles Today", "total": "Total"},
}


def _s(v, n: int = 30) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()[:n]


def normalize(raw) -> dict:
    """A rule set's Fight EXP rules made safe ({} = the rule set has none)."""
    if not isinstance(raw, dict):
        return {}
    kinds = {}
    for k in KINDS:
        r = (raw.get("kinds") or {}).get(k) if isinstance(raw.get("kinds"), dict) else None
        if isinstance(r, (list, tuple)) and len(r) == 2:
            lo, hi = max(0, as_int(r[0])), max(0, as_int(r[1]))
            kinds[k] = [min(lo, hi), max(lo, hi)]
    stats = [_s(x) for x in raw.get("stats") or [] if _s(x)][:8] if isinstance(raw.get("stats"), list) else []
    if not kinds or not stats:
        return {}
    bonus = raw.get("bonus") if isinstance(raw.get("bonus"), dict) else {}
    links = bonus.get("links") if isinstance(bonus.get("links"), dict) else {}
    streak = [max(0.0, min(5.0, float(x))) for x in raw.get("streak") or [] if isinstance(x, (int, float))][:5] \
        if isinstance(raw.get("streak"), list) else []
    log = raw.get("log") if isinstance(raw.get("log"), dict) else {}

    def frac(v, default):
        return max(0.0, min(1.0, float(v))) if isinstance(v, (int, float)) else default

    return {"kinds": kinds, "long_after": max(0, as_int(raw.get("long_after"), 4)), "stats": stats,
            "bonus": {"min": as_int(bonus.get("min"), 0), "exp": max(0, as_int(bonus.get("exp"), 0)),
                      "links": {_s(k): _s(v) for k, v in list(links.items())[:8] if _s(k) and _s(v)}},
            "streak": streak or [1.0], "lost": frac(raw.get("lost"), 0.75), "second": frac(raw.get("second"), 0.5),
            "log": {"today": _s(log.get("today")), "total": _s(log.get("total"))}}


def _word(text: str, table: dict, default: str) -> str:
    low = (text or "").lower()
    for key, words in table.items():
        if key in low or any(re.search(rf"(?<!\w){re.escape(w)}", low) for w in words):
            return key
    return default


def kind_of(text: str) -> str:
    return _word(text, {k: KIND_WORDS[k] for k in ("lethal", "drill", "spar", "battle")}, "spar")


def take_tags(reply: str) -> tuple[str, list[tuple[str, str]], list[tuple[str, list[str]]]]:
    """The fight tags taken out of a reply: (clean reply, [(opponent, kind)], [(result, [stats])])."""
    starts: list[tuple[str, str]] = []
    ends: list[tuple[str, list[str]]] = []

    def end(m):
        ends.append((_word(m.group(1) or "", RESULTS, "draw"),
                     [_s(x) for x in re.split(r"[,/;&]| and | e ", m.group(2) or "") if _s(x)][:3]))
        return ""

    def start(m):
        starts.append((_s(m.group(1), 60), kind_of(m.group(2) or "")))
        return ""

    reply = END_TAG.sub(end, reply)
    reply = START_TAG.sub(start, reply)
    reply = re.sub(r"[ \t]+\n", "\n", reply)
    return re.sub(r"\n{3,}", "\n\n", reply).strip(), starts, ends


def start(state: dict, opponent: str, kind: str) -> None:
    state["fight"] = {"active": True, "opponent": opponent or "someone", "kind": kind if kind in KINDS else "spar",
                      "exchanges": 1, "quiet": 0}


def count_turn(state: dict, text: str) -> bool:
    """One of the player's turns during a fight. True when a forgotten fight has gone quiet and should close."""
    f = state.get("fight") or {}
    if not f.get("active"):
        return False
    if FIGHTING.search(text or ""):
        f["exchanges"] = int(f.get("exchanges", 0)) + 1
        f["quiet"] = 0
    else:
        f["quiet"] = int(f.get("quiet", 0)) + 1
    return f["quiet"] >= QUIET_LIMIT


def base_exp(cfg: dict, kind: str, exchanges: int) -> tuple[str, int]:
    """(the kind it counted as, EXP before bonus and streak). Longer fights earn the top of the range."""
    if kind == "spar" and cfg["long_after"] and exchanges >= cfg["long_after"] and "battle" in cfg["kinds"]:
        kind = "battle"  # "Extended/Multi-Turn Battle"
    lo, hi = cfg["kinds"].get(kind) or cfg["kinds"].get("spar") or next(iter(cfg["kinds"].values()))
    t = min(1.0, max(0, exchanges - 1) / 5)
    return kind, round(lo + (hi - lo) * t)


def _number(v) -> int | None:
    m = re.search(r"-?\d+", str(v or ""))
    return int(m.group(0)) if m else None


def _stat_key(cfg: dict, name: str) -> str | None:
    low = (name or "").strip().lower()
    return next((s for s in cfg["stats"] if s.lower() == low or low.startswith(s.lower())), None)


def finish(cfg: dict, state: dict, result: str, stats: list[str], day: int) -> list[str]:
    """Close the fight and pay its EXP into the sheet. Lines like 'Body +23 EXP → D+ [43/100]' come back."""
    f = state.get("fight") or {}
    if not f.get("active"):
        return []
    state["fight"] = {"active": False}
    kind, exp = base_exp(cfg, f.get("kind", "spar"), int(f.get("exchanges", 1)))
    log = state.get("fight_log") if isinstance(state.get("fight_log"), dict) else {}
    today = int(log.get("today", 0)) + 1 if log.get("day") == day else 1
    mult = cfg["streak"][min(today, len(cfg["streak"])) - 1]
    if result == "lost":
        mult *= cfg["lost"]
    sheet = state.setdefault("card_status", {})
    keys = [k for k in dict.fromkeys(_stat_key(cfg, s) for s in stats) if k] or [cfg["stats"][0]]
    lines = []
    for i, key in enumerate(keys[:2]):
        gain = exp * (1 if i == 0 else cfg["second"])
        attr = cfg["bonus"]["links"].get(key)
        if attr and cfg["bonus"]["exp"] and (_number(sheet.get(attr)) or 0) >= cfg["bonus"]["min"] > 0:
            gain += cfg["bonus"]["exp"]
        gain = round(gain * mult)
        m = PROGRESS.match(str(sheet.get(key) or "").strip())
        if not m or gain <= 0:
            continue
        before = m["grade"]
        sheet[key] = bump_progress(f"{m['grade']} [{int(m['x']) + gain}/{m['max']}]")
        up = PROGRESS.match(sheet[key])["grade"]
        lines.append(f"{key} +{gain} EXP → {sheet[key]}" + (f" (grade up: {before} → {up})" if up != before else ""))
    total = int(log.get("total", 0)) + 1
    state["fight_log"] = {"day": day, "today": today, "total": total,
                          "last": ([{"opponent": f.get("opponent", ""), "kind": kind, "result": result,
                                     "exchanges": int(f.get("exchanges", 1)), "day": day}] + list(log.get("last") or []))[:5]}
    if cfg["log"]["today"]:
        sheet[cfg["log"]["today"]] = f"{today} ({mult if result != 'lost' else cfg['streak'][min(today, len(cfg['streak'])) - 1]:g}x)"
    if cfg["log"]["total"]:
        sheet[cfg["log"]["total"]] = str(total)
    head = f"⚔ {kind.capitalize()} with {f.get('opponent') or 'someone'}: {result}, {int(f.get('exchanges', 1))} exchange(s)"
    return [head] + lines


def drop(state: dict) -> str:
    """A fight that went quiet: closed with no EXP."""
    f = state.get("fight") or {}
    state["fight"] = {"active": False}
    return f"⚔ The fight with {f.get('opponent') or 'someone'} faded out (no EXP)." if f.get("active") else ""


def prompt_text(cfg: dict, state: dict) -> str:
    """What the Aedo is told: mark fights, never count EXP."""
    if not cfg:
        return ""
    f = state.get("fight") or {}
    now = (f"A {f.get('kind', 'fight')} with {f.get('opponent')} is going on (exchange {f.get('exchanges', 1)}). "
           if f.get("active") else "")
    return (f"{now}Fights are counted by the app. When a spar, duel, battle, drill or lethal trial BEGINS, write "
            "[[fight: opponent | spar]] (or drill / battle / lethal) once on its own line. When it ENDS, write "
            f"[[fight end: won | Main stat, Second stat]] (won, lost or draw; stats from: {', '.join(cfg['stats'])}). "
            "Never write EXP numbers yourself: the app adds them to the sheet.")
