"""Calíope's loading screen: a small window with the icon and a progress bar while the app starts.

Started by Play.bat (with pythonw, so no black window) before anything else. Play.bat and launcher.py write their
progress to data/splash.txt, one line: "<percent>;<what is happening>". "done" closes the loading screen (the app's
window is open); "error;<text>" shows the problem with a Close button, since there is no black window to read it in.
Without tkinter (a Python installed without it) this simply ends and the app starts without a loading screen.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
STATUS = BACKEND / "data" / "splash.txt"
LOG = BACKEND / "data" / "caliope.log"
ICON = BACKEND.parent / "assets" / "icon.png"
GIVE_UP = 15 * 60  # seconds: a first setup can take long; past this the loading screen closes by itself

BG, FG, MUTED, ACCENT, TRACK = "#151220", "#f3effa", "#a79fb6", "#b46cf0", "#2a2438"


def read_status() -> tuple[str, int, str]:
    """('progress'|'done'|'error', percent, text)."""
    try:
        line = STATUS.read_text("utf-8", errors="replace").strip().splitlines()[-1]
    except (OSError, IndexError):
        return "progress", 0, ""
    if line.lower() == "done":
        return "done", 100, ""
    head, _, text = line.partition(";")
    if head.lower() == "error":
        return "error", 100, text.replace("\\n", "\n")
    try:
        return "progress", max(0, min(100, int(head))), text
    except ValueError:
        return "progress", 0, line


def main() -> int:
    try:
        import tkinter as tk
    except Exception:
        return 0
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Caliope.Loading")
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

    root = tk.Tk()
    root.title("Calíope · loading")  # not the game window's title: its icon goes to the game window
    root.overrideredirect(True)          # no title bar: a loading card
    root.configure(bg=BG)
    root.attributes("-topmost", True)
    w, h = 440, 250
    root.geometry(f"{w}x{h}+{(root.winfo_screenwidth() - w) // 2}+{(root.winfo_screenheight() - h) // 2}")

    frame = tk.Frame(root, bg=BG, highlightthickness=1, highlightbackground="#352f46")
    frame.pack(fill="both", expand=True)
    try:
        img = tk.PhotoImage(file=str(ICON))
        k = max(1, img.width() // 72)
        img = img.subsample(k, k)
        tk.Label(frame, image=img, bg=BG).pack(pady=(22, 4))
    except Exception:
        img = None
        tk.Label(frame, text="✦", fg=ACCENT, bg=BG, font=("Segoe UI", 32)).pack(pady=(22, 4))
    tk.Label(frame, text="Calíope", fg=FG, bg=BG, font=("Georgia", 20, "bold")).pack()
    step = tk.Label(frame, text="Starting…", fg=MUTED, bg=BG, font=("Segoe UI", 10), wraplength=390, justify="center")
    step.pack(pady=(6, 8))
    bar = tk.Canvas(frame, width=360, height=8, bg=TRACK, highlightthickness=0)
    bar.pack()
    fill = bar.create_rectangle(0, 0, 0, 8, fill=ACCENT, width=0)
    buttons = tk.Frame(frame, bg=BG)

    state = {"shown": 0.0, "started": time.monotonic(), "error": False}

    def close():
        root.destroy()

    def show_error(text: str):
        state["error"] = True
        root.attributes("-topmost", False)
        root.geometry(f"{w}x{h + 120}")
        bar.coords(fill, 0, 0, 360, 8)
        bar.itemconfig(fill, fill="#e0566b")
        step.config(text=(text or "Calíope could not start.")[:900], fg=FG, font=("Segoe UI", 9), justify="left")
        buttons.pack(pady=10)
        if LOG.is_file() and sys.platform == "win32":
            tk.Button(buttons, text="Open the log", command=lambda: os.startfile(str(LOG)), relief="flat",  # noqa: S606
                      bg=TRACK, fg=FG, padx=10).pack(side="left", padx=6)
        tk.Button(buttons, text="Close", command=close, relief="flat", bg=ACCENT, fg="#fff", padx=14).pack(side="left", padx=6)

    def tick():
        if state["error"]:
            return
        kind, percent, text = read_status()
        if kind == "done":
            close()
            return
        if kind == "error":
            show_error(text)
            return
        if text:
            step.config(text=text)
        # glide toward the reported step, and creep a little while a long step runs, so it never looks frozen
        target = max(percent, min(state["shown"] + 0.05, percent + 8))
        state["shown"] += (target - state["shown"]) * 0.15
        bar.coords(fill, 0, 0, 360 * state["shown"] / 100, 8)
        if time.monotonic() - state["started"] > GIVE_UP:
            close()
            return
        root.after(120, tick)

    root.after(50, tick)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
