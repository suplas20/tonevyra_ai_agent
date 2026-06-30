"""Per-user single-instance guard for T-030."""

from __future__ import annotations

import ctypes
import getpass
import os
from dataclasses import dataclass
from pathlib import Path

from tonevyra_agent.core.config import Settings, get_settings


ERROR_ALREADY_EXISTS = 183


@dataclass
class SingleInstanceGuard:
    name: str
    settings: Settings | None = None
    acquired: bool = False
    _handle: int | None = None
    _lock_path: Path | None = None

    def acquire(self) -> bool:
        if os.name == "nt":
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.CreateMutexW(None, False, self.name)
            already_exists = kernel32.GetLastError() == ERROR_ALREADY_EXISTS
            self._handle = int(handle)
            self.acquired = bool(handle) and not already_exists
            if already_exists and handle:
                kernel32.CloseHandle(handle)
                self._handle = None
            return self.acquired

        settings = self.settings or get_settings()
        safe_name = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in self.name)
        self._lock_path = settings.project_path(settings.runtime_dir) / f"{safe_name}.lock"
        try:
            fd = os.open(self._lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode("ascii"))
            os.close(fd)
            self.acquired = True
        except FileExistsError:
            self.acquired = False
        return self.acquired

    def release(self) -> None:
        if os.name == "nt" and self._handle:
            ctypes.windll.kernel32.CloseHandle(self._handle)
            self._handle = None
        elif self._lock_path and self._lock_path.exists() and self.acquired:
            self._lock_path.unlink(missing_ok=True)
        self.acquired = False

    def __enter__(self) -> "SingleInstanceGuard":
        self.acquire()
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        self.release()


def per_user_mutex_name(component: str) -> str:
    user = getpass.getuser() or "user"
    safe_user = "".join(char if char.isalnum() else "_" for char in user)
    return f"Local\\TonevyraAI.{component}.{safe_user}"
