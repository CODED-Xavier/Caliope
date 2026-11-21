"""Calíope's own window (a real app window, not a browser): `python window.py <url> <storage folder>`.

Uses pywebview, which shows the page with Windows' built-in WebView2 (the engine of Edge). Exits with code 3
when pywebview is not installed or cannot start, so the launcher falls back to an Edge app window.
"""
from __future__ import annotations

import sys


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
        webview.create_window("Calíope", url, width=1400, height=900, min_size=(900, 600), text_select=True)
        webview.start(private_mode=False, storage_path=storage)  # keeps your settings between sessions
    except Exception as e:  # no WebView2, or another start problem: the launcher uses Edge instead
        print(f"  ! App window could not start ({e}); using Edge.", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
