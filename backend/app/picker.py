"""Windows' own folder picker, opened on this PC (the app only runs on this PC, so the dialog appears here)."""
from __future__ import annotations


def pick_folder(title: str = "Pick a folder") -> str:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError as exc:  # Python without Tk
        raise ValueError("The folder picker is not available here. Paste the folder's address instead.") from exc
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)  # above the game window
    try:
        return filedialog.askdirectory(parent=root, title=title, mustexist=True) or ""
    finally:
        root.destroy()
