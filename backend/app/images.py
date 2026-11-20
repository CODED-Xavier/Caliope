"""Portrait images: fetched once from their link, saved on this PC and served from there.

Keeping a local copy means the portraits still work offline and if the site that hosted them disappears.
Only real images are accepted, with a size limit, and addresses that point inside your own network are refused.
"""
from __future__ import annotations

import hashlib
import ipaddress
import socket
from pathlib import Path
from typing import Awaitable, Callable
from urllib.parse import urlparse

MAX_IMAGE_BYTES = 8 * 1024 * 1024
TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif"}


class ImageError(ValueError):
    pass


def validate_url(url: str) -> str:
    """Return the URL if it is a public http(s) link, otherwise raise ImageError."""
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ImageError("Only http(s) image links are allowed.")
    try:
        infos = socket.getaddrinfo(parsed.hostname, None)
    except OSError as exc:
        raise ImageError(f"Cannot resolve {parsed.hostname}.") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise ImageError("Links that point inside your own network are not allowed.")
    return parsed.geturl()


def cache_key(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()


def find_cached(cache_dir: Path, url: str) -> Path | None:
    for ext in TYPES.values():
        p = cache_dir / f"{cache_key(url)}{ext}"
        if p.is_file():
            return p
    return None


Fetcher = Callable[[str], Awaitable[tuple[bytes, str]]]


async def http_fetch(url: str) -> tuple[bytes, str]:
    import httpx

    async with httpx.AsyncClient(follow_redirects=True, timeout=20.0) as client:
        resp = await client.get(url, headers={"User-Agent": "LocalRPGChat/0.6"})
        if resp.status_code != 200:
            raise ImageError(f"The image server answered {resp.status_code}.")
        return resp.content, resp.headers.get("content-type", "").split(";")[0].strip().lower()


async def get_image(url: str, cache_dir: Path, fetch: Fetcher = http_fetch, check: Callable[[str], str] = validate_url) -> Path:
    """Local path of the image, downloading it the first time."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = find_cached(cache_dir, url)
    if cached:
        return cached
    check(url)
    data, ctype = await fetch(url)
    if ctype not in TYPES:
        raise ImageError("That link is not a PNG, JPEG, WebP or GIF image.")
    if len(data) > MAX_IMAGE_BYTES:
        raise ImageError("The image is larger than 8 MB.")
    path = cache_dir / f"{cache_key(url)}{TYPES[ctype]}"
    path.write_bytes(data)
    return path
