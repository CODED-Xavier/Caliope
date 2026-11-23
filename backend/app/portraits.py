"""Big character portraits shown above the part of a reply where that character speaks or acts.

The model marks a portrait with a line like  [[show: Lilia Valenheart | Happy]]. Some cards instead ask
for a markdown image  ![Lilia - Happy](https://...)  and small models often garble those links, so the
app never trusts the link: it reads the name and the mood, finds the right picture in the character's
portrait list, and rewrites the line as a clean [[show: ...]] tag. At most two portraits per reply.
"""
from __future__ import annotations

import re

MAX_PER_REPLY = 2


def _url(value) -> str:
    v = str(value or "").strip()
    return v if v.startswith(("http://", "https://", "/", "r2:")) and len(v) < 600 else ""


def normalize_portraits(raw) -> dict:
    """{"default": url, "moods": [{"n": 2, "label": "Happy", "url": url}, ...]} (at most 12 moods)."""
    if not isinstance(raw, dict):
        return {"default": "", "moods": []}
    moods = []
    for m in raw.get("moods", [])[:12] if isinstance(raw.get("moods"), list) else []:
        if isinstance(m, dict) and _url(m.get("url")) and str(m.get("label", "")).strip():
            try:
                n = int(m["n"]) if m.get("n") not in (None, "") else None
            except (TypeError, ValueError):
                n = None
            moods.append({"n": n, "label": str(m["label"]).strip()[:40], "url": _url(m["url"])})
    return {"default": _url(raw.get("default")), "moods": moods}


# Words the model may use for a mood -> the number most cards use (1=Standard ... 6=Blushing).
MOOD_WORDS = {
    1: ("standard", "neutral", "default", "normal", "calm", "serious"),
    2: ("happy", "smile", "smiling", "joy", "joyful", "glad", "cheerful", "excited"),
    3: ("sad", "upset", "crying", "worried", "hurt"),
    4: ("angry", "annoyed", "mad", "irritated", "frustrated"),
    5: ("disgusted", "very angry", "furious", "rage", "contempt"),
    6: ("blushing", "blush", "embarrassed", "shy", "flustered", "love"),
}

# What the text says right after a portrait tag, when the model gave no mood (or just "Standard").
FACE_WORDS = {
    6: r"blush\w*|flush\w*|fluster\w*|cora\w*|ruboriz\w*|embarrass\w*",
    5: r"sneer\w*|disgust\w*|scoff\w*|contempt\w*|furious|seeth\w*|nojo\w*|desprez\w*",
    4: r"glar\w*|scowl\w*|snap\w*|snarl\w*|growl\w*|angr\w*|frown\w*|clench\w*|irrit\w*|irad\w*|carranc\w*",
    3: r"tear\w*|sob\w*|cry\w*|cries|sad\w*|sigh\w*|trembl\w*|lágrim\w*|chor\w*|trist\w*|suspir\w*",
    2: r"smil\w*|smirk\w*|grin\w*|laugh\w*|beam\w*|chuckl\w*|giggl\w*|sorri\w*|ri\b|riu|risad\w*",
}


def face_from_text(text: str) -> str:
    """The mood number the next lines show ("she smiles" -> 2), or "" when nothing stands out."""
    low = (text or "").lower()[:320]
    best, pos = "", len(low) + 1
    for n, pat in FACE_WORDS.items():
        m = re.search(rf"\b({pat})", low)
        if m and m.start() < pos:
            best, pos = str(n), m.start()
    return best


_SHOW = re.compile(r"\[\[\s*show\s*:\s*([^|\]\n]+?)\s*(?:\|\s*([^\]\n]*?)\s*)?\]\]", re.I)
_IMG = re.compile(r"!\[([^\]\n]*)\]\(([^)\s]*)\)")
_DASH = re.compile(r"\s+[-–—:|]\s+|\s*[–—|]\s*")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def find_character(npcs: list[dict], name: str) -> dict | None:
    """The character a name refers to: exact name, then a unique first-name / part match."""
    target = _norm(name)
    if not target:
        return None
    for n in npcs:
        if _norm(n["name"]) == target:
            return n
    parts = [n for n in npcs if target in _norm(n["name"]).split() or _norm(n["name"]).startswith(target + " ")]
    if len(parts) == 1:
        return parts[0]
    first = target.split()[0]
    parts = [n for n in npcs if _norm(n["name"]).split()[:1] == [first]]
    return parts[0] if len(parts) == 1 else None


def pick_mood(portraits: dict, mood: str) -> tuple[str, str]:
    """(mood label, picture URL) for a mood word or number. Falls back to the standard picture."""
    moods = portraits.get("moods") or []
    want = _norm(mood)
    if moods:
        number = int(want) if want.isdigit() else None
        if number is None:
            for m in moods:  # the card's own label first ("Disgusted/Very Angry" matches "disgusted")
                labels = [_norm(x) for x in re.split(r"[/,]", m["label"])]
                if want and (want == _norm(m["label"]) or want in labels):
                    return m["label"], m["url"]
            for n, words in MOOD_WORDS.items():
                if want in words or any(w in want for w in words if len(w) > 3):
                    number = n
                    break
        for m in moods:
            if m["n"] == (number or 1):
                return m["label"], m["url"]
        return moods[0]["label"], moods[0]["url"]
    return ("Standard", portraits.get("default", "")) if portraits.get("default") else ("", "")


