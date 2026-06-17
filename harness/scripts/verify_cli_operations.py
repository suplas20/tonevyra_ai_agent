from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tonevyra_agent.core.config import Settings
from tonevyra_agent.core.enums import TaskStatus
from tonevyra_agent.db.database import session_scope
from tonevyra_agent.db.repositories import FeedbackRecordRepository, ImageTaskRepository

FIXTURE_IMAGE = PROJECT_ROOT / "harness" / "fixtures" / "images" / "sample_underwater_01.jpg"
CLI_RUNTIME_DIR = PROJECT_ROOT / "runtime" / "harness" / "cli_t014"
CLI_FILE_NAME = "cli_process_sample.jpg"


def _settings() -> Settings:
    return Settings(
        runtime_dir=CLI_RUNTIME_DIR,
        input_dir=CLI_RUNTIME_DIR / "input",
        output_dir=CLI_RUNTIME_DIR / "output",
        artifact_dir=CLI_RUNTIME_DIR / "artifacts",
        preview_dir=CLI_RUNTIME_DIR / "previews",
        bridge_dir=CLI_RUNTIME_DIR / "bridge",
        log_dir=CLI_RUNTIME_DIR / "logs",
        models_dir=PROJECT_ROOT / "models",
        vision_backend="mock",
        vision_mock_fixture=PROJECT_ROOT / "harness" / "fixtures" / "vision" / "valid_underwater.json",
        lightroom_backend="fake",
        file_stable_checks=2,
        file_stable_interval_seconds=0.01,
        file_stable_timeout_seconds=5,
        lightroom_response_timeout_seconds=20,
    )


def _env(settings: Settings) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": str(SRC_ROOT),
            "TONEVYRA_RUNTIME_DIR": str(settings.project_path(settings.runtime_dir)),
            "TONEVYRA_INPUT_DIR": str(settings.project_path(settings.input_dir)),
            "TONEVYRA_OUTPUT_DIR": str(settings.project_path(settings.output_dir)),
            "TONEVYRA_ARTIFACT_DIR": str(settings.project_path(settings.artifact_dir)),
            "TONEVYRA_PREVIEW_DIR": str(settings.project_path(settings.preview_dir)),
            "TONEVYRA_BRIDGE_DIR": str(settings.project_path(settings.bridge_dir)),
            "TONEVYRA_LOG_DIR": str(settings.project_path(settings.log_dir)),
            "TONEVYRA_MODELS_DIR": str(settings.project_path(settings.models_dir)),
            "TONEVYRA_VISION_BACKEND": "mock",
            "TONEVYRA_VISION_MOCK_FIXTURE": str(settings.project_path(settings.vision_mock_fixture)),
            "TONEVYRA_LIGHTROOM_BACKEND": "fake",
            "TONEVYRA_FILE_STABLE_CHECKS": "2",
            "TONEVYRA_FILE_STABLE_INTERVAL_SECONDS": "0.01",
            "TONEVYRA_FILE_STABLE_TIMEOUT_SECONDS": "5",
            "TONEVYRA_LIGHTROOM_RESPONSE_TIMEOUT_SECONDS": "20",
            "TONEVYRA_MODEL_OFFLINE": "true",
            "TONEVYRA_WORKER_CONCURRENCY": "1",
        }
    )
    return env


def _reset_runtime(settings: Settings) -> None:
    runtime_dir = settings.project_path(settings.runtime_dir)
    if runtime_dir.exists():
        shutil.rmtree(runtime_dir)
    for path in settings.required_runtime_dirs():
        path.mkdir(parents=True, exist_ok=True)


def _cleanup_db(settings: Settings) -> None:
    task_repo = ImageTaskRepository()
    with session_scope(settings) as session:
        for task in task_repo.list_by_file_name(session, CLI_FILE_NAME):
            task_repo.delete(session, task)


def _copy_fixture(settings: Settings) -> Path:
    target = settings.project_path(settings.input_dir) / CLI_FILE_NAME
    shutil.copy2(FIXTURE_IMAGE, target)
    return target


def _run_cli(settings: Settings, *args: str) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, "-m", "tonevyra_agent.cli", *args]
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        env=_env(settings),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"CLI command failed: {' '.join(args)}\nstdout={result.stdout}\nstderr={result.stderr}"
        )
    return result


def _task_id_from_process_output(output: str) -> str:
    match = re.search(r"task=([0-9a-fA-F-]{36}) status=([A-Z_]+)", output)
    if match is None:
        raise RuntimeError(f"could not parse task id from process output: {output}")
    status = TaskStatus(match.group(2))
    if status not in {TaskStatus.PASS, TaskStatus.REVIEW_REQUIRED, TaskStatus.FAILED}:
        raise RuntimeError(f"process ended in invalid final status: {status.value}")
    return match.group(1)


def _fail(message: str) -> int:
    print(f"FAIL {message}")
    return 1


def main() -> int:
    settings = _settings()
    try:
        _cleanup_db(settings)
        _reset_runtime(settings)
        input_path = _copy_fixture(settings)

        _run_cli(settings, "init")
        _run_cli(settings, "doctor")
        status_result = _run_cli(settings, "status", "--json")
        if '"counts"' not in status_result.stdout:
            return _fail("status --json did not render counts")

        process_result = _run_cli(settings, "process", str(input_path))
        task_id = _task_id_from_process_output(process_result.stdout)
        print(f"OK CLI process finalized task: {task_id}")

        task_result = _run_cli(settings, "task", task_id)
        if "Artifacts:" not in task_result.stdout or "Events:" not in task_result.stdout:
            return _fail("task command did not show artifacts and events")
        print("OK CLI task detail rendered")

        loop_result = _run_cli(settings, "loop-events", task_id)
        if "processing_loop" not in loop_result.stdout or "quality_loop" not in loop_result.stdout:
            return _fail("loop-events command did not show processing and quality loops")
        print("OK CLI loop-events rendered")

        retry_result = _run_cli(settings, "retry", task_id, "--process-now")
        if f"task={task_id}" not in retry_result.stdout:
            return _fail("retry --process-now did not process the expected task")
        print("OK CLI retry reprocessed task")

        feedback_result = _run_cli(settings, "feedback", "reject", task_id, "--reason", "too_blue")
        if "feedback captured" not in feedback_result.stdout:
            return _fail("feedback reject did not capture feedback")

        with session_scope(settings) as session:
            feedback_rows = FeedbackRecordRepository().list_for_task(session, task_id)
            if not feedback_rows:
                return _fail("feedback reject did not create feedback_records row")
        print("OK CLI feedback reject persisted feedback")

        benchmark_result = _run_cli(settings, "benchmark-models", "--sample-set", "harness")
        if "model benchmark artifact" not in benchmark_result.stdout or "default_backend_after=mock" not in benchmark_result.stdout:
            return _fail("benchmark-models did not run bounded benchmark loop safely")
        print("OK CLI benchmark command writes artifact without changing default backend")

        _cleanup_db(settings)
        shutil.rmtree(settings.project_path(settings.runtime_dir), ignore_errors=True)
        print("CLI operations verification complete.")
        return 0
    except Exception as exc:
        return _fail(f"CLI operations verification failed: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
