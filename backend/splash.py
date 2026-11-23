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
ORANGE, TOP, BOTTOM, LINE = "#f0a050", "#221a35", "#100d18", "#3a3150"
TIPS = ("Tuning the lyre…", "Waking the Aedo…", "Dusting off the lorebooks…", "Counting the stars over Asterion…",
        "Sharpening the dice…", "Calling the Muse…")


def _mix(a: str, b: str, t: float) -> str:
    """A colour between a and b (t from 0 to 1)."""
    ca, cb = [int(a[i:i + 2], 16) for i in (1, 3, 5)], [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(ca, cb))


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
    w, h = 500, 300
    root.geometry(f"{w}x{h}+{(root.winfo_screenwidth() - w) // 2}+{(root.winfo_screenheight() - h) // 2}")

    # one canvas draws the whole card: a violet-to-night gradient, a glow, stars, ornamented corners, the bar
    c = tk.Canvas(root, width=w, height=h, bg=BG, highlightthickness=1, highlightbackground=LINE)
    c.pack(fill="both", expand=True)
    for y in range(0, h, 2):
        c.create_rectangle(0, y, w, y + 2, fill=_mix(TOP, BOTTOM, y / h), width=0)
    for r, col in ((150, _mix(TOP, ACCENT, .10)), (110, _mix(TOP, ACCENT, .16)), (70, _mix(TOP, ACCENT, .22))):
        c.create_oval(w / 2 - r, 92 - r * .7, w / 2 + r, 92 + r * .7, fill=col, width=0)  # halo behind the icon
    for x, y, col in ((40, 60, ACCENT), (460, 48, ORANGE), (430, 220, ACCENT), (70, 240, ORANGE), (330, 30, MUTED), (150, 34, MUTED)):
        c.create_oval(x - 1.2, y - 1.2, x + 1.2, y + 1.2, fill=col, width=0)
    for x0, y0, dx, dy in ((10, 10, 1, 1), (w - 10, 10, -1, 1), (10, h - 10, 1, -1), (w - 10, h - 10, -1, -1)):  # corners
        c.create_line(x0, y0 + 30 * dy, x0, y0, x0 + 30 * dx, y0, fill=ACCENT, width=2)
        c.create_line(x0 + 6 * dx, y0 + 30 * dy, x0 + 6 * dx, y0 + 6 * dy, x0 + 30 * dx, y0 + 6 * dy, fill=_mix(ACCENT, BG, .5), width=1)
        c.create_oval(x0 + 9 * dx - 2, y0 + 9 * dy - 2, x0 + 9 * dx + 2, y0 + 9 * dy + 2, fill=ORANGE, width=0)
    try:
        img = tk.PhotoImage(file=str(ICON))
        k = max(1, img.width() // 88)
        img = img.subsample(k, k)
        c.create_image(w / 2, 86, image=img)
    except Exception:
        img = None
        c.create_text(w / 2, 86, text="✦", fill=ACCENT, font=("Segoe UI", 34))
    c.create_text(w / 2, 158, text="Calíope", fill=FG, font=("Georgia", 24, "bold"))
    c.create_line(w / 2 - 80, 180, w / 2 - 10, 180, fill=ACCENT)
    c.create_text(w / 2, 180, text="✦", fill=ORANGE, font=("Segoe UI", 8))
    c.create_line(w / 2 + 10, 180, w / 2 + 80, 180, fill=ORANGE)
    step_id = c.create_text(w / 2, 204, text="Starting…", fill=MUTED, font=("Segoe UI", 10), width=420, justify="center")
    bx, by, bw, bh = 70, 236, 360, 8
    c.create_rectangle(bx, by, bx + bw, by + bh, fill=TRACK, width=0)
    segs = [c.create_rectangle(bx, by, bx, by + bh, fill=_mix(ACCENT, ORANGE, i / 23), width=0) for i in range(24)]
    pct_id = c.create_text(bx + bw, by + 22, text="0%", fill=MUTED, font=("Segoe UI", 9), anchor="e")
    tip_id = c.create_text(bx, by + 22, text=TIPS[0], fill=_mix(MUTED, BG, .3), font=("Segoe UI", 9, "italic"), anchor="w")
    buttons = tk.Frame(root, bg=BG)

    class _Bar:  # the old Label/Canvas calls, kept for the error view
        @staticmethod
        def set(frac: float, colour: str | None = None):
            end = bx + bw * max(0.0, min(1.0, frac))
            for i, seg in enumerate(segs):
                x0 = bx + bw * i / len(segs)
                x1 = min(end, bx + bw * (i + 1) / len(segs))
                c.coords(seg, x0, by, max(x0, x1), by + bh)
                if colour:
                    c.itemconfig(seg, fill=colour)
            c.itemconfig(pct_id, text=f"{round(frac * 100)}%")

    state = {"shown": 0.0, "started": time.monotonic(), "error": False}

    def close():
        root.destroy()

    def show_error(text: str):
        state["error"] = True
        root.attributes("-topmost", False)
        root.geometry(f"{w}x{h + 140}")
        c.config(height=h + 90)
        _Bar.set(1.0, "#e0566b")
        c.itemconfig(tip_id, text="")
        c.coords(step_id, w / 2, by + 60)
        c.itemconfig(step_id, text=(text or "Calíope could not start.")[:900], fill=FG, font=("Segoe UI", 9), anchor="n", justify="left")
        buttons.pack(pady=8)
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
            c.itemconfig(step_id, text=text)
        # glide toward the reported step, and creep a little while a long step runs, so it never looks frozen
        target = max(percent, min(state["shown"] + 0.05, percent + 8))
        state["shown"] += (target - state["shown"]) * 0.15
        _Bar.set(state["shown"] / 100)
        c.itemconfig(tip_id, text=TIPS[int((time.monotonic() - state["started"]) // 4) % len(TIPS)])
        if time.monotonic() - state["started"] > GIVE_UP:
            close()
            return
        root.after(120, tick)

    root.after(50, tick)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
