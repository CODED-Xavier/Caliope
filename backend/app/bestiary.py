"""The Bestiary: monster sheets kept in a folder (backend/data/bestiary, one JSON file per monster).

Fights use these numbers: an enemy whose name matches a monster here (or its plural, "Goblins") gets its AC, HP,
attack, damage, initiative, speed and range, unless the fight sets them. Monsters come from the Create monster sheet,
or are read from stat blocks in a book's text (the usual 5e layout: "Armor Class 15", "Hit Points 7 (2d6)", the
ability table, "+4 to hit ... Hit: 5 (1d6 + 2)"), as in an adventure's appendix.
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from .util import truncate

ABILITIES = ("STR", "DEX", "CON", "INT", "WIS", "CHA")
MAX_MONSTERS = 2000


class BestiaryError(ValueError):
    pass


def slug(name: str) -> str:
    t = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:60]


def _int(v, default=0, lo=-1000, hi=100000) -> int:
    try:
        return max(lo, min(hi, int(float(str(v).strip()))))
    except (TypeError, ValueError):
        return default


def _dice(v: str, default: str = "") -> str:
    t = re.sub(r"\s+", "", str(v or ""))
    return t if re.fullmatch(r"\d{0,2}d\d{1,3}([+-]\d{1,3})?|\d{1,3}", t) else default


def normalize(raw: dict) -> dict:
    if not isinstance(raw, dict) or not str(raw.get("name", "")).strip():
        raise BestiaryError("A monster needs a name.")
    stats = raw.get("stats") if isinstance(raw.get("stats"), dict) else {}
    actions = []
    for a in (raw.get("actions") or [])[:12] if isinstance(raw.get("actions"), list) else []:
        if isinstance(a, dict) and str(a.get("name", "")).strip():
            actions.append({"name": truncate(str(a["name"]).strip(), 50),
                            "attack_bonus": _int(a.get("attack_bonus"), 0, -5, 30) if a.get("attack_bonus") not in (None, "") else None,
                            "damage": _dice(a.get("damage")), "range": _int(a.get("range"), 1, 1, 60),
                            "text": truncate(str(a.get("text") or ""), 600)})
    return {
        "name": truncate(str(raw["name"]).strip(), 60),
        "type": truncate(str(raw.get("type") or ""), 120),
        "ac": _int(raw.get("ac"), 12, 1, 40),
        "ac_note": truncate(str(raw.get("ac_note") or ""), 80),
        "hp": _int(raw.get("hp"), 7, 1, 999),
        "hp_dice": _dice(raw.get("hp_dice")),
        "speed": truncate(str(raw.get("speed") or "30 ft."), 80),
        "init_bonus": _int(raw.get("init_bonus"), 0, -5, 15),
        "stats": {k: _int(stats.get(k), 10, 1, 30) for k in ABILITIES},
        "skills": truncate(str(raw.get("skills") or ""), 200),
        "senses": truncate(str(raw.get("senses") or ""), 200),
        "languages": truncate(str(raw.get("languages") or ""), 200),
        "cr": truncate(str(raw.get("cr") or ""), 10),
        "xp": _int(raw.get("xp"), 0, 0, 1_000_000),
        "traits": truncate(str(raw.get("traits") or ""), 3000),
        "actions": actions,
        "notes": truncate(str(raw.get("notes") or ""), 2000),
        "picture": str(raw.get("picture") or "")[:600],
    }


def combat_numbers(m: dict) -> dict:
    """What a fight needs from a sheet: the first attack with a bonus is the one the monster uses."""
    att = next((a for a in m.get("actions") or [] if a.get("attack_bonus") is not None and a.get("damage")), None)
    feet = re.search(r"\d+", m.get("speed") or "")
    out = {"hp": m["hp"], "ac": m["ac"], "init_bonus": m["init_bonus"],
           "speed": max(1, min(12, (int(feet.group(0)) // 5) if feet else 6))}
    if att:
        out.update(attack_bonus=att["attack_bonus"], damage=att["damage"], range=att.get("range", 1))
    return out


def book_folder(name: str) -> str:
    """A safe folder name for a book ("Lost Mine of Phandelver"), or '' for monsters of your own."""
    t = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', " ", str(name or "")).strip(" .")
    return re.sub(r"\s{2,}", " ", t)[:80]


class Bestiary:
    """One JSON file per monster. Monsters from a book live in a folder named after it
    (bestiary/Lost Mine of Phandelver/goblin.json); the ones you make yourself sit at the top."""

    def __init__(self, folder: Path):
        self.folder = Path(folder)

    def _files(self) -> list[Path]:
        if not self.folder.is_dir():
            return []
        top = sorted(self.folder.glob("*.json"))
        inner = sorted(p for p in self.folder.glob("*/*.json"))
        return (top + inner)[:MAX_MONSTERS]

    def _id(self, p: Path) -> str:
        return p.relative_to(self.folder).with_suffix("").as_posix()

    def _load(self, p: Path) -> dict | None:
        try:
            m = normalize(json.loads(p.read_text("utf-8")))
        except (OSError, ValueError):
            return None
        book = p.parent.name if p.parent != self.folder else ""
        return {**m, "book": book, "id": self._id(p)}

    def _by_id(self, monster_id: str) -> Path | None:
        parts = [x for x in str(monster_id or "").split("/") if x]
        if not parts or len(parts) > 2 or any(x in (".", "..") for x in parts):
            return None
        p = self.folder.joinpath(*parts[:-1], f"{slug(parts[-1])}.json")
        return p if p.is_file() and self.folder.resolve() in p.resolve().parents else None

    def list(self) -> list[dict]:
        out = [m for m in (self._load(p) for p in self._files()) if m]
        return sorted(out, key=lambda m: (m["book"].lower(), m["name"].lower()))

    def books(self) -> list[str]:
        return sorted({m["book"] for m in self.list() if m["book"]}, key=str.lower)

    def get(self, name_or_id: str) -> dict | None:
        """By id ("Lost Mine of Phandelver/goblin") or by name; your own monsters win over a book's."""
        p = self._by_id(name_or_id) if "/" in str(name_or_id) else None
        if p:
            return self._load(p)
        s = slug(name_or_id)
        if not s:
            return None
        own = self.folder / f"{s}.json"
        if own.is_file():
            return self._load(own)
        for p in sorted(self.folder.glob(f"*/{s}.json")) if self.folder.is_dir() else []:
            m = self._load(p)
            if m:
                return m
        return None

    def save(self, raw: dict, old_id: str = "") -> dict:
        m = normalize(raw)
        book = book_folder(raw.get("book", ""))
        s = slug(m["name"])
        if not s:
            raise BestiaryError("A monster needs a name.")
        folder = self.folder / book if book else self.folder
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{s}.json"
        path.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
        old = self._by_id(old_id) if "/" in str(old_id) else (self.folder / f"{slug(old_id)}.json" if old_id else None)
        if old and old.is_file() and old.resolve() != path.resolve():  # renamed or moved to another book: the old file goes
            old.unlink(missing_ok=True)
        return self._load(path)

    def delete(self, monster_id: str) -> None:
        p = self._by_id(monster_id) if "/" in str(monster_id) else self.folder / f"{slug(monster_id)}.json"
        if p and p.is_file():
            p.unlink(missing_ok=True)

    def find(self, name: str) -> dict | None:
        """A monster for an enemy's name: 'Goblin', 'Goblins', 'goblin 2', 'Cragmaw goblin'."""
        base = re.sub(r"\s*#?\d+$", "", str(name or "")).strip()
        for cand in (base, base[:-1] if base.endswith("s") else "", base[:-3] + "f" if base.endswith("ves") else "",
                     base[:-3] + "y" if base.endswith("ies") else "", base.split()[-1] if " " in base else ""):
            if cand:
                m = self.get(cand)
                if m:
                    return m
        return None

    def enrich(self, enemies: list[dict]) -> list[dict]:
        """Fill an enemy's missing numbers from its sheet here (what the fight already says stays)."""
        out = []
        for e in enemies or []:
            if not isinstance(e, dict):
                continue
            m = self.find(e.get("monster") or e.get("name", ""))
            if m:
                nums = combat_numbers(m)
                e = {**nums, **{k: v for k, v in e.items() if v not in (None, "") and not (k in nums and e.get("_guessed"))}}
            out.append(e)
        return out


