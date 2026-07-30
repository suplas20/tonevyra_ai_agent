from __future__ import annotations

import json
import sys
from types import SimpleNamespace

from typer.testing import CliRunner

from tonevyra_agent import cli
from tonevyra_agent.core.config import Settings


def test_model_runtime_check_writes_success_evidence(monkeypatch, tmp_path) -> None:
    class FakeCuda:
        @staticmethod
        def is_available() -> bool:
            return True

        @staticmethod
        def get_device_name(_index: int) -> str:
            return "Test GPU"

    class FakeBackend:
        def close(self) -> None:
            pass

    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(__version__="test-torch", cuda=FakeCuda()))
    monkeypatch.setitem(sys.modules, "transformers", SimpleNamespace(__version__="test-transformers"))
    monkeypatch.setattr(
        cli,
        "get_settings",
        lambda: Settings(
            vision_backend="qwen3vl",
            models_dir=tmp_path,
            qwen3_model_path=tmp_path / "Qwen3-VL-4B-Instruct",
        ),
    )
    monkeypatch.setattr("tonevyra_agent.vision.model.create_vision_backend", lambda _settings: FakeBackend())
    evidence = tmp_path / "model-runtime-check.json"

    result = CliRunner().invoke(cli.app, ["model-runtime-check", "--output", str(evidence)])

    assert result.exit_code == 0, result.output
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert payload["status"] == "passed"
    assert payload["model_loaded"] is True
    assert payload["cuda_available"] is True
    assert payload["cuda_device"] == "Test GPU"
