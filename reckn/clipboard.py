"""System clipboard support for Reckn.

Tries xclip, then xsel, then pyperclip. Falls back gracefully if none available.
"""

import subprocess
import shutil
from typing import Optional


def _has_command(name: str) -> bool:
    return shutil.which(name) is not None


def _copy_wl(text: str) -> bool:
    try:
        proc = subprocess.Popen(
            ["wl-copy"],
            stdin=subprocess.PIPE,
        )
        proc.communicate(text.encode("utf-8"), timeout=2)
        return proc.returncode == 0
    except Exception:
        return False


def _paste_wl() -> Optional[str]:
    try:
        result = subprocess.run(
            ["wl-paste", "--no-newline"],
            capture_output=True, timeout=2,
        )
        if result.returncode == 0:
            return result.stdout.decode("utf-8")
    except Exception:
        pass
    return None


def _copy_xclip(text: str) -> bool:
    try:
        proc = subprocess.Popen(
            ["xclip", "-selection", "clipboard"],
            stdin=subprocess.PIPE,
        )
        proc.communicate(text.encode("utf-8"), timeout=2)
        return proc.returncode == 0
    except Exception:
        return False


def _paste_xclip() -> Optional[str]:
    try:
        result = subprocess.run(
            ["xclip", "-selection", "clipboard", "-o"],
            capture_output=True, timeout=2,
        )
        if result.returncode == 0:
            return result.stdout.decode("utf-8")
    except Exception:
        pass
    return None


def _copy_xsel(text: str) -> bool:
    try:
        proc = subprocess.Popen(
            ["xsel", "--clipboard", "--input"],
            stdin=subprocess.PIPE,
        )
        proc.communicate(text.encode("utf-8"), timeout=2)
        return proc.returncode == 0
    except Exception:
        return False


def _paste_xsel() -> Optional[str]:
    try:
        result = subprocess.run(
            ["xsel", "--clipboard", "--output"],
            capture_output=True, timeout=2,
        )
        if result.returncode == 0:
            return result.stdout.decode("utf-8")
    except Exception:
        pass
    return None


def _copy_pyperclip(text: str) -> bool:
    try:
        import pyperclip
        pyperclip.copy(text)
        return True
    except Exception:
        return False


def _paste_pyperclip() -> Optional[str]:
    try:
        import pyperclip
        return pyperclip.paste()
    except Exception:
        return None


# Detect available backend once at import time
_backend: Optional[str] = None

import os as _os
_is_wayland = _os.environ.get("WAYLAND_DISPLAY") or _os.environ.get("XDG_SESSION_TYPE") == "wayland"

if _is_wayland and _has_command("wl-copy"):
    _backend = "wl"
elif _has_command("xclip"):
    _backend = "xclip"
elif _has_command("xsel"):
    _backend = "xsel"
else:
    try:
        import pyperclip
        _backend = "pyperclip"
    except ImportError:
        _backend = None


def is_available() -> bool:
    """Check if clipboard support is available."""
    return _backend is not None


def copy(text: str) -> bool:
    """Copy text to the system clipboard. Returns True on success."""
    if _backend == "wl":
        return _copy_wl(text)
    elif _backend == "xclip":
        return _copy_xclip(text)
    elif _backend == "xsel":
        return _copy_xsel(text)
    elif _backend == "pyperclip":
        return _copy_pyperclip(text)
    return False


def paste() -> Optional[str]:
    """Paste text from the system clipboard. Returns None if unavailable."""
    if _backend == "wl":
        return _paste_wl()
    elif _backend == "xclip":
        return _paste_xclip()
    elif _backend == "xsel":
        return _paste_xsel()
    elif _backend == "pyperclip":
        return _paste_pyperclip()
    return None
