"""Adventures for rules RPG cards: a published adventure (a PDF or pasted text) split into scenes the Aedo runs.

An adventure is part of a card (`data["adventure"]`):
- parts ("Goblin Arrows", "Phandalin"...), each with its scenes in order;
- scenes: the place or encounter ("Goblin Ambush", "Cragmaw Hideout · 3. Kennel") with the read-aloud text the Aedo
  narrates close to word for word on the first visit, hidden GM notes (who is there, what they do, developments),
  the checks and traps with their DC (rolled by the app's dice, not decided by the model), enemies with numbers for the
  battle grid, treasure, an XP award and the areas it leads to;
- maps: a picture of a location (the GM version and, optionally, the player version) with one marker per scene.

The book itself never leaves the PC and nothing of it ships with the app: the text is split by code here (numbered
areas, headings, "you" paragraphs for read-aloud text, "DC 15 Wisdom (Perception)" for checks), then corrected by
hand in the card editor.

In a game, `state["adventure"]` says where the player is: {"scene": id, "visited": [ids], "xp_given": [ids]}.
"""
from __future__ import annotations

import re
import unicodedata

from .portraits import _url
from .util import truncate

MAX_SCENES = 200
MAP_MAX = 80  # squares across an adventure map (the battle grid follows it)
MAX_MAPS = 30
TEXT_LIMIT = 6000

# A few common monsters with their SRD 5.1 numbers (Creative Commons BY 4.0, Wizards of the Coast), so a fight can start
# with real values. Anything else: the numbers are filled by hand or by "Suggest from the scene".
#           name             ac  hp   atk  damage    init
MONSTERS = {
    "goblin": (15, 7, 4, "1d6+2", 2), "hobgoblin": (18, 11, 3, "1d8+1", 1), "bugbear": (16, 27, 4, "2d8+2", 2),
    "kobold": (12, 5, 4, "1d4+2", 2), "orc": (13, 15, 5, "1d12+3", 1), "ogre": (11, 59, 6, "2d8+4", -1),
    "wolf": (13, 11, 4, "2d4+2", 2), "dire wolf": (14, 37, 5, "2d6+3", 2), "giant rat": (12, 7, 4, "1d4+2", 2),
    "rat": (10, 1, 0, "1", 0), "giant spider": (14, 26, 5, "1d8+3", 3), "stirge": (14, 2, 5, "1d4+3", 3),
    "skeleton": (13, 13, 4, "1d6+2", 2), "zombie": (8, 22, 3, "1d6+1", -2), "ghoul": (12, 22, 4, "2d6+2", 2),
    "specter": (12, 22, 4, "3d6", 2), "bandit": (12, 11, 3, "1d6+1", 1), "bandit captain": (15, 65, 5, "1d6+3", 3),
    "thug": (11, 32, 4, "1d6+2", 0), "cultist": (12, 9, 3, "1d6+1", 1), "guard": (16, 11, 3, "1d6+1", 1),
    "veteran": (17, 58, 5, "1d8+3", 1), "mage": (12, 40, 5, "1d4+2", 2), "owlbear": (13, 59, 7, "2d8+5", 1),
    "twig blight": (13, 4, 3, "1d4+1", 1), "nothic": (15, 45, 4, "1d6+3", 3), "doppelganger": (14, 52, 6, "1d6+4", 4),
    "ochre jelly": (8, 45, 4, "2d6+2", -2), "drow": (15, 13, 4, "1d6+2", 2), "giant bat": (13, 22, 4, "1d6+2", 3),
    "bat": (12, 1, 0, "1", 2), "boar": (11, 11, 3, "1d6+1", 0), "brown bear": (11, 34, 6, "2d6+4", 0),
    "ankheg": (14, 39, 5, "2d6+3", 0), "gnoll": (15, 22, 4, "1d8+2", 1), "lizardfolk": (15, 22, 4, "1d6+2", 0),
    "troll": (15, 84, 7, "2d6+4", 1), "wight": (14, 45, 4, "1d8+2", 1), "flameskull": (13, 40, 5, "3d6", 3),
    "young green dragon": (18, 136, 7, "2d10+4", 1), "wyvern": (13, 110, 7, "2d6+4", 0), "harpy": (11, 38, 3, "2d4+1", 1),
}
NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
           "ten": 10, "eleven": 11, "twelve": 12, "a pair of": 2, "pair of": 2}
SUBSECTION = re.compile(r"^(developments?|treasure|rests?|awarding experience points|what'?s next\??|general features|"
                        r"roleplaying\b.*|what the .* knows?|driving the .*|npc party members|adventure maps|"
                        r"read-?aloud.*|xp awards?|experience points|tactics|sidebar.*)$", re.I)
SKIP_HEADINGS = re.compile(r"^(introduction|running the adventure|the dungeon master|rules to game by|improvising ability checks|"
                           r"glossary|magic items and monsters|abbreviations|roleplaying and inspiration|player version|"
                           r"dm version|contents|credits|table of contents|the forgotten realms)$", re.I)
BACKGROUND_HEADINGS = re.compile(r"^(background|overview|adventure hooks?|.*\bhook\b.*|meet me in .*)$", re.I)
PART = re.compile(r"^(?:part|chapter|capítulo|parte)\s+(\d+|[ivx]+)\s*[:.\-–—]?\s*(.*)$", re.I)
AREA = re.compile(r"^([A-Z]?\d{1,2}[a-z]?)\.\s+([A-Z][^.!?]{1,60})$")
CHECK = re.compile(r"DC\s*(\d{1,2})\s+(Strength|Dexterity|Constitution|Intelligence|Wisdom|Charisma)"
                   r"(?:\s*\(([A-Za-z ]+)\))?\s+(check|saving throw|save)", re.I)
