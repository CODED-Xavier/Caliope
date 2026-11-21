"""One-click start (run by Play.bat).

1. Builds the interface when it is missing or its code changed (needs Node.js only for that).
2. Starts the app (backend + interface at http://127.0.0.1:8000).
3. Makes sure the shortcuts exist (desktop and Start menu).
4. Opens the app in its own window (the AI model loads in the background, with the built-in engine).

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
    sources = [frontend / "src", frontend / "public", frontend / "index.html", frontend / "package.json", frontend / "vite.config.js"]
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


def create_shortcut(only_if_missing: bool = False) -> bool:
    """Shortcuts on the desktop and in the Start menu: Calíope's icon, the black window starts minimized."""
    if os.name != "nt":
        return False
    target = ROOT / "Play.bat"
    icon = ROOT / "assets" / "icon.ico"
    icon_loc = str(icon) if icon.is_file() else "%SystemRoot%\\System32\\imageres.dll,76"
    one = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut($p);"
           f"$s.TargetPath='{target}';$s.WorkingDirectory='{ROOT}';$s.IconLocation='{icon_loc}';$s.WindowStyle=7;"
           "$s.Description='Caliope: roleplay and tabletop stories on this PC';$s.Save();")
    skip = "if(-not (Test-Path $p)){" if only_if_missing else "if($true){"
    script = (f"$p=[Environment]::GetFolderPath('Desktop')+'\\Caliope.lnk';{skip}{one}}};"
              f"$p=[Environment]::GetFolderPath('Programs')+'\\Caliope.lnk';{skip}{one}}}")
    try:
        return subprocess.call(["powershell", "-NoProfile", "-Command", script],
                               creationflags=0x08000000) == 0  # no extra window
    except OSError:
        return False


def first_run_questions() -> None:
    """Calíope always has its shortcuts (desktop and Start menu); a missing one is made again at every start."""
    create_shortcut(only_if_missing=True)


# ------------------------------------------------------------------ main
# ------------------------------------------------------------------ the app's own window
def _browser_for_window() -> str | None:
    """Edge (on every Windows 10/11), else Chrome or Brave: they can show a page as an app window (no tabs, no address bar)."""
    if os.name != "nt":
        return None
    roots = [os.environ.get(k, "") for k in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")]
    for rel in (r"Microsoft\Edge\Application\msedge.exe", r"Google\Chrome\Application\chrome.exe",
                r"BraveSoftware\Brave-Browser\Application\brave.exe"):
        for root in roots:
            p = Path(root) / rel
            if root and p.is_file():
                return str(p)
    return None


def _native_window(url: str, profile: Path):
    """The real app window (pywebview + WebView2). None when it is not installed or did not start."""
    import importlib.util  # noqa: PLC0415

    if getattr(sys, "frozen", False) or importlib.util.find_spec("webview") is None:
        return None
    profile.mkdir(parents=True, exist_ok=True)
    try:
        win = subprocess.Popen([sys.executable, str(BACKEND / "window.py"), url, str(profile)], cwd=BACKEND)
    except OSError:
        return None
    try:
        win.wait(timeout=4)          # it ended at once: it could not start (exit code 3)
    except subprocess.TimeoutExpired:
        return win                   # still open: that's the app window
    return None


def open_app_window(url: str, profile: Path):
    """Open the app in a window of its own. Returns the window's process, or None (then the normal browser is used)."""
    native = _native_window(url, profile.parent / "webview")
    if native:
        return native
    exe = _browser_for_window()
    if not exe:
        return None
    profile.mkdir(parents=True, exist_ok=True)
    try:
        return subprocess.Popen([exe, f"--app={url}", f"--user-data-dir={profile}", "--window-size=1400,900",
                                 "--no-first-run", "--no-default-browser-check", "--disable-features=Translate"])
    except OSError:
        return None


def minimize_console(hide: bool = False) -> None:
    """Minimize the black window, or hide it completely (while the app's own window is open; it shows again when
    that window closes, and the app's messages are in backend/data/caliope.log)."""
    if os.name == "nt":
        try:
            import ctypes
            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 0 if hide else 6)  # SW_HIDE / SW_MINIMIZE
        except Exception:
            pass


def show_console() -> None:
    if os.name == "nt":
        try:
            import ctypes
            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        except Exception:
            pass


def show_app(settings: dict, url: str = APP_URL):
    """The app's own window when the setting is on (the default), else a browser tab. Returns the window process or None."""
    if settings.get("app_window", True):
        win = open_app_window(url, BACKEND / "data" / "window")
        if win:
            return win
    webbrowser.open(url)
    return None


def wait_window(win) -> bool:
    """Wait until the app window is closed. False when the window handed itself to one already open (then keep running)."""
    started = time.monotonic()
    win.wait()
    return time.monotonic() - started > 5


def main() -> int:
    ap = argparse.ArgumentParser(description="Start Caliope")
    ap.add_argument("--no-browser", action="store_true", help="do not open the browser")
    ap.add_argument("--shortcut", action="store_true", help="create the desktop shortcut and exit")
    args = ap.parse_args()

    if args.shortcut:
        ok = create_shortcut()
        say("Shortcuts created (desktop and Start menu)." if ok else "Could not create the shortcuts (Windows only).")
        return 0 if ok else 1

    say("=== Caliope ===")
    if get_json(APP_URL + "/api/health"):
        say("  The app is already running. Opening it...")
        if not args.no_browser:
            show_app(get_json(APP_URL + "/api/settings") or {})
        return 0

    first_run_questions()
    if not build_interface():
        return 1

    say("  Starting the app...")
    DATA.mkdir(parents=True, exist_ok=True)
    log_path = DATA / "caliope.log"
    if log_path.is_file() and log_path.stat().st_size > 2_000_000:
        log_path.replace(DATA / "caliope.log.1")
    log = open(log_path, "a", encoding="utf-8", errors="replace")  # noqa: SIM115 (open while the app runs)
    log.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
    log.flush()
    server = subprocess.Popen([sys.executable, "run.py"], cwd=BACKEND, stdout=log, stderr=subprocess.STDOUT)
    try:
        if not wait_for(lambda: get_json(APP_URL + "/api/health") or server.poll() is not None, 60) \
                or server.poll() is not None:
            say("  ! The app did not start. The reason (last lines of backend\\data\\caliope.log):\n")
            log.flush()
            say("\n".join(log_path.read_text("utf-8", errors="replace").splitlines()[-25:]))
            server.terminate()
            return 1
        settings = get_json(APP_URL + "/api/settings") or {}
        if settings.get("ai_engine") == "builtin":
            say("  The AI model loads in the background (Models window).")
        say(f"\n  Ready: {APP_URL}")
        win = None if args.no_browser else show_app(settings)
        if win:
            say("  The game opened in its own window. Closing that window stops everything.")
            say("  (The app's messages and errors go to backend\\data\\caliope.log.)\n")
            minimize_console(hide=True)  # only Calíope's window stays on the taskbar
            handed_over = not wait_window(win)
            if handed_over:
                show_console()  # the window joined one already open: this window must stay to stop the app
            else:
                say("  Window closed: stopping...")
                server.terminate()
                try:
                    server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    server.kill()
                return 0
        say("  Keep this window open while you play. Close it (or press Ctrl+C) to stop.\n")
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
