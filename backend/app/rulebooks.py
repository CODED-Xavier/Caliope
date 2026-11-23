"""Rulebooks: import a PDF (or text), split it into searchable sections, and give the GM the right passage.

A whole rulebook never fits in the context window, so the book is stored in the database in sections of
about 150-250 words, each with its heading and page. Every turn, the sections that match what is
happening are searched (keywords, plus meaning when an embedding model is set) and only the best one or
two go to the AI. House rules written by you are always sent and win over the book.

Text PDFs are read directly. Pages without text (scanned books) are read with OCR when Tesseract is
installed (free: https://github.com/UB-Mannheim/tesseract/wiki).
"""
from __future__ import annotations

import io
import json
import logging
import os
import re
import shutil
from array import array
from pathlib import Path
from typing import Callable

from .db import Database
from .util import now, tokenize, truncate
from .config import embedding_key

log = logging.getLogger("rpg.rulebooks")

MAX_UPLOAD_BYTES = 120 * 1024 * 1024
CHUNK_WORDS = 200
MIN_CHUNK_WORDS = 40
SYSTEMS = ("dnd5e", "vtm5", "other")


APPLIES = ("always", "fights", "words")
FIGHT_WORDS = ("fight", "duel", "spar", "sparring", "battle", "attack", "strike", "blow", "clash", "faster", "stronger",
               "overwhelm", "power", "speed", "durability", "dodge", "parry", "punch", "slash", "luta", "lutar", "duelo",
               "treino", "batalha", "ataque", "ataca", "golpe", "mais rápido", "mais forte", "esquiva", "poder", "velocidade")


def applies_now(applies: str, words: str, text: str, fighting: bool = False) -> bool:
    low = (text or "").lower()
    has = lambda ws: any(re.search(rf"(?<!\w){re.escape(w.strip().lower())}", low) for w in ws if w.strip())  # noqa: E731
    if applies == "fights":
        return fighting or has(FIGHT_WORDS) or has(words.split(","))
    if applies == "words":
        return has(words.split(","))
    return True


class RulebookError(ValueError):
    pass


# ------------------------------------------------------------------ reading files
def find_tesseract() -> str | None:
    found = shutil.which("tesseract")
    if found:
        return found
    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                 os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs")):
        p = Path(base) / "Tesseract-OCR" / "tesseract.exe"
        if p.is_file():
            return str(p)
    return None


def ocr_available() -> bool:
    try:
        import pypdfium2  # noqa: F401
        import pytesseract  # noqa: F401
    except ImportError:
        return False
    return find_tesseract() is not None


def _ocr_page(pdf_bytes: bytes, index: int, lang: str = "eng") -> str:
    import pypdfium2
    import pytesseract

    pytesseract.pytesseract.tesseract_cmd = find_tesseract() or "tesseract"
    doc = pypdfium2.PdfDocument(pdf_bytes)
    try:
        image = doc[index].render(scale=2.2).to_pil()
    finally:
        doc.close()
    return pytesseract.image_to_string(image, lang=lang)


