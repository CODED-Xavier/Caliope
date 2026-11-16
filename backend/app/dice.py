"""Dice rolling. Done in code (never by the model) so results are fair and verifiable.

Supported syntax examples:
    d20          2d6+3          1d20+5 adv        1d20-1 disadvantage
    4d6kh3       2d8+1d4+2      d%
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass, field


class DiceError(ValueError):
    pass


MAX_DICE = 100
MAX_SIDES = 1000

_TERM = re.compile(
    r"(?P<sign>[+-]?)(?:(?P<n>\d*)d(?P<s>\d+|%)(?:k(?P<kd>[hl])(?P<kn>\d+))?|(?P<c>\d+))"
)


@dataclass
class RollResult:
    expression: str
    total: int
    mode: str = "normal"                 # normal | advantage | disadvantage
    natural: int | None = None           # the natural d20 value when a single d20 was rolled
    crit: bool = False
    fumble: bool = False
    terms: list[dict] = field(default_factory=list)
    text: str = ""

    def to_dict(self) -> dict:
        return {
            "expression": self.expression,
            "total": self.total,
            "mode": self.mode,
            "natural": self.natural,
            "crit": self.crit,
            "fumble": self.fumble,
            "terms": self.terms,
            "text": self.text,
        }


class DiceRoller:
    def __init__(self, rng: random.Random | None = None):
        self.rng = rng or random.SystemRandom()

    def roll(self, expression: str) -> RollResult:
        original = (expression or "").strip()
        if not original:
            raise DiceError("Empty dice expression.")
        expr = re.sub(r"\s+", "", original.lower())

        mode = "normal"
        for word, value in (
            ("disadvantage", "disadvantage"),
            ("dis", "disadvantage"),
            ("advantage", "advantage"),
            ("adv", "advantage"),
        ):
            if word in expr:
                mode = value
                expr = expr.replace(word, "")
                break
        if not expr:
            expr = "1d20"

        pos = 0
        terms: list[dict] = []
        adv_used = False
        while pos < len(expr):
            m = _TERM.match(expr, pos)
            if not m or m.end() == pos:
                raise DiceError(f"Cannot understand dice expression: {original!r}")
            if pos > 0 and not m.group("sign"):
                raise DiceError(f"Cannot understand dice expression: {original!r}")
            sign = -1 if m.group("sign") == "-" else 1
            pos = m.end()

            if m.group("c") is not None:
                terms.append({"kind": "const", "sign": sign, "value": int(m.group("c")), "subtotal": sign * int(m.group("c"))})
                continue

            count = int(m.group("n") or 1)
            sides = 100 if m.group("s") == "%" else int(m.group("s"))
            if not (1 <= count <= MAX_DICE) or not (2 <= sides <= MAX_SIDES):
                raise DiceError(f"Dice out of range (max {MAX_DICE} dice, d2 to d{MAX_SIDES}).")

            keep_mode = m.group("kd")
            keep_n = int(m.group("kn")) if m.group("kn") else None

            if mode != "normal" and not adv_used and count == 1 and sides == 20 and sign == 1:
                rolls = [self.rng.randint(1, 20), self.rng.randint(1, 20)]
                kept = [max(rolls)] if mode == "advantage" else [min(rolls)]
                adv_used = True
            else:
                rolls = [self.rng.randint(1, sides) for _ in range(count)]
                if keep_mode and keep_n:
                    ordered = sorted(rolls, reverse=(keep_mode == "h"))
                    kept = ordered[: min(keep_n, count)]
                else:
                    kept = list(rolls)
            terms.append(
                {
                    "kind": "dice",
                    "sign": sign,
                    "count": count,
                    "sides": sides,
                    "rolls": rolls,
                    "kept": kept,
                    "subtotal": sign * sum(kept),
                }
            )

        if mode != "normal" and not adv_used:
            mode = "normal"  # advantage only applies to a single d20

        total = sum(t["subtotal"] for t in terms)
        d20_terms = [t for t in terms if t["kind"] == "dice" and t["sides"] == 20 and len(t["kept"]) == 1 and t["sign"] == 1]
        natural = d20_terms[0]["kept"][0] if len(d20_terms) == 1 else None
        result = RollResult(
            expression=original,
            total=total,
            mode=mode,
            natural=natural,
            crit=natural == 20,
            fumble=natural == 1,
            terms=terms,
        )
        result.text = self._format(result)
        return result

    @staticmethod
    def _format(result: RollResult) -> str:
        parts: list[str] = []
        for i, t in enumerate(result.terms):
            sign = "-" if t["sign"] < 0 else "+"
            prefix = "" if i == 0 and sign == "+" else f"{sign}"
            if t["kind"] == "const":
                parts.append(f"{prefix}{t['value']}")
                continue
            shown = list(t["rolls"])
            kept_pool = list(t["kept"])
            pieces = []
            for r in shown:
                if r in kept_pool:
                    kept_pool.remove(r)
                    pieces.append(str(r))
                else:
                    pieces.append(f"~~{r}~~")
            parts.append(f"{prefix}d{t['sides']}[{', '.join(pieces)}]" if t["count"] == 1 else f"{prefix}{t['count']}d{t['sides']}[{', '.join(pieces)}]")
        detail = " ".join(parts)
        tag = {"advantage": " (advantage)", "disadvantage": " (disadvantage)"}.get(result.mode, "")
        suffix = ""
        if result.crit:
            suffix = " - natural 20!"
        elif result.fumble:
            suffix = " - natural 1!"
        return f"\U0001F3B2 {result.expression.strip()}{tag} \u2192 **{result.total}** ({detail}){suffix}"
