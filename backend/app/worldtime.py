"""The world's calendar and clock. The APP keeps the date and hour; the AI only reports how long a scene took.

A card defines its calendar (week days, months and their lengths, what a month and a year are called, the era,
the starting date and hour). Each game keeps `state["clock"]`: minutes since the start of the starting day.

- After each turn the tracker reports `minutes_passed` (a talk takes minutes, a meal an hour); at most 12 hours
  are taken from one turn, so the story never jumps ahead on its own.
- Longer skips happen only when the player asks: "/wait 2 days", "/wait until Sunday", or in plain words
  ("I sleep until morning", "we travel for three days"). Speech in quotes never counts.
- Appointments ("the festival is on Sunday") are stored with their exact day and come up when that day arrives.
"""
from __future__ import annotations

import re
import uuid

from .util import truncate

EARTH = {
    "weekdays": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    "months": [{"name": n, "days": d} for n, d in (("January", 31), ("February", 28), ("March", 31), ("April", 30), ("May", 31),
                                                    ("June", 30), ("July", 31), ("August", 31), ("September", 30), ("October", 31),
                                                    ("November", 30), ("December", 31))],
    "month_word": "month", "year_word": "year", "era": "", "hours_per_day": 24,
}
FANTASY = {
    "weekdays": ["Moonday", "Emberday", "Tideday", "Thornday", "Starday", "Stoneday", "Sunday"],
    "months": [{"name": n, "days": 30} for n in ("Deepwinter", "Thawmoon", "Seedtide", "Rainmoon", "Bloomtide", "Highsun",
                                                  "Goldmoon", "Harvestide", "Mistmoon", "Leaffall", "Frostmoon", "Longnight")],
    "month_word": "moon", "year_word": "year", "era": "AE", "hours_per_day": 24,
}
PRESETS = {"earth": EARTH, "fantasy": FANTASY}
DEFAULT_START = {"year": 1, "month": 1, "day": 1, "hour": 8, "minute": 0, "weekday": 0}
CLIMATES = ("temperate", "cold", "warm", "dry", "tropical", "none")
MAX_TURN_MINUTES = 12 * 60
MAX_SKIP_DAYS = 366
MAX_EVENTS = 40

PARTS = [("midnight", 0), ("dawn", 6), ("morning", 8), ("noon", 12), ("midday", 12), ("afternoon", 14), ("evening", 18),
         ("dusk", 19), ("night", 21), ("tonight", 20),
         ("madrugada", 3), ("amanhecer", 6), ("manhã", 8), ("meio-dia", 12), ("tarde", 14), ("anoitecer", 18), ("noite", 21)]
NUMBERS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
           "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fourteen": 14, "twenty": 20, "thirty": 30,
           "um": 1, "uma": 1, "dois": 2, "duas": 2, "três": 3, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6, "sete": 7,
           "oito": 8, "nove": 9, "dez": 10}
UNITS = {"minute": 1, "minutes": 1, "min": 1, "mins": 1, "minuto": 1, "minutos": 1,
         "hour": 60, "hours": 60, "hr": 60, "hrs": 60, "hora": 60, "horas": 60,
         "day": "d", "days": "d", "dia": "d", "dias": "d",
         "week": "w", "weeks": "w", "semana": "w", "semanas": "w"}
SKIP_VERB = re.compile(r"\b(wait|waits|waiting|sleep|sleeps|sleeping|rest|rests|resting|travel|travels|travelling|traveling|"
                       r"camp|camps|stay|stays|spend|spends|pass|passes|skip|skips|ride|rides|sail|sails|march|marches|walk|walks|"
                       r"espero|esperar|espera|durmo|dormir|dorme|descanso|descansar|viajo|viajar|viajamos|passo|passar|pulo|pular|"
                       r"acampo|acampar|fico|ficar)\b", re.I)