def read_pdf(data: bytes, progress: Callable[[float, str], None] = lambda p, m: None, use_ocr: bool = True) -> tuple[list[str], dict]:
    """Text of every page, plus info: pages, how many were read with OCR, how many stayed empty."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise RulebookError("The PDF reader is not installed. Run Play.bat again to install it.") from exc
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            reader.decrypt("")
        total = len(reader.pages)
    except Exception as exc:
        raise RulebookError(f"This PDF could not be opened ({exc}).") from exc
    pages: list[str] = []
    ocr_ok = use_ocr and ocr_available()
    info = {"pages": total, "ocr_pages": 0, "empty_pages": 0, "ocr_available": ocr_ok}
    for i, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
        except Exception:  # a broken page should not stop the whole book
            text = ""
        if len(text.strip()) < 25 and ocr_ok:
            try:
                text = _ocr_page(data, i)
                info["ocr_pages"] += 1
            except Exception as exc:
                log.warning("OCR failed on page %s: %s", i + 1, exc)
        if len(text.strip()) < 25:
            info["empty_pages"] += 1
        pages.append(text)
        progress((i + 1) / max(1, total), f"Reading page {i + 1} of {total}" + (" (OCR)" if info["ocr_pages"] else ""))
    return pages, info


def read_text(data: bytes) -> list[str]:
    """Plain text or Markdown. A form-feed (\\f) or a line '--- page N ---' starts a new page."""
    text = data.decode("utf-8", errors="replace")
    parts = re.split(r"\f|^-{3,}\s*page\s*\d+\s*-{3,}\s*$", text, flags=re.M | re.I)
    return [p for p in parts if p.strip()] or [text]


# ------------------------------------------------------------------ splitting into sections
_HEADING_MD = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")


def _is_heading(line: str, nxt: str) -> bool:
    s = line.strip()
    if not s or len(s) > 70 or len(s) < 3:
        return False
    if _HEADING_MD.match(s):
        return True
    if s[-1] in ".,;:!?)" or s[0].islower() or not s[0].isalpha():
        return False
    words = s.split()
    if len(words) > 9 or sum(ch.isdigit() for ch in s) > 3:
        return False
    if s.isupper() and len(s) >= 4:
        return True
    capitalized = sum(1 for w in words if w[0].isupper() or w.lower() in ("of", "the", "and", "a", "an", "in", "on", "to", "or", "for", "with"))
    return capitalized == len(words) and bool(nxt.strip()) and len(nxt.strip()) > len(s)


def _clean(text: str) -> str:
    text = text.replace("\u00ad", "").replace("\r", "")
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)          # hyphenated line breaks
    text = re.sub(r"[ \t]+", " ", text)
    return text


def split_sections(pages: list[str]) -> list[dict]:
    """[{heading, page, text}] of about CHUNK_WORDS words, cut at headings when possible."""
    chunks: list[dict] = []
    heading, buf, start_page = "", [], 1

    def flush():
        nonlocal buf
        words = " ".join(buf).split()
        while words:
            part = words[:CHUNK_WORDS]
            # do not leave a tiny tail: merge it into this chunk
            if 0 < len(words) - CHUNK_WORDS < MIN_CHUNK_WORDS:
                part = words
            chunks.append({"heading": heading, "page": start_page, "text": " ".join(part)})
            words = words[len(part):]
        buf = []

    for page_no, page in enumerate(pages, 1):
        lines = _clean(page).split("\n")
        for i, line in enumerate(lines):
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            if _is_heading(line, nxt):
                if len(" ".join(buf).split()) >= MIN_CHUNK_WORDS:
                    flush()
                m = _HEADING_MD.match(line.strip())
                heading = (m.group(1) if m else line.strip()).title() if line.strip().isupper() else (m.group(1) if m else line.strip())
                if not buf:
                    start_page = page_no
                continue
            if line.strip():
                if not buf:
                    start_page = page_no
                buf.append(line.strip())
                if len(" ".join(buf).split()) >= CHUNK_WORDS:
                    flush()
    if buf:
        flush()
    # merge leftovers that are too small to be useful into the previous section
    merged: list[dict] = []
    for c in chunks:
        if merged and len(c["text"].split()) < MIN_CHUNK_WORDS // 2 and merged[-1]["heading"] == c["heading"]:
            merged[-1]["text"] += " " + c["text"]
        else:
            merged.append(c)
    return merged


# ------------------------------------------------------------------ storage and search
def _pack(vec: list[float]) -> bytes:
    return array("f", vec).tobytes()


def _fts_query(query: str) -> str:
    tokens: list[str] = []
    for tok in tokenize(query):
        if tok not in tokens and len(tok) >= 3:
            tokens.append(tok)
    return " OR ".join(f'"{t}"*' if len(t) >= 4 else f'"{t}"' for t in tokens[:14])


def _similarities(rows: list[dict], q: list[float]) -> list[tuple[float, int]]:
    """Cosine similarity of the query with every stored vector (numpy when available: ~100x faster)."""
    try:
        import numpy as np
        dim = len(q)
        good = [r for r in rows if len(r["embedding"]) == dim * 4]
        if not good:
            return []
        mat = np.frombuffer(b"".join(r["embedding"] for r in good), dtype=np.float32).reshape(len(good), dim)
        qv = np.asarray(q, dtype=np.float32)
        sims = (mat @ qv) / (np.linalg.norm(mat, axis=1) * np.linalg.norm(qv) + 1e-9)
        return [(float(x), r["id"]) for x, r in zip(sims, good)]
    except ImportError:  # pragma: no cover
        from .memory import cosine
        out = []
        for r in rows:
            v = array("f")
            v.frombytes(r["embedding"])
            if len(v) == len(q):
                out.append((cosine(list(v), q), r["id"]))
        return out


class RulebookRepository:
    def __init__(self, db: Database, llm=None, get_settings: Callable[[], dict] = dict):
        self.db = db
        self.llm = llm
        self._get = get_settings
        # A book that was being read when the app closed would say "processing" forever.
        db.execute("UPDATE rulebooks SET status = 'error', progress = 0, "
                   "message = 'The import was interrupted when the app closed. Delete the book and import it again.' "
                   "WHERE status = 'processing'")

    async def embed_missing(self) -> int:
        """Give every ready book vectors for the current embedding model (after the model changed)."""
        done = 0
        for row in self.db.query("SELECT id FROM rulebooks WHERE status = 'ready'"):
            done += await self.embed_book(row["id"])
        return done

    # ---- books
    def create(self, name: str, system: str = "other", source: str = "") -> dict:
        cur = self.db.execute(
            "INSERT INTO rulebooks(name, system, source, status, progress, message, info, house_rules, created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (truncate(name.strip() or "Rulebook", 80), system if system in SYSTEMS else "other", truncate(source, 120),
             "processing", 0.0, "Waiting…", "{}", "", now()),
        )
        return self.get(cur.lastrowid)

    def get(self, book_id: int) -> dict:
        row = self.db.query_one("SELECT * FROM rulebooks WHERE id = ?", (book_id,))
        if not row:
            raise RulebookError(f"Rulebook {book_id} not found.")
        return self._book(row)

    def list(self) -> list[dict]:
        return [self._book(r) for r in self.db.query("SELECT * FROM rulebooks ORDER BY name COLLATE NOCASE")]

    def _book(self, row: dict) -> dict:
        count = self.db.query_one("SELECT COUNT(*) AS n FROM rule_chunks WHERE book_id = ?", (row["id"],))["n"]
        return {"id": row["id"], "name": row["name"], "system": row["system"], "source": row["source"], "status": row["status"],
                "progress": row["progress"], "message": row["message"], "info": json.loads(row["info"] or "{}"),
                "house_rules": row["house_rules"], "sections": count, "created_at": row["created_at"],
                "applies": row.get("applies") or "always", "trigger_words": row.get("trigger_words") or ""}

    def create_ruleset(self, name: str, core: str = "", applies: str = "always", words: str = "") -> dict:
        """A rule set written in Calíope (no file): its core rules are sent to the Aedo when they apply."""
        cur = self.db.execute(
            "INSERT INTO rulebooks(name, system, source, status, progress, message, info, house_rules, created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (truncate(name.strip() or "Rule set", 80), "other", "", "ready", 1.0, "Rule set", "{}", "", now()))
        return self.update(cur.lastrowid, house_rules=core, applies=applies, trigger_words=words)

    def update(self, book_id: int, name: str | None = None, house_rules: str | None = None, system: str | None = None,
               applies: str | None = None, trigger_words: str | None = None) -> dict:
        self.get(book_id)
        if applies in APPLIES:
            self.db.execute("UPDATE rulebooks SET applies = ? WHERE id = ?", (applies, book_id))
        if trigger_words is not None:
            words = ", ".join(dict.fromkeys(w.strip() for w in str(trigger_words).split(",") if w.strip()))
            self.db.execute("UPDATE rulebooks SET trigger_words = ? WHERE id = ?", (truncate(words, 800), book_id))
        if name is not None and name.strip():
            self.db.execute("UPDATE rulebooks SET name = ? WHERE id = ?", (truncate(name.strip(), 80), book_id))
        if house_rules is not None:
            self.db.execute("UPDATE rulebooks SET house_rules = ? WHERE id = ?", (truncate(house_rules, 6000), book_id))
        if system in SYSTEMS:
            self.db.execute("UPDATE rulebooks SET system = ? WHERE id = ?", (system, book_id))
        return self.get(book_id)

    def delete(self, book_id: int) -> None:
        self.get(book_id)
        with self.db.transaction():
            self.db.execute("DELETE FROM rule_chunks WHERE book_id = ?", (book_id,))
            self.db.execute("DELETE FROM rulebooks WHERE id = ?", (book_id,))

    def _status(self, book_id: int, status: str, progress: float, message: str, info: dict | None = None) -> None:
        if info is None:
            self.db.execute("UPDATE rulebooks SET status=?, progress=?, message=? WHERE id=?", (status, progress, message, book_id))
        else:
            self.db.execute("UPDATE rulebooks SET status=?, progress=?, message=?, info=? WHERE id=?",
                            (status, progress, message, json.dumps(info), book_id))

    # ---- import
    def import_bytes(self, book_id: int, data: bytes, filename: str) -> dict:
        """Read the file and store its sections (runs in a worker thread; progress is saved as it goes)."""
        try:
            if len(data) > MAX_UPLOAD_BYTES:
                raise RulebookError("The file is larger than 120 MB.")
            is_pdf = data[:5] == b"%PDF-" or filename.lower().endswith(".pdf")
            if is_pdf:
                pages, info = read_pdf(data, lambda p, m: self._status(book_id, "processing", round(p * 0.9, 3), m))
            else:
                pages = read_text(data)
                info = {"pages": len(pages), "ocr_pages": 0, "empty_pages": 0, "ocr_available": ocr_available()}
            sections = split_sections(pages)
            if not sections:
                hint = (" It looks scanned: install Tesseract OCR (see the Rulebooks window) and import it again."
                        if info.get("empty_pages") and not info.get("ocr_available") else "")
                raise RulebookError("No text was found in this file." + hint)
            with self.db.transaction():
                self.db.execute("DELETE FROM rule_chunks WHERE book_id = ?", (book_id,))
                for i, s in enumerate(sections):
                    self.db.execute("INSERT INTO rule_chunks(book_id, seq, heading, page, text) VALUES(?,?,?,?,?)",
                                    (book_id, i, truncate(s["heading"], 120), s["page"], s["text"]))
            info["sections"] = len(sections)
            note = f"{len(sections)} sections from {info['pages']} pages"
            if info["empty_pages"]:
                note += f"; {info['empty_pages']} pages had no readable text" + ("" if info["ocr_available"] else " (OCR not installed)")
            self._status(book_id, "ready", 1.0, note, info)
        except RulebookError as exc:
            self._status(book_id, "error", 0.0, str(exc))
        except Exception as exc:  # pragma: no cover - unexpected
            log.exception("Rulebook import failed")
            self._status(book_id, "error", 0.0, f"Import failed: {exc}")
        return self.get(book_id)

    async def embed_book(self, book_id: int, batch: int = 32) -> int:
        """Add meaning-based search to a book (only when an embedding model is set)."""
        model = embedding_key(self._get()) or ""
        if not model or self.llm is None:
            return 0
        rows = self.db.query("SELECT id, heading, text FROM rule_chunks WHERE book_id = ? AND (embedding IS NULL OR embed_model != ?)",
                             (book_id, model))
        done = 0
        for i in range(0, len(rows), batch):
            part = rows[i:i + batch]
            vecs = await self.llm.embed([f"{r['heading']}: {r['text']}" for r in part])
            if not vecs:
                break
            for r, v in zip(part, vecs):
                self.db.execute("UPDATE rule_chunks SET embedding = ?, embed_model = ? WHERE id = ?", (_pack(v), model, r["id"]))
            done += len(part)
        return done

    # ---- search
    def search_keyword(self, book_ids: list[int], query: str, limit: int = 6) -> list[dict]:
        match = _fts_query(query)
        if not match or not book_ids:
            return []
        marks = ",".join("?" * len(book_ids))
        try:
            return self.db.query(
                "SELECT c.id, c.book_id, c.heading, c.page, c.text, b.name AS book, bm25(rule_chunks_fts, 3.0, 1.0) AS rank "
                f"FROM rule_chunks_fts JOIN rule_chunks c ON c.id = rule_chunks_fts.rowid JOIN rulebooks b ON b.id = c.book_id "
                f"WHERE rule_chunks_fts MATCH ? AND c.book_id IN ({marks}) ORDER BY rank LIMIT ?",
                (match, *book_ids, limit),
            )
        except Exception as exc:
            log.warning("Rule search failed: %s", exc)
            return []

    async def search_semantic(self, book_ids: list[int], query: str, limit: int = 6) -> list[dict]:
        model = embedding_key(self._get()) or ""
        if not model or not book_ids or self.llm is None or not query.strip():
            return []
        marks = ",".join("?" * len(book_ids))
        # Vectors only first (a book has thousands of passages); the text is read for the few best ones.
        rows = self.db.query(
            f"SELECT id, embedding FROM rule_chunks WHERE book_id IN ({marks}) AND embedding IS NOT NULL AND embed_model = ?",
            (*book_ids, model),
        )
        if not rows:
            return []
        vecs = await self.llm.embed([query])
        if not vecs:
            return []
        q = vecs[0]
        scored = _similarities(rows, q)
        scored = [t for t in scored if t[0] >= 0.45]
        scored.sort(key=lambda t: t[0], reverse=True)
        best = scored[:limit]
        if not best:
            return []
        ids = [r_id for _, r_id in best]
        texts = {r["id"]: r for r in self.db.query(
            f"SELECT c.id, c.book_id, c.heading, c.page, c.text, b.name AS book FROM rule_chunks c JOIN rulebooks b ON b.id = c.book_id "
            f"WHERE c.id IN ({','.join('?' * len(ids))})", tuple(ids))}
        return [texts[i] | {"similarity": s} for s, i in best if i in texts]

    async def search(self, book_ids: list[int], query: str, k: int = 3) -> list[dict]:
        keyword = self.search_keyword(book_ids, query, limit=k * 3)
        semantic = await self.search_semantic(book_ids, query, limit=k * 3)
        scores: dict[int, float] = {}
        items: dict[int, dict] = {}
        for ranked in (semantic, keyword):
            for rank, item in enumerate(ranked):
                scores[item["id"]] = scores.get(item["id"], 0.0) + 1.0 / (60 + rank)
                items.setdefault(item["id"], item)
        best = sorted(items.values(), key=lambda it: -scores[it["id"]])
        return best[:k]

    async def passages_for_turn(self, book_ids: list[int], query: str, char_budget: int = 1400) -> list[dict]:
        """The rule sections worth sending this turn (at most two, within the budget)."""
        if not book_ids or char_budget <= 0:
            return []
        found = await self.search(book_ids, query, k=4)
        # Keyword-only hits must match at least two words of the message, so small talk does not pull rules in.
        words = set(tokenize(query))
        out, used = [], 0
        for f in found:
            if "similarity" not in f:
                hit = words & set(tokenize(f["heading"] + " " + f["text"]))
                if len(hit) < 2:
                    continue
            text = truncate(f["text"], max(200, char_budget - used))
            if out and used + len(text) > char_budget:
                break
            out.append({**f, "text": text})
            used += len(text)
            if len(out) == 2:
                break
        return out

    def house_rules(self, book_ids: list[int], text: str | None = None, fighting: bool = False) -> list[tuple[str, str]]:
        """The core rules of the card's books and rule sets. With `text` (this turn's words), only those that apply
        now: *always*, *in fights and shows of power* (a fight is on or the words say so), *when these words appear*."""
        if not book_ids:
            return []
        marks = ",".join("?" * len(book_ids))
        rows = self.db.query(f"SELECT name, house_rules, applies, trigger_words FROM rulebooks WHERE id IN ({marks}) "
                             f"AND status = 'ready' ORDER BY name", tuple(book_ids))
        out = []
        for r in rows:
            if not (r["house_rules"] or "").strip():
                continue
            if text is not None and not applies_now(r.get("applies") or "always", r.get("trigger_words") or "", text, fighting):
                continue
            out.append((r["name"], r["house_rules"].strip()))
        return out

    def core_rules(self, book_ids: list[int], text: str, fighting: bool = False) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
        """(rules that always apply: the stable part of the prompt, rules that apply this turn only)."""
        if not book_ids:
            return [], []
        marks = ",".join("?" * len(book_ids))
        rows = self.db.query(f"SELECT name, house_rules, applies, trigger_words FROM rulebooks WHERE id IN ({marks}) "
                             f"AND status = 'ready' ORDER BY name", tuple(book_ids))
        always, now_ = [], []
        for r in rows:
            core = (r["house_rules"] or "").strip()
            if not core:
                continue
            if (r.get("applies") or "always") == "always":
                always.append((r["name"], core))
            elif applies_now(r["applies"], r.get("trigger_words") or "", text, fighting):
                now_.append((r["name"], core))
        return always, now_

    def ready_ids(self, book_ids: list[int]) -> list[int]:
        if not book_ids:
            return []
        marks = ",".join("?" * len(book_ids))
        return [r["id"] for r in self.db.query(f"SELECT id FROM rulebooks WHERE id IN ({marks}) AND status = 'ready'", tuple(book_ids))]
