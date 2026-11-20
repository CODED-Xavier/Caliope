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


# ------------------------------------------------------------------ PixAI (optional, needs your own API key)
PIXAI_API = "https://api.pixai.art"
PIXAI_PREFIX = "pixai:"
PIXAI_POLL_SECONDS = 2.0   # PixAI asks for at most one status check every 1.5 s
PIXAI_TIMEOUT = 180.0


class PixAIError(RuntimeError):
    pass


def pixai_url(prompt: str, seed: int) -> str:
    """A picture link the app paints through PixAI when the interface first shows it (then it is cached)."""
    return f"{PIXAI_PREFIX}{int(seed)}:{quote(prompt, safe='')}"


def is_pixai(url: str) -> bool:
    return (url or "").startswith(PIXAI_PREFIX)


def parse_pixai_url(url: str) -> tuple[int, str]:
    from urllib.parse import unquote

    seed, _, prompt = url[len(PIXAI_PREFIX):].partition(":")
    return int(seed or 0), unquote(prompt)


def _find_url(obj) -> str:
    """The best picture link in PixAI's answer: a PUBLIC one if marked, otherwise the first http link."""
    found: list[str] = []

    def walk(o, public=False):
        if isinstance(o, dict):
            is_public = public or str(o.get("type", "")).upper() == "PUBLIC"
            for k, v in o.items():
                walk(v, is_public or str(k).upper() == "PUBLIC")
        elif isinstance(o, list):
            for v in o:
                walk(v, public)
        elif isinstance(o, str) and o.startswith("http"):
            found.append(("0" if public else "1") + o)

    walk(obj)
    return sorted(found)[0][1:] if found else ""


async def pixai_paint(url: str, key: str, model: str, client=None) -> str:
    """Ask PixAI for the picture, wait for it, and return the link of the finished image."""
    if not key:
        raise PixAIError("Add your PixAI API key in Settings > Scene pictures.")
    if not model:
        raise PixAIError("Add the PixAI model version ID in Settings > Scene pictures (from the model's page on PixAI).")
    seed, prompt = parse_pixai_url(url)
    body = {"prompt": prompt, "modelVersionId": model, "aspectRatio": "16:9", "batchSize": 1, "seed": seed}
    own = client is None
    if own:
        import httpx

        client = httpx.AsyncClient(timeout=30.0)
    headers = {"Authorization": f"Bearer {key}", "User-Agent": "Caliope"}
    try:
        r = await client.post(f"{PIXAI_API}/v2/image/create", json=body, headers=headers)
        if r.status_code >= 400:
            raise PixAIError(f"PixAI refused the picture ({r.status_code}): {r.text[:200]}")
        task = r.json()
        task_id = task.get("id")
        if not task_id:
            raise PixAIError("PixAI did not return a task.")
        waited = 0.0
        while True:
            media = (task.get("outputs") or {}).get("mediaUrls") or []
            status = str(task.get("status", "")).lower()
            if media:
                break
            if status in ("failed", "cancelled", "canceled", "error"):
                raise PixAIError(f"PixAI could not paint it ({status}).")
            if waited >= PIXAI_TIMEOUT:
                raise PixAIError("PixAI took too long.")
            await asyncio.sleep(PIXAI_POLL_SECONDS)
            waited += PIXAI_POLL_SECONDS
            r = await client.get(f"{PIXAI_API}/v2/task/{task_id}", headers=headers)
            if r.status_code >= 400:
                raise PixAIError(f"PixAI answered {r.status_code} while painting.")
            task = r.json()
        first = media[0] if isinstance(media[0], str) else _find_url(media[0])
        if first.startswith("http"):
            return first
        r = await client.get(f"{PIXAI_API}/v2/media/batch", params={"ids": first}, headers=headers)
        if r.status_code >= 400:
            raise PixAIError(f"PixAI answered {r.status_code} for the finished picture.")
        link = _find_url(r.json())
        if not link:
            raise PixAIError("PixAI finished but sent no picture link.")
        return link
    finally:
        if own:
            await client.aclose()