# ------------------------------------------------------------------ the calendar definition
def normalize_calendar(raw) -> dict:
    """Card field `calendar`. Missing or broken parts fall back to the Earth calendar."""
    raw = raw if isinstance(raw, dict) else {}
    base = PRESETS.get(str(raw.get("preset") or ""), EARTH)
    listed = lambda key: raw.get(key) if isinstance(raw.get(key), list) and raw.get(key) else base[key]  # noqa: E731
    weekdays = [truncate(str(w).strip(), 24) for w in listed("weekdays") if str(w).strip()][:14] or list(EARTH["weekdays"])
    months = []
    for m in listed("months"):
        if isinstance(m, dict) and str(m.get("name", "")).strip():
            try:
                days = int(m.get("days", 30))
            except (TypeError, ValueError):
                days = 30
            months.append({"name": truncate(str(m["name"]).strip(), 30), "days": max(1, min(100, days))})
    months = months[:24] or [dict(m) for m in EARTH["months"]]
    try:
        hpd = max(4, min(48, int(raw.get("hours_per_day", base["hours_per_day"]))))
    except (TypeError, ValueError):
        hpd = 24
    start = dict(DEFAULT_START)
    for k in start:
        try:
            start[k] = int((raw.get("start") or {}).get(k, start[k]))
        except (TypeError, ValueError, AttributeError):
            pass
    start["month"] = max(1, min(len(months), start["month"]))
    start["day"] = max(1, min(months[start["month"] - 1]["days"], start["day"]))
    start["hour"] = max(0, min(hpd - 1, start["hour"]))
    start["minute"] = max(0, min(59, start["minute"]))
    start["weekday"] = start["weekday"] % len(weekdays)
    return {
        "enabled": bool(raw.get("enabled", False)),
        "climate": raw.get("climate") if raw.get("climate") in CLIMATES else "temperate",
        "preset": str(raw.get("preset") or ""),
        "weekdays": weekdays,
        "months": months,
        "month_word": truncate(str(raw.get("month_word") or base["month_word"]).strip(), 20),
        "year_word": truncate(str(raw.get("year_word") or base["year_word"]).strip(), 20),
        "era": truncate(str(raw.get("era") if raw.get("era") is not None else base["era"]).strip(), 20),
        "hours_per_day": hpd,
        "start": start,
    }


def day_minutes(cal: dict) -> int:
    return cal["hours_per_day"] * 60


def year_days(cal: dict) -> int:
    return sum(m["days"] for m in cal["months"])


def _start_offset(cal: dict) -> int:
    return cal["start"]["hour"] * 60 + cal["start"]["minute"]


def absolute(cal: dict, clock: int) -> int:
    """Minutes since midnight of the starting day."""
    return _start_offset(cal) + int(clock)


def day_index(cal: dict, clock: int) -> int:
    return absolute(cal, clock) // day_minutes(cal)


# ------------------------------------------------------------------ reading the clock
def date_of_day(cal: dict, day: int) -> dict:
    """Year, month and day of the N-th day since the starting day."""
    s = cal["start"]
    doy = sum(m["days"] for m in cal["months"][: s["month"] - 1]) + s["day"] - 1 + day
    yl = year_days(cal)
    year = s["year"] + doy // yl
    doy %= yl
    for i, m in enumerate(cal["months"]):
        if doy < m["days"]:
            return {"year": year, "month": i + 1, "day": doy + 1, "weekday": (s["weekday"] + day) % len(cal["weekdays"])}
        doy -= m["days"]
    return {"year": year, "month": len(cal["months"]), "day": 1, "weekday": 0}  # unreachable


