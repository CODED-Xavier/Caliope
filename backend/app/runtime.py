"""The built-in AI engine: llama.cpp's server, started and stopped by the app (no LM Studio needed).

- The engine (llama-server, Vulkan build for AMD/NVIDIA/Intel GPUs) is downloaded once from llama.cpp's
  official GitHub releases into the `engine` folder next to the app.
- Your model is a .gguf file. The app lists the ones LM Studio already downloaded, so nothing is copied.
- A second small server runs the embedding model, if you chose one (for meaning-based memory search).
- The engine is stopped when the app stops. On Windows the engine is tied to the app's process, so it also
  stops if the app's window is closed abruptly.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

from .config import APP_HOME, DATA_DIR

log = logging.getLogger("rpg.runtime")

ENGINE_DIR = APP_HOME / "engine"
LOG_PATH = DATA_DIR / "engine.log"
PID_PATH = DATA_DIR / "engine.pid"
RELEASES_API = "https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=10"
PINNED_TAG = "b12380"  # known-good fallback
ASSET = "llama-{tag}-bin-win-vulkan-x64.zip"
DOWNLOAD = "https://github.com/ggml-org/llama.cpp/releases/download/{tag}/{asset}"
ENGINE_KEYS = ("ai_engine", "engine_model_path", "engine_embedding_path", "engine_port", "engine_gpu_layers", "context_window")
MODEL_DIRS = [Path.home() / ".lmstudio" / "models", Path.home() / ".cache" / "lm-studio" / "models", DATA_DIR / "models"]


class EngineError(RuntimeError):
    pass


# ------------------------------------------------------------------ finding things
def server_binary(engine_dir: Path | None = None) -> Path | None:
    engine_dir = engine_dir or ENGINE_DIR
    for name in ("llama-server.exe", "llama-server"):
        for p in sorted(engine_dir.rglob(name)) if engine_dir.exists() else []:
            if p.is_file():
                return p
    return None


def find_models(dirs: list[Path] | None = None) -> list[dict]:
    """GGUF files already on this PC (LM Studio's folder and the app's own), largest first."""
    out, seen = [], set()
    for d in dirs or MODEL_DIRS:
        if not d.exists():
            continue
        for p in d.rglob("*.gguf"):
            name = p.name.lower()
            if "mmproj" in name or p in seen:
                continue
            seen.add(p)
            try:
                size = p.stat().st_size
            except OSError:
                continue
            out.append({"path": str(p), "name": p.name, "size_gb": round(size / 1e9, 2),
                        "embedding": any(k in name for k in ("embed", "nomic", "bge", "e5-", "gte"))})
    return sorted(out, key=lambda m: (m["embedding"], -m["size_gb"]))


SLOTS = 2  # see build_command
STORY_SLOT, HELPER_SLOT = 0, 1


def build_command(binary: Path, model: str, ctx: int, port: int, gpu_layers: str, embedding: bool = False) -> list[str]:
    cmd = [str(binary), "-m", model, "--host", "127.0.0.1", "--port", str(port), "-ngl", str(gpu_layers or "auto"),
           "--no-webui"]
    if embedding:
        cmd += ["--embeddings", "-c", "2048"]
    else:
        # Two slots, each with the full context: slot 0 only ever holds the story, slot 1 the helpers (tracker,
        # summaries, the Aedo's answers outside the story). So the story's long, unchanged beginning stays in memory
        # between turns and only the new part is read: the first word comes in seconds instead of a minute.
        cmd += ["-c", str(int(ctx) * SLOTS), "-np", str(SLOTS), "--cache-reuse", "256"]
    return cmd


# ------------------------------------------------------------------ Windows: children die with the app
def _kill_with_parent(proc: subprocess.Popen) -> None:
    if os.name != "nt":
        return
    try:
        import ctypes
        from ctypes import wintypes

        k32 = ctypes.windll.kernel32
        job = k32.CreateJobObjectW(None, None)

        class LIMIT(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

        class IO(ctypes.Structure):
            _fields_ = [(n, ctypes.c_uint64) for n in ("R", "W", "O", "RT", "WT", "OT")]

        class EXT(ctypes.Structure):
            _fields_ = [("Basic", LIMIT), ("Io", IO), ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

        info = EXT()
        info.Basic.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))
        k32.AssignProcessToJobObject(job, ctypes.c_void_p(proc._handle))  # noqa: SLF001
        _JOBS.append(job)  # keep the handle open for the app's lifetime
    except Exception as exc:  # best effort only
        log.warning("Could not tie the engine to the app process: %s", exc)


_JOBS: list = []


# ------------------------------------------------------------------ the manager
class EngineManager:
    def __init__(self, get_settings, http_get=None):
        self._get = get_settings
        self.chat: subprocess.Popen | None = None
        self.embed: subprocess.Popen | None = None
        self.state = "stopped"          # stopped | starting | ready | error | downloading
        self.message = ""
        self.progress = 0.0
        self._lock = asyncio.Lock()
        self._http_get = http_get

    # ---- status
    def status(self, with_log: bool = True) -> dict:
        s = self._get()
        binary = server_binary()
        if self.state == "ready" and self.chat is not None and self.chat.poll() is not None:
            self._set("error", "The engine stopped unexpectedly. Read the engine log, then press Start.")
        out = {"mode": s.get("ai_engine", "lmstudio"), "installed": binary is not None, "binary": str(binary or ""),
               "state": self.state, "message": self.message, "progress": round(self.progress, 3),
               "model": s.get("engine_model_path", "")}
        if with_log:
            out["log"] = self.log_tail()
        return out

    @staticmethod
    def log_tail(lines: int = 12) -> str:
        """The end of the engine log (only the last few KB are read: the settings window asks every 1.5 s)."""
        try:
            with open(LOG_PATH, "rb") as fh:
                fh.seek(0, os.SEEK_END)
                size = fh.tell()
                fh.seek(max(0, size - 8192))
                text = fh.read().decode("utf-8", errors="replace")
        except OSError:
            return ""
        return "\n".join(text.splitlines()[-lines:])

    # ---- start / stop
    def _spawn(self, cmd: list[str]) -> subprocess.Popen:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8", errors="replace") as logf:  # the child keeps its own copy open
            logf.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} {' '.join(cmd)}\n")
            logf.flush()
            flags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW
            proc = subprocess.Popen(cmd, stdout=logf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, creationflags=flags,
                                    cwd=str(Path(cmd[0]).parent))
        _kill_with_parent(proc)
        return proc

    @staticmethod
    def _rotate_log() -> None:
        """One log per engine start (the previous one is kept as engine.log.1), so it never grows without end."""
        try:
            if LOG_PATH.exists():
                LOG_PATH.replace(LOG_PATH.with_name(LOG_PATH.name + ".1"))
        except OSError:
            pass

    async def start(self, wait: bool = True) -> dict:
        async with self._lock:
            if self.state == "downloading":
                return self.status()  # the download starts the engine when it finishes
            await self._stop_locked()
            s = self._get()
            if s.get("ai_engine") != "builtin":
                return self.status()
            binary = server_binary()
            model = s.get("engine_model_path", "")
            if not binary:
                self._set("error", "The built-in engine is not downloaded yet. Use Settings > AI engine > Download.")
                return self.status()
            if not model or not Path(model).is_file():
                self._set("error", "Choose a model file (.gguf) in Settings > AI engine.")
                return self.status()
            port = int(s.get("engine_port", 8091))
            self._kill_stale()
            self._rotate_log()
            self.chat = self._spawn(build_command(binary, model, int(s.get("context_window", 8192)), port,
                                                  str(s.get("engine_gpu_layers", "auto"))))
            emb = s.get("engine_embedding_path", "")
            if emb and Path(emb).is_file():
                self.embed = self._spawn(build_command(binary, emb, 2048, port + 1, "all", embedding=True))
            PID_PATH.write_text(json.dumps([p.pid for p in (self.chat, self.embed) if p]))
            self._set("starting", "Loading the model (the first time can take a minute)…")
        if wait:
            await self.wait_ready()
        return self.status()

    async def wait_ready(self, timeout: float = 240.0) -> bool:
        port = int(self._get().get("engine_port", 8091))
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.chat is None:
                return False
            if self.chat.poll() is not None:
                self._set("error", "The engine stopped while loading. Read the engine log below (often: not enough video memory "
                                   "— lower the context window or the GPU layers).")
                return False
            if await self._healthy(port):
                self._set("ready", "Ready")
                return True
            await asyncio.sleep(1.0)
        self._set("error", "The model took too long to load.")
        return False

    async def _healthy(self, port: int) -> bool:
        get = self._http_get or _http_get
        try:
            code = await get(f"http://127.0.0.1:{port}/health")
        except Exception:
            return False
        return code == 200

    async def stop(self) -> None:
        async with self._lock:
            await self._stop_locked()

    async def _stop_locked(self) -> None:
        for proc in (self.chat, self.embed):
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    await asyncio.to_thread(proc.wait, 10)
                except subprocess.TimeoutExpired:
                    proc.kill()
        self.chat = self.embed = None
        try:
            PID_PATH.unlink()
        except OSError:
            pass
        if self.state != "downloading":
            self._set("stopped", "")

    def stop_now(self) -> None:
        """Synchronous stop for app shutdown."""
        for proc in (self.chat, self.embed):
            if proc and proc.poll() is None:
                proc.terminate()

    @staticmethod
    def _kill_stale() -> None:
        """An engine left over from a crash would hold the port and the video memory."""
        try:
            pids = json.loads(PID_PATH.read_text())
        except (OSError, ValueError):
            return
        for pid in pids if isinstance(pids, list) else []:
            try:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(int(pid)), "/F"], capture_output=True, creationflags=0x08000000)
                else:
                    os.kill(int(pid), 15)
            except (OSError, ValueError):
                pass

    def _set(self, state: str, message: str) -> None:
        self.state, self.message = state, message

    # ---- download
    async def download(self, fetch_json=None, fetch_bytes=None) -> dict:
        """Get llama.cpp's Vulkan server for Windows from its official GitHub releases."""
        if sys.platform != "win32" and fetch_bytes is None:
            raise EngineError("The built-in engine download is for Windows. On other systems install llama.cpp yourself "
                              "and put llama-server in the engine folder.")
        self._set("downloading", "Looking for the latest llama.cpp release…")
        self.progress = 0.0
        fetch_json = fetch_json or _http_json
        fetch_bytes = fetch_bytes or _http_bytes
        url = None
        try:
            releases = await fetch_json(RELEASES_API)
            for rel in releases if isinstance(releases, list) else []:
                for a in rel.get("assets", []):
                    if a.get("name", "").endswith("-bin-win-vulkan-x64.zip"):
                        url = a.get("browser_download_url")
                        break
                if url:
                    break
        except Exception as exc:
            log.warning("Release lookup failed (%s); using the pinned version", exc)
        url = url or DOWNLOAD.format(tag=PINNED_TAG, asset=ASSET.format(tag=PINNED_TAG))
        try:
            self._set("downloading", f"Downloading {url.rsplit('/', 1)[-1]}…")
            data = await fetch_bytes(url, self._on_progress)
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                names = zf.namelist()
                if not any(n.endswith(("llama-server.exe", "llama-server")) for n in names):
                    raise EngineError("The download does not contain llama-server.")
                tmp = ENGINE_DIR.with_name("engine.new")
                shutil.rmtree(tmp, ignore_errors=True)
                tmp.mkdir(parents=True)
                for n in names:  # never write outside the engine folder
                    target = (tmp / n).resolve()
                    if tmp.resolve() not in target.parents and target != tmp.resolve():
                        raise EngineError("The download contains unsafe paths.")
                zf.extractall(tmp)
            await self.stop()
            shutil.rmtree(ENGINE_DIR, ignore_errors=True)
            tmp.rename(ENGINE_DIR)
            (ENGINE_DIR / "SOURCE.txt").write_text(url + "\n", "utf-8")
            self._set("stopped", "Engine downloaded.")
        except Exception as exc:
            self._set("error", f"Download failed: {exc}")
            raise EngineError(str(exc)) from exc
        return self.status()

    def _on_progress(self, done: int, total: int) -> None:
        self.progress = done / total if total else 0.0
        self.message = f"Downloading the engine… {done // 1_000_000} / {max(1, total // 1_000_000)} MB"


# ------------------------------------------------------------------ small HTTP helpers (httpx)
async def _http_get(url: str) -> int:
    import httpx
    async with httpx.AsyncClient(timeout=3.0) as c:
        return (await c.get(url)).status_code


async def _http_json(url: str):
    import httpx
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as c:
        r = await c.get(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "Caliope"})
        r.raise_for_status()
        return r.json()


async def _http_bytes(url: str, progress) -> bytes:
    import httpx
    buf = bytearray()
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=120.0), follow_redirects=True) as c:
        async with c.stream("GET", url, headers={"User-Agent": "Caliope"}) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length") or 0)
            async for chunk in r.aiter_bytes(1 << 16):
                buf.extend(chunk)
                if len(buf) > 600_000_000:
                    raise EngineError("The download is unexpectedly large.")
                progress(len(buf), total)
    return bytes(buf)
