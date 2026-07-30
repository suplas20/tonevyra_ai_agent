"""Small Win32 user notification adapter."""

from __future__ import annotations

import ctypes
import os


MB_OK = 0x00000000
MB_ICONERROR = 0x00000010
MB_SETFOREGROUND = 0x00010000
MB_TOPMOST = 0x00040000


def show_error_message(title: str, message: str) -> bool:
    if os.name != "nt":
        return False
    try:
        ctypes.windll.user32.MessageBoxW(  # type: ignore[attr-defined]
            None,
            message,
            title,
            MB_OK | MB_ICONERROR | MB_SETFOREGROUND | MB_TOPMOST,
        )
        return True
    except Exception:
        return False
