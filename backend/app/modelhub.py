"""The Models window: your .gguf models, Hugging Face search and downloads, load/unload, hide, delete.

- Models live in Calíope's own folder (backend/data/models/<author>/<repo>/). Other folders can be added by hand.
- Downloads come from huggingface.co (public repositories only), resume after an interruption, and are checked
  against the SHA-256 that Hugging Face publishes for every large file.
- "Deactivated" models stay on disk but are hidden from the model pickers.
- Delete removes the file for good (the window asks first) and only inside the model folders.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import shutil
import time
from pathlib import Path
from urllib.parse import quote

from . import runtime
from .db import Database

log = logging.getLogger("rpg.models")

HF = "https://huggingface.co"
REPO_RE = re.compile(r"^[A-Za-z0-9][\w.-]*/[\w.-]+$")
SPLIT_RE = re.compile(r"-(\d{5})-of-(\d{5})\.gguf$", re.I)
QUANT_RE = re.compile(r"(IQ\d_[A-Z]+|Q\d_K_[SML]|Q\d_K|Q\d_\d|Q\d|BF16|F16|F32)", re.I)
QUANT_NOTE = {
    "Q4_K_M": "recommended: good quality, fits 8 GB cards (8B models)",
    "Q4_K_S": "recommended: a little smaller than Q4_K_M",
    "Q5_K_M": "better quality, needs more memory",
    "Q5_K_S": "better quality, needs more memory",
    "Q6_K": "near full quality, large",
    "Q8_0": "almost no quality loss, very large",
    "Q3_K_M": "smaller, noticeably weaker",
    "Q3_K_S": "smaller, noticeably weaker",
    "Q3_K_L": "smaller, a bit weaker",
    "Q2_K": "smallest, weak writing",
    "F16": "full size, too large for most cards",
    "BF16": "full size, too large for most cards",
    "F32": "full size, too large for most cards",
}


class ModelError(ValueError):
    pass


def model_roots(extra: list[str] | tuple = ()) -> list[Path]:
    roots = list(runtime.MODEL_DIRS) + [Path(p) for p in extra]
    out, seen = [], set()
    for r in roots:
        key = str(r).lower().rstrip("\\/")
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def pick_model_file() -> str:
    """Open Windows' own file picker on this PC and return the chosen .gguf ('' when cancelled)."""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError as exc:  # Python without Tk
        raise ModelError("The file picker is not available here. Paste the folder's address instead.") from exc
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)  # above the game window
    try:
        return filedialog.askopenfilename(parent=root, title="Pick a model file (.gguf)",
                                          filetypes=[("Models", "*.gguf"), ("All files", "*.*")]) or ""
    finally:
        root.destroy()


def download_root() -> Path:
    """Calíope's own models folder: downloads go here (backend/data/models/<author>/<repo>/)."""
    return runtime.DATA_DIR / "models"


def own_copy(path: str) -> str | None:
    """A model file with the same name inside Calíope's folder (for a model that was used from LM Studio's)."""
    p = Path(path or "")
    root = download_root()
    if not p.name or root in p.parents or not root.is_dir():
        return None
    for found in root.rglob(p.name):
        if found.is_file() and (not p.is_file() or found.stat().st_size == p.stat().st_size):
            return str(found)
    return None


def quant_of(name: str) -> str:
    m = QUANT_RE.search(name)
    return m.group(1).upper() if m else ""


def quant_note(q: str) -> str:
    if q.startswith("IQ1") or q.startswith("IQ2"):
        return "very small, weak writing"
    if q.startswith("IQ3"):
        return "small, a bit weaker"
    if q.startswith("IQ4"):
        return "good quality for its size"
    return QUANT_NOTE.get(q, "")


def inside_roots(path: Path, roots: list[Path] | None = None) -> bool:
    try:
        rp = path.resolve()
    except OSError:
        return False
    return any(r.exists() and r.resolve() in rp.parents for r in (roots if roots is not None else model_roots()))