XP = re.compile(r"(?:award|awarded|earns?|gains?)\s+(?:each character\s+|the party\s+)?([\d,]+)\s*XP", re.I)
READ_CUE = re.compile(r"boxed text|read-?aloud|read aloud|read the following|(?:^|\s)add:\s*$", re.I)
DM_WORDS = re.compile(r"\b(DC|the characters?|the party|players?|stat block|appendix|hit points|saving throw|ability check|"
                      r"initiative|XP|the adventurers|creatures?|rulebook|award)\b", re.I)
PRESENCE = re.compile(r"\b(are|is|stand|stands|guard|guards|inhabit|inhabits|lurk|lurks|hide|hiding|hidden|wait|waits|"
                      r"share|shares|confined|stationed|rest|rests|tend|tends|dwell|dwells|live|lives|keep watch|patrol|sleep|sleeps|sit|sits|here)\b", re.I)
JUNK_LINE = re.compile(r"^(p\d{1,3}|\d{1,3}|player version|dm version)$", re.I)


# ------------------------------------------------------------------ normalizing (what a card may store)
def _slug(text: str) -> str:
    t = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:48]


def _int(v, default=0, lo=-10_000, hi=1_000_000) -> int:
    try:
        return max(lo, min(hi, int(float(v))))
    except (TypeError, ValueError):
        return default


def _enemy(raw) -> dict | None:
    if not isinstance(raw, dict) or not str(raw.get("name", "")).strip():
        return None
    out = {"name": truncate(str(raw["name"]).strip(), 50), "count": _int(raw.get("count"), 1, 1, 8)}
    for k, lo, hi in (("hp", 1, 999), ("ac", 1, 40), ("attack_bonus", -5, 30), ("init_bonus", -5, 15)):
        if raw.get(k) not in (None, ""):
            out[k] = _int(raw.get(k), 0, lo, hi)
    if str(raw.get("damage") or "").strip():
        out["damage"] = truncate(re.sub(r"[^0-9d+\- ]", "", str(raw["damage"])).replace(" ", "") or "1d6", 16)
    return out


def _check(raw) -> dict | None:
    if not isinstance(raw, dict) or not str(raw.get("what", "")).strip():
        return None
    return {"what": truncate(str(raw["what"]).strip(), 240), "skill": truncate(str(raw.get("skill", "")).strip(), 40),
            "dc": _int(raw.get("dc"), 10, 1, 40)}


def _grid(raw) -> dict:
    """Where the map picture's own squares are, in the picture's pixels: square size and the first line's offset (as
    Foundry VTT and Roll20 align a map). Empty when not set: then the squares just divide the picture evenly."""
    if not isinstance(raw, dict):
        return {}
    try:
        g = {k: float(raw.get(k) or 0) for k in ("size", "ox", "oy", "nat_w", "nat_h")}
    except (TypeError, ValueError):
        return {}
    if not (4 <= g["size"] <= 1000 and g["nat_w"] > 0 and g["nat_h"] > 0):
        return {}
    g["ox"] %= g["size"]
    g["oy"] %= g["size"]
    return {k: round(v, 2) for k, v in g.items()}


def _painted(m: dict) -> dict:
    """A map Calíope painted itself keeps its terrain tiles (walls block, trees give cover) and its type."""
    if not isinstance(m.get("tiles"), list) or not m["tiles"]:
        return {}
    from .maps import MapError, clean_tiles
    try:
        return {"tiles": clean_tiles(m["tiles"]), "kind": str(m.get("kind") or "")[:20]}
    except MapError:
        return {}


# words in a scene that say what kind of place it is (the first kind with most hits wins)
PLACE_WORDS = {
    "cave": ("cave", "cavern", "grotto", "tunnel", "hideout", "lair", "den", "mine", "caverna", "gruta", "toca", "covil", "mina"),
    "dungeon": ("dungeon", "crypt", "tomb", "vault", "cellar", "ruin", "castle", "keep", "manor", "temple", "corridor",
                "chamber", "masmorra", "cripta", "tumba", "ruína", "castelo", "templo", "corredor", "câmara", "porão"),
    "tavern": ("tavern", "inn", "pub", "hall", "house", "shop", "room", "taverna", "estalagem", "casa", "loja", "salão", "quarto"),
    "street": ("street", "town", "village", "city", "alley", "market", "square", "rua", "vila", "aldeia", "cidade", "beco",
               "mercado", "praça"),
    "river": ("river", "stream", "creek", "bridge", "ford", "lake", "rio", "riacho", "ponte", "lago"),
    "road": ("road", "trail", "path", "ambush", "wagon", "cart", "highway", "estrada", "trilha", "caminho", "emboscada", "carroça"),
    "forest": ("forest", "wood", "woods", "grove", "jungle", "thicket", "floresta", "bosque", "mata", "selva"),
}


def pick_kind(scene: dict | None) -> str:
    """Which generated map fits a scene, from its name first and then its text."""
    if not scene:
        return "field"
    best, score = "field", 0
    name = (scene.get("name", "") + " " + " ".join(scene.get("aliases") or [])).lower()
    body = (scene.get("read_aloud", "") + " " + scene.get("notes", "")).lower()[:4000]
    for kind, words in PLACE_WORDS.items():
        pat = r"\b(" + "|".join(re.escape(w) for w in words) + r")s?\b"
        n = 5 * len(re.findall(pat, name)) + len(re.findall(pat, body))
        if n > score:
            best, score = kind, n
    return best


