"""Client for any OpenAI-compatible local server (LM Studio, llama.cpp server, Ollama, ...).

The rest of the app only talks to this class, so swapping the model or the server
never requires touching game logic.
"""
from __future__ import annotations

import json
import logging
import re
from typing import AsyncIterator, Callable

log = logging.getLogger("rpg.llm")


class LLMError(Exception):
    """Raised when the model server cannot be reached or returns an error."""


class ThinkFilter:
    """Removes <think>...</think> blocks (reasoning models) from a token stream."""

    OPEN = "<think>"
    CLOSE = "</think>"

    def __init__(self) -> None:
        self.buf = ""
        self.inside = False
        self._strip_next = False

    @staticmethod
    def _partial_suffix(text: str, tag: str) -> int:
        """Length of the longest suffix of `text` that is a proper prefix of `tag`."""
        for k in range(min(len(tag) - 1, len(text)), 0, -1):
            if text.endswith(tag[:k]):
                return k
        return 0

    def feed(self, chunk: str) -> str:
        self.buf += chunk
        out: list[str] = []
        while True:
            if self.inside:
                idx = self.buf.find(self.CLOSE)
                if idx == -1:
                    keep = self._partial_suffix(self.buf, self.CLOSE)
                    self.buf = self.buf[len(self.buf) - keep :] if keep else ""
                    break
                self.buf = self.buf[idx + len(self.CLOSE) :]
                self.inside = False
                self._strip_next = True
            else:
                idx = self.buf.find(self.OPEN)
                if idx == -1:
                    keep = self._partial_suffix(self.buf, self.OPEN)
                    if keep:
                        out.append(self.buf[:-keep])
                        self.buf = self.buf[-keep:]
                    else:
                        out.append(self.buf)
                        self.buf = ""
                    break
                out.append(self.buf[:idx])
                self.buf = self.buf[idx + len(self.OPEN) :]
                self.inside = True
        text = "".join(out)
        if self._strip_next and text:
            text = text.lstrip()
            if text:
                self._strip_next = False
        return text

    def flush(self) -> str:
        rest = "" if self.inside else self.buf
        self.buf = ""
        return rest


def strip_think(text: str) -> str:
    return re.sub(r"<think>.*?</think>\s*", "", text or "", flags=re.S)


