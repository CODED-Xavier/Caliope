"""Cloudflare R2 (private bucket) for a card's pictures.

R2 speaks the S3 protocol. The bucket stays private: the app signs each request with your R2 keys (AWS
Signature Version 4). To show a picture it makes a link that works for a few minutes, downloads it once and
keeps a copy on this PC. Card pictures are stored as "r2:<key>" links, which only an app holding the keys can
open, so a copy of the card shared by accident shows nothing to anyone else.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
from urllib.parse import quote

PREFIX = "r2:"
REGION = "auto"
SERVICE = "s3"


class R2Error(RuntimeError):
    pass


def is_r2(url: str) -> bool:
    return (url or "").startswith(PREFIX)


def config_of(settings: dict) -> dict:
    cfg = {k: str(settings.get(f"r2_{k}") or "").strip() for k in ("account_id", "bucket", "access_key_id", "secret_access_key")}
    return cfg


def ready(settings: dict) -> bool:
    return all(config_of(settings).values())


def endpoint(cfg: dict) -> str:
    return f"https://{cfg['account_id']}.r2.cloudflarestorage.com"


def _h(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _signing_key(secret: str, date: str, region: str, service: str) -> bytes:
    k = _h(("AWS4" + secret).encode("utf-8"), date)
    k = _h(k, region)
    k = _h(k, service)
    return _h(k, "aws4_request")


def _path(bucket: str, key: str) -> str:
    return "/" + quote(bucket, safe="") + "/" + quote(key, safe="/-_.~")


def presign(method: str, host: str, path: str, access: str, secret: str, region: str = REGION,
            expires: int = 600, now: dt.datetime | None = None, service: str = SERVICE) -> str:
    """Query-string signed URL (SigV4, UNSIGNED-PAYLOAD)."""
    now = now or dt.datetime.now(dt.timezone.utc)
    amz_date, date = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
    scope = f"{date}/{region}/{service}/aws4_request"
    params = {
        "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
        "X-Amz-Credential": f"{access}/{scope}",
        "X-Amz-Date": amz_date,
        "X-Amz-Expires": str(int(expires)),
        "X-Amz-SignedHeaders": "host",
    }
    query = "&".join(f"{quote(k, safe='-_.~')}={quote(v, safe='-_.~')}" for k, v in sorted(params.items()))
    canonical = "\n".join([method, path, query, f"host:{host}\n", "host", "UNSIGNED-PAYLOAD"])
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()])
    sig = hmac.new(_signing_key(secret, date, region, service), to_sign.encode(), hashlib.sha256).hexdigest()
    return f"https://{host}{path}?{query}&X-Amz-Signature={sig}"


def signed_headers(method: str, host: str, path: str, body: bytes, access: str, secret: str,
                   content_type: str = "", region: str = REGION, now: dt.datetime | None = None) -> dict:
    """Authorization headers for a request with a body (used to upload)."""
    now = now or dt.datetime.now(dt.timezone.utc)
    amz_date, date = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
    payload = hashlib.sha256(body).hexdigest()
    headers = {"host": host, "x-amz-content-sha256": payload, "x-amz-date": amz_date}
    if content_type:
        headers["content-type"] = content_type
    names = sorted(headers)
    canonical = "\n".join([method, path, "", "".join(f"{k}:{headers[k]}\n" for k in names), ";".join(names), payload])
    scope = f"{date}/{region}/{SERVICE}/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()])
    sig = hmac.new(_signing_key(secret, date, region, SERVICE), to_sign.encode(), hashlib.sha256).hexdigest()
    auth = f"AWS4-HMAC-SHA256 Credential={access}/{scope}, SignedHeaders={';'.join(names)}, Signature={sig}"
    return {**{k: v for k, v in headers.items() if k != "host"}, "Authorization": auth}


def download_link(settings: dict, url: str, expires: int = 600) -> str:
    cfg = config_of(settings)
    if not all(cfg.values()):
        raise R2Error("This picture is in your private R2 bucket: add the R2 keys in Settings > Pictures in the cloud.")
    key = url[len(PREFIX):]
    host = endpoint(cfg)[len("https://"):]
    return presign("GET", host, _path(cfg["bucket"], key), cfg["access_key_id"], cfg["secret_access_key"], expires=expires)


async def upload(settings: dict, key: str, data: bytes, content_type: str, client=None) -> str:
    """Put one file in the bucket; returns its r2: link."""
    cfg = config_of(settings)
    if not all(cfg.values()):
        raise R2Error("Add the R2 account ID, bucket and keys in Settings first.")
    host = endpoint(cfg)[len("https://"):]
    path = _path(cfg["bucket"], key)
    headers = signed_headers("PUT", host, path, data, cfg["access_key_id"], cfg["secret_access_key"], content_type)
    own = client is None
    if own:
        import httpx

        client = httpx.AsyncClient(timeout=60.0)
    try:
        r = await client.put(f"https://{host}{path}", content=data, headers=headers)
        if r.status_code >= 300:
            raise R2Error(f"R2 refused the upload ({r.status_code}): {r.text[:200]}")
    finally:
        if own:
            await client.aclose()
    return PREFIX + key
