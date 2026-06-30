"""Current-user autostart registration for T-030."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "Tonevyra AI"


@dataclass(frozen=True)
class StartupStatus:
    supported: bool
    enabled: bool
    command: str | None = None
    error: str | None = None


class StartupRegistration:
    """HKCU Run-key abstraction; no admin rights required."""

    def enable(self, executable: Path, args: Sequence[str]) -> StartupStatus:
        if os.name != "nt":
            return StartupStatus(False, False, error="autostart is only supported on Windows")
        import winreg

        command = " ".join([_quote(str(executable.resolve())), *(_quote(str(arg)) for arg in args)])
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command)
        return StartupStatus(True, True, command=command)

    def disable(self) -> StartupStatus:
        if os.name != "nt":
            return StartupStatus(False, False, error="autostart is only supported on Windows")
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, VALUE_NAME)
        except FileNotFoundError:
            pass
        return StartupStatus(True, False)

    def status(self) -> StartupStatus:
        if os.name != "nt":
            return StartupStatus(False, False, error="autostart is only supported on Windows")
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
                command, _kind = winreg.QueryValueEx(key, VALUE_NAME)
            return StartupStatus(True, True, command=str(command))
        except FileNotFoundError:
            return StartupStatus(True, False)


def _quote(value: str) -> str:
    if not value:
        return '""'
    if " " in value or "\t" in value:
        return '"' + value.replace('"', '\\"') + '"'
    return value