class ModelHub:
    def __init__(self, db: Database, engine, get_settings, update_settings, fetch_json=None, stream=None):
        self.db = db
        self.engine = engine
        self._get = get_settings
        self._update = update_settings
        self._fetch_json = fetch_json or _http_json
        self._stream = stream or _http_stream
        self.downloads: dict[str, dict] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    # ------------------------------------------------------------------ on this PC
    def added_folders(self) -> list[str]:
        return [x.strip() for x in str(self._get().get("model_folders") or "").splitlines() if x.strip()]

    def roots(self) -> list[Path]:
        return model_roots(self.added_folders())

    def folders(self) -> list[dict]:
        """Where the app looks for models: its own folder, plus the ones you added."""
        added = {a.lower().rstrip("\\/") for a in self.added_folders()}
        out = []
        for r in self.roots():
            mine = str(r).lower().rstrip("\\/") in added
            if r.exists() or mine:
                out.append({"path": str(r), "added": mine, "exists": r.is_dir()})
        return out

    def add_folder(self, path: str) -> str:
        p = Path(str(path or "").strip().strip('"')).expanduser()
        if p.suffix.lower() == ".gguf" and p.is_file():
            p = p.parent  # a model file: use the folder it is in
        if not str(path or "").strip() or not p.is_dir():
            raise ModelError(f"Folder not found: {path}")
        p = p.resolve()
        if p.parent == p or p == Path.home().resolve():
            raise ModelError("Pick the folder that has your models, not a whole drive or your user folder (searching it would be very slow).")
        if not any(True for _ in p.rglob("*.gguf")):
            raise ModelError(f"No .gguf model files were found in {p}.")
        current = self.added_folders()
        if str(p).lower() not in {c.lower().rstrip("\\/") for c in current} and not any(
                str(r).lower().rstrip("\\/") == str(p).lower() for r in model_roots()):
            self._update({"model_folders": "\n".join(current + [str(p)])})
        return str(p)

    def remove_folder(self, path: str) -> None:
        key = str(path or "").lower().rstrip("\\/")
        self._update({"model_folders": "\n".join(a for a in self.added_folders() if a.lower().rstrip("\\/") != key)})

    def disabled(self) -> set[str]:
        return {r["path"] for r in self.db.query("SELECT path FROM model_prefs WHERE disabled = 1")}

    def local(self) -> list[dict]:
        s = self._get()
        off = self.disabled()
        st = self.engine.status(with_log=False)
        running = st["state"] in ("ready", "starting")
        out = []
        for m in runtime.find_models(self.roots()):
            split = SPLIT_RE.search(m["name"])
            if split and split.group(1) != "00001":
                continue  # later parts of a split model are shown as one model
            path = m["path"]
            role = "embedding" if path == s.get("engine_embedding_path") else "story" if path == s.get("engine_model_path") else ""
            folder = Path(path).parent
            out.append({**m, "quant": quant_of(m["name"]), "disabled": path in off,
                        "selected": role, "loaded": bool(role) and running and s.get("ai_engine") == "builtin",
                        "folder": str(folder), "repo": "/".join(folder.parts[-2:])})
        return out

    def set_disabled(self, path: str, disabled: bool) -> None:
        if disabled:
            self.db.execute("INSERT INTO model_prefs(path, disabled) VALUES(?, 1) ON CONFLICT(path) DO UPDATE SET disabled = 1", (path,))
        else:
            self.db.execute("DELETE FROM model_prefs WHERE path = ?", (path,))

    async def delete(self, path: str) -> None:
        p = Path(path)
        if p.suffix.lower() != ".gguf" or not p.is_file() or not inside_roots(p, self.roots()):
            raise ModelError("Only .gguf files inside the model folders can be deleted here.")
        s = self._get()
        if path in (s.get("engine_model_path"), s.get("engine_embedding_path")):
            if s.get("ai_engine") == "builtin" and self.engine.state in ("ready", "starting"):
                await self.engine.stop()
            self._update({"engine_model_path": "" if path == s.get("engine_model_path") else s.get("engine_model_path", ""),
                          "engine_embedding_path": "" if path == s.get("engine_embedding_path") else s.get("engine_embedding_path", "")})
        files = [p]
        split = SPLIT_RE.search(p.name)
        if split:
            stem = p.name[: split.start()]
            files = [f for f in p.parent.glob(f"{glob_escape(stem)}-*-of-{split.group(2)}.gguf")]
        for f in files:
            f.unlink()
        self.set_disabled(path, False)
        folder = p.parent  # tidy up empty author/repo folders
        roots = {r.resolve() for r in self.roots() if r.exists()}
        while folder.resolve() not in roots and folder.exists() and not any(folder.iterdir()):
            folder.rmdir()
            folder = folder.parent

    # ------------------------------------------------------------------ Hugging Face
    async def search(self, query: str, limit: int = 30) -> list[dict]:
        q = (query or "").strip()
        url = f"{HF}/api/models?filter=gguf&sort=downloads&direction=-1&limit={int(limit)}"
        if q:
            url += "&search=" + quote(q)
        rows = await self._fetch_json(url)
        out = []
        for r in rows if isinstance(rows, list) else []:
            rid = r.get("id") or r.get("modelId") or ""
            if not REPO_RE.match(rid) or r.get("private") or r.get("gated"):
                continue
            tags = [t for t in r.get("tags", []) if ":" not in t and t not in ("gguf", "region", "endpoints_compatible")]
            out.append({"id": rid, "downloads": r.get("downloads", 0), "likes": r.get("likes", 0), "tags": tags[:6],
                        "updated": r.get("lastModified") or r.get("createdAt") or ""})
        return out

    async def files(self, repo: str) -> list[dict]:
        if not REPO_RE.match(repo or ""):
            raise ModelError("Not a valid Hugging Face repository name (author/name).")
        tree = await self._fetch_json(f"{HF}/api/models/{repo}/tree/main?recursive=true")
        groups: dict[str, dict] = {}
        for f in tree if isinstance(tree, list) else []:
            path = f.get("path", "")
            if f.get("type") != "file" or not path.lower().endswith(".gguf") or "mmproj" in path.lower():
                continue
            size = int((f.get("lfs") or {}).get("size") or f.get("size") or 0)
            sha = (f.get("lfs") or {}).get("oid", "")
            split = SPLIT_RE.search(path)
            key = path[: split.start()] if split else path
            g = groups.setdefault(key, {"name": Path(key).name if split else Path(path).name, "parts": [], "size": 0})
            g["parts"].append({"path": path, "size": size, "sha256": sha})
            g["size"] += size
        installed = {m["name"] for m in runtime.find_models(self.roots())}
        out = []
        for g in groups.values():
            g["parts"].sort(key=lambda x: x["path"])
            first = Path(g["parts"][0]["path"]).name
            q = quant_of(g["name"])
            out.append({"name": g["name"] if g["name"].endswith(".gguf") else g["name"] + ".gguf", "file": g["parts"][0]["path"],
                        "parts": g["parts"], "size": g["size"], "size_gb": round(g["size"] / 1e9, 2), "quant": q, "note": quant_note(q),
                        "installed": first in installed})
        return sorted(out, key=lambda x: x["size"])

    # ------------------------------------------------------------------ downloads
    def start_download(self, repo: str, file: str) -> dict:
        if not REPO_RE.match(repo or "") or ".." in file or not file.lower().endswith(".gguf") or file.startswith("/"):
            raise ModelError("Not a valid model file.")
        key = f"{repo}/{file}"
        cur = self.downloads.get(key)
        if cur and cur["state"] in ("queued", "downloading", "checking"):
            return cur
        item = {"key": key, "repo": repo, "file": file, "name": Path(file).name, "state": "queued", "done": 0, "total": 0,
                "speed_mb": 0.0, "error": "", "path": ""}
        self.downloads[key] = item
        self._tasks[key] = asyncio.create_task(self._run(item))
        return item

    def cancel(self, key: str) -> None:
        task = self._tasks.get(key)
        if task and not task.done():
            task.cancel()
        item = self.downloads.get(key)
        if item and item["state"] not in ("done", "error"):
            item["state"] = "cancelled"

    def forget(self, key: str) -> None:
        """Remove a finished/failed/cancelled download from the list (and its unfinished .part files)."""
        self.cancel(key)
        item = self.downloads.pop(key, None)
        if item and item["state"] != "done":
            folder = download_root() / item["repo"]
            stem = Path(item["file"]).name
            split = SPLIT_RE.search(stem)
            pattern = (glob_escape(stem[: split.start()]) + "-*.gguf.part") if split else glob_escape(stem) + ".part"
            for f in folder.glob(pattern) if folder.is_dir() else []:
                f.unlink(missing_ok=True)

    def list_downloads(self) -> list[dict]:
        return list(self.downloads.values())

    async def _run(self, item: dict) -> None:
        try:
            files = await self.files(item["repo"])
            entry = next((f for f in files if f["file"] == item["file"]), None)
            if not entry:
                raise ModelError("That file is no longer in the repository.")
            target_dir = download_root() / item["repo"]
            item["total"] = sum(p["size"] for p in entry["parts"])
            target_dir.mkdir(parents=True, exist_ok=True)
            need = item["total"] - sum((target_dir / (Path(p["path"]).name + ".part")).stat().st_size
                                       for p in entry["parts"] if (target_dir / (Path(p["path"]).name + ".part")).exists())
            if shutil.disk_usage(target_dir).free < need + 500_000_000:
                raise ModelError(f"Not enough free disk space ({need / 1e9:.1f} GB needed).")
            base = 0
            for part in entry["parts"]:
                final = target_dir / Path(part["path"]).name
                if not final.exists():
                    await self._fetch_part(item, part, final, base)
                base += part["size"]
                item["done"] = base
            item["path"] = str(target_dir / Path(entry["parts"][0]["path"]).name)
            item["state"] = "done"
        except asyncio.CancelledError:
            item["state"] = "cancelled"
            raise
        except Exception as exc:  # shown in the window
            log.warning("Model download failed: %s", exc)
            item["state"], item["error"] = "error", str(exc)[:300]

    async def _fetch_part(self, item: dict, part: dict, final: Path, base: int) -> None:
        tmp = final.with_name(final.name + ".part")
        sha = hashlib.sha256()
        have = tmp.stat().st_size if tmp.exists() else 0
        if have > part["size"]:
            tmp.unlink()
            have = 0
        if have:  # resume: hash what is already there
            with open(tmp, "rb") as fh:
                while chunk := await asyncio.to_thread(fh.read, 1 << 22):
                    sha.update(chunk)
        url = f"{HF}/{item['repo']}/resolve/main/{quote(part['path'])}"
        item["state"] = "downloading"
        t0, got0 = time.monotonic(), have
        with open(tmp, "ab") as fh:
            async for chunk in self._stream(url, have):
                fh.write(chunk)
                sha.update(chunk)
                have += len(chunk)
                item["done"] = base + have
                dt = time.monotonic() - t0
                if dt > 1:
                    item["speed_mb"] = round((have - got0) / dt / 1e6, 1)
                if have > part["size"] > 0:
                    raise ModelError("The server sent more data than expected.")
        if part["size"] and have != part["size"]:
            raise ModelError("The download stopped early. Press Download again to resume.")
        item["state"] = "checking"
        if part.get("sha256") and sha.hexdigest() != part["sha256"]:
            tmp.unlink()
            raise ModelError("The file is damaged (checksum mismatch). Download it again.")
        tmp.replace(final)

    # ------------------------------------------------------------------ load / unload
    def load_values(self, path: str, role: str = "story") -> dict:
        """The settings that make the built-in engine use this model (the caller saves them and restarts the engine)."""
        p = Path(path)
        if p.suffix.lower() != ".gguf" or not p.is_file():
            raise ModelError("Model file not found.")
        key = "engine_embedding_path" if role == "embedding" else "engine_model_path"
        return {"ai_engine": "builtin", key: str(p)}