def now(cal: dict, clock: int) -> dict:
    a = absolute(cal, clock)
    day, mins = divmod(a, day_minutes(cal))
    return {**date_of_day(cal, day), "hour": mins // 60, "minute": mins % 60, "day_index": day}


def part_of_day(cal: dict, hour: int) -> str:
    f = hour / cal["hours_per_day"] * 24
    if f < 5:
        return "night"
    if f < 7:
        return "dawn"
    if f < 12:
        return "morning"
    if f < 14:
        return "midday"
    if f < 18:
        return "afternoon"
    if f < 21:
        return "evening"
    return "night"


def format_date(cal: dict, d: dict, weekday: bool = True) -> str:
    month = cal["months"][d["month"] - 1]["name"]
    year = f"{cal['year_word'].capitalize()} {d['year']}" if cal["year_word"] and cal["year_word"].lower() != "year" else str(d["year"])
    era = f" {cal['era']}" if cal["era"] else ""
    head = f"{cal['weekdays'][d['weekday']]}, " if weekday else ""
    return f"{head}{d['day']} {month}, {year}{era}"


def format_now(cal: dict, clock: int) -> str:
    d = now(cal, clock)
    return f"{format_date(cal, d)} · {d['hour']:02d}:{d['minute']:02d} ({part_of_day(cal, d['hour'])})"


def time_label(cal: dict, clock: int) -> str:
    d = now(cal, clock)
    return f"{part_of_day(cal, d['hour'])}, {d['hour']:02d}:{d['minute']:02d}"


def week_ahead(cal: dict, clock: int) -> str:
    """'Tomorrow: Tuesday 4 Frostmoon. In 2 days: …' so the GM never miscounts the days."""
    today = day_index(cal, clock)
    out = []
    for i in range(1, len(cal["weekdays"]) + 1):
        d = date_of_day(cal, today + i)
        label = "Tomorrow" if i == 1 else f"In {i} days"
        out.append(f"{label}: {cal['weekdays'][d['weekday']]} {d['day']} {cal['months'][d['month'] - 1]['name']}")
    return ". ".join(out) + "."


# ------------------------------------------------------------------ understanding "Sunday", "in 2 days", "until morning"
def _num(word: str) -> int | None:
    word = word.lower()
    if word.isdigit():
        return int(word)
    return NUMBERS.get(word)


def parse_when(cal: dict, text: str, clock: int) -> int | None:
    """Days from today for 'today', 'tomorrow', 'Sunday', 'in 3 days', 'next week', '5 Frostmoon'… (None if unknown)."""
    t = (text or "").strip().lower()
    if not t:
        return None
    if re.search(r"\b(today|tonight|this (morning|afternoon|evening)|hoje|esta noite|hoje à noite)\b", t):
        return 0
    if re.search(r"\b(day after tomorrow|depois de amanhã)\b", t):
        return 2
    if re.search(r"\b(tomorrow|amanhã|amanha)\b", t):
        return 1
    m = re.search(r"\b(?:in|em|daqui a)\s+(\w+)\s+(day|days|dia|dias|week|weeks|semana|semanas)\b", t)
    if m and _num(m.group(1)):
        n = _num(m.group(1))
        return n * (len(cal["weekdays"]) if m.group(2).startswith(("week", "semana")) else 1)
    if re.search(r"\b(next week|semana que vem|próxima semana)\b", t):
        return len(cal["weekdays"])
    today = now(cal, clock)
    for i, name in enumerate(cal["weekdays"]):
        if re.search(rf"\b{re.escape(name.lower())}\b", t):
            ahead = (i - today["weekday"]) % len(cal["weekdays"])
            return ahead or len(cal["weekdays"])  # "Sunday" said on a Sunday means next Sunday
    for mi, month in enumerate(cal["months"], 1):
        name = re.escape(month["name"].lower())
        m = re.search(rf"\b(\d{{1,3}})(?:st|nd|rd|th|º)?\s+(?:of\s+|de\s+)?{name}\b", t) or re.search(rf"\b{name}\s+(\d{{1,3}})\b", t)
        if m:
            day = max(1, min(month["days"], int(m.group(1))))
            return _days_until_date(cal, clock, mi, day)
    return None


def _days_until_date(cal: dict, clock: int, month: int, day: int) -> int:
    today = day_index(cal, clock)
    for ahead in range(0, year_days(cal) + 1):
        d = date_of_day(cal, today + ahead)
        if d["month"] == month and d["day"] == day:
            return ahead
    return 0


def _hour_of(text: str) -> int | None:
    t = text.lower()
    m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|h)?\b", t)
    if m and (m.group(3) or m.group(2)):
        h = int(m.group(1)) % 24
        if m.group(3) == "pm" and h < 12:
            h += 12
        if m.group(3) == "am" and h == 12:
            h = 0
        return h
    for word, hour in PARTS:
        if re.search(rf"\b{re.escape(word)}\b", t):
            return hour
    return None


def minutes_until(cal: dict, clock: int, spec: str) -> int | None:
    """Minutes to wait for '2 days', '3 hours', 'until Sunday', 'until morning', 'until tomorrow evening'."""
    t = (spec or "").strip().lower()
    if not t:
        return None
    dm = day_minutes(cal)
    m = re.match(r"^(?:for\s+|por\s+)?(\w+)\s+(\w+)\b", t)
    if m and _num(m.group(1)) and m.group(2) in UNITS:
        n, unit = _num(m.group(1)), UNITS[m.group(2)]
        mins = n * (dm if unit == "d" else dm * len(cal["weekdays"]) if unit == "w" else unit)
        return min(mins, MAX_SKIP_DAYS * dm)
    t = re.sub(r"^(until|till|til|to|até|ate|a)\s+", "", t)
    days = parse_when(cal, t, clock)
    hour = _hour_of(t)
    cur = now(cal, clock)
    cur_min = cur["hour"] * 60 + cur["minute"]
    scale = cal["hours_per_day"] / 24
    if days is None and hour is None:
        return None
    if hour is not None:
        hour = min(cal["hours_per_day"] - 1, round(hour * scale))
    if days is None:  # "until morning": the next time it is that hour
        target = hour * 60
        return (target - cur_min) % dm or dm
    target_hour = hour if hour is not None else round(8 * scale)  # a day without an hour: arrive in its morning
    return max(1, days * dm + target_hour * 60 - cur_min)


