"""Small shared helpers (no third-party dependencies)."""
from __future__ import annotations

import json
import re
import time
import unicodedata
from typing import Any


def now() -> float:
    return time.time()


CHARS_PER_TOKEN = 3.4  # measured from the model server's real counts after each reply (see set_chars_per_token)


def set_chars_per_token(value: float) -> None:
    global CHARS_PER_TOKEN
    CHARS_PER_TOKEN = max(2.5, min(5.0, float(value)))


def estimate_tokens(text: str) -> int:
    """Token estimate from the measured characters-per-token of the model in use (3.4 until measured),
    with a 3% safety margin so the small context window never overflows."""
    if not text:
        return 0
    return int(len(text) / (CHARS_PER_TOKEN * 0.97)) + 1


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return value or "item"


def clamp(value: int | float, low: int | float, high: int | float):
    return max(low, min(high, value))


def truncate(text: str, limit: int, suffix: str = "...") -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - len(suffix))].rstrip() + suffix


def extract_json(text: str) -> dict | None:
    """Find the first valid JSON object inside free-form model output."""
    if not text:
        return None
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    start = 0
    while True:
        i = cleaned.find("{", start)
        if i == -1:
            return None
        depth = 0
        in_str = False
        esc = False
        for j in range(i, len(cleaned)):
            ch = cleaned[j]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(cleaned[i : j + 1])
                        if isinstance(obj, dict):
                            return obj
                    except ValueError:
                        pass
                    break
        start = i + 1


def deep_merge(base: dict, patch: dict) -> dict:
    """Recursively merge `patch` into a copy of `base` (lists are replaced)."""
    out = json.loads(json.dumps(base))
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


STOPWORDS = set(
    """a an and are as at be but by for from has have he her his i if in into is it its me my of on or our
    she so that the their them then there they this to was we were what when where which who will with you your
    de da do das dos e em um uma uns umas para por com sem que se na no nas nos ao aos como mais mas ou eu tu
    ele ela nos voces eles elas meu minha seu sua""".split()
)


def stem(token: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            return token[: -len(suffix)]
    return token


def tokenize(text: str, do_stem: bool = True) -> list[str]:
    """Lowercase word tokens without stop words (light stemming)."""
    text = re.sub(r"[_\-/]", " ", (text or "").lower())
    tokens = [t for t in re.findall(r"[^\W_]{2,}", text) if t not in STOPWORDS]
    return [stem(t) for t in tokens] if do_stem else tokens


def as_int(value: Any, default: int = 0) -> int:
    try:
        if isinstance(value, str):
            value = value.strip().replace("+", "")
        return int(float(value))
    except (TypeError, ValueError, OverflowError):  # "1e999" from a model would be infinite
        return default


def render_macros(text: str, user: str, char: str) -> str:
    """Replace the card macros {{user}} / {{char}} (and <USER> / <BOT>) with real names."""
    if not text:
        return text
    out = re.sub(r"\{\{\s*user\s*\}\}|<USER>", lambda _: user, text, flags=re.I)
    return re.sub(r"\{\{\s*char\s*\}\}|<BOT>", lambda _: char, out, flags=re.I)
