"""What this PC can run: graphics card(s) and their memory, RAM, processor, and the roleplay model that fits best.

On Windows the graphics memory comes from the display driver's registry entry (exact, also above 4 GB, where
the usual WMI number stops). The suggestions are a short hand-picked list of roleplay models that are known to
work well; each comes with the words to type in Models > Find more.
"""
from __future__ import annotations

import ctypes
import os
import platform
import re
import subprocess
import sys

GPU_CLASS = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"


def _windows_gpus() -> list[dict]:
    import winreg  # noqa: PLC0415 (Windows only)

    out = []
    try:
        root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, GPU_CLASS)
    except OSError:
        return out
    for i in range(32):
        try:
            sub = winreg.EnumKey(root, i)
        except OSError:
            break
        if not sub.isdigit():
            continue
        try:
            k = winreg.OpenKey(root, sub)
        except OSError:
            continue
        name, mem = "", 0
        try:
            name = str(winreg.QueryValueEx(k, "DriverDesc")[0])
        except OSError:
            pass
        for value in ("HardwareInformation.qwMemorySize", "HardwareInformation.MemorySize"):
            try:
                raw = winreg.QueryValueEx(k, value)[0]
                mem = int.from_bytes(raw[:8], "little") if isinstance(raw, (bytes, bytearray)) else int(raw)
                if mem:
                    break
            except (OSError, ValueError, TypeError):
                continue
        if name and not re.search(r"basic display|remote|virtual|parsec|mirage", name, re.I):
            out.append({"name": name, "vram_gb": round(mem / 2**30, 1) if mem else 0})
    return out


def _windows_ram_gb() -> float:
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong), ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]

    st = MEMORYSTATUSEX()
    st.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))  # type: ignore[attr-defined]
    return round(st.ullTotalPhys / 2**30, 1)


def _windows_cpu() -> str:
    try:
        import winreg  # noqa: PLC0415

        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
        return str(winreg.QueryValueEx(k, "ProcessorNameString")[0]).strip()
    except OSError:
        return platform.processor()


def _other_ram_gb() -> float:
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            kb = int(re.search(r"MemTotal:\s+(\d+)", f.read()).group(1))
        return round(kb / 2**20, 1)
    except (OSError, AttributeError):
        return 0.0


def _nvidia_smi() -> list[dict]:
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    gpus = []
    for line in out.splitlines():
        if "," in line:
            name, mem = line.rsplit(",", 1)
            gpus.append({"name": name.strip(), "vram_gb": round(int(mem.strip() or 0) / 1024, 1)})
    return gpus


def scan() -> dict:
    """{"gpus": [{"name", "vram_gb"}], "ram_gb", "cpu", "os"} (fields are empty when they can't be read)."""
    info = {"gpus": [], "ram_gb": 0.0, "cpu": "", "os": f"{platform.system()} {platform.release()}"}
    try:
        if sys.platform == "win32":
            info["gpus"] = _windows_gpus()
            info["ram_gb"] = _windows_ram_gb()
            info["cpu"] = _windows_cpu()
        else:
            info["gpus"] = _nvidia_smi()
            info["ram_gb"] = _other_ram_gb()
            info["cpu"] = platform.processor() or os.uname().machine
    except Exception:  # a scan problem never breaks the app; the tutorial explains how to ask instead
        pass
    return info


# (minimum graphics memory in GB, model, file size to pick, search words, why)
PICKS = [
    (20, "Cydonia 24B (Mistral Small 24B roleplay)", "Q4_K_M", "Cydonia-24B",
     "A big roleplay model: richer writing and better memory of details. Needs a 20+ GB card."),
    (12, "Mag-Mell 12B (MN-12B-Mag-Mell-R1)", "Q6_K (16 GB) or Q4_K_M (12 GB)", "Mag-Mell-R1",
     "One of the best 12B roleplay models: creative, good at characters, still fast."),
    (7.5, "Stheno 8B (L3-8B-Stheno-v3.2)", "Q4_K_M", "Stheno-v3.2",
     "The recommended choice for 8 GB cards: great roleplay quality and quick replies."),
    (5.5, "Stheno 8B (L3-8B-Stheno-v3.2)", "Q3_K_M", "Stheno-v3.2",
     "The smaller file of the same model fits 6 GB; a bit less precise, still good."),
    (3.5, "Llama 3.2 3B Instruct", "Q6_K", "Llama-3.2-3B-Instruct-GGUF",
     "A small model for 4 GB cards. Fast, but simpler stories than the bigger ones."),
]


def suggest(info: dict) -> dict:
    """The model that fits this PC best, with the file size to pick and what to search."""
    vram = max([g.get("vram_gb") or 0 for g in info.get("gpus") or []] or [0])
    ram = info.get("ram_gb") or 0
    if vram:
        for need, model, size, search, why in PICKS:
            if vram >= need:
                ctx = 8192 if vram < 12 else 12288 if vram < 20 else 16384
                return {"model": model, "file": size, "search": search, "why": why, "context": ctx, "gpu": True}
    if ram >= 16:
        return {"model": "Stheno 8B (L3-8B-Stheno-v3.2)", "file": "Q4_K_M", "search": "Stheno-v3.2", "context": 4096, "gpu": False,
                "why": "No suitable graphics card was found, so it runs on the processor: it works, but replies are slow "
                       "(a few words per second). A graphics card with 8 GB makes a big difference."}
    return {"model": "Llama 3.2 3B Instruct", "file": "Q4_K_M", "search": "Llama-3.2-3B-Instruct-GGUF", "context": 4096, "gpu": False,
            "why": "This PC has little memory for AI models; a small model runs on the processor. Replies will be slow and simple."}
