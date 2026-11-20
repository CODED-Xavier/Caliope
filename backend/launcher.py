"""One-click start (run by Play.bat).

1. Builds the interface when it is missing or its code changed (needs Node.js only for that).
2. Starts the app (backend + interface at http://127.0.0.1:8000).
3. Starts LM Studio's server and loads your model when they are not running yet (if LM Studio's
   command-line tool "lms" is installed, which it is with any recent LM Studio).
4. Opens the app in your browser.

Close the window or press Ctrl+C to stop everything this script started.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
ROOT = BACKEND.parent
FRONTEND = ROOT / "frontend"
DATA = BACKEND / "data"
APP_URL = "http://127.0.0.1:8000"


def say(msg: str = "") -> None:
    print(msg, flush=True)


# ------------------------------------------------------------------ interface build
def newest_mtime(paths) -> float:
    newest = 0.0
    for p in paths:
        p = Path(p)
        if p.is_dir():
            for f in p.rglob("*"):
                if f.is_file():
                    newest = max(newest, f.stat().st_mtime)
        elif p.is_file():
            newest = max(newest, p.stat().st_mtime)
    return newest


def needs_build(frontend: Path) -> bool:
    """True when frontend/dist is missing or older than the interface's code."""
    index = frontend / "dist" / "index.html"
    if not index.is_file():
        return True
    sources = [frontend / "src", frontend / "index.html", frontend / "package.json", frontend / "vite.config.js"]
    return newest_mtime(sources) > index.stat().st_mtime


def needs_npm_install(frontend: Path) -> bool:
    marker = frontend / "node_modules" / ".package-lock.json"
    if not marker.is_file():
        return True
    return newest_mtime([frontend / "package.json", frontend / "package-lock.json"]) > marker.stat().st_mtime


def find_npm() -> str | None:
    return shutil.which("npm.cmd") or shutil.which("npm")


def build_interface(frontend: Path = FRONTEND) -> bool:
    """Returns False only when there is no interface at all and it could not be built."""
    if not needs_build(frontend):
        return True
    has_old = (frontend / "dist" / "index.html").is_file()
    npm = find_npm()
    if not npm:
        if has_old:
            say("  ! The interface code changed, but Node.js is not installed, so the previous build is used.")
            return True
        say("  ! Node.js is needed once to build the interface. Install the LTS version from https://nodejs.org and run Play.bat again.")
        return False
    if needs_npm_install(frontend):
        say("  Installing interface packages (first time only, needs internet)...")
        if subprocess.call([npm, "install", "--no-fund", "--no-audit"], cwd=frontend) != 0:
            say("  ! npm install failed.")
            return has_old
    say("  Building the interface...")
    if subprocess.call([npm, "run", "build"], cwd=frontend) != 0:
        say("  ! The interface build failed." + (" Using the previous build." if has_old else ""))
        return has_old
    return True


# ------------------------------------------------------------------ small HTTP helpers
def get_json(url: str, timeout: float = 3.0):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None


def wait_for(fn, seconds: float, step: float = 0.5):
    end = time.time() + seconds
    while time.time() < end:
        value = fn()
        if value:
            return value
        time.sleep(step)
    return None


# ------------------------------------------------------------------ LM Studio
def find_lms() -> str | None:
    found = shutil.which("lms")
    if found:
        return found
    for name in ("lms.exe", "lms"):
        p = Path.home() / ".lmstudio" / "bin" / name
        if p.is_file():
            return str(p)
    return None


def lmstudio_root(base_url: str) -> str:
    """http://localhost:1234/v1 -> http://localhost:1234"""
    base = (base_url or "http://localhost:1234/v1").rstrip("/")
    return base[:-3] if base.endswith("/v1") else base


def loaded_models(base_url: str) -> list[str] | None:
    """Models LM Studio has in memory right now (None when it cannot tell)."""
    data = get_json(lmstudio_root(base_url) + "/api/v0/models")
    if not isinstance(data, dict) or not isinstance(data.get("data"), list):
        return None
    return [m.get("id", "") for m in data["data"] if m.get("state") == "loaded" and m.get("type") != "embeddings"]


