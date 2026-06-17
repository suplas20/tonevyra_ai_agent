"""Replaceable local vision model backends."""

from pathlib import Path
from typing import Protocol

from mw_photo_agent.vision.schemas import VisionAnalysisResult


class VisionModelBackend(Protocol):
    def analyze(self, preview_path: Path, metadata: dict[str, object]) -> VisionAnalysisResult:
        ...


class MockVisionBackend:
    def analyze(self, preview_path: Path, metadata: dict[str, object]) -> VisionAnalysisResult:
        return VisionAnalysisResult(
            scene_type="unknown",
            main_subject=None,
            usable=True,
            issues=[],
            edit_intent="neutral_cleanup",
            confidence=0.5,
            risk_flags=["mock_backend"],
        )


class QwenVisionBackend:
    def analyze(self, preview_path: Path, metadata: dict[str, object]) -> VisionAnalysisResult:
        raise NotImplementedError("Qwen backend must be implemented as local-only and offline.")