def glob_escape(text: str) -> str:
    return re.sub(r"([\[\]*?])", r"[\1]", text)


# ------------------------------------------------------------------ HTTP (httpx)
async def _http_json(url: str):
    import httpx
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as c:
        try:
            r = await c.get(url, headers={"User-Agent": "Caliope"})
        except httpx.HTTPError as exc:
            raise ModelError(f"Could not reach Hugging Face (check your internet): {exc.__class__.__name__}") from exc
        if r.status_code in (401, 403):
            raise ModelError("This repository needs a Hugging Face login (gated). Choose another one.")
        if r.status_code == 404:
            raise ModelError("Not found on Hugging Face.")
        r.raise_for_status()
        return r.json()


async def _http_stream(url: str, start: int = 0):
    import httpx
    headers = {"User-Agent": "Caliope"}
    if start:
        headers["Range"] = f"bytes={start}-"
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=120.0), follow_redirects=True) as c:
        async with c.stream("GET", url, headers=headers) as r:
            if r.status_code in (401, 403):
                raise ModelError("This model needs a Hugging Face login (gated). Choose another one.")
            if start and r.status_code != 206:
                raise ModelError("The server cannot resume this download. Delete it and start again.")
            r.raise_for_status()
            async for chunk in r.aiter_bytes(1 << 20):
                yield chunk


