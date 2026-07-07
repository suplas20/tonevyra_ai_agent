"""Platform runtime contracts for T-031."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class FolderAccessResult:
    path: Path
    readable: bool
    writable: bool
    error_code: str | None = None
    error_message: str | None = None


class PlatformRuntime(Protocol):
    name: str

    def open_path(self, path: Path) -> None:
        ...

    def check_folder_access(self, path: Path, *, write: bool = False) -> FolderAccessResult:
        ...

    def autostart_status(self) -> object:
        ...

