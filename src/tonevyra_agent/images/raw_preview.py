"""Embedded JPEG preview extraction for RAW containers."""

from __future__ import annotations

from pathlib import Path


RAW_SOURCE_EXTENSIONS = {".cr3", ".cr2", ".nef", ".arw", ".dng"}


def is_raw_source(path: Path) -> bool:
    return path.suffix.lower() in RAW_SOURCE_EXTENSIONS


def extract_largest_embedded_jpeg(source_path: Path) -> bytes | None:
    """Return the largest *decodable* embedded JPEG byte range from a RAW file.

    A naive scan for the single largest SOI..EOI range is not robust: RAW sensor
    payloads and JPEG entropy data can contain stray ``FFD8``/``FFD9`` markers, so
    the largest byte range is not guaranteed to be a valid image. Instead, collect
    every candidate range and return the largest one that Pillow can actually
    decode, skipping corrupt candidates.
    """

    data = source_path.read_bytes()
    soi_positions: list[int] = []
    start = 0
    while True:
        soi = data.find(b"\xff\xd8", start)
        if soi < 0:
            break
        soi_positions.append(soi)
        start = soi + 2

    # Each embedded JPEG runs from its SOI to the first following EOI marker.
    candidates: list[tuple[int, int]] = []
    for soi in soi_positions:
        eoi = data.find(b"\xff\xd9", soi + 2)
        if eoi > soi:
            candidates.append((soi, eoi + 2))

    if not candidates:
        return None

    # Choose the candidate with the largest *decoded* pixel area. This naturally
    # rejects tiny thumbnails and corrupt ranges that fail to decode.
    best_chunk: bytes | None = None
    best_pixels = -1
    for soi, end in candidates:
        chunk = data[soi:end]
        pixels = _decoded_pixel_count(chunk)
        if pixels > best_pixels:
            best_pixels = pixels
            best_chunk = chunk
    return best_chunk


def _decoded_pixel_count(chunk: bytes) -> int:
    """Return decoded width*height, or -1 if Pillow cannot decode the chunk."""

    try:
        from io import BytesIO

        from PIL import Image

        with Image.open(BytesIO(chunk)) as image:
            image.load()
            width, height = image.size
        return int(width) * int(height)
    except Exception:
        return -1
