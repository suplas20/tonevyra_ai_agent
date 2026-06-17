"""Folder watcher and file stabilization placeholders."""

from pathlib import Path

SUPPORTED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".tif",
    ".tiff",
    ".dng",
    ".arw",
    ".cr2",
    ".cr3",
    ".nef",
    ".orf",
    ".raf",
    ".rw2",
}


def is_supported_photo(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS

