from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from tonevyra_agent.core.errors import TonevyraError
from tonevyra_agent.images.metadata import extract_basic_metadata
from tonevyra_agent.images.preview import create_preview_bytes
from tonevyra_agent.images.raw_preview import extract_largest_embedded_jpeg


def test_arw_embedded_jpeg_creates_preview_and_metadata(tmp_path: Path) -> None:
    source = tmp_path / "sample.ARW"
    jpeg = _jpeg_bytes(size=(1600, 900), color=(96, 122, 148))
    source.write_bytes(b"RAW-HEADER" + jpeg + b"RAW-TRAILER")

    preview = create_preview_bytes(source, max_long_edge=1024)
    metadata = extract_basic_metadata(source)

    assert preview.format == "JPEG"
    assert preview.mode == "RGB"
    assert preview.long_edge == 1024
    assert metadata["file"]["extension"] == ".arw"
    assert metadata["image"]["metadata_source"] == "embedded_jpeg_preview"
    assert metadata["image"]["width"] == 1600


def test_arw_without_embedded_jpeg_fails_clearly(tmp_path: Path) -> None:
    source = tmp_path / "sample.ARW"
    source.write_bytes(b"RAW-WITHOUT-JPEG")

    assert extract_largest_embedded_jpeg(source) is None
    with pytest.raises(TonevyraError):
        create_preview_bytes(source)


def _jpeg_bytes(*, size: tuple[int, int], color: tuple[int, int, int]) -> bytes:
    image = Image.new("RGB", size, color)
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()