def strip_speech(text: str) -> str:
    """Only the player's own narration and actions count, never what their character says or thinks."""
    t = re.sub(r"\"[^\"]*\"|“[^”]*”", " ", text or "")
    t = re.sub(r"(?<!\w)'[^'\n]+'(?!\w)", " ", t)
    return t


def parse_skip(cal: dict, text: str, clock: int) -> tuple[int, str] | None:
    """(minutes, spec) when the player asks to let time pass, else None."""
    raw = (text or "").strip()
    m = re.match(r"^/(wait|esperar|espera)\b\s*(.*)$", raw, re.I | re.S)
    if m:
        spec = m.group(2).strip() or "1 hour"
        mins = minutes_until(cal, clock, spec)
        if mins is None:
            raise ValueError("Try /wait 2 hours, /wait 3 days, /wait until Sunday or /wait until morning.")
        return mins, spec
    t = strip_speech(raw)
    if not SKIP_VERB.search(t):
        return None
    for pattern in (r"\b(?:until|till|til|até|ate)\s+([^.,;!?*\n]{2,40})",
                    r"\b(?:for|por|durante)\s+((?:\w+)\s+(?:minutes?|hours?|days?|weeks?|minutos?|horas?|dias?|semanas?))\b"):
        m = re.search(pattern, t, re.I)
        if m:
            mins = minutes_until(cal, clock, m.group(1))
            if mins:
                return mins, m.group(1).strip()
    return None


# ------------------------------------------------------------------ appointments
def add_event(state: dict, cal: dict, text: str, when: str = "", days_guess=None, hour_text: str = "") -> dict | None:
    clock = int((state.get("clock") or {}).get("minutes", 0))
    days = parse_when(cal, when, clock)
    if days is None:
        try:
            days = int(days_guess) if days_guess is not None and str(days_guess).strip() != "" else None
        except (TypeError, ValueError):
            days = None
    if days is None or days < 0 or days > MAX_SKIP_DAYS:
        return None
    text = truncate(str(text).strip(), 160)
    if not text:
        return None
    day = day_index(cal, clock) + days
    events = state.setdefault("events", [])
    today = day_index(cal, clock)
    if any(e["day"] >= today and _same(e["text"], text) for e in events):
        return None  # already planned (models often repeat a known appointment)
    hour = _hour_of(f"{when} {hour_text}")
    d = date_of_day(cal, day)
    label = f"{cal['weekdays'][d['weekday']]} {d['day']} {cal['months'][d['month'] - 1]['name']}" + (f", {hour:02d}:00" if hour is not None else "")
    ev = {"id": uuid.uuid4().hex[:8], "day": day, "hour": hour, "text": text, "date": label}
    events.append(ev)
    events.sort(key=lambda e: (e["day"], e["hour"] if e["hour"] is not None else 99))
    past = [e for e in events if e["day"] < day_index(cal, clock) - 30]
    for e in past:
        events.remove(e)
    del events[MAX_EVENTS:]
    return ev


def _same(a: str, b: str) -> bool:
    wa, wb = set(re.findall(r"\w{4,}", a.lower())), set(re.findall(r"\w{4,}", b.lower()))
    return a.lower() == b.lower() or (bool(wa and wb) and len(wa & wb) / min(len(wa), len(wb)) >= 0.6)


def describe_event(cal: dict, ev: dict, today: int) -> str:
    d = date_of_day(cal, ev["day"])
    when = "Today" if ev["day"] == today else "Tomorrow" if ev["day"] == today + 1 else f"In {ev['day'] - today} days"
    at = f" at {ev['hour']:02d}:00" if ev.get("hour") is not None else ""
    return f"{when} ({cal['weekdays'][d['weekday']]} {d['day']} {cal['months'][d['month'] - 1]['name']}{at}): {ev['text']}"


def events_between(state: dict, cal: dict, from_clock: int, to_clock: int) -> list[dict]:
    a, b = day_index(cal, from_clock), day_index(cal, to_clock)
    return [e for e in state.get("events", []) if a < e["day"] <= b]


# ------------------------------------------------------------------ moving the clock
def clock_of(state: dict) -> int:
    return int((state.get("clock") or {}).get("minutes", 0))


