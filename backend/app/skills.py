"""Skills: folders with a SKILL.md (YAML frontmatter + instructions), the same format used by
skills.sh and Claude skills.

How they are used
-----------------
* Skills are CARD ADD-ONS: a card attaches up to 3 of them and their text becomes part of the stable
  start of the prompt. There is no per-message automatic selection (it cost time, filled the small
  context window and often picked the wrong skill).
* The game works the same with zero skills.
* "Suggest skills for this card" asks the model ONE time to pick the best matches from your library.
* Skill scripts are NEVER executed. Only the text of SKILL.md is used.
"""
from __future__ import annotations

import hashlib
import io
import logging
import math
import re
import shutil
import tempfile
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .db import Database
from .memory import _pack, _unpack, cosine
from .util import now, slugify, tokenize, truncate
from .config import embedding_key

log = logging.getLogger("rpg.skills")

MAX_ZIP_BYTES = 100 * 1024 * 1024
MAX_SKILL_DEPTH = 5
MAX_ATTACHED = 3
IGNORE = shutil.ignore_patterns(".git", ".github", "node_modules", "__pycache__", "*.pyc")
_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.S)


class SkillError(ValueError):
    pass


@dataclass
class Skill:
    name: str
    description: str
    body: str
    folder: Path
    tags: list[str] = field(default_factory=list)
    hash: str = ""

    @property
    def search_text(self) -> str:
        return f"{self.name} {self.description} {' '.join(self.tags)}"


def parse_skill_md(text: str) -> tuple[dict, str]:
    text = text.lstrip("\ufeff").replace("\r\n", "\n")
    m = _FRONTMATTER.match(text)
    if not m:
        return {}, text.strip()
    raw, body = m.groups()
    meta: dict = {}
    try:
        import yaml

        loaded = yaml.safe_load(raw)
        if isinstance(loaded, dict):
            meta = loaded
        else:
            raise ValueError("frontmatter is not a mapping")
    except Exception:
        for line in raw.split("\n"):  # tolerant fallback for slightly invalid YAML
            if ":" in line and not line.startswith((" ", "\t")):
                key, _, value = line.partition(":")
                meta[key.strip()] = value.strip().strip("\"'")
    return meta, body.strip()


