"""Image metadata extraction placeholder."""

from pathlib import Path


def extract_basic_metadata(path: Path) -> dict[str, object]:
    raise NotImplementedError(f"Metadata extraction is not implemented yet: {path}")