def use_own_models(settings) -> None:
    """Calíope runs its models itself: a game set to LM Studio moves to the built-in engine (an online service with
    its own address and key stays), and a model used from LM Studio's folder switches to its copy in Calíope's folder."""
    s = settings.all()
    local = str(s.get("llm_base_url") or "").startswith(("http://localhost", "http://127.0.0.1"))
    changes = {}
    if s.get("ai_engine") == "lmstudio" and local:
        changes["ai_engine"] = "builtin"
    for key in ("engine_model_path", "engine_embedding_path"):
        mine = own_copy(str(s.get(key) or ""))
        if mine and mine != s.get(key):
            changes[key] = mine
    if changes:
        settings.update(changes)
        log.info("Using Calíope's own models: %s", changes)


def adopt_model(path: str) -> str | None:
    """Copy a model that is used from another program's folder (LM Studio's) into Calíope's own folder, keeping its
    <author>/<repo>/ names. Returns the new path, or None when there is nothing to copy (or no room on the disk)."""
    src = Path(path or "")
    root = download_root()
    if not src.is_file() or root in src.parents:
        return None
    mine = own_copy(path)
    if mine:
        return mine
    dest = root / src.parent.parent.name / src.parent.name / src.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(dest.parent).free < src.stat().st_size + 2 * 2**30:  # leave 2 GB free
        log.warning("Not enough free disk space to copy %s into Calíope's folder", src.name)
        return None
    part = dest.with_name(dest.name + ".copying")
    shutil.copyfile(src, part)
    part.replace(dest)
    log.info("Copied %s into Calíope's models folder", src.name)
    return str(dest)


def adopt_models(settings) -> None:
    """At start: models still used from LM Studio's folder are copied into Calíope's (in the background); the
    settings switch to the copies, used from the next model load on."""
    for key in ("engine_model_path", "engine_embedding_path"):
        try:
            new = adopt_model(str(settings.get(key) or ""))
        except OSError as exc:
            log.warning("Could not copy the model into Calíope's folder: %s", exc)
            continue
        if new and new != settings.get(key):
            settings.update({key: new})