class SkillManager:
    def __init__(self, db: Database, skills_dir: Path, llm, get_settings: Callable[[], dict]):
        self.db = db
        self.dir = Path(skills_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.llm = llm
        self._get = get_settings
        self._skills: dict[str, Skill] = {}
        self.scan()

    # --------------------------------------------------------------- discovery
    def scan(self) -> int:
        found: dict[str, Skill] = {}
        for md in sorted(self.dir.glob("*/SKILL.md")):
            try:
                text = md.read_text(encoding="utf-8")
            except OSError:
                continue
            meta, body = parse_skill_md(text)
            name = slugify(str(meta.get("name") or md.parent.name))
            tags = meta.get("tags") or []
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",") if t.strip()]
            found[name] = Skill(
                name=name,
                description=" ".join(str(meta.get("description") or "").split()),
                body=body,
                folder=md.parent,
                tags=[str(t) for t in tags],
                hash=hashlib.sha1(text.encode("utf-8")).hexdigest(),
            )
        self._skills = found
        return len(found)

    def _enabled_map(self) -> dict[str, bool]:
        return {r["name"]: bool(r["enabled"]) for r in self.db.query("SELECT name, enabled FROM skills_meta")}

    def list(self) -> list[dict]:
        enabled = self._enabled_map()
        meta = {r["name"]: r for r in self.db.query("SELECT * FROM skills_meta")}
        return [
            {
                "name": s.name,
                "description": s.description,
                "tags": s.tags,
                "enabled": enabled.get(s.name, True),
                "source": meta.get(s.name, {}).get("source", "local"),
                "size": len(s.body),
            }
            for s in sorted(self._skills.values(), key=lambda s: s.name)
        ]

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def set_enabled(self, name: str, enabled: bool) -> None:
        if name not in self._skills:
            raise SkillError(f"Skill '{name}' is not installed")
        self.db.execute(
            "INSERT INTO skills_meta(name, enabled, source, installed_at) VALUES(?,?, 'local', ?) "
            "ON CONFLICT(name) DO UPDATE SET enabled = excluded.enabled",
            (name, 1 if enabled else 0, now()),
        )

    # -------------------------------------------------------------- installing
    def _install_folder(self, src: Path, source: str) -> str:
        text = (src / "SKILL.md").read_text(encoding="utf-8")
        meta, _ = parse_skill_md(text)
        name = slugify(str(meta.get("name") or src.name))
        dest = self.dir / name
        if dest.resolve() != src.resolve():
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src, dest, ignore=IGNORE)
        self.db.execute(
            "INSERT INTO skills_meta(name, enabled, source, installed_at) VALUES(?,1,?,?) "
            "ON CONFLICT(name) DO UPDATE SET source = excluded.source, installed_at = excluded.installed_at",
            (name, source[:300], now()),
        )
        return name

    def install_from_path(self, path: str | Path, source: str | None = None) -> list[str]:
        p = Path(path).expanduser()
        if not p.exists():
            raise SkillError(f"Path not found: {p}")
        p = p.resolve()
        if p.is_file():
            if p.suffix.lower() == ".zip":
                return self.install_from_zip_bytes(p.read_bytes(), source or str(p))
            raise SkillError("Give a skill folder or a .zip file.")
        if (p / "SKILL.md").is_file():
            candidates = [p]
        else:
            candidates = sorted(
                {f.parent for f in p.rglob("SKILL.md")
                 if len(f.relative_to(p).parts) <= MAX_SKILL_DEPTH and ".git" not in f.parts}
            )
        if not candidates:
            raise SkillError("No SKILL.md file was found there.")
        names = [self._install_folder(c, source or str(p)) for c in candidates]
        self.scan()
        return names

    def install_from_zip_bytes(self, data: bytes, source: str = "zip upload", subpath: str = "") -> list[str]:
        try:
            zf = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile as exc:
            raise SkillError("That is not a valid zip file.") from exc
        with zf, tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            total = 0
            for info in zf.infolist():
                total += info.file_size
                if total > MAX_ZIP_BYTES:
                    raise SkillError("Zip is too large (limit 100 MB).")
                target = (root / info.filename).resolve()
                if root != target and root not in target.parents:
                    raise SkillError("Unsafe path inside zip file.")
            zf.extractall(root)
            base = root
            entries = [e for e in root.iterdir()]
            if len(entries) == 1 and entries[0].is_dir():
                base = entries[0]  # GitHub zips wrap everything in one folder
            if subpath:
                base = base / subpath.strip("/")
                if not base.exists():
                    raise SkillError(f"Folder '{subpath}' not found in the archive.")
            return self.install_from_path(base, source)

    async def install_from_url(self, url: str) -> list[str]:
        import httpx

        url = url.strip()
        gh = re.match(r"^https?://github\.com/([^/]+)/([^/#?]+?)(?:\.git)?(?:/tree/([^/]+)(?:/(.+?))?)?/?(?:[#?].*)?$", url)
        candidates: list[tuple[str, str]] = []
        subpath = ""
        if gh:
            owner, repo, branch, subpath = gh.group(1), gh.group(2), gh.group(3), gh.group(4) or ""
            refs = [branch] if branch else ["HEAD", "main", "master"]
            candidates = [(f"https://codeload.github.com/{owner}/{repo}/zip/{ref}", ref) for ref in refs]
        elif url.lower().endswith(".zip"):
            candidates = [(url, "")]
        else:
            raise SkillError("Use a GitHub link (repo or /tree/branch/folder), a direct .zip link, or a local path.")
        last_error = ""
        async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
            for dl_url, _ in candidates:
                try:
                    resp = await client.get(dl_url)
                except httpx.HTTPError as exc:
                    last_error = str(exc)
                    continue
                if resp.status_code == 200:
                    return self.install_from_zip_bytes(resp.content, url, subpath=subpath)
                last_error = f"HTTP {resp.status_code}"
        raise SkillError(f"Could not download the skill ({last_error}).")

    def uninstall(self, name: str) -> None:
        skill = self._skills.get(name)
        if not skill:
            raise SkillError(f"Skill '{name}' is not installed")
        if skill.folder.resolve().parent == self.dir.resolve():
            shutil.rmtree(skill.folder, ignore_errors=True)
        self.db.execute("DELETE FROM skills_meta WHERE name = ?", (name,))
        self.db.execute("DELETE FROM skill_embeddings WHERE name = ?", (name,))
        self.scan()

    # --------------------------------------------------------------- selection
    def _bm25(self, query: str, docs: dict[str, str]) -> dict[str, float]:
        q_tokens = set(tokenize(query))
        tokenized = {name: tokenize(text) for name, text in docs.items()}
        n = len(tokenized)
        if not q_tokens or n == 0:
            return {name: 0.0 for name in docs}
        avgdl = sum(len(t) for t in tokenized.values()) / n or 1.0
        df: Counter = Counter()
        for toks in tokenized.values():
            df.update(set(toks))
        k1, b = 1.2, 0.75
        scores: dict[str, float] = {}
        for name, toks in tokenized.items():
            tf = Counter(toks)
            dl = len(toks)
            s = 0.0
            for t in q_tokens:
                if t not in tf:
                    continue
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                s += idf * (tf[t] * (k1 + 1)) / (tf[t] + k1 * (1 - b + b * dl / avgdl))
            scores[name] = s
        return scores

    async def _skill_vectors(self, skills: list[Skill]) -> dict[str, list[float]] | None:
        model = embedding_key(self._get()) or ""
        if not model:
            return None
        vectors: dict[str, list[float]] = {}
        missing: list[Skill] = []
        for s in skills:
            row = self.db.query_one("SELECT hash, model, embedding FROM skill_embeddings WHERE name = ?", (s.name,))
            if row and row["hash"] == s.hash and row["model"] == model:
                vectors[s.name] = _unpack(row["embedding"])
            else:
                missing.append(s)
        if missing:
            vecs = await self.llm.embed([s.search_text for s in missing])
            if not vecs:
                return None
            for s, v in zip(missing, vecs):
                vectors[s.name] = v
                self.db.execute(
                    "INSERT INTO skill_embeddings(name, hash, model, embedding) VALUES(?,?,?,?) "
                    "ON CONFLICT(name) DO UPDATE SET hash=excluded.hash, model=excluded.model, embedding=excluded.embedding",
                    (s.name, s.hash, model, _pack(v)),
                )
        return vectors

    def attached(self, names: list[str]) -> list[dict]:
        """The skills a card has attached (installed and enabled only, at most 3), with text trimmed to share the budget."""
        enabled = self._enabled_map()
        chosen = [self._skills[n] for n in names[:MAX_ATTACHED] if n in self._skills and enabled.get(n, True)]
        if not chosen:
            return []
        per_skill = int(self._get().get("skills_char_budget", 3500)) // len(chosen)
        return [{"name": sk.name, "description": sk.description, "text": self._fit(sk.body, per_skill)} for sk in chosen]

    async def suggest(self, text: str, k: int = 3) -> list[dict]:
        """Pick the best skills for a card: shortlist by keywords or embeddings, then ask the model once."""
        enabled = self._enabled_map()
        pool = [sk for n, sk in self._skills.items() if enabled.get(n, True)]
        text = (text or "").strip()
        if not pool or not text:
            return []
        shortlist: list[Skill] = []
        vectors = await self._skill_vectors(pool)
        qv = (await self.llm.embed([text[:1500]])) if vectors else None
        if vectors and qv:
            ranked = sorted(pool, key=lambda sk: cosine(qv[0], vectors[sk.name]) if sk.name in vectors else -1, reverse=True)
            shortlist = ranked[:12]
        else:
            scores = self._bm25(text, {sk.name: sk.search_text for sk in pool})
            shortlist = [sk for sk in sorted(pool, key=lambda sk: scores.get(sk.name, 0), reverse=True)[:12] if scores.get(sk.name, 0) > 0]
        if not shortlist:
            return []

        picked: list[str] = []
        options = "\n".join(f"- {sk.name}: {truncate(sk.description, 140)}" for sk in shortlist)
        prompt = (
            f"A roleplaying card is described below. From the list of skills, choose up to {k} that would really help the "
            "narrator run THIS card. Choose fewer, or none, if nothing fits.\n\n"
            f"CARD:\n{text[:1500]}\n\nSKILLS:\n{options}\n\nAnswer as JSON: {{\"skills\": [\"name\", ...]}}"
        )
        try:
            from .util import extract_json

            raw = await self.llm.chat(
                [{"role": "user", "content": prompt}],
                json_schema={"type": "object", "properties": {"skills": {"type": "array", "items": {"type": "string"}}}, "required": ["skills"]},
                temperature=0.2, max_tokens=120,
            )
            data = extract_json(raw) or {}
            names = {sk.name for sk in shortlist}
            picked = [n for n in data.get("skills", []) if isinstance(n, str) and n in names][:k]
        except Exception as exc:  # no model available: fall back to the shortlist
            log.info("Skill suggestion fell back to keywords: %s", exc)
        source = "ai"
        if not picked:
            picked, source = [sk.name for sk in shortlist[:k]], "keywords"
        by_name = {sk.name: sk for sk in shortlist}
        return [{"name": n, "description": by_name[n].description, "source": source} for n in picked]

    @staticmethod
    def _fit(body: str, limit: int) -> str:
        if len(body) <= limit:
            return body
        cut = body[:limit]
        last_break = max(cut.rfind("\n\n"), cut.rfind("\n"))
        if last_break > limit * 0.6:
            cut = cut[:last_break]
        return cut.rstrip() + "\n[...skill text shortened...]"
