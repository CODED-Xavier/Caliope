"""Narration voice: Piper, a small text-to-speech program that runs on the processor (it leaves the graphics card
to the story model). The program and the voices are downloaded once, on request, from Piper's official places
(GitHub releases and Hugging Face); after that nothing leaves this PC. Each spoken reply is kept as a .wav file,
so playing it again is instant.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from .config import DATA_DIR
from .runtime import _http_bytes

VOICE_DIR = DATA_DIR / "voice"
PIPER_URL = "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_windows_amd64.zip"
HF = "https://huggingface.co/rhasspy/piper-voices/resolve/main"

# id -> (label, language, path inside the voices repository)
CATALOG = {
    "en_US-lessac-medium": ("Lessac · English (US), calm female narrator", "en", "en/en_US/lessac/medium"),
    "en_US-amy-medium": ("Amy · English (US), bright female", "en", "en/en_US/amy/medium"),
    "en_US-ryan-medium": ("Ryan · English (US), warm male", "en", "en/en_US/ryan/medium"),
    "en_GB-alan-medium": ("Alan · English (UK), storyteller male", "en", "en/en_GB/alan/medium"),
    "pt_BR-faber-medium": ("Faber · Português (Brasil), masculina", "pt-BR", "pt/pt_BR/faber/medium"),
}


class VoiceError(RuntimeError):
    pass


def speakable(text: str) -> str:
    """The reply as plain sentences: no status block, portrait tags, markdown marks or links."""
    t = re.split(r"^[ \t]*(?:\*\*|\[)?INFO(?:\*\*|\])?[ \t]*$", text or "", maxsplit=1, flags=re.M)[0]
    t = re.sub(r"\[\[\s*show\s*:[^\]\n]*\]\]", " ", t, flags=re.I)
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"[*_#>`~|]+", " ", t)
    t = re.sub(r"^[ \t]*[-=]{3,}[ \t]*$", " ", t, flags=re.M)
    t = re.sub(r"[⚔⚔️🎲💥✨🛒💰⏳🛌🏁📜🗨💭]", " ", t)
    t = re.sub(r"\s*\n\s*", "\n", t)
    t = re.sub(r"[ \t]{2,}", " ", t).strip()
    return t[:6000]


class VoiceManager:
    def __init__(self, folder: Path | None = None):
        self.dir = folder or VOICE_DIR
        self.progress: dict[str, float] = {}   # voice id (or "engine") -> 0..1 while downloading
        self.errors: dict[str, str] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ what is here
    def piper_exe(self) -> Path | None:
        engine = self.dir / "engine"
        for name in ("piper.exe", "piper"):
            for p in sorted(engine.rglob(name)) if engine.exists() else []:
                if p.is_file():
                    return p
        return None

    def voice_files(self, voice: str) -> tuple[Path, Path]:
        return self.dir / "voices" / f"{voice}.onnx", self.dir / "voices" / f"{voice}.onnx.json"

    def installed(self, voice: str) -> bool:
        onnx, cfg = self.voice_files(voice)
        return onnx.is_file() and cfg.is_file()

    def status(self) -> dict:
        return {
            "engine": bool(self.piper_exe()),
            "voices": [{"id": vid, "label": label, "language": lang, "installed": self.installed(vid),
                        "progress": self.progress.get(vid), "error": self.errors.get(vid, "")}
                       for vid, (label, lang, _) in CATALOG.items()],
            "engine_progress": self.progress.get("engine"),
            "supported": sys.platform == "win32" or bool(self.piper_exe()),
        }

    # ------------------------------------------------------------------ downloads
    async def install(self, voice: str, fetch_bytes=None) -> dict:
        if voice not in CATALOG:
            raise VoiceError("Unknown voice.")
        fetch_bytes = fetch_bytes or _http_bytes
        async with self._lock:
            self.errors.pop(voice, None)
            try:
                if not self.piper_exe():
                    if sys.platform != "win32" and fetch_bytes is _http_bytes:
                        raise VoiceError("The voice program download is for Windows.")
                    self.progress["engine"] = 0.0
                    data = await fetch_bytes(PIPER_URL, lambda d, t: self.progress.__setitem__("engine", d / t if t else 0.0))
                    self._unzip_engine(data)
                    self.progress.pop("engine", None)
                if not self.installed(voice):
                    path = CATALOG[voice][2]
                    onnx, cfg = self.voice_files(voice)
                    onnx.parent.mkdir(parents=True, exist_ok=True)
                    self.progress[voice] = 0.0
                    cfg_bytes = await fetch_bytes(f"{HF}/{path}/{voice}.onnx.json", lambda d, t: None)
                    model = await fetch_bytes(f"{HF}/{path}/{voice}.onnx", lambda d, t: self.progress.__setitem__(voice, d / t if t else 0.0))
                    if len(model) < 1_000_000:
                        raise VoiceError("The voice download is incomplete.")
                    onnx.with_suffix(".part").write_bytes(model)
                    cfg.write_bytes(cfg_bytes)
                    onnx.with_suffix(".part").replace(onnx)
            except Exception as exc:
                self.errors[voice] = str(exc)
                raise VoiceError(f"Download failed: {exc}") from exc
            finally:
                self.progress.pop(voice, None)
                self.progress.pop("engine", None)
        return self.status()

    def _unzip_engine(self, data: bytes) -> None:
        target = self.dir / "engine"
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = zf.namelist()
            if not any(n.endswith(("piper.exe", "/piper")) for n in names):
                raise VoiceError("The download does not contain Piper.")
            tmp = self.dir / "engine.new"
            shutil.rmtree(tmp, ignore_errors=True)
            tmp.mkdir(parents=True)
            for n in names:  # never write outside the voice folder
                t = (tmp / n).resolve()
                if tmp.resolve() not in t.parents and t != tmp.resolve():
                    raise VoiceError("The download contains unsafe paths.")
            zf.extractall(tmp)
        shutil.rmtree(target, ignore_errors=True)
        tmp.rename(target)

    def remove(self, voice: str) -> dict:
        for p in self.voice_files(voice):
            p.unlink(missing_ok=True)
        return self.status()

    # ------------------------------------------------------------------ speaking
    def speak(self, text: str, voice: str, speed: float = 1.0, runner=None) -> Path:
        """The .wav of this text (made once, then kept)."""
        if not self.installed(voice):
            raise VoiceError("Download a voice first (Settings > Narration voice).")
        exe = self.piper_exe()
        if not exe and runner is None:
            raise VoiceError("The voice program is missing: download a voice again in Settings.")
        text = speakable(text)
        if not text:
            raise VoiceError("Nothing to read in this message.")
        speed = max(0.5, min(2.0, float(speed or 1.0)))
        key = hashlib.sha1(f"{voice}|{speed:.2f}|{text}".encode("utf-8")).hexdigest()
        out = self.dir / "cache" / f"{key}.wav"
        if out.is_file():
            return out
        out.parent.mkdir(parents=True, exist_ok=True)
        onnx, _ = self.voice_files(voice)
        cmd = [str(exe), "--model", str(onnx), "--output_file", str(out.with_suffix(".tmp")), "--length_scale", f"{1 / speed:.3f}"]
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            run = runner or (lambda c, data: subprocess.run(c, input=data, capture_output=True, timeout=180, creationflags=flags))
            result = run(cmd, text.replace("\n", " ").encode("utf-8"))
        except subprocess.TimeoutExpired as exc:
            raise VoiceError("The voice took too long.") from exc
        tmp = out.with_suffix(".tmp")
        if getattr(result, "returncode", 0) != 0 or not tmp.is_file():
            err = (getattr(result, "stderr", b"") or b"").decode("utf-8", "ignore")[-300:]
            raise VoiceError(f"The voice could not read it. {err}".strip())
        tmp.replace(out)
        self._trim_cache()
        return out

    def _trim_cache(self, keep: int = 300) -> None:
        files = sorted((self.dir / "cache").glob("*.wav"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in files[keep:]:
            old.unlink(missing_ok=True)
