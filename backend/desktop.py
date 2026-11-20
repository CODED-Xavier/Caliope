"""Entry point of the Windows program (Caliope.exe, made by build-exe.bat).

Runs the app inside this one process, opens it in your browser, and (in LM Studio mode) starts LM Studio's
server like Play.bat does. With the built-in engine the app starts the AI by itself.
Close this window to stop everything.
"""
from __future__ import annotations

import multiprocessing
import sys
import threading
import time
import webbrowser

from app.config import DATA_DIR
from launcher import APP_URL, get_json, minimize_console, open_app_window, prepare_lmstudio, say, wait_for

SERVER = None  # the in-process web server (stopped when the app window closes)

PORT = 8000


def after_start() -> None:
    if not wait_for(lambda: get_json(APP_URL + "/api/health"), 60):
        say("  ! The app did not start. Read the messages above for the reason.")
        return
    settings = get_json(APP_URL + "/api/settings") or {}
    if settings.get("ai_engine") == "builtin":
        say("  Built-in AI engine: the model loads in the background (see Settings > Model).")
    else:
        prepare_lmstudio(settings)
    say(f"\n  Ready: {APP_URL}")
    win = open_app_window(APP_URL, DATA_DIR / "window") if settings.get("app_window", True) else None
    if not win:
        say("  Keep this window open while you play. Close it to stop.\n")
        webbrowser.open(APP_URL)
        return
    say("  The game opened in its own window. Closing that window stops everything.\n")
    minimize_console()
    started = time.monotonic()
    win.wait()
    if time.monotonic() - started > 5 and SERVER is not None:
        SERVER.should_exit = True


def main() -> int:
    multiprocessing.freeze_support()
    say("=== Caliope ===")
    if get_json(APP_URL + "/api/health"):
        say("  The app is already running. Opening it...")
        if not open_app_window(APP_URL, DATA_DIR / "window"):
            webbrowser.open(APP_URL)
        return 0
    import uvicorn

    from app.main import app

    global SERVER
    SERVER = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning"))
    threading.Thread(target=after_start, daemon=True).start()
    SERVER.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
