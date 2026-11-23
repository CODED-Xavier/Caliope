"""Resources named in the chat are spent on the 5e sheet, the same as the buttons: "I use Lay on Hands for 5",
"I rage", "I cast Cure Wounds at 2nd level", "I smite the bandit" (and in Portuguese: "uso Imposição das Mãos",
"entro em fúria", "conjuro Curar Ferimentos"). The Aedo is told what was spent, or that it falters.

To keep chatter from spending things, a feature or spell only counts in a sentence that also has a verb for using it
("use", "activate", "spend", "cast"…), or when the feature is the verb itself ("I rage", "I action surge").
"""
from __future__ import annotations

import random
import re

from ..dice import DiceRoller
from . import magic, store
from .character import derive

USE = (r"use|uses|using|used|activate|activates|activating|spend|spends|spending|channel|channels|invoke|invokes|call on|"
       r"uso|usar|usando|utilizo|utilizar|ativo|ativar|ativando|gasto|gastar|gastando|canalizo|canalizar|invoco|invocar")
CAST = r"cast|casts|casting|conjuro|conjurar|conjurando|lanço|lanco|lançar|lancar|lançando|lancando"
SELF = r"\b(myself|me|my own|mim|mim mesmo|mim mesma|me curo|em mim)\b"
ORDINAL = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9,
           "primeiro": 1, "segundo": 2, "terceiro": 3, "quarto": 4, "quinto": 5, "sexto": 6, "sétimo": 7, "oitavo": 8, "nono": 9}
# Portuguese names players use for the features the sheet keeps in English
PT_NAMES = {
    "lay on hands": ["imposição das mãos", "imposição de mãos", "imposicao das maos", "imposicao de maos", "cura pelas mãos"],
    "rage": ["fúria", "furia"],
    "second wind": ["retomar o fôlego", "retomar o folego", "segundo fôlego", "segundo folego", "recuperar o fôlego"],
    "action surge": ["surto de ação", "surto de acao", "surto de ações"],
    "channel divinity": ["canalizar divindade", "canalizo divindade"],
    "divine sense": ["sentido divino"],
    "bardic inspiration": ["inspiração de bardo", "inspiração bárdica", "inspiracao de bardo", "inspiracao bardica"],
    "wild shape": ["forma selvagem"],
    "arcane recovery": ["recuperação arcana", "recuperacao arcana"],
    "ki": ["pontos de ki"],
    "font of magic": ["pontos de feitiçaria", "pontos de feiticaria", "fonte de magia"],
}
# features that are verbs on their own: "I rage", "entro em fúria", "I action surge"
AS_VERB = {"rage": r"\b(i|he|she|we)\s+(rage|go into a rage|enter (?:a|my) rage|fly into a rage)\b|"
                   r"\b(entro|entrar|entrando|fico|ficar)\s+em\s+f[úu]ria\b|\benfure[çc]o\b",
           "action surge": r"\bi\s+action\s+surge\b",
           "wild shape": r"\bi\s+wild\s*shape\b",
           "second wind": r"\b(catch|take|get)\s+(my|a)\s+second wind\b"}
SMITE = r"\b(divine smite|smite|smites|smiting|destrui[çc][ãa]o divina|golpe divino)\b"


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?;\n])\s+|\n+", text) if s.strip()]


def _has(pattern: str, text: str) -> bool:
    return bool(re.search(rf"\b(?:{pattern})\b", text, re.I))


def _named(name: str, sentence: str) -> bool:
    keys = [name.lower()] + PT_NAMES.get(name.lower(), [])
    low = sentence.lower()
    return any(re.search(rf"(?<![\w']){re.escape(k)}(?![\w'])", low) for k in keys)


def _slot_level(sentence: str) -> int | None:
    m = (re.search(r"\b([1-9])\s*(?:st|nd|rd|th|º|°|o)?[\s-]*(?:level|n[íi]vel)\b", sentence, re.I)
         or re.search(r"\b(?:level|n[íi]vel)\s*([1-9])\b", sentence, re.I))
    if m:
        return int(m.group(1))
    m = re.search(r"\b(" + "|".join(ORDINAL) + r")[\s-]+(?:level|n[íi]vel)\b", sentence, re.I)
    return ORDINAL[m.group(1).lower()] if m else None


def _amount(sentence: str) -> int | None:
    clean = re.sub(r"\b\d+d\d+\b|\b[1-9]\s*(?:st|nd|rd|th)\b", " ", sentence, flags=re.I)
    m = re.search(r"\b(\d{1,3})\b", clean)
    return int(m.group(1)) if m else None