def _from_url(npcs: list[dict], url: str) -> tuple[dict | None, str]:
    """Guess the character (and mood number) from a link like .../Lilia/2.png or .../Lilia.png."""
    m = re.search(r"/([^/]+?)/(\d)\.\w+$", url) or re.search(r"/([^/]+?)\.\w+$", url)
    if not m:
        return None, ""
    who = re.sub(r"[_%20]+", " ", m.group(1))
    return find_character(npcs, who), (m.group(2) if m.lastindex and m.lastindex >= 2 else "")


def resolve_portraits(text: str, npcs: list[dict], max_n: int = MAX_PER_REPLY) -> tuple[str, dict[str, str]]:
    """Rewrite portrait marks as clean tags. Returns (new text, {"Name|Mood": picture URL})."""
    shown: dict[str, str] = {}
    people: set[str] = set()
    last_mood: dict[str, str] = {}
    last_who = [""]

    def tag(npc: dict | None, mood: str) -> str:
        if not npc or not npc.get("portraits"):
            return ""
        label, url = pick_mood(npc["portraits"], mood)
        if not url:
            return ""
        key = f"{npc['name']}|{label}"
        if npc["name"] not in people and len(people) >= max_n:
            return ""  # only the two most important characters get a picture
        if last_mood.get(npc["name"]) == label and last_who[0] == npc["name"]:
            return ""  # the same face again, nothing changed
        people.add(npc["name"])
        last_mood[npc["name"]] = label
        last_who[0] = npc["name"]
        shown[key] = url
        return f"\n[[show: {npc['name']} | {label}]]\n"

    def img_sub(m: re.Match) -> str:
        alt, url = m.group(1), m.group(2)
        bits = _DASH.split(alt, maxsplit=1)
        npc = find_character(npcs, bits[0]) if bits and bits[0] else None
        mood = bits[1] if len(bits) > 1 else ""
        if npc is None:
            npc, number = _from_url(npcs, url)
            mood = mood or number
        return tag(npc, mood)

    # Both forms in reading order, so "the first two" means the first two that appear.
    combined = re.compile(f"{_SHOW.pattern}|{_IMG.pattern}", re.I)

    def any_sub(m: re.Match) -> str:
        if m.group(1) is not None:
            mood = (m.group(2) or "").strip()
            if not mood or _norm(mood) in ("standard", "neutral", "default", "normal"):
                after = text[m.end():]
                nxt = combined.search(after)
                mood = face_from_text(after[: nxt.start() if nxt else None]) or mood  # the face the next lines describe
            return tag(find_character(npcs, m.group(1)), mood)
        return img_sub(_IMG.match(m.group(0)))

    out = combined.sub(any_sub, text or "")
    out = place_before_speech(out)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out, shown


_QUOTE = re.compile(r"[\"\u201c\u00ab]")
_TAG_LINE = re.compile(r"^\[\[show:[^\]]*\]\]$")


def place_before_speech(text: str) -> str:
    """Move each portrait to just before the character's spoken line, after the narration.

    A tag followed by narration slides down to the first paragraph with speech (before the next tag). When that
    paragraph starts with narration and the speech comes after a full sentence, the paragraph is split there so the
    picture sits between the narration and the line."""
    paras = [p for p in re.split(r"\n\s*\n|\n(?=\[\[show:)|(?<=\]\])\n", text) if p.strip()]
    out: list[str] = []
    i = 0
    while i < len(paras):
        p = paras[i].strip()
        if not _TAG_LINE.match(p):
            out.append(p)
            i += 1
            continue
        # find the first paragraph with speech after this tag, before the next tag
        j = i + 1
        while j < len(paras) and not _TAG_LINE.match(paras[j].strip()) and not _QUOTE.search(paras[j]):
            j += 1
        if j >= len(paras) or _TAG_LINE.match(paras[j].strip()):
            out.append(p)  # no speech follows: keep the picture where the model put it
            i += 1
            continue
        out.extend(x.strip() for x in paras[i + 1:j])  # the narration first
        target = paras[j].strip()
        q = _QUOTE.search(target)
        head = target[:q.start()].rstrip()
        if q.start() > 0 and re.search(r"[.!?*\u2026]$", head):
            out += [head, p, target[q.start():]]
        else:
            out += [p, target]
        i = j + 1
    return "\n\n".join(out)