# ------------------------------------------------------------------ reading stat blocks from a book's text
_BLOCK_START = re.compile(r"^\s*>*\s*#{1,4}\s*(.+?)\s*$")


def _clean(line: str) -> str:
    line = re.sub(r"^\s*>+\s?", "", line)
    return re.sub(r"[*_`]", "", line).strip()


def parse_statblocks(text: str) -> list[dict]:
    """Monster sheets found in a text: a name line followed (within a few lines) by 'Armor Class' and 'Hit Points'."""
    lines = [_clean(x) for x in (text or "").replace("\r", "").split("\n")]
    found: dict[str, dict] = {}
    i = 0
    while i < len(lines):
        if lines[i].lower().startswith(("- armor class", "armor class")):
            # the name is the closest heading-like line above
            name, j = "", i - 1
            while j >= max(0, i - 6):
                cand = lines[j].lstrip("#").strip()
                if cand and not cand.startswith(("-", "|")) and len(cand) <= 50 and not re.search(r"(humanoid|beast|undead|monstrosity|aberration|construct|dragon|fiend|fey|giant|ooze|plant|elemental|celestial)", cand, re.I):
                    name = cand
                    break
                j -= 1
            type_line = lines[i - 1] if i and re.search(r",", lines[i - 1]) else ""
            end = i + 1
            while end < len(lines) and not lines[end].lower().startswith(("- armor class", "armor class")) and end - i < 80:
                if lines[end].startswith("#") and end - i > 8 and not lines[end].lower().lstrip("# ").startswith(("actions", "reactions", "bonus actions", "legendary")):
                    break
                end += 1
            m = _read_block(name, type_line, lines[i:end])
            if m and slug(m["name"]) not in found:
                found[slug(m["name"])] = m
            i = end
        else:
            i += 1
    return list(found.values())


