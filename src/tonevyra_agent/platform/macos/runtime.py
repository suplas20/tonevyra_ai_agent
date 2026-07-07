"""macOS Apple Silicon runtime scaffold for T-031."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from tonevyra_agent.platform.contracts import FolderAccessResult


class MacOSRuntime:
    name = "macos"

    def open_path(self, path: Path) -> None:
        subprocess.Popen(["open", str(path)])

    def check_folder_access(self, path: Path, *, write: bool = False) -> FolderAccessResult:
        target = path.resolve()
        readable = target.exists() and os.access(target, os.R_OK)
        writable = os.access(target, os.W_OK) if write else False
        error_code = None if readable and (writable or not write) else "MACOS_INPUT_FOLDER_PERMISSION_DENIED"
        return FolderAccessResult(target, readable=readable, writable=writable, error_code=error_code)

    def autostart_status(self) -> dict[str, object]:
        return {
            "supported": False,
            "enabled": False,
            "error": "BLOCKED_MACOS_LIVE_EVIDENCE_MISSING",
        }