def portrait_instructions(npcs: list[dict], mode: str = "gm_world") -> str:
    """Prompt text that tells the model how to show portraits (only when some characters have pictures)."""
    names = [n["name"] for n in npcs if n.get("active", True) and n.get("portraits") and
             (n["portraits"].get("default") or n["portraits"].get("moods"))]
    if not names:
        return ""
    standard = {"standard", "happy", "sad", "angry", "disgusted", "disgusted/very angry", "very angry", "blushing"}
    extra = []
    for n in npcs:
        own = [m["label"] for m in (n.get("portraits") or {}).get("moods", []) if m.get("label", "").lower() not in standard]
        if own and n["name"] in names:
            extra.append(f"{n['name']}: {', '.join(own)}")
    extra_line = (" Extra moods some characters have: " + "; ".join(extra) + ".") if extra else ""
    main = next((n for n in npcs if n.get("is_main")), None)
    if mode == "character" and main and main["name"] in names:
        return (
            "## Portrait and emotion\n"
            f"Start EVERY reply with a line  [[show: {main['name']} | Mood]]  that matches {main['name']}'s emotion at that moment. "
            "Moods: Standard, Happy, Sad, Angry, Disgusted, Blushing." + extra_line + " Change it whenever the feeling changes. Never write image links."
        )
    return (
        "## Portraits\n"
        "Narrate first. Then, right before a character's spoken line, write a line  [[show: Name | Mood]]  with their mood. "
        "When their mood changes later in the reply, write the line again with the new mood before they speak again. "
        "Moods: Standard, Happy, Sad, Angry, Disgusted, Blushing." + extra_line + " At most 2 characters with portraits per "
        "reply (the 2 most important of the scene). Never write image links or URLs; the app inserts the pictures.\n"
        "Characters with portraits: " + ", ".join(names)
    )


def _mentioned(npc: dict, text: str) -> bool:
    """Whole-word mention of the name (or its first long word), so "Pria" is not found inside "appropriate"."""
    return _mentions(npc, text) > 0


def _name_patterns(npc: dict) -> list[str]:
    name = npc["name"].lower()
    words = [w for w in re.findall(r"[^\W_]+", name) if len(w) >= 4 and w not in ("professor", "lady", "lord", "sister")]
    return [rf"\b{re.escape(name)}\b"] + [rf"\b{re.escape(w)}\b" for w in words[:1]]


def _mentions(npc: dict, text: str) -> int:
    low = text.lower()
    return max((len(re.findall(p, low)) for p in _name_patterns(npc)), default=0)


def _interacts(npc: dict, text: str) -> bool:
    """Met = really part of the scene: named twice, or named in a sentence where someone speaks or that involves the
    player ("Lilia waves at you"). A name seen once in
    the crowd ("Lilia stood with her arms crossed") is not a meeting yet."""
    if _mentions(npc, text) >= 2:
        return True
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
        if _mentions(npc, sentence) and (re.search(r"[\"\u201c\u201d]", sentence) or re.search(r"\byou(r|rs)?\b|\bvoc[eê]\b", sentence, re.I)):
            return True
    return False


def auto_portraits(story: str, npcs: list[dict], max_n: int = MAX_PER_REPLY) -> tuple[str, dict[str, str]]:
    """Pictures for a reply the model didn't tag: the first characters (with pictures) who speak or act in it, each
    shown before the paragraph where they first appear, with the mood that paragraph shows (smirks -> Happy)."""
    paras = re.split(r"(\n\s*\n)", story)
    found: list[tuple[int, dict]] = []
    for n in npcs:
        if not n.get("portraits") or not (n["portraits"].get("default") or n["portraits"].get("moods")):
            continue
        # in the scene: named twice, or named in a paragraph where someone speaks ("You think of Lyra" is not)
        if _mentions(n, story) < 2 and not any(_mentions(n, p) and re.search(r"[\"\u201c\u201d]|^\s*\[", p) for p in paras[::2]):
            continue
        first = next((i for i in range(0, len(paras), 2) if _mentions(n, paras[i])), None)
        if first is not None:
            found.append((first, n))
    found.sort(key=lambda x: (x[0], story.lower().find(x[1]["name"].lower().split()[0])))
    shown: dict[str, str] = {}
    for idx, n in found[:max_n]:
        mood = face_from_text(paras[idx][max(0, paras[idx].lower().find(n["name"].lower().split()[-1]) - 5):]) or ""
        label, url = pick_mood(n["portraits"], mood)
        if not url:
            continue
        shown[f"{n['name']}|{label}"] = url
        paras[idx] = f"[[show: {n['name']} | {label}]]\n" + paras[idx]
    return "".join(paras), shown


def process_reply(text: str, npcs: list[dict]) -> tuple[str, dict, list[int]]:
    """Finish a reply from the model: take out the INFO block, clean the portrait tags, and find the
    characters the player meets for the first time. Returns (story text, meta to store, ids now met)."""
    from .status import split_status

    story, block = split_status(text)
    story, shown = resolve_portraits(story, npcs)
    if not shown:  # the model forgot the tags: the characters who speak or act get their picture anyway
        story, shown = auto_portraits(story, npcs)
    meta: dict = {}
    if block:
        meta["status"] = block
    if shown:
        meta["portraits"] = shown
    shown_names = {k.split("|", 1)[0] for k in shown}
    met = [n["id"] for n in npcs if "id" in n and not n.get("met", True)
           and (n["name"] in shown_names or _interacts(n, story))]
    return story, meta, met
