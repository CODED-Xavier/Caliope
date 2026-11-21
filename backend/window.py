"""Calíope's own window (a real app window, not a browser): `python window.py <url> <storage folder>`.

Uses pywebview, which shows the page with Windows' built-in WebView2 (the engine of Edge). Exits with code 3
when pywebview is not installed or cannot start, so the launcher falls back to an Edge app window.
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path


TITLE = "Calíope"
ICON = Path(__file__).resolve().parent.parent / "assets" / "icon.ico"


def _own_taskbar_entry() -> None:
    """Windows groups windows by program; without this the taskbar shows Python's icon and name."""
    if sys.platform != "win32":
        return
    try:
        import ctypes  # noqa: PLC0415
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Caliope.App")
    except Exception:
        pass


def _set_icon() -> None:
    """Put Calíope's icon on the window (title bar, taskbar and Alt+Tab)."""
    if sys.platform != "win32" or not ICON.is_file():
        return
    import ctypes  # noqa: PLC0415
    from ctypes import wintypes  # noqa: PLC0415

    user32 = ctypes.windll.user32
    user32.FindWindowW.restype = wintypes.HWND
    user32.LoadImageW.restype = wintypes.HANDLE
    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    for _ in range(50):  # the window may take a moment to get its title
        hwnd = user32.FindWindowW(None, TITLE)
        if hwnd:
            break
        time.sleep(0.1)
    else:
        return
    IMAGE_ICON, LR_LOADFROMFILE, WM_SETICON = 1, 0x10, 0x80
    for kind, size in ((0, 16), (1, 32)):  # ICON_SMALL, ICON_BIG
        h = user32.LoadImageW(None, str(ICON), IMAGE_ICON, size, size, LR_LOADFROMFILE)
        if h:
            user32.SendMessageW(hwnd, WM_SETICON, kind, h)


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    storage = sys.argv[2] if len(sys.argv) > 2 else None
    try:
        import webview  # noqa: PLC0415
    except Exception:
        return 3
    try:
        try:
            webview.settings["ALLOW_DOWNLOADS"] = True          # "Save file", exports and backups
            webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
        except Exception:
            pass
        _own_taskbar_entry()
        window = webview.create_window(TITLE, url, width=1400, height=900, min_size=(900, 600), text_select=True)
        window.events.shown += lambda: threading.Thread(target=_set_icon, daemon=True).start()
        webview.start(private_mode=False, storage_path=storage)  # keeps your settings between sessions
    except Exception as e:  # no WebView2, or another start problem: the launcher uses Edge instead
        print(f"  ! App window could not start ({e}); using Edge.", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
