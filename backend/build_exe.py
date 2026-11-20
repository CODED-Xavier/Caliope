"""Builds the Windows program:  build-exe.bat  (or: .venv\\Scripts\\python build_exe.py)

Result: the folder Caliope\\ next to Play.bat, with Caliope.exe inside. Copy that whole folder anywhere.
Your saves stay in Caliope\\data, the engine in Caliope\\engine; rebuilding never touches them.
Needs internet the first time (to install PyInstaller) and Node.js (to build the interface).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from launcher import FRONTEND, ROOT, build_interface, say

BACKEND = Path(__file__).resolve().parent
OUT = ROOT / "Caliope"
WORK = ROOT / "build"
SEP = ";" if sys.platform == "win32" else ":"


def ensure_pyinstaller() -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        say("  Installing PyInstaller (first time only)...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "-q", "pyinstaller"])


def copy_missing(src: Path, dst: Path) -> None:
    """Copy folders/files that do not exist yet in dst (never overwrite the user's copies)."""
    if not src.is_dir():
        return
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dst / item.name
        if target.exists() or item.name == "__pycache__":
            continue
        (shutil.copytree if item.is_dir() else shutil.copy2)(item, target)


def main() -> int:
    say("=== Building Caliope.exe ===")
    if not build_interface(FRONTEND) or not (FRONTEND / "dist" / "index.html").is_file():
        say("  ! The interface could not be built.")
        return 1
    ensure_pyinstaller()
    say("  Packing the program (a few minutes)...")
    import PyInstaller.__main__

    icon = ROOT / "assets" / "icon.ico"
    PyInstaller.__main__.run([
        str(BACKEND / "desktop.py"), "--name", "Caliope", "--onedir", "--console", "--noconfirm", "--clean",
        "--distpath", str(WORK / "dist"), "--workpath", str(WORK / "work"), "--specpath", str(WORK),
        "--paths", str(BACKEND),
        "--add-data", f"{FRONTEND / 'dist'}{SEP}frontend_dist",
        "--add-data", f"{BACKEND / 'app' / 'seed'}{SEP}app/seed",
        "--collect-submodules", "app", "--collect-submodules", "uvicorn",
        "--collect-all", "pypdfium2", "--hidden-import", "pytesseract", "--hidden-import", "tkinter.filedialog",
        *(["--icon", str(icon)] if icon.is_file() else []),
    ])
    built = WORK / "dist" / "Caliope"
    if not (built / ("Caliope.exe" if sys.platform == "win32" else "Caliope")).exists():
        say("  ! PyInstaller did not produce the program.")
        return 1
    # Replace only the program files; keep data/, engine/ and skills/ that already live in the output folder.
    OUT.mkdir(exist_ok=True)
    for item in built.iterdir():
        target = OUT / item.name
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
        shutil.move(str(item), str(target))
    copy_missing(BACKEND / "skills", OUT / "skills")
    old = ROOT / "LocalRPG"  # the program's folder before it was renamed Calíope (v2.0)
    for part in ("data", "engine"):
        if (old / part).is_dir() and not (OUT / part).exists():
            say(f"  Copying {part} from the old LocalRPG folder (you can delete that folder afterwards)...")
            shutil.copytree(old / part, OUT / part, ignore=shutil.ignore_patterns("*.db-wal", "*.db-shm", "engine.pid"))
    if (ROOT / "engine").is_dir() and not (OUT / "engine").exists():
        shutil.copytree(ROOT / "engine", OUT / "engine")
    if not (OUT / "data").exists() and (BACKEND / "data").is_dir():
        say("  Copying your saves (backend\\data) into the program folder...")
        shutil.copytree(BACKEND / "data", OUT / "data", ignore=shutil.ignore_patterns("*.db-wal", "*.db-shm", "engine.pid"))
    say(f"\n  Done: {OUT / 'Caliope.exe'}")
    say("  The program keeps its own saves in Caliope\\data (copied from Play.bat's saves the first time).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