def advance(state: dict, cal: dict, minutes: int) -> dict:
    minutes = max(0, int(minutes))
    state["clock"] = {**(state.get("clock") or {}), "minutes": clock_of(state) + minutes}
    state["time"] = time_label(cal, state["clock"]["minutes"])
    if cal.get("climate", "temperate") != "none":
        state["weather"] = weather_on(cal, day_index(cal, state["clock"]["minutes"]), state["clock"].get("seed", 0))
    return state


# ------------------------------------------------------------------ weather (rolled by the app, by season)
WEATHER = {  # season: [(weather, weight)]
    "winter": [("clear and cold", 3), ("grey and overcast", 3), ("light snow", 3), ("heavy snow", 1), ("freezing fog", 1), ("icy rain", 1)],
    "spring": [("clear and mild", 3), ("cloudy", 2), ("light rain", 3), ("heavy rain", 1), ("morning fog", 1), ("windy", 1)],
    "summer": [("clear and hot", 4), ("sunny with a light breeze", 3), ("humid and hazy", 1), ("a thunderstorm", 1), ("cloudy", 1)],
    "autumn": [("cool and clear", 2), ("overcast", 3), ("drizzle", 2), ("heavy rain", 1), ("windy, leaves blowing", 2), ("fog", 1)],
}
CLIMATE_SHIFT = {"cold": {"summer": "spring", "spring": "winter", "autumn": "winter"},
                 "warm": {"winter": "autumn", "spring": "summer", "autumn": "summer"},
                 "tropical": {"winter": "summer", "spring": "summer", "autumn": "summer"},
                 "dry": {}}


def season_of(cal: dict, month: int) -> str:
    f = (month - 0.5) / len(cal["months"])  # where the month falls in the year (northern seasons)
    return "winter" if f < 2 / 12 or f >= 11 / 12 else "spring" if f < 5 / 12 else "summer" if f < 8 / 12 else "autumn"


def weather_on(cal: dict, day: int, seed: int = 0) -> str:
    """The weather of a day: rolled from the season, and it tends to last a day or two (same seed, same weather)."""
    import random
    climate = cal.get("climate", "temperate")
    season = season_of(cal, date_of_day(cal, day)["month"])
    season = CLIMATE_SHIFT.get(climate, {}).get(season, season)
    rng = random.Random(f"{seed}:{day // 2}:{day % 2 if (day * 7 + seed) % 3 == 0 else 0}")
    options = WEATHER[season]
    if climate == "dry":
        options = [(w, n) for w, n in options if not any(x in w for x in ("rain", "snow", "drizzle", "storm", "fog"))] or options
    if climate == "tropical":
        options = options + [("a warm downpour", 3)]
    return rng.choices([w for w, _ in options], weights=[n for _, n in options])[0]


def skip_note(cal: dict, before: int, after: int, passed: list[dict], spec: str, seed: int = 0) -> str:
    span = after - before
    dm = day_minutes(cal)
    days, rest = divmod(span, dm)
    hours = round(rest / 60)
    length = ", ".join(x for x in (f"{days} day{'s' * (days != 1)}" if days else "", f"{hours} hour{'s' * (hours != 1)}" if hours else "") if x) or "a few minutes"
    note = f"⏳ Time passes ({length}). It is now {format_now(cal, after)}."
    if cal.get("climate", "temperate") != "none":
        note += f" Weather: {weather_on(cal, day_index(cal, after), seed)}."
    if passed:
        note += " On the way: " + "; ".join(f"{cal['weekdays'][date_of_day(cal, e['day'])['weekday']]}: {e['text']}" for e in passed) + "."
    return note


def gm_notes(state: dict, cal: dict) -> str:
    """The calendar part of the GM notes: now, the coming week, appointments."""
    clock = clock_of(state)
    today = day_index(cal, clock)
    lines = [f"Now: {format_now(cal, clock)}" + (f", weather: {state['weather']}" if state.get("weather") else "") + f". {week_ahead(cal, clock)}"]
    soon = [e for e in state.get("events", []) if today <= e["day"] <= today + len(cal["weekdays"])]
    if soon:
        lines.append("Appointments: " + " | ".join(describe_event(cal, e, today) for e in soon))
    return "\n".join(lines)


CALENDAR_RULES = (
    "The app keeps the calendar and the clock (shown under Now). Use exactly that date, week day and hour. "
    "Never jump ahead in time on your own: play scenes out in order; days pass only when the player chooses to wait, "
    "sleep or travel. A promised day (\"on Sunday\") arrives only when the calendar says it is that day. "
    "When you mention a future day, count it from the list of coming days."
)
