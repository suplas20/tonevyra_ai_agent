"""Agent startup helpers."""

from pathlib import Path

from mw_photo_agent.core.config import Settings


def ensure_runtime_dirs(settings: Settings) -> None:
    paths: list[Path] = [
        settings.runtime_dir,
        settings.input_dir,
        settings.output_dir / "pass",
        settings.output_dir / "review_required",
        settings.output_dir / "failed",
        settings.artifact_dir,
        settings.preview_dir,
        settings.bridge_dir / "requests",
        settings.bridge_dir / "processing",
        settings.bridge_dir / "responses",
        settings.bridge_dir / "errors",
        settings.log_dir,
        settings.models_dir,
    ]
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)