class LLMClient:
    def __init__(self, get_settings: Callable[[], dict]):
        self._get = get_settings
        self._client = None
        self._auto_model: str | None = None
        self._embed_cache: dict[tuple[str, str], list[float]] = {}  # the same query is often embedded twice a turn
        self.last_usage: dict | None = None   # real token counts of the last streamed reply (when the server reports them)
        self._no_usage = False

    # ---------------------------------------------------------------- plumbing
    async def _http(self):
        if self._client is None:
            import httpx

            self._client = httpx.AsyncClient(timeout=httpx.Timeout(900.0, connect=10.0))
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _builtin(self) -> bool:
        return self._get().get("ai_engine") == "builtin"

    def _base(self) -> str:
        s = self._get()
        if s.get("ai_engine") == "builtin":
            return f"http://127.0.0.1:{int(s.get('engine_port', 8091))}/v1"
        return str(s["llm_base_url"]).rstrip("/")

    def _embed_base(self) -> str:
        """The built-in engine runs the embedding model as a second server on the next port."""
        s = self._get()
        if s.get("ai_engine") == "builtin":
            return f"http://127.0.0.1:{int(s.get('engine_port', 8091)) + 1}/v1"
        return self._base()

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._get().get('api_key') or 'none'}"}

    def _unreachable(self, exc: Exception) -> LLMError:
        hint = ("Is the built-in engine started? (Settings > AI engine)" if self._builtin()
                else "Is LM Studio's local server running?")
        return LLMError(f"Cannot reach the model server at {self._base()}. {hint} ({exc.__class__.__name__}: {exc})")

    # ------------------------------------------------------------------ models
    async def list_models(self) -> list[str]:
        import httpx

        client = await self._http()
        try:
            resp = await client.get(f"{self._base()}/models", headers=self._headers(), timeout=10.0)
        except httpx.HTTPError as exc:
            raise self._unreachable(exc) from exc
        if resp.status_code != 200:
            raise LLMError(f"Model server returned {resp.status_code}: {resp.text[:300]}")
        return [m.get("id", "") for m in resp.json().get("data", []) if m.get("id")]

    async def health(self) -> dict:
        try:
            models = await self.list_models()
            return {"ok": True, "base_url": self._base(), "models": models}
        except LLMError as exc:
            return {"ok": False, "base_url": self._base(), "error": str(exc), "models": []}

    async def _resolve_model(self) -> str:
        if self._builtin():
            return "local"  # the built-in engine serves exactly one model and ignores the name
        configured = self._get().get("model") or ""
        if configured:
            return configured
        if self._auto_model:
            return self._auto_model
        ids = [i for i in await self.list_models() if "embed" not in i.lower()]
        if not ids:
            raise LLMError("The model server reports no models. Load a model in LM Studio first.")
        self._auto_model = ids[0]
        return self._auto_model

    # ------------------------------------------------------------------- chat
    def _payload(self, messages: list[dict], model: str, stream: bool, stop, overrides: dict) -> dict:
        s = self._get()
        payload: dict = {
            "model": model,
            "messages": messages,
            "stream": stream,
            "temperature": s["temperature"],
            "top_p": s["top_p"],
            "max_tokens": s["max_tokens"],
        }
        if s.get("top_k"):
            payload["top_k"] = s["top_k"]
        if s.get("min_p"):
            payload["min_p"] = s["min_p"]
        if s.get("repeat_penalty"):
            payload["repeat_penalty"] = s["repeat_penalty"]
        payload.update({k: v for k, v in overrides.items() if v is not None})
        if stop:
            payload["stop"] = list(stop)
        return payload

    async def stream_chat(self, messages: list[dict], stop: list[str] | None = None, **overrides) -> AsyncIterator[str]:
        """Yield text pieces as the model produces them."""
        import httpx

        client = await self._http()
        model = await self._resolve_model()
        payload = self._payload(messages, model, True, stop, overrides)
        if not self._no_usage:
            payload["stream_options"] = {"include_usage": True}  # the real prompt size, to measure tokens exactly
        self.last_usage = None
        think = ThinkFilter()
        try:
            for attempt in range(2):
                async with client.stream("POST", f"{self._base()}/chat/completions", json=payload, headers=self._headers()) as resp:
                    if resp.status_code == 400 and "stream_options" in payload and attempt == 0:
                        await resp.aread()
                        self._no_usage = True  # an older server that does not know stream_options: ask again without it
                        payload.pop("stream_options")
                        continue
                    if resp.status_code != 200:
                        body = (await resp.aread()).decode("utf-8", "replace")
                        self._auto_model = None
                        raise LLMError(f"Model server returned {resp.status_code}: {body[:500]}")
                    async for line in resp.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            obj = json.loads(data)
                        except ValueError:
                            continue
                        if "error" in obj:
                            raise LLMError(str(obj["error"])[:500])
                        if isinstance(obj.get("usage"), dict):
                            self.last_usage = obj["usage"]
                        choices = obj.get("choices") or []
                        if not choices:
                            continue
                        piece = (choices[0].get("delta") or {}).get("content")
                        if piece:
                            visible = think.feed(piece)
                            if visible:
                                yield visible
                break
        except httpx.HTTPError as exc:
            raise self._unreachable(exc) from exc
        tail = think.flush()
        if tail:
            yield tail

    async def chat(self, messages: list[dict], json_schema: dict | None = None, **overrides) -> str:
        """Single, non-streaming completion. Optionally constrained to a JSON schema."""
        import httpx

        client = await self._http()
        model = await self._resolve_model()
        payload = self._payload(messages, model, False, overrides.pop("stop", None), overrides)
        if json_schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "result", "schema": json_schema},
            }
            if self._builtin():  # llama.cpp's documented form; harmless next to the OpenAI form
                payload["response_format"]["schema"] = json_schema
        url = f"{self._base()}/chat/completions"
        try:
            resp = await client.post(url, json=payload, headers=self._headers())
            if resp.status_code == 400 and json_schema:
                # Some servers/models do not support structured output: retry unconstrained.
                payload.pop("response_format", None)
                resp = await client.post(url, json=payload, headers=self._headers())
        except httpx.HTTPError as exc:
            raise self._unreachable(exc) from exc
        if resp.status_code != 200:
            self._auto_model = None
            raise LLMError(f"Model server returned {resp.status_code}: {resp.text[:500]}")
        try:
            text = resp.json()["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMError("Unexpected response format from the model server.") from exc
        return strip_think(text).strip()

    # -------------------------------------------------------------- embeddings
    async def embed(self, texts: list[str]) -> list[list[float]] | None:
        """Return one vector per text, or None if embeddings are unavailable."""
        from .config import embedding_key

        model = embedding_key(self._get())
        if not model or not texts:
            return None
        if len(texts) == 1 and (model, texts[0]) in self._embed_cache:
            return [self._embed_cache[(model, texts[0])]]
        import httpx

        client = await self._http()
        try:
            resp = await client.post(
                f"{self._embed_base()}/embeddings",
                json={"model": model.removeprefix("gguf:"), "input": texts},
                headers=self._headers(),
                timeout=60.0,
            )
            if resp.status_code != 200:
                log.warning("Embedding request failed: %s %s", resp.status_code, resp.text[:200])
                return None
            data = sorted(resp.json()["data"], key=lambda d: d.get("index", 0))
            out = [d["embedding"] for d in data]
            if len(texts) == 1 and out:
                if len(self._embed_cache) >= 64:
                    self._embed_cache.pop(next(iter(self._embed_cache)))
                self._embed_cache[(model, texts[0])] = out[0]
            return out
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            log.warning("Embedding request failed: %s", exc)
            return None
