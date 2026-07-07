"""Windows platform runtime adapter."""

from __future__ import annotations

import os
from pathlib import Path

from tonevyra_agent.platform.contracts import FolderAccessResult
from tonevyra_agent.windows.startup_registration import StartupRegistration


class WindowsRuntime:
    name = "windows"

    def open_path(self, path: Path) -> None:
        os.startfile(path)  # type: ignore[attr-defined]

    def check_folder_access(self, path: Path, *, write: bool = False) -> FolderAccessResult:
        target = path.resolve()
        readable = target.exists() and os.access(target, os.R_OK)
        writable = os.access(target, os.W_OK) if write else False
        error_code = None if readable and (writable or not write) else "WINDOWS_FOLDER_ACCESS_DENIED"
        return FolderAccessResult(target, readable=readable, writable=writable, error_code=error_code)

    def autostart_status(self):
        return StartupRegistration().status()

