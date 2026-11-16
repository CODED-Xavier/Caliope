"""Skills: folders with a SKILL.md (YAML frontmatter + instructions), the same format used by
skills.sh and Claude skills.

How they are used
-----------------
* The app works fine with zero skills installed.
* In "auto" mode each turn the user's message is matched against every enabled skill's
  name/description (embeddings if available, otherwise BM25 keyword scoring). The best
  matches are injected into the prompt for that turn only.
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

log = logging.getLogger("rpg.skills")

MAX_ZIP_BYTES = 100 * 1024 * 1024
MAX_SKILL_DEPTH = 5
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
        model = self._get().get("embedding_model") or ""
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

    async def select(self, query: str, policy: dict | None = None) -> list[dict]:
        """Pick the skills to inject this turn.

        `policy` is the scenario's skills config: {"mode": auto|manual|off, "allow": [...], "pinned": [...]}.
        Returns dicts with name, description, text, score and reason ("pinned" or "auto").
        """
        policy = policy or {}
        mode = policy.get("mode", "auto")
        if mode == "off" or not self._skills:
            return []
        settings = self._get()
        enabled = self._enabled_map()
        usable = {n: s for n, s in self._skills.items() if enabled.get(n, True)}
        chosen: list[tuple[Skill, float, str]] = []

        for name in policy.get("pinned", []):
            if name in usable:
                chosen.append((usable[name], 1.0, "pinned"))

        if mode == "auto":
            allow = set(policy.get("allow") or [])
            pool = [s for n, s in usable.items() if (not allow or n in allow) and n not in policy.get("pinned", [])]
            top_k = int(settings.get("skills_top_k", 2))
            if pool and top_k > 0 and query.strip():
                vectors = await self._skill_vectors(pool)
                qv = (await self.llm.embed([query])) if vectors else None
                ranked: list[tuple[Skill, float]] = []
                if vectors and qv:
                    min_sim = float(settings.get("skills_min_similarity", 0.45))
                    ranked = [(s, cosine(qv[0], vectors[s.name])) for s in pool if s.name in vectors]
                    ranked = [(s, v) for s, v in ranked if v >= min_sim]
                else:
                    scores = self._bm25(query, {s.name: s.search_text for s in pool})
                    min_score = float(settings.get("skills_min_score", 0.6))
                    ranked = [(s, scores[s.name]) for s in pool if scores.get(s.name, 0) >= min_score]
                ranked.sort(key=lambda t: t[1], reverse=True)
                chosen.extend((s, v, "auto") for s, v in ranked[:top_k])

        budget = int(settings.get("skills_char_budget", 3500))
        out: list[dict] = []
        for skill, score, reason in chosen:
            if budget <= 200:
                break
            text = self._fit(skill.body, budget)
            budget -= len(text)
            out.append({"name": skill.name, "description": skill.description, "text": text, "score": round(float(score), 3), "reason": reason})
        return out

    @staticmethod
    def _fit(body: str, limit: int) -> str:
        if len(body) <= limit:
            return body
        cut = body[:limit]
        last_break = max(cut.rfind("\n\n"), cut.rfind("\n"))
        if last_break > limit * 0.6:
            cut = cut[:last_break]
        return cut.rstrip() + "\n[...skill text shortened...]"
