"""Entry point of the Windows program (LocalRPG.exe, made by build-exe.bat).

Runs the app inside this one process, opens it in your browser, and (in LM Studio mode) starts LM Studio's
server like Play.bat does. With the built-in engine the app starts the AI by itself.
Close this window to stop everything.
"""
from __future__ import annotations

import multiprocessing
import sys
import threading
import webbrowser

from launcher import APP_URL, get_json, prepare_lmstudio, say, wait_for

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
    say("  Keep this window open while you play. Close it to stop.\n")
    webbrowser.open(APP_URL)


def main() -> int:
    multiprocessing.freeze_support()
    say("=== Local RPG ===")
    if get_json(APP_URL + "/api/health"):
        say("  The app is already running. Opening it...")
        webbrowser.open(APP_URL)
        return 0
    import uvicorn

    from app.main import app

    threading.Thread(target=after_start, daemon=True).start()
    uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning")).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
