"""Embedded JPEG preview extraction for RAW containers."""

from __future__ import annotations

from pathlib import Path


RAW_SOURCE_EXTENSIONS = {".cr3", ".cr2", ".nef", ".arw", ".dng"}


def is_raw_source(path: Path) -> bool:
    return path.suffix.lower() in RAW_SOURCE_EXTENSIONS


def extract_largest_embedded_jpeg(source_path: Path) -> bytes | None:
    """Return the largest embedded JPEG byte range from a RAW-like file."""

    data = source_path.read_bytes()
    ranges: list[tuple[int, int]] = []
    start = 0
    while True:
        soi = data.find(b"\xff\xd8", start)
        if soi < 0:
            break
        eoi = data.find(b"\xff\xd9", soi + 2)
        if eoi < 0:
            break
        end = eoi + 2
        ranges.append((soi, end))
        start = end

    if not ranges:
        return None
    soi, end = max(ranges, key=lambda item: item[1] - item[0])
    return data[soi:end]
