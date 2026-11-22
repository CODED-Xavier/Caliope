"""5e.tools entries as plain text: {@tag ...} markup removed and nested entries flattened."""
from __future__ import annotations

import re

_TAG = re.compile(r"\{@(\w+)\s*([^{}]*)\}")
_FIXED = {"atk": None, "h": "Hit: ", "hom": "Hit or Miss: ", "recharge": None}
_ATK = {"mw": "Melee Weapon Attack:", "rw": "Ranged Weapon Attack:", "mw,rw": "Melee or Ranged Weapon Attack:",
        "ms": "Melee Spell Attack:", "rs": "Ranged Spell Attack:", "m": "Melee Attack:", "r": "Ranged Attack:"}


def _one(m: re.Match) -> str:
    tag, body = m.group(1).lower(), m.group(2).strip()
    if tag == "atk":
        return _ATK.get(body.lower(), "Attack:")
    if tag in ("h", "hom"):
        return _FIXED[tag]
    if tag == "hit":
        return f"+{body}" if body and not body.startswith(("+", "-")) else body
    if tag == "dc":
        return f"DC {body}"
    if tag == "recharge":
        return f"(Recharge {body or 6}–6)" if body != "6" and body else "(Recharge 6)"
    parts = body.split("|")
    return (parts[2] if len(parts) >= 3 and parts[2] else parts[0]).strip()


def strip_tags(s: str) -> str:
    text = str(s or "")
    for _ in range(4):  # tags can nest one inside another
        new = _TAG.sub(_one, text).replace("Hit:  ", "Hit: ")
        if new == text:
            break
        text = new
    return text


def render(entries, depth: int = 0) -> str:
    """Strings, named sections, lists and tables, as readable text lines."""
    if entries is None:
        return ""
    if isinstance(entries, str):
        return strip_tags(entries)
    if isinstance(entries, list):
        return "\n".join(x for x in (render(e, depth) for e in entries) if x)
    if not isinstance(entries, dict):
        return str(entries)
    kind = entries.get("type", "entries")
    name = strip_tags(entries.get("name", ""))
    if kind == "list":
        return "\n".join("• " + render(i, depth + 1) for i in entries.get("items", []))
    if kind == "table":
        rows = [" | ".join(strip_tags(str(c)) for c in entries.get("colLabels", []))] if entries.get("colLabels") else []
        rows += [" | ".join(render(c, depth + 1) for c in r) for r in entries.get("rows", []) if isinstance(r, list)]
        return (name + "\n" if name else "") + "\n".join(rows)
    if kind in ("item", "itemSub", "itemSpell"):
        body = render(entries.get("entry", entries.get("entries")), depth + 1)
        return f"{name}: {body}" if name else body
    body = render(entries.get("entries", entries.get("entry")), depth + 1)
    if name:
        return f"{name}: {body}" if "\n" not in body else f"{name}\n{body}"
    return body
