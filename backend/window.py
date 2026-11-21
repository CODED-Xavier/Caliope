"""Calíope's own window (a real app window, not a browser): `python window.py <url> <storage folder>`.

Uses pywebview, which shows the page with Windows' built-in WebView2 (the engine of Edge). Exits with code 3
when pywebview is not installed or cannot start, so the launcher falls back to an Edge app window.
"""
from __future__ import annotations

import os
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
    # this process's own window with the title (the loading screen has a similar one: it must not get the icon)
    pid = os.getpid()
    found = []
    proto = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def check(hwnd, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(128)
            user32.GetWindowTextW(hwnd, buf, 128)
            if buf.value == TITLE:
                found.append(hwnd)
                return False
        return True

    for _ in range(50):  # the window may take a moment to get its title
        user32.EnumWindows(proto(check), 0)
        if found:
            break
        time.sleep(0.1)
    else:
        return
    hwnd = found[0]
    IMAGE_ICON, LR_LOADFROMFILE, WM_SETICON = 1, 0x10, 0x80
    for kind, size in ((0, 16), (1, 32)):  # ICON_SMALL, ICON_BIG
        h = user32.LoadImageW(None, str(ICON), IMAGE_ICON, size, size, LR_LOADFROMFILE)
        if h:
            user32.SendMessageW(hwnd, WM_SETICON, kind, h)


class WindowApi:
    """Called by the page through window.pywebview.api (F11). The window is kept in an underscore attribute: pywebview
    hands every public attribute of this object to the page, and walking the whole Window object froze the app."""
    _window = None

    def toggle_fullscreen(self):
        if self._window is not None:
            self._window.toggle_fullscreen()
        return True


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
        api = WindowApi()
        try:  # opens maximized; F11 (sent by the page) switches full screen
            window = webview.create_window(TITLE, url, width=1400, height=900, min_size=(900, 600), text_select=True,
                                           maximized=True, js_api=api)
        except TypeError:  # an older pywebview without "maximized"
            window = webview.create_window(TITLE, url, width=1400, height=900, min_size=(900, 600), text_select=True, js_api=api)
        api._window = window
        window.events.shown += lambda: threading.Thread(target=_set_icon, daemon=True).start()
        webview.start(private_mode=False, storage_path=storage)  # keeps your settings between sessions
    except Exception as e:  # no WebView2, or another start problem: the launcher uses Edge instead
        print(f"  ! App window could not start ({e}); using Edge.", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
