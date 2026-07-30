from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from tonevyra_agent.agent.install_repair import requeue_legacy_mock_tasks
from tonevyra_agent.core.config import Settings


def test_legacy_model_repair_is_disabled_for_mock_backend(tmp_path: Path) -> None:
    result = requeue_legacy_mock_tasks(Settings(vision_backend="mock", input_dir=tmp_path))

    assert result.enabled is False
    assert result.requeued_task_ids == []


def test_repair_contract_is_bounded_and_targets_mock_stage() -> None:
    source = Path("src/tonevyra_agent/agent/install_repair.py").read_text(encoding="utf-8")

    assert 'backend != "mock"' in source
    assert "task.retry_count >= max_retry_count" in source
    assert "scanned >= max_tasks" in source
    assert "source_path.is_relative_to(input_root)" in source
    assert "installer_repair_loop" in source