def _read_block(name: str, type_line: str, block: list[str]) -> dict | None:
    if not name:
        return None
    body = "\n".join(block)
    get = lambda label: (re.search(rf"^-?\s*{label}\s+(.+)$", body, re.I | re.M) or [None, ""])[1].strip()  # noqa: E731
    ac_txt, hp_txt = get("Armor Class"), get("Hit Points")
    ac = re.match(r"(\d+)\s*(?:\((.*)\))?", ac_txt)
    hp = re.match(r"(\d+)\s*(?:\((.*)\))?", hp_txt)
    if not ac or not hp:
        return None
    stats = {}
    for k, line in enumerate(block):
        if re.match(r"^\|?\s*STR\s*\|", line, re.I):
            row = next((x for x in block[k + 1:k + 4] if re.search(r"\d+\s*\(", x)), "")
            nums = re.findall(r"(\d+)\s*\(", row)
            if len(nums) >= 6:
                stats = dict(zip(ABILITIES, (int(n) for n in nums[:6])))
            break
    init = get("Initiative")
    dex = stats.get("DEX", 10)
    challenge = get("Challenge")
    cr = re.match(r"([\d/]+)", challenge)
    xp = re.search(r"XP\s*([\d,.]+)", challenge) or re.search(r"([\d,.]+)\s*XP", challenge)  # "1,100" or "1.100"
    traits, actions, section = [], [], "traits"
    for line in block:
        low = line.lower().lstrip("# ")
        if low in ("actions", "reactions", "bonus actions", "legendary actions"):
            section = "actions" if low == "actions" else "other"
            continue
        m = re.match(r"^([A-Z][\w' ()/,-]{1,48}?)\.\s+(.+)$", line)
        if not m:
            continue
        title, rest = m.group(1).strip(), m.group(2).strip()
        if section == "actions":
            atk = re.search(r"([+-]\d+)\s*to hit", rest)
            dmg = re.search(r"Hit:\s*\d+\s*\(([^)]+)\)", rest)
            rng = re.search(r"range\s+(\d+)", rest)
            actions.append({"name": title, "attack_bonus": int(atk.group(1)) if atk else None,
                            "damage": re.sub(r"\s+", "", dmg.group(1)) if dmg else "",
                            "range": max(1, int(rng.group(1)) // 5) if rng and "Ranged" in rest and "Melee" not in rest else 1,
                            "text": rest})
        elif section == "traits" and not re.match(r"^(armor class|hit points|speed|initiative|skills|senses|languages|challenge|"
                                                  r"proficiency bonus|gear|saving throws|damage|condition)", title, re.I):
            traits.append(f"{title}. {rest}")
    return normalize({
        "name": name, "type": type_line, "ac": ac.group(1), "ac_note": ac.group(2) or "", "hp": hp.group(1),
        "hp_dice": hp.group(2) or "", "speed": get("Speed") or "30 ft.",
        "init_bonus": (re.match(r"([+-]?\d+)", init).group(1) if re.match(r"([+-]?\d+)", init) else (dex - 10) // 2),
        "stats": stats, "skills": get("Skills"), "senses": get("Senses"), "languages": get("Languages"),
        "cr": cr.group(1) if cr else "", "xp": re.sub(r"[,.]", "", xp.group(1)) if xp else 0,
        "traits": "\n".join(traits), "actions": actions,
    })
