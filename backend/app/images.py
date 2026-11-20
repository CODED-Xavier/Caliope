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


async def http_fetch(url: str, timeout: float = 20.0, check: Callable[[str], str] | None = None) -> tuple[bytes, str]:
    """Download an image: every redirect is checked again (a public link must not bounce into your own
    network), and the download stops past the size limit instead of filling the memory."""
    import httpx

    check = check or validate_url
    async with httpx.AsyncClient(follow_redirects=False, timeout=timeout) as client:
        for _ in range(5):
            async with client.stream("GET", url, headers={"User-Agent": "Caliope/2.0"}) as resp:
                if resp.status_code in (301, 302, 303, 307, 308) and resp.headers.get("location"):
                    url = check(str(resp.url.join(resp.headers["location"])))
                    continue
                if resp.status_code != 200:
                    raise ImageError(f"The image server answered {resp.status_code}.")
                buf = bytearray()
                async for chunk in resp.aiter_bytes(1 << 16):
                    buf.extend(chunk)
                    if len(buf) > MAX_IMAGE_BYTES:
                        raise ImageError("The image is larger than 8 MB.")
                return bytes(buf), resp.headers.get("content-type", "").split(";")[0].strip().lower()
    raise ImageError("Too many redirects.")


async def get_image(url: str, cache_dir: Path, fetch: Fetcher = http_fetch, check: Callable[[str], str] = validate_url) -> Path:
    """Local path of the image, downloading it the first time."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = find_cached(cache_dir, url)
    if cached:
        return cached
    check(url)
    data, ctype = await fetch(url)
    ext = sniff_type(data) or TYPES.get(ctype)  # trust the bytes over the server's label
    if not ext or (sniff_type(data) is None and data[:1] == b"<"):
        raise ImageError("That link is not a PNG, JPEG, WebP or GIF image.")
    if len(data) > MAX_IMAGE_BYTES:
        raise ImageError("The image is larger than 8 MB.")
    path = cache_dir / f"{cache_key(url)}{ext}"
    path.write_bytes(data)
    return path


# ------------------------------------------------------------------ pictures from this PC
UPLOAD_NAME = r"^[0-9a-f]{40}\.(png|jpg|webp|gif)$"


def sniff_type(data: bytes) -> str | None:
    """The real image type from the first bytes (the file name or browser header can lie)."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return None


def save_upload(data: bytes, upload_dir: Path) -> str:
    """Save a picture chosen on this PC and return its file name (the same picture always gets the same name)."""
    if not data:
        raise ImageError("The file is empty.")
    if len(data) > MAX_IMAGE_BYTES:
        raise ImageError("The image is larger than 8 MB.")
    ext = sniff_type(data)
    if not ext:
        raise ImageError("That file is not a PNG, JPEG, WebP or GIF image.")
    upload_dir.mkdir(parents=True, exist_ok=True)
    name = hashlib.sha1(data).hexdigest() + ext
    path = upload_dir / name
    if not path.exists():
        path.write_bytes(data)
    return name