def prepare_lmstudio(settings: dict) -> None:
    base = settings.get("llm_base_url", "http://localhost:1234/v1")
    if "localhost" not in base and "127.0.0.1" not in base:
        return  # a server on another machine: not ours to start
    lms = find_lms()
    health = get_json(APP_URL + "/api/health") or {}
    if not (health.get("llm") or {}).get("ok"):
        if not lms:
            say("  ! LM Studio's server is not running. Open LM Studio > Developer > Start Server.")
            return
        say("  Starting LM Studio's server...")
        subprocess.call([lms, "server", "start"], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        ok = wait_for(lambda: ((get_json(APP_URL + "/api/health") or {}).get("llm") or {}).get("ok"), 25)
        if not ok:
            say("  ! LM Studio did not answer. Open LM Studio and start the server there.")
            return
    model = settings.get("model") or ""
    loaded = loaded_models(base)
    if loaded is None or loaded or not model or not lms:
        if loaded == [] and not model:
            say("  i No model is loaded. Choose one in Settings, or load it in LM Studio (it also loads by itself on the first message).")
        return
    ctx = int(settings.get("context_window") or 8192)
    say(f"  Loading {model} with a {ctx}-token context window (can take a minute)...")
    code = subprocess.call([lms, "load", model, "--context-length", str(ctx), "-y"])
    if code != 0:
        say("  ! Could not load the model. Load it in LM Studio; the app will use it.")


# ------------------------------------------------------------------ desktop shortcut
def create_shortcut() -> bool:
    if os.name != "nt":
        return False
    target = ROOT / "Play.bat"
    script = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\\Local RPG.lnk');"
        f"$s.TargetPath='{target}';$s.WorkingDirectory='{ROOT}';$s.IconLocation='%SystemRoot%\\System32\\imageres.dll,76';$s.Save()"
    )
    return subprocess.call(["powershell", "-NoProfile", "-Command", script]) == 0


def first_run_questions() -> None:
    flag = DATA / "launcher.json"
    try:
        state = json.loads(flag.read_text("utf-8")) if flag.is_file() else {}
    except ValueError:
        state = {}
    if state.get("asked_shortcut") or os.name != "nt" or not sys.stdin.isatty():
        return
    answer = input("  Create a 'Local RPG' shortcut on your desktop? (y/n) ").strip().lower()
    if answer.startswith(("y", "s")):
        say("  Shortcut created." if create_shortcut() else "  ! Could not create the shortcut.")
    DATA.mkdir(parents=True, exist_ok=True)
    flag.write_text(json.dumps({**state, "asked_shortcut": True}), "utf-8")


# ------------------------------------------------------------------ main
def main() -> int:
    ap = argparse.ArgumentParser(description="Start Local RPG")
    ap.add_argument("--no-browser", action="store_true", help="do not open the browser")
    ap.add_argument("--no-lmstudio", action="store_true", help="do not start LM Studio or load the model")
    ap.add_argument("--shortcut", action="store_true", help="create the desktop shortcut and exit")
    args = ap.parse_args()

    if args.shortcut:
        ok = create_shortcut()
        say("Shortcut created on your desktop." if ok else "Could not create the shortcut (Windows only).")
        return 0 if ok else 1

    say("=== Local RPG ===")
    if get_json(APP_URL + "/api/health"):
        say("  The app is already running. Opening it...")
        if not args.no_browser:
            webbrowser.open(APP_URL)
        return 0

    first_run_questions()
    if not build_interface():
        return 1

    say("  Starting the app...")
    server = subprocess.Popen([sys.executable, "run.py"], cwd=BACKEND)
    try:
        if not wait_for(lambda: get_json(APP_URL + "/api/health"), 60):
            say("  ! The app did not start. Read the messages above for the reason.")
            server.terminate()
            return 1
        settings = get_json(APP_URL + "/api/settings") or {}
        if settings.get("ai_engine") == "builtin":
            say("  Built-in AI engine: the model loads in the background (see Settings > Model).")
        elif not args.no_lmstudio:
            prepare_lmstudio(settings)
        say(f"\n  Ready: {APP_URL}")
        say("  Keep this window open while you play. Close it (or press Ctrl+C) to stop.\n")
        if not args.no_browser:
            webbrowser.open(APP_URL)
        return server.wait()
    except KeyboardInterrupt:
        say("\n  Stopping...")
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
        return 0


if __name__ == "__main__":
    sys.exit(main())