def found_in_text(text: str, char: dict, lib) -> list[dict]:
    """What the message spends: features with uses, levelled spells on the sheet, Divine Smite (Paladin 2+)."""
    sheet = derive(char, lib)
    out: list[dict] = []
    feats = [f for f in sheet["features"] if f.get("uses_max")]
    spells = []
    for sp in char.get("spells") or []:
        e = lib.items.get(("spell", str(sp.get("name", "")).lower(), str(sp.get("source", "PHB")).upper()))
        if e and int(e.get("level", 0)) > 0:
            spells.append((e["name"], int(e["level"])))
    for s in _sentences(text):
        for f in feats:
            if any(x.get("name") == f["name"] for x in out) or not _named(f["name"], s) and not re.search(AS_VERB.get(f["name"].lower(), r"$^"), s, re.I):
                continue
            if _has(USE, s) or re.search(AS_VERB.get(f["name"].lower(), r"$^"), s, re.I):
                item = {"kind": "feature", "name": f["name"], "amount": None}
                if f["name"].lower() in store.POOLS:
                    item["amount"] = _amount(s)
                out.append(item)
        for name, level in spells:
            if _named(name, s) and _has(CAST + "|" + USE, s) and not any(x.get("name") == name for x in out):
                out.append({"kind": "spell", "name": name, "spell_level": level, "slot": _slot_level(s),
                            "self": bool(re.search(SELF, s, re.I))})
        if (sheet["class"] == "Paladin" and sheet["level"] >= 2 and re.search(SMITE, s, re.I)
                and not any(x["kind"] == "smite" for x in out)):
            out.append({"kind": "smite", "slot": _slot_level(s)})
    return out[:4]


def apply(state: dict, text: str, lib, rng: random.Random | None = None) -> list[dict]:
    """Spend what the message names. Returns [{name, ok, line}] (✨ lines for the chat and the Aedo)."""
    char = state.get("character5e")
    if not char:
        return []
    found = found_in_text(text, char, lib)
    if not found:
        return []
    store.pull_hp(state, "")
    char = state["character5e"]
    out = []
    for item in found:
        try:
            if item["kind"] == "feature":
                char, line = store.use_feature(char, item["name"], lib, rng=rng, amount=item.get("amount"))
                out.append({"name": item["name"], "ok": True, "line": line})
            elif item["kind"] == "spell":
                sheet = derive(char, lib)
                char, used = magic.spend_slot(char, sheet, item["spell_level"], item.get("slot"))
                left = magic.slots_left(sheet, char).get(str(used), 0) if str(used) in (sheet.get("slots") or {}) else magic.pact_left(sheet, char)
                line = f"✨ {item['name']}: a level {used} slot spent ({left} left at level {used})"
                if item.get("self"):
                    line += _heal_self(char, sheet, item, used, lib, rng)  # sets char["hp"]
                out.append({"name": item["name"], "ok": True, "line": line})
            elif item["kind"] == "smite":
                sheet = derive(char, lib)
                char, used = magic.spend_slot(char, sheet, 1, item.get("slot"))
                out.append({"name": "Divine Smite", "ok": True,
                            "line": f"✨ Divine Smite: a level {used} slot spent, +{magic.smite_dice(used)} radiant on the hit "
                                    f"(+1d8 against undead or fiends)"})
        except ValueError as exc:
            out.append({"name": item.get("name") or "Divine Smite", "ok": False,
                        "line": f"✨ {item.get('name') or 'Divine Smite'}: {exc}"})
    store.put_char(state, "", char, lib)
    return out


def _heal_self(char: dict, sheet: dict, item: dict, used: int, lib, rng) -> str:
    """A healing spell on yourself rolls and heals at once (on someone else, the Aedo narrates it)."""
    e = next((v for (k, n, _), v in lib.items.items() if k == "spell" and n == item["name"].lower()), None) or {}
    ab = sheet.get("spell_ability") or "wis"
    roll = magic.spell_roll(e, sheet["level"], used, sheet["abilities"][ab]["mod"])
    if roll["kind"] != "heal" or not roll["dice"]:
        return ""
    r = DiceRoller(rng).roll(roll["dice"])
    hp = min(sheet["hp_max"], sheet["hp"] + r.total)
    char["hp"] = {**(char.get("hp") or {}), "current": hp}
    return f": 🎲 {roll['dice']} = {r.total} → {hp}/{sheet['hp_max']} HP"


def prompt_section(used: list[dict]) -> str:
    """For the turn the player names a feature or spell: what the app spent, or why it falters."""
    if not used:
        return ""
    lines = ["## The player uses their sheet this turn (resolved by the app)"]
    for u in used:
        if u["ok"]:
            lines.append(f"- {u['name']} WORKS. The app already spent it: {u['line'].lstrip('✨ ')}. Show it happening.")
        else:
            lines.append(f"- {u['name']} FALTERS: {u['line'].split(': ', 1)[-1]} Show the attempt failing (nothing left to spend).")
    return "\n".join(lines)
