from __future__ import annotations

from pathlib import Path

from tonevyra_agent.cli import _vision_backend_check
from tonevyra_agent.core.config import Settings


def test_vision_backend_check_accepts_existing_qwen_model_path(tmp_path: Path) -> None:
    model_dir = tmp_path / "models" / "qwen"
    model_dir.mkdir(parents=True)
    settings = Settings(
        vision_backend="qwen",
        models_dir=tmp_path / "models",
        qwen_model_path=model_dir,
    )

    result = _vision_backend_check(settings)

    assert result.ok is True
    assert "local_model" in result.detail


def test_vision_backend_check_rejects_missing_qwen_model_path(tmp_path: Path) -> None:
    settings = Settings(
        vision_backend="qwen",
        models_dir=tmp_path / "models",
        qwen_model_path=tmp_path / "models" / "missing",
    )

    result = _vision_backend_check(settings)

    assert result.ok is False
    assert "missing" in result.detail


def test_vision_backend_check_accepts_t021_module_provider() -> None:
    settings = Settings(vision_backend="module")

    result = _vision_backend_check(settings)

    assert result.ok is True
    assert "local deterministic provider" in result.detail
