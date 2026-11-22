"""Portuguese games: the app's own lines in the chat (round cards, flavour, update lines) have a PT-BR translation in
frontend/src/i18n/pt-BR.json. This mirrors the screen's translator (frontend/src/i18n/index.js) closely enough to
catch an English line the app writes with no translation."""
import json
import random
import re
import unittest
from pathlib import Path

from app.combat import CombatError
from tests.test_action_economy import monk
from tests.test_combat import engine

PT = json.loads((Path(__file__).resolve().parents[2] / "frontend/src/i18n/pt-BR.json").read_text(encoding="utf-8"))
EXACT = PT["exact"]
PATTERNS = []
for en, pt in sorted(PT["patterns"], key=lambda p: -len(re.sub(r"\{\d\}", "", p[0]))):
    PATTERNS.append(re.compile("^" + "".join("(.+?)" if re.fullmatch(r"\{\d\}", part) else re.escape(part)
                                             for part in re.split(r"(\{\d\})", en)) + "$", re.S))


def known(text: str) -> bool:
    if text in EXACT or any(p.match(text) for p in PATTERNS):
        return True
    m = re.match(r"^([^A-Za-z\"'(]*)(.*?)([\s:.…!?)·]*)$", text, re.S)
    if m and (m[1] or m[3]):
        for mid in (m[1] + m[2], m[2] + m[3], m[2]):
            mid = mid.strip()
            if mid in EXACT or any(p.match(mid) for p in PATTERNS):
                return True
    return False


def pieces(card: str) -> list[str]:
    """The text pieces the screen shows: lines, split where bold and italic start and end."""
    out = []
    for line in card.replace("\r", "").split("\n"):
        for part in re.split(r"\*\*|(?<!\*)\*(?!\*)", line):
            part = re.sub(r"\s+", " ", part).strip()
            if re.search(r"[A-Za-z]{3}", part) and not part.startswith(("💬", "[[face")):
                out.append(part)
    return out


class RoundCardsInPortugueseTest(unittest.TestCase):
    def test_every_line_of_a_fight_has_a_translation(self):
        missing = set()
        for seed in range(12):
            eng = engine(seed)
            allies = [{"name": "Dorna", "hp": 12, "ac": 14, "attack_bonus": 4, "damage": "1d6+2", "range": 1, "speed": 6,
                       "init_bonus": 2, "role": "fighter", "companion": True, "weapon": "Mace"},
                      {"name": "Lio", "hp": 10, "ac": 14, "attack_bonus": 3, "damage": "1d4", "range": 1, "speed": 6, "init_bonus": 1,
                       "role": "healer", "companion": True, "heal": "1d8+3", "heals": 2},
                      {"name": "Mira", "hp": 9, "ac": 13, "attack_bonus": 5, "damage": "1d8+3", "range": 16, "speed": 6,
                       "init_bonus": 3, "role": "archer", "companion": True, "weapon": "Longbow"}]
            foes = [{"name": "Goblin", "count": 3, "hp": 8, "ac": 12, "attack_bonus": 6, "damage": "1d6+4", "init_bonus": 2}]
            st, card = eng.start(monk(), "d20", foes, allies=allies, grid={"w": 12, "h": 8})
            cards = [card]
            for turn in range(10):
                c = st.get("combat") or {}
                if not c.get("active"):
                    break
                alive = [x for x in c["combatants"] if x["side"] == "enemy" and x["hp"] > 0]
                try:
                    if alive and random.Random(seed + turn).random() < 0.7:
                        st, card = eng.player_step(st, "attack", alive[0]["id"])
                        cards.append(card)
                    else:
                        st, card = eng.player_action(st, random.Random(seed).choice(["dodge", "dash"]))
                        cards.append(card)
                    st, card = eng.player_action(st, "end")
                    cards.append(card)
                except CombatError:
                    break
            for card in cards:
                missing |= {p for p in pieces(card) if not known(p)}
        self.assertEqual(sorted(missing), [])

    def test_update_lines(self):
        for line in ["Professor Artemis: relationship +4 → 4 (mostrou respeito: Aster foi educado)", "Note on Lilia: gosta de chá",
                     "Body: C [20/100] (grade up: C- → C)", "HP -3 (5/8)", "Gold +30 (130)", "New character: Lise",
                     "⏳ Time passes (2 hours). It is now Monday, morning.", "✨ Aster uses Soul Forge"]:
            self.assertTrue(known(line), line)


if __name__ == "__main__":
    unittest.main()
