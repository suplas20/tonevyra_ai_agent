from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from tonevyra_agent.core.config import Settings
from tonevyra_agent.inference.lifecycle import InferenceWorkerState, ProcessInferenceWorkerController
from tonevyra_agent.inference.memory_telemetry import _parse_nvidia_rows, process_used_memory_mb


def test_inference_worker_controller_starts_one_child_and_observes_exit(tmp_path: Path) -> None:
    settings = Settings(
        runtime_dir=tmp_path,
        inference_idle_grace_seconds=0.1,
        max_inference_workers=1,
    )
    command = [sys.executable, "-c", "import time; time.sleep(0.15)"]
    controller = ProcessInferenceWorkerController(settings, command_override=command)

    first = controller.ensure_started()
    second = controller.ensure_started()

    assert first.pid == second.pid
    assert controller.snapshot().max_workers == 1
    assert controller.snapshot().started_count == 1
    assert controller.wait_for_unloaded(timeout_seconds=5.0) is True
    assert controller.snapshot().state == InferenceWorkerState.UNLOADED
    assert controller.snapshot().stopped_count == 1


def test_nvidia_rows_are_parsed_for_process_memory() -> None:
    rows = _parse_nvidia_rows("1234, TonevyraAI.exe, 2048\n1234, helper.exe, 16\n9999, other.exe, 32\n")

    assert process_used_memory_mb(rows, 1234) == 2064
    assert process_used_memory_mb(rows, 9999) == 32
    assert process_used_memory_mb(rows, None) == 0


def test_cli_import_does_not_import_vision_model_boundary() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    code = (
        "import json, sys;"
        "import tonevyra_agent.cli;"
        "print(json.dumps({"
        "'vision_model': 'tonevyra_agent.vision.model' in sys.modules,"
        "'vision_analyzer': 'tonevyra_agent.vision.analyzer' in sys.modules"
        "}))"
    )
    result = subprocess.run([sys.executable, "-c", code], text=True, capture_output=True, env=env, check=True)
    payload = json.loads(result.stdout)

    assert payload == {"vision_model": False, "vision_analyzer": False}

