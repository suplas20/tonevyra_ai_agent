"""Export quality analyzer placeholder."""

from pathlib import Path

from mw_photo_agent.quality.schemas import QualityResult


def analyze_export(export_path: Path) -> QualityResult:
    raise NotImplementedError(f"Quality analysis is not implemented yet: {export_path}")

