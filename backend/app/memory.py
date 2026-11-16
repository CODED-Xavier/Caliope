"""Searchable long-term memory.

Every important fact is stored in SQLite. Retrieval works in two layers:
  1. Keyword search (SQLite FTS5) - always available, no model needed.
  2. Semantic search (embeddings from the local server) - used automatically if an
     embedding model is configured in settings.
Results from both are fused (reciprocal rank fusion) and weighted by importance.
"""
from __future__ import annotations

import logging
import math
from array import array
from collections import defaultdict
from typing import Callable

from .db import Database
from .util import now, stem, tokenize

try:  # numpy makes semantic search fast; everything still works without it
    import numpy as np
except ImportError:  # pragma: no cover
    np = None

log = logging.getLogger("rpg.memory")


def _pack(vec: list[float]) -> bytes:
    return array("f", vec).tobytes()


def _unpack(blob: bytes) -> list[float]:
    arr = array("f")
    arr.frombytes(blob)
    return list(arr)


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb + 1e-9)


class MemoryManager:
    def __init__(self, db: Database, llm, get_settings: Callable[[], dict]):
        self.db = db
        self.llm = llm
        self._get = get_settings

    # ------------------------------------------------------------------ writing
    async def add(self, conv_id: int, text: str, kind: str = "event", importance: int = 3, message_id: int | None = None) -> int | None:
        text = " ".join((text or "").split())[:600]
        if len(text) < 8:
            return None
        dup = self.db.query_one(
            "SELECT id FROM memories WHERE conversation_id = ? AND lower(text) = lower(?)", (conv_id, text)
        )
        if dup:
            return None
        vec = await self._embed_one(text)
        model = self._get().get("embedding_model") or None
        cur = self.db.execute(
            "INSERT INTO memories(conversation_id, message_id, text, kind, importance, embedding, embed_model, created_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (conv_id, message_id, text, kind, max(1, min(5, int(importance))), _pack(vec) if vec else None, model if vec else None, now()),
        )
        return cur.lastrowid

    async def _embed_one(self, text: str) -> list[float] | None:
        vecs = await self.llm.embed([text])
        return vecs[0] if vecs else None

    async def reindex(self, conv_id: int | None = None) -> int:
        """Embed memories that have no vector for the current embedding model."""
        model = self._get().get("embedding_model") or ""
        if not model:
            return 0
        sql = "SELECT id, text FROM memories WHERE (embedding IS NULL OR embed_model IS NOT ?)"
        params: list = [model]
        if conv_id is not None:
            sql += " AND conversation_id = ?"
            params.append(conv_id)
        rows = self.db.query(sql, params)
        done = 0
        for i in range(0, len(rows), 16):
            batch = rows[i : i + 16]
            vecs = await self.llm.embed([r["text"] for r in batch])
            if not vecs:
                break
            for r, v in zip(batch, vecs):
                self.db.execute("UPDATE memories SET embedding = ?, embed_model = ? WHERE id = ?", (_pack(v), model, r["id"]))
                done += 1
        return done

    # ---------------------------------------------------------------- admin/CRUD
    def list(self, conv_id: int, limit: int = 200, offset: int = 0) -> list[dict]:
        return self.db.query(
            "SELECT id, conversation_id, message_id, text, kind, importance, created_at, "
            "(embedding IS NOT NULL) AS has_embedding FROM memories WHERE conversation_id = ? "
            "ORDER BY id DESC LIMIT ? OFFSET ?",
            (conv_id, limit, offset),
        )

    def count(self, conv_id: int) -> int:
        return self.db.query_one("SELECT COUNT(*) AS n FROM memories WHERE conversation_id = ?", (conv_id,))["n"]

    def delete(self, memory_id: int) -> None:
        self.db.execute("DELETE FROM memories WHERE id = ?", (memory_id,))

    def delete_by_message(self, message_id: int) -> None:
        self.db.execute("DELETE FROM memories WHERE message_id = ?", (message_id,))

    # ---------------------------------------------------------------- retrieval
    @staticmethod
    def _fts_query(query: str) -> str:
        tokens: list[str] = []
        for tok in tokenize(query):
            if tok not in tokens:
                tokens.append(tok)
        tokens = tokens[:12]
        parts = []
        for tok in tokens:
            safe = tok.replace('"', "")
            parts.append(f'"{safe}"*' if len(safe) >= 4 else f'"{safe}"')
        return " OR ".join(parts)

    def search_keyword(self, conv_id: int, query: str, limit: int = 10) -> list[dict]:
        match = self._fts_query(query)
        if not match:
            return []
        try:
            return self.db.query(
                "SELECT m.id, m.text, m.kind, m.importance, m.message_id, bm25(memories_fts) AS rank "
                "FROM memories_fts JOIN memories m ON m.id = memories_fts.rowid "
                "WHERE memories_fts MATCH ? AND m.conversation_id = ? ORDER BY rank LIMIT ?",
                (match, conv_id, limit),
            )
        except Exception as exc:  # malformed query -> just skip keyword layer
            log.warning("FTS query failed: %s", exc)
            return []

    async def search_semantic(self, conv_id: int, query: str, limit: int = 10) -> list[dict]:
        settings = self._get()
        model = settings.get("embedding_model") or ""
        if not model or not query.strip():
            return []
        rows = self.db.query(
            "SELECT id, text, kind, importance, message_id, embedding FROM memories "
            "WHERE conversation_id = ? AND embedding IS NOT NULL AND embed_model = ?",
            (conv_id, model),
        )
        if not rows:
            return []
        qv = await self._embed_one(query)
        if not qv:
            return []
        min_sim = float(settings.get("memory_min_similarity", 0.4))
        scored: list[tuple[float, dict]] = []
        if np is not None:
            try:
                mat = np.vstack([np.frombuffer(r["embedding"], dtype=np.float32) for r in rows])
                q = np.asarray(qv, dtype=np.float32)
                sims = (mat @ q) / (np.linalg.norm(mat, axis=1) * np.linalg.norm(q) + 1e-9)
                scored = [(float(s), r) for s, r in zip(sims, rows)]
            except ValueError:  # mixed dimensions
                scored = []
        if not scored:
            scored = [(cosine(_unpack(r["embedding"]), qv), r) for r in rows if len(r["embedding"]) // 4 == len(qv)]
        scored = [(s, r) for s, r in scored if s >= min_sim]
        scored.sort(key=lambda t: t[0], reverse=True)
        out = []
        for s, r in scored[:limit]:
            item = {k: v for k, v in r.items() if k != "embedding"}
            item["similarity"] = s
            out.append(item)
        return out

    async def search(self, conv_id: int, query: str, k: int | None = None) -> list[dict]:
        k = k if k is not None else int(self._get().get("memory_top_k", 5))
        if k <= 0:
            return []
        keyword = self.search_keyword(conv_id, query, limit=k * 3)
        semantic = await self.search_semantic(conv_id, query, limit=k * 3)
        scores: dict[int, float] = defaultdict(float)
        items: dict[int, dict] = {}
        for ranked in (semantic, keyword):
            for rank, item in enumerate(ranked):
                scores[item["id"]] += 1.0 / (60 + rank)
                items.setdefault(item["id"], item)
        for mem_id, item in items.items():
            scores[mem_id] *= 1.0 + 0.15 * (item["importance"] - 3)
        ordered = sorted(items, key=lambda i: scores[i], reverse=True)[:k]
        return [{**items[i], "score": round(scores[i], 5)} for i in ordered]
