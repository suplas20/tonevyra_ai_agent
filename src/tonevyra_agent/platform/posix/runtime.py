"""Fallback POSIX runtime adapter."""

from __future__ import annotations

import os
from pathlib import Path

from tonevyra_agent.platform.contracts import FolderAccessResult


class PosixRuntime:
    name = "posix"

    def open_path(self, path: Path) -> None:
        raise RuntimeError(f"open_path is not implemented for this platform: {path}")

    def check_folder_access(self, path: Path, *, write: bool = False) -> FolderAccessResult:
        target = path.resolve()
        readable = target.exists() and os.access(target, os.R_OK)
        writable = os.access(target, os.W_OK) if write else False
        error_code = None if readable and (writable or not write) else "POSIX_FOLDER_ACCESS_DENIED"
        return FolderAccessResult(target, readable=readable, writable=writable, error_code=error_code)

    def autostart_status(self) -> dict[str, object]:
        return {"supported": False, "enabled": False, "error": "UNSUPPORTED_PLATFORM"}