def start_cell(tiles: list[str]) -> tuple[int, int]:
    """Where a generated map's scene marker goes: the open square nearest the middle (on the road, if there is one)."""
    from .maps import open_cells
    h, w = len(tiles), len(tiles[0])
    cells = open_cells(tiles) or [(w // 2, h // 2)]
    road = [c for c in cells if tiles[c[1]][c[0]] == ":"]
    return min(road or cells, key=lambda c: (c[0] - w / 2) ** 2 + (c[1] - h / 2) ** 2)


def add_painted_map(adv: dict, scene_id: str, kind: str, tiles: list[str], url: str, geom: dict) -> dict:
    """Put a painted map in the adventure as the scene's map (replacing the one painted for it before)."""
    adv = normalize_adventure(adv)
    s = get_scene(adv, scene_id)
    if not s:
        return adv
    mid = "painted-" + s["id"]
    x, y = start_cell(tiles)
    m = {"id": mid, "name": truncate("Painted: " + s["name"], 80), "picture": url, "player_picture": "", "cols": len(tiles[0]),
         "rows": len(tiles), "markers": {s["id"]: [round((x + 0.5) / len(tiles[0]), 4), round((y + 0.5) / len(tiles), 4)]},
         "grid": geom, "reveal": 0, "tiles": tiles, "kind": kind}
    adv["maps"] = [x for x in adv["maps"] if x["id"] != mid] + [m]
    for sc in adv["scenes"]:
        if sc["id"] == s["id"]:
            sc["map"] = mid
    return normalize_adventure(adv)


def normalize_adventure(raw) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    parts, part_ids = [], set()
    for p in raw.get("parts") if isinstance(raw.get("parts"), list) else []:
        if isinstance(p, dict) and str(p.get("title", "")).strip():
            pid = _slug(p.get("id") or p["title"]) or f"part-{len(parts) + 1}"
            while pid in part_ids:
                pid += "-x"
            part_ids.add(pid)
            parts.append({"id": pid, "title": truncate(str(p["title"]).strip(), 80)})
    scenes, ids = [], set()
    for s in (raw.get("scenes") if isinstance(raw.get("scenes"), list) else [])[:MAX_SCENES]:
        if not isinstance(s, dict) or not str(s.get("name", "")).strip():
            continue
        sid = _slug(s.get("id") or f"{s.get('group', '')} {s['name']}") or f"scene-{len(scenes) + 1}"
        while sid in ids:
            sid += "-x"
        ids.add(sid)
        part = str(s.get("part") or "")
        if part not in part_ids:
            part = parts[0]["id"] if parts else ""
        scenes.append({
            "id": sid, "part": part, "name": truncate(str(s["name"]).strip(), 80),
            "group": truncate(str(s.get("group") or "").strip(), 80),
            "aliases": [truncate(str(a).strip(), 60) for a in (s.get("aliases") or []) if str(a).strip()][:8]
            if isinstance(s.get("aliases"), list) else [],
            "read_aloud": str(s.get("read_aloud") or "")[:TEXT_LIMIT],
            "notes": str(s.get("notes") or "")[:TEXT_LIMIT],
            "checks": [c for c in (_check(x) for x in (s.get("checks") or [])[:12]) if c] if isinstance(s.get("checks"), list) else [],
            "enemies": [e for e in (_enemy(x) for x in (s.get("enemies") or [])[:8]) if e] if isinstance(s.get("enemies"), list) else [],
            "treasure": truncate(str(s.get("treasure") or ""), 1500),
            "xp": _int(s.get("xp"), 0, 0, 1_000_000),
            "leads": [str(x)[:48] for x in (s.get("leads") or []) if str(x).strip()][:12] if isinstance(s.get("leads"), list) else [],
            "music": str(s.get("music") or "")[:20],
            "map": str(s.get("map") or "")[:48],
        })
    maps, map_ids = [], set()
    for m in (raw.get("maps") if isinstance(raw.get("maps"), list) else [])[:MAX_MAPS]:
        if not isinstance(m, dict) or not str(m.get("name", "")).strip():
            continue
        mid = _slug(m.get("id") or m["name"]) or f"map-{len(maps) + 1}"
        while mid in map_ids:
            mid += "-x"
        map_ids.add(mid)
        markers = {}
        for k, v in (m.get("markers") or {}).items() if isinstance(m.get("markers"), dict) else []:
            if k in ids and isinstance(v, (list, tuple)) and len(v) == 2:
                try:
                    markers[k] = [round(min(1.0, max(0.0, float(v[0]))), 4), round(min(1.0, max(0.0, float(v[1]))), 4)]
                except (TypeError, ValueError):
                    pass
        maps.append({"id": mid, "name": truncate(str(m["name"]).strip(), 80), "picture": _url(m.get("picture")),
                     "player_picture": _url(m.get("player_picture")), "cols": _int(m.get("cols"), 30, 6, MAP_MAX),
                     "rows": _int(m.get("rows"), 20, 4, MAP_MAX), "markers": markers, "grid": _grid(m.get("grid")),
                     "reveal": _int(m.get("reveal"), 6, 0, 40), **_painted(m)})
    for s in scenes:
        if s["map"] and s["map"] not in map_ids:
            s["map"] = ""
    return {"title": truncate(str(raw.get("title") or "").strip(), 100), "background": str(raw.get("background") or "")[:4000],
            "parts": parts, "scenes": scenes, "maps": maps}


def has_adventure(data: dict) -> bool:
    return bool(((data or {}).get("adventure") or {}).get("scenes"))


# ------------------------------------------------------------------ splitting a book into scenes
def _paragraphs(text: str) -> list[str]:
    """Lines of the text joined into paragraphs. Text copied from a web page has one paragraph per line; text read from
    a PDF is cut at the column width, so short lines are joined until a sentence ends."""
    lines = [ln.rstrip() for ln in text.replace("\r", "").replace("­", "").split("\n")]
    filled = [ln for ln in lines if ln.strip()]
    pdf_like = filled and sum(len(ln) for ln in filled) / len(filled) < 75 and len(filled) > 20
    out: list[str] = []
    buf = ""
    for ln in lines:
        s = ln.strip()
        if not s or JUNK_LINE.match(s) or (ln.startswith(" ") and len(s.split()) <= 3 and not s.endswith(".")):
            if buf:
                out.append(buf)
                buf = ""
            continue
        if not pdf_like:
            out.append(s)
            continue
        if buf and (_heading_like(s) or _heading_like(buf) or buf.endswith((".", "!", "?", ":", "\"", "”")) and s[:1].isupper()
                    and len(buf) < 60):
            out.append(buf)
            buf = s
        else:
            buf = re.sub(r"(\w)-$", r"\1", buf) + ("" if buf.endswith("-") else " ") + s if buf else s
    if buf:
        out.append(buf)
    return [p.strip() for p in out if p.strip()]


def _heading_like(s: str) -> bool:
    s = s.strip()
    if AREA.match(s) or PART.match(s):
        return True
    if not s or len(s) > 60 or s[-1] in ".,;:)" or not s[0].isalpha() or s[0].islower():
        return False
    words = s.split()
    if len(words) > 8:
        return False
    small = ("of", "the", "and", "a", "an", "in", "on", "to", "or", "for", "with", "at", "by", "from")
    return all(w[0].isupper() or w.lower() in small or not w[0].isalpha() for w in words)


def _read_aloud(par: str, cued: bool) -> bool:
    if par.startswith(BOXED):
        return True
    words = len(par.split())
    if words < 8:
        return False
    if READ_CUE.search(par):  # "Read the boxed text when you're ready" is advice to the GM
        return False
    narration = re.sub(r"[\"“][^\"”]*[\"”]", " ", par)  # "Klarg will build a throne from your bones" is dialogue
    you = len(re.findall(r"\b(you|your|you're|you've|yourselves)\b", narration, re.I))
    if cued:
        return not re.search(r"\b(DC \d|stat block|appendix)\b", par)
    return you >= 1 and not DM_WORDS.search(par) and not par.lower().startswith(("if ", "when ", "any character"))


def _monster_rx() -> re.Pattern:
    names = sorted(MONSTERS, key=len, reverse=True)
    forms = []
    for n in names:
        plural = n[:-1] + "ves" if n.endswith("f") else n[:-1] + "ies" if n.endswith("y") else n + "s"
        forms.append(re.escape(plural))
        forms.append(re.escape(n))
    return re.compile(r"\b(" + "|".join(forms) + r")\b", re.I)


_MON = _monster_rx()
_ONE = "|".join(re.escape(n) for n in sorted(MONSTERS, key=len, reverse=True))
NOT_NAMES = {"If", "When", "The", "Since", "While", "Once", "After", "Before", "Unless", "Each", "Every", "A", "An", "And",
             "But", "Then", "This", "That", "Any", "No", "As", "Although", "Because", "Until", "With", "Without"}


def _singular(word: str) -> str:
    w = word.lower()
    if w in MONSTERS:
        return w
    for n in MONSTERS:
        if w in (n + "s", n[:-1] + "ves", n[:-1] + "ies"):
            return n
    return w


def monster_stats(name: str) -> dict:
    base = _singular(name)
    if base not in MONSTERS:
        return {}
    ac, hp, atk, dmg, init = MONSTERS[base]
    return {"ac": ac, "hp": hp, "attack_bonus": atk, "damage": dmg, "init_bonus": init}


def find_enemies(paragraphs: list[str]) -> list[dict]:
    """'Four goblins are hiding in the woods', 'Klarg the bugbear', 'his pet wolf, Ripper' -> enemies with SRD numbers."""
    found: dict[str, dict] = {}
    num = "|".join(sorted((re.escape(k) for k in NUMBERS), key=len, reverse=True))
    for par in paragraphs:
        for sentence in re.split(r"(?<=[.!?])\s+", par):
            if not PRESENCE.search(sentence) or re.match(r"\s*(if|when|after|once)\b", sentence, re.I):
                continue
            for m in re.finditer(rf"\b({num}|\d+)\s+(?:[a-z\-]+\s+){{0,2}}?({_MON.pattern[3:-3]})\b", sentence, re.I):
                count = NUMBERS.get(m.group(1).lower()) or _int(m.group(1), 1)
                kind = _singular(m.group(2))
                key = kind
                if key in found:  # the same group told twice ("a pair of goblins" ... "Two goblins are stationed")
                    found[key]["count"] = min(8, max(found[key]["count"], count))
                else:
                    found[key] = {"name": kind.title(), "count": min(8, count), **monster_stats(kind)}
            for m in re.finditer(rf"\b([A-Z][a-z]+) the ({_ONE})\b(?!s)", sentence):
                name, kind = m.group(1), _singular(m.group(2))
                if name not in NOT_NAMES and name not in found:
                    found[name] = {"name": name, "count": 1, **monster_stats(kind)}
            for m in re.finditer(rf"\b({_ONE}),?\s+(?:named\s+|called\s+)?([A-Z][a-z]+)\b", sentence):
                kind, name = _singular(m.group(1)), m.group(2)
                if name not in found and name not in NOT_NAMES:
                    found[name] = {"name": name, "count": 1, **monster_stats(kind)}
    return list(found.values())[:8]


def find_checks(text: str) -> list[dict]:
    out, seen = [], set()
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        for m in CHECK.finditer(sentence):
            ability, skill, kind = m.group(2).title(), (m.group(3) or "").strip(), m.group(4).lower()
            label = f"{ability} ({skill})" if skill else ability
            label += " save" if kind.startswith("sav") else ""
            key = (label, m.group(1), sentence[:40])
            if key in seen:
                continue
            seen.add(key)
            out.append({"what": truncate(sentence.strip(), 240), "skill": label, "dc": int(m.group(1))})
    return out[:12]


def _guess_music(text: str) -> str:
    t = text.lower()
    for mood, words in (("dungeon", ("cave", "cavern", "tunnel", "crypt", "dungeon", "mine")), ("tavern", ("inn", "tavern", "alehouse")),
                        ("town", ("town", "village", "market", "street")), ("forest", ("woods", "forest", "trail", "thicket")),
                        ("horror", ("undead", "corpse", "banshee", "ghoul", "zombie"))):
        if any(w in t for w in words):
            return mood
    return ""


BOXED = "\u0001"  # marks a paragraph the book itself shows as read-aloud text (a ">>" box in Markdown)


def is_markdown(text: str) -> bool:
    lines = text.splitlines()
    return sum(1 for ln in lines if re.match(r"^#{1,6}\s+\S", ln)) >= 3


def markdown_to_text(text: str) -> str:
    """A Markdown book (as exported by 5e.tools or Homebrewery) -> the plain layout the splitter reads: headings without
    '#', '# Part' titles as "Part N: ...", '>>' boxes as read-aloud paragraphs, '>' sidebars as plain text, pictures and
    the appendices (monsters, items: read separately) left out."""
    out: list[str] = []
    part = 0
    box: list[str] = []

    def flush_box():
        if box:
            out.append(BOXED + " ".join(x for x in box if x))
            out.append("")
            box.clear()

    for raw in text.replace("\r", "").split("\n"):
        line = raw.rstrip()
        if line.startswith(">>"):
            body = line[2:].strip()
            if body:
                box.append(_plain(body))
            else:
                flush_box()
            continue
        flush_box()
        if line.startswith(">"):
            line = line.lstrip(">").strip()
        if re.match(r"^!\[[^\]]*\]\([^)]*\)", line) or line.strip() in ("___", "---"):
            continue
        h = re.match(r"^(#{1,6})\s+(.+?)\s*#*$", line)
        if h:
            title = _plain(h.group(2))
            if len(h.group(1)) == 1:
                if re.match(r"^(appendix|credits)", title, re.I):
                    break                                   # monsters and items: not scenes
                if not re.match(r"^introduction$", title, re.I):
                    part += 1
                    out += ["", f"Part {part}: {title}", ""]
                    continue
            out += ["", ("¶" if len(h.group(1)) >= 4 else "") + title, ""]   # ¶: a minor heading (a subsection inside an area)
            continue
        b = re.match(r"^\*\*([^*]{2,60})\*\*\s*$", line)
        if b:                                               # a bold line on its own: a subsection title
            out += ["", "§" + b.group(1).strip().rstrip("."), ""]
            continue
        out.append(_plain(line))
    flush_box()
    return "\n".join(out)


def _plain(text: str) -> str:
    t = re.sub(r"\*\*\*|\*\*|(?<![\w*])\*(?!\s)|(?<=\S)\*(?![\w*])", "", text)
    return re.sub(r"\{@\w+\s+([^}|]+)[^}]*\}", r"\1", t).strip()


def split_adventure(text: str, part_title: str = "") -> dict:
    """A book (or a chapter of it) -> {"background", "parts", "scenes", "npcs"} for the card editor to review."""
    strict = is_markdown(text)  # the book marks its read-aloud boxes: no guessing
    if strict:
        text = markdown_to_text(text)
    pars = _paragraphs(text)
    parts: list[dict] = []
    scenes: list[dict] = []
    background: list[str] = []
    npcs: list[dict] = []
    group = ""
    mode = "scene"          # scene | sub | background | skip
    sub = ""
    cued = False

    def part_id() -> str:
        if not parts:
            parts.append({"id": _slug(part_title or "Part 1") or "part-1", "title": part_title or "Part 1"})
        return parts[-1]["id"]

    def new_scene(name: str, number: str = "") -> dict:
        sc = {"name": name, "group": group if number else "", "number": number, "part": part_id(), "body": [], "subs": [],
              "aliases": [name.split(". ", 1)[-1], f"area {number}"] if number else []}
        scenes.append(sc)
        return sc

    area_numbers = [(i, AREA.match(p)) for i, p in enumerate(pars)]
    current: dict | None = None
    for i, par in enumerate(pars):
        nxt = pars[i + 1] if i + 1 < len(pars) else ""
        if par.startswith("§"):  # a bold line on its own (Markdown): always a subsection of the current scene
            if current is not None:
                mode, sub = "sub", par[1:].strip()
                if sub.lower().startswith("roleplaying "):
                    npcs.append({"name": sub[12:].strip(), "lines": []})
                cued = False
                continue
            par = par[1:].strip()
        if par.startswith("¶"):
            par = par[1:].strip()
            if current is not None and (current.get("number") or SUBSECTION.match(par)) and not AREA.match(par):
                mode, sub = "sub", par
                if par.lower().startswith(("roleplaying ", "role playing ")):
                    npcs.append({"name": re.sub(r"^role\s?playing\s+", "", par, flags=re.I).strip(), "lines": []})
                cued = False
                continue
        area = AREA.match(par)
        heading = area or (_heading_like(par) and nxt and not _heading_like(nxt) or _heading_like(par) and len(par) < 40)
        if heading and not area and (len(par.split()) > 8 or "\t" in par):
            heading = False
        if heading:
            cued = False
            title = par.strip()
            pm = PART.match(title)
            if pm:
                label = pm.group(2).strip().strip("\"'“”") or f"Part {pm.group(1)}"
                parts.append({"id": _slug(label) or f"part-{len(parts) + 1}", "title": label})
                group, current, mode = "", None, "scene"
                continue
            if area:
                current = new_scene(f"{area.group(1)}. {area.group(2).strip()}", area.group(1))
                mode = "scene"
                continue
            if SKIP_HEADINGS.match(title):
                mode = "skip"
                continue
            if BACKGROUND_HEADINGS.match(title):
                mode, sub = "background", title
                continue
            if current and title.lower() == current["name"].lower() or group and title.lower() == group.lower():
                continue  # the map's title repeats the heading
            if SUBSECTION.match(title) and current is not None:
                mode, sub = "sub", title
                if title.lower().startswith("roleplaying "):
                    npcs.append({"name": title[12:].strip(), "lines": []})
                continue
            inside_areas = current is not None and current.get("number")
            if inside_areas:
                later = next((m for j, m in area_numbers[i + 1:] if m), None)
                cur_n = _int(re.sub(r"\D", "", current["number"]), 0)
                resets = later is not None and _int(re.sub(r"\D", "", later.group(1)), 0) <= cur_n
                if not resets:
                    mode, sub = "sub", title
                    continue
            group = title
            current = new_scene(title)
            mode = "scene"
            continue

        # a paragraph
        if mode == "skip":
            continue
        if mode == "background":
            background.append(par)
            continue
        if current is None:
            current = new_scene(part_title or (f"{parts[-1]['title']}: the start" if parts else "Beginning"))
        if mode == "sub":
            current["subs"].append((sub, par))
            if par.startswith(BOXED):  # a read-aloud box inside a subsection ("Flood!") is still read aloud
                current["body"].append((par, True))
            if npcs and re.match(r"role\s?playing\s", sub, re.I) and npcs[-1]["name"] == re.sub(r"^role\s?playing\s+", "", sub, flags=re.I).strip():
                npcs[-1]["lines"].append(par)
        else:
            current["body"].append((par, par.startswith(BOXED) if strict else _read_aloud(par, cued)))
        cued = bool(READ_CUE.search(par))

    out_scenes = []
    for k, sc in enumerate(scenes):
        intro = not sc["number"] and any(x["number"] and x["group"] == sc["name"] for x in scenes[k + 1:])
        body = sc["body"]
        if not body and not sc["subs"]:
            continue
        if sc["number"] and not strict and not any(ra for _, ra in body):
            # boxed text without "you" ("Sacks and crates of looted provisions..."): the first plain description after the intro
            for k, (p, _) in enumerate(body[1:], 1):
                if len(p.split()) >= 15 and not DM_WORDS.search(p) and not re.match(r"\s*(if|when)\b", p, re.I):
                    body[k] = (p, True)
                    break
        body = [(p.lstrip(BOXED), ra) for p, ra in body]
        sc["subs"] = [(t, p.lstrip(BOXED)) for t, p in sc["subs"]]
        read = "\n\n".join(p for p, ra in body if ra)
        notes = [p for p, ra in body if not ra]
        subs_text: dict[str, list[str]] = {}
        for title, par in sc["subs"]:
            subs_text.setdefault(title, []).append(par)
        treasure = "\n".join(next((v for k, v in subs_text.items() if k.lower() == "treasure"), []))
        for title, ps in subs_text.items():
            if title.lower() != "treasure":
                notes.append(f"{title}: " + " ".join(ps))
        all_text = "\n".join([p for p, _ in body] + [p for _, p in sc["subs"]])
        xp = sum(_int(m.group(1).replace(",", ""), 0) for m in XP.finditer(all_text))
        leads = sorted({m.group(1) for m in re.finditer(r"\barea\s+(\d{1,2})\b", all_text, re.I)} - {sc["number"]}, key=int)
        out_scenes.append({
            "name": sc["name"], "group": sc["group"], "part": sc["part"], "aliases": sc["aliases"],
            "read_aloud": read, "notes": "\n\n".join(notes), "treasure": treasure, "xp": xp,
            "checks": find_checks(all_text), "enemies": [] if intro else find_enemies([p for p, ra in body if not ra]),
            "leads": [f"area {n}" for n in leads], "music": _guess_music(sc["name"] + " " + sc["group"] + " " + read),
        })
    # area leads -> scene ids of the same group
    norm = normalize_adventure({"parts": parts, "scenes": out_scenes})
    by_area = {(s["group"], a): s["id"] for s in norm["scenes"] for a in s["aliases"] if a.startswith("area ")}
    for s in norm["scenes"]:
        s["leads"] = [by_area.get((s["group"], x), "") for x in s["leads"]]
        s["leads"] = [x for x in s["leads"] if x]
    # a scene with no keyed areas leads on to the next one in the book (the start -> the ambush -> the trail -> the hideout)
    sc = norm["scenes"]
    for i, s in enumerate(sc[:-1]):
        nxt = sc[i + 1]
        if not s["leads"] and not re.match(r"^[A-Z]?\d", s["name"]) and nxt["part"] == s["part"]:
            s["leads"] = [nxt["id"]]
    found_npcs = [{"name": n["name"], "description": truncate(" ".join(n["lines"]), 600)} for n in npcs
                  if n["lines"] and n["name"][:1].isupper() and not re.search(r"\b(NPCs|the)\b|s$", n["name"])]
    return {"background": truncate("\n\n".join(background), 4000), "parts": norm["parts"], "scenes": norm["scenes"],
            "npcs": found_npcs}


def merge(old: dict, new: dict, title: str = "") -> dict:
    """Add an imported chapter to the card's adventure (scenes with the same id are replaced)."""
    old = normalize_adventure(old)
    parts = old["parts"] + [p for p in new["parts"] if p["id"] not in {x["id"] for x in old["parts"]}]
    new_ids = {s["id"] for s in new["scenes"]}
    scenes = [s for s in old["scenes"] if s["id"] not in new_ids] + new["scenes"]
    background = old["background"] or new.get("background", "")
    if old["background"] and new.get("background") and new["background"] not in old["background"]:
        background = truncate(old["background"] + "\n\n" + new["background"], 4000)
    maps = list(old["maps"])
    for g in dict.fromkeys(s["group"] for s in new["scenes"] if s["group"]):
        if not any(m["name"].lower() == g.lower() for m in maps):
            maps.append({"name": g, "picture": "", "markers": {}})
    adv = normalize_adventure({"title": old["title"] or title, "background": background, "parts": parts,
                               "scenes": scenes, "maps": maps})
    by_name = {m["name"].lower(): m["id"] for m in adv["maps"]}
    for s in adv["scenes"]:
        if s["group"] and not s["map"]:
            s["map"] = by_name.get(s["group"].lower(), "")
    return adv


# ------------------------------------------------------------------ in a game
def leads_of(adv: dict, scene: dict) -> list[str]:
    """Where a scene leads: its own list, or (a scene without keyed areas) the next scene of the same part."""
    if scene.get("leads"):
        return scene["leads"]
    scenes = (adv or {}).get("scenes") or []
    if re.match(r"^[A-Z]?\d", scene.get("name", "")):
        return []
    i = next((k for k, x in enumerate(scenes) if x["id"] == scene["id"]), -1)
    if 0 <= i < len(scenes) - 1 and scenes[i + 1].get("part") == scene.get("part"):
        return [scenes[i + 1]["id"]]  # (a location's intro: its first area)
    return []


def get_scene(adv: dict, scene_id: str) -> dict | None:
    return next((s for s in (adv or {}).get("scenes") or [] if s["id"] == scene_id), None)


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", re.sub(r"\b(the|a|an|of)\b", " ", t)).strip()


def match_scene(adv: dict, location: str, text: str = "", current: str = "") -> str | None:
    """The scene the story is in now, from the tracker's location (and "area 3" in the reply), or None."""
    loc = _norm(location)
    scenes = (adv or {}).get("scenes") or []
    cur = get_scene(adv, current)
    best, score = None, 0
    for s in scenes:
        for name in [s["name"].split(". ", 1)[-1], s["name"], *[a for a in s["aliases"] if not a.startswith("area ")]]:
            n = _norm(name)
            if not n or len(n) < 3:
                continue
            sc = 3 if n == loc else 2 if loc and re.search(rf"\b{re.escape(n)}\b", loc) else 0
            if sc and cur and s["group"] and s["group"] == cur["group"]:
                sc += 0.5  # the same location group wins ties
            if sc and s["group"] and _norm(s["group"]) and _norm(s["group"]) in loc:
                sc += 1    # "Mill Ruins yard": the yard of the mill, not the mill itself
            if sc > score:
                best, score = s["id"], sc
    if not best and cur and cur["group"]:
        m = re.search(r"\barea\s+(\d{1,2}[a-z]?)\b", f"{location} {text}", re.I)
        if m:
            best = next((s["id"] for s in scenes if s["group"] == cur["group"] and f"area {m.group(1)}" in s["aliases"]), None)
    return best


def follow_player(adv: dict, state: dict, text: str) -> str | None:
    """The player heads for one of the ways on from here ("I climb up to the overpass", "we go to area 3")."""
    cur = get_scene(adv, (state.get("adventure") or {}).get("scene", ""))
    if not cur:
        return None
    said = _norm(text)
    for lead in (get_scene(adv, x) for x in leads_of(adv, cur)):
        if not lead:
            continue
        names = [lead["name"].split(". ", 1)[-1], *[a for a in lead["aliases"] if not a.startswith("area ")]]
        if any(len(_norm(n)) >= 4 and re.search(rf"\b{re.escape(_norm(n))}\b", said) for n in names):
            return lead["id"]
        m = re.search(r"\barea\s+(\d{1,2}[a-z]?)\b", text, re.I)
        if m and f"area {m.group(1)}" in lead["aliases"]:
            return lead["id"]
    return None


FIGHT_WORDS = re.compile(
    r"\b(attack\w*|charg\w*|ambush\w*|leap\w* (?:out|at)|lunge\w*|swing\w*|strike\w*|shoot\w*|arrows? (?:fly|whizz|thud)\w*|"
    r"draws? (?:a |their |his |her )?(?:weapon|blade|sword|bow)s?|battle|fight\w*|initiative|combat|close in|"
    r"atac\w*|embosca\w*|investe\w*|golpe\w*|flecha\w*|batalha|luta\w*|combate|iniciativa)\b", re.I)


def _mentions(text: str, name: str) -> bool:
    n = _singular(name)
    forms = {n, n + "s", n[:-1] + "ves" if n.endswith("f") else n, n[:-1] + "ies" if n.endswith("y") else n}
    return any(re.search(rf"\b{re.escape(f)}\b", text, re.I) for f in forms if len(f) >= 3)


def follow_story(adv: dict, state: dict, text: str) -> str | None:
    """The story itself walked into the next scene: its enemies show up ("goblins leap out") or its name is said."""
    cur = get_scene(adv, (state.get("adventure") or {}).get("scene", ""))
    if not cur:
        return None
    for lead in (get_scene(adv, x) for x in leads_of(adv, cur)):
        if not lead:
            continue
        if any(_mentions(text, e["name"]) for e in lead["enemies"]) and not any(_mentions(text, e["name"]) for e in cur["enemies"]):
            return lead["id"]
        short = _norm(lead["name"].split(". ", 1)[-1])
        if len(short) >= 6 and re.search(rf"\b{re.escape(short)}\b", _norm(text)):
            return lead["id"]
    return None


def fight_offer(adv: dict, state: dict, user_text: str, reply: str) -> dict | None:
    """A fight is breaking out in a scene that has enemies: the chat offers to start it on the battle grid."""
    st = state.get("adventure") or {}
    s = get_scene(adv, st.get("scene", ""))
    if not s or not s["enemies"] or (state.get("combat") or {}).get("active") or s["id"] in (st.get("fought") or []):
        return None
    talked_of = any(_mentions(reply, e["name"]) for e in s["enemies"])
    if FIGHT_WORDS.search(user_text) or (talked_of and FIGHT_WORDS.search(reply)):
        return {"scene": s["id"], "name": s["name"],
                "enemies": [{"name": e["name"], "count": e["count"]} for e in s["enemies"]]}
    return None


def enter(state: dict, scene_id: str) -> bool:
    """Move the game to a scene. True when the scene changed."""
    adv = state.setdefault("adventure", {"scene": "", "visited": [], "xp_given": []})
    if adv.get("scene") == scene_id:
        return False
    adv["scene"] = scene_id
    adv.setdefault("visited", [])
    if scene_id and scene_id not in adv["visited"]:
        adv["visited"].append(scene_id)
        adv["fresh"] = scene_id  # the read-aloud text is narrated on the first reply in a new scene
    return True


def move(adv: dict, state: dict, scene_id: str | None) -> str:
    """Enter a scene and set its music. Returns the scene's name when the game moved, else ''."""
    s = get_scene(adv, scene_id or "")
    if not s or not enter(state, s["id"]):
        return ""
    if s["music"]:
        state["scene_mood"] = s["music"]
    return s["name"]


def narrated(state: dict) -> bool:
    """After a reply: the scene's read-aloud text has been told."""
    st = state.get("adventure") or {}
    if st.get("fresh") and st.get("fresh") == st.get("scene"):
        st["fresh"] = ""
        return True
    return False


def scene_section(adv: dict, state: dict, limit: int = 2600) -> str:
    """The current scene for the Aedo's notes (sent with the reply, kept short: the RX 580 reads every token)."""
    st = state.get("adventure") or {}
    s = get_scene(adv, st.get("scene", ""))
    if not s:
        return ""
    title = f"{s['group']} · {s['name']}" if s["group"] else s["name"]
    lines = [f"## Adventure scene: {title}"]
    if s["read_aloud"] and st.get("fresh") == s["id"]:
        lines.append("The player just arrived. Narrate this read-aloud text close to word for word (in the story's language), "
                     "adapted to what the player is doing, then stop for the player:\n" + truncate(s["read_aloud"], 1400))
    elif s["read_aloud"]:
        lines.append("Already described: " + truncate(s["read_aloud"], 240))
    if s["notes"]:
        lines.append("GM notes (hidden; the player learns them only through play: what they see, ask the right person, or find "
                     "with a check):\n" + truncate(s["notes"], 1000))
    if s["checks"]:
        lines.append("Checks here (when the player tries one, ask for that roll with its DC and wait for the result; never "
                     "decide the outcome without the roll): " + "; ".join(f"{c['skill']} DC {c['dc']} ({truncate(c['what'], 90)})"
                                                                               for c in s["checks"]))
    if s["enemies"]:
        lines.append("Enemies here: " + ", ".join(f"{e['count']}x {e['name']}" if e["count"] > 1 else e["name"] for e in s["enemies"])
                     + ". If a fight breaks out, say so plainly: the app runs it on the battle grid.")
    if s["treasure"]:
        lines.append("Treasure (only if found): " + truncate(s["treasure"], 300))
    leads = [get_scene(adv, x) for x in leads_of(adv, s)]
    if any(leads):
        lines.append("Ways on from here: " + ", ".join(x["name"] for x in leads if x))
    return truncate("\n".join(lines), limit)


def adventure_background(adv: dict) -> str:
    """The adventure's background for the stable part of the prompt (GM-only, read once)."""
    if not adv or not adv.get("background"):
        return ""
    return "## The adventure (GM only; the player discovers it in play)\n" + truncate(adv["background"], 2500)


def combat_enemies(adv: dict, state: dict) -> list[dict]:
    s = get_scene(adv, (state.get("adventure") or {}).get("scene", ""))
    return [dict(e) for e in (s or {}).get("enemies") or []]


def battle_map(adv: dict, state: dict) -> dict | None:
    """The scene's map picture as the battle grid's background, with the scene's marker as the place to start."""
    s = get_scene(adv, (state.get("adventure") or {}).get("scene", ""))
    m = next((x for x in (adv or {}).get("maps") or [] if s and x["id"] == s["map"]), None)
    if not m or not (m["picture"] or m["player_picture"]):
        return None
    mark = m["markers"].get(s["id"])
    g = m.get("grid") or {}
    if g:  # the battle grid is the picture's own squares
        cols = max(6, min(MAP_MAX, int((g["nat_w"] - g["ox"]) // g["size"])))
        rows = max(4, min(MAP_MAX, int((g["nat_h"] - g["oy"]) // g["size"])))
        to_cell = lambda fx, fy: [(fx * g["nat_w"] - g["ox"]) / g["size"], (fy * g["nat_h"] - g["oy"]) / g["size"]]  # noqa: E731
    else:
        cols, rows = m["cols"], m["rows"]
        to_cell = lambda fx, fy: [fx * cols, fy * rows]  # noqa: E731
    near = None
    if mark:
        cx, cy = to_cell(*mark)
        near = [max(0, min(cols - 1, int(cx))), max(0, min(rows - 1, int(cy)))]
    visited = set((state.get("adventure") or {}).get("visited") or []) | {s["id"]}
    fog = [{"x": round(to_cell(*m["markers"][sid])[0], 2), "y": round(to_cell(*m["markers"][sid])[1], 2), "r": m["reveal"]}
           for sid in visited if sid in m["markers"]] if m.get("reveal") else []
    out = {"background": m["player_picture"] or m["picture"], "name": truncate(s["name"], 60), "w": cols, "h": rows,
           "near": near, "geom": g or None, "fog": fog}
    if m.get("tiles") and len(m["tiles"]) == rows and len(m["tiles"][0]) == cols:
        out.update(tiles=m["tiles"], painted=True)
    return out
