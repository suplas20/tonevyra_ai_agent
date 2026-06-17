"""1024px sRGB JPEG preview generation placeholder."""

from pathlib import Path


def create_preview(source_path: Path, preview_path: Path, max_size: int = 1024) -> Path:
    raise NotImplementedError(f"Preview generation is not implemented yet: {source_path}")

