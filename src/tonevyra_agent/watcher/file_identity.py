"""T-030 file identity helpers."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FileIdentity:
    normalized_path: str
    size_bytes: int
    mtime_ns: int
    source_hash: str | None = None


def normalize_path(path: Path) -> str:
    """Normalize paths for Windows-style case-insensitive watcher comparisons."""

    return str(path.resolve(strict=False)).replace("/", "\\").lower()


def calculate_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def identify_file(path: Path, *, include_hash: bool = True) -> FileIdentity:
    stat = path.stat()
    return FileIdentity(
        normalized_path=normalize_path(path),
        size_bytes=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
        source_hash=calculate_sha256(path) if include_hash else None,
    )
