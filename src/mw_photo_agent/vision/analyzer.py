"""Vision analysis orchestration."""

from pathlib import Path

from mw_photo_agent.vision.model import MockVisionBackend, VisionModelBackend
from mw_photo_agent.vision.schemas import VisionAnalysisResult


def create_backend(name: str) -> VisionModelBackend:
    if name == "mock":
        return MockVisionBackend()
    if name == "qwen":
        from mw_photo_agent.vision.model import QwenVisionBackend

        return QwenVisionBackend()
    raise ValueError(f"Unsupported vision backend: {name}")


def analyze_preview(
    backend: VisionModelBackend,
    preview_path: Path,
    metadata: dict[str, object],
) -> VisionAnalysisResult:
    return backend.analyze(preview_path, metadata)

