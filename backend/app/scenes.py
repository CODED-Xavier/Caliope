"""Scene pictures: the AI writes a short picture prompt for the scene, and Pollinations.ai paints it.

Optional and off by default (Settings > Scene pictures). The prompt leaves this PC, so only the
description of the place goes out: no character names and no player text.

Pollinations' free service needs no account but paints one picture at a time per address, at least
45 seconds apart, at most 768x768 pixels. The app waits its turn instead of failing, and keeps a copy of
every picture on this PC (the same cache as the portraits), so a picture is only ever made once.
"""
from __future__ import annotations

import asyncio
import random
import re
import time
from urllib.parse import quote, urlparse

from .util import truncate

POLLINATIONS_HOST = "image.pollinations.ai"
MIN_GAP_SECONDS = 46
WIDTH, HEIGHT = 768, 432  # 16:9 within the free size limit

_lock = asyncio.Lock()
_last_request = 0.0


def picture_url(prompt: str, seed: int) -> str:
    return f"https://{POLLINATIONS_HOST}/prompt/{quote(prompt, safe='')}?width={WIDTH}&height={HEIGHT}&seed={int(seed)}"


def is_pollinations(url: str) -> bool:
    try:
        return urlparse(url).hostname == POLLINATIONS_HOST
    except ValueError:
        return False


async def polite_fetch(url: str, fetch) -> tuple[bytes, str]:
    """Download from Pollinations one picture at a time, respecting the free service's 45-second gap."""
    global _last_request
    async with _lock:
        wait = MIN_GAP_SECONDS - (time.monotonic() - _last_request)
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            return await fetch(url)
        finally:
            _last_request = time.monotonic()


def clean_prompt(text: str) -> str:
    t = re.sub(r"^\W*(image prompt|prompt)\s*:\s*", "", (text or "").strip(), flags=re.I)
    t = t.strip().strip('"\u201c\u201d').strip()
    t = re.sub(r"\s+", " ", t)
    return truncate(t, 400)


async def write_prompt(llm, scene_text: str, state: dict, style: str, names: list[str]) -> str:
    """One short call: describe the place, light and mood for a painter (no names, no text in the picture)."""
    where = ", ".join(x for x in (state.get("location"), state.get("time"), state.get("weather")) if x)
    prompt = (
        "Write a prompt for an illustrator who paints ONE picture of the current scene of a story.\n"
        "Describe in at most 45 words: the place, the light and weather, the mood, and the important things or creatures "
        "in view. Do not use any person's name, do not describe the main character's face, no text or letters in the "
        "picture. English only. Output only the prompt.\n"
        + (f"Where/when: {where}\n" if where else "")
        + f"Scene:\n{truncate(scene_text, 1500)}"
    )
    raw = await llm.chat([{"role": "user", "content": prompt}], max_tokens=120, temperature=0.7)
    text = clean_prompt(raw)
    for name in names:  # names never leave the PC
        if len(name) >= 3:
            text = re.sub(rf"\b{re.escape(name)}\b", "a figure", text, flags=re.I)
    if not text:
        raise ValueError("The model did not describe the scene.")
    style = (style or "").strip()
    return truncate(f"{text}, {style}" if style else text, 450)


def new_seed() -> int:
    return random.randrange(1, 2_000_000_000)
