from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tonevyra_agent.agent.runner import AgentRunner
from tonevyra_agent.core.config import Settings
from tonevyra_agent.core.enums import QualityDecision
from tonevyra_agent.db.database import session_scope
from tonevyra_agent.db.repositories import ImageTaskRepository

FIXTURE_IMAGE = PROJECT_ROOT / "harness" / "fixtures" / "images" / "sample_underwater_01.jpg"
VISION_FIXTURE = PROJECT_ROOT / "harness" / "fixtures" / "vision" / "valid_underwater.json"
SMOKE_RUNTIME_DIR = PROJECT_ROOT / "runtime" / "harness" / "smoke_t010"
SMOKE_FILE_NAME = "smoke_pipeline_sample.jpg"
SMOKE_MANIFEST_NAME = "smoke_result.json"


def _settings(runtime_dir: Path) -> Settings:
    return Settings(
        runtime_dir=runtime_dir,
        input_dir=runtime_dir / "input",
        output_dir=runtime_dir / "output",
        artifact_dir=runtime_dir / "artifacts",
        preview_dir=runtime_dir / "previews",
        bridge_dir=runtime_dir / "bridge",
        log_dir=runtime_dir / "logs",
        models_dir=PROJECT_ROOT / "models",
        vision_backend="mock",
        vision_mock_fixture=VISION_FIXTURE,
        lightroom_backend="fake",
        vision_review_confidence_threshold=0.7,
        planner_review_confidence_threshold=0.7,
        preview_long_edge=1024,
        file_stable_checks=2,
        file_stable_interval_seconds=0.01,
        file_stable_timeout_seconds=5.0,
        lightroom_response_timeout_seconds=20,
    )


def _reset_runtime(settings: Settings) -> None:
    runtime_dir = settings.project_path(settings.runtime_dir)
    if runtime_dir.exists():
        shutil.rmtree(runtime_dir)
    for path in settings.required_runtime_dirs():
        path.mkdir(parents=True, exist_ok=True)


def _cleanup_db(settings: Settings) -> None:
    task_repo = ImageTaskRepository()
    with session_scope(settings) as session:
        for task in task_repo.list_by_file_name(session, SMOKE_FILE_NAME):
            task_repo.delete(session, task)


def _copy_fixture(settings: Settings) -> Path:
    input_path = settings.project_path(settings.input_dir) / SMOKE_FILE_NAME
    input_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(FIXTURE_IMAGE, input_path)
    return input_path


def _start_fake_lightroom(settings: Settings) -> subprocess.Popen:
    command = [
        sys.executable,
        str(PROJECT_ROOT / "harness" / "fake_lightroom" / "fake_lightroom_worker.py"),
        "--bridge-dir",
        str(settings.project_path(settings.bridge_dir)),
        "--poll-interval",
        "0.1",
    ]
    env = os.environ.copy()
    env.update(
        {
            "TONEVYRA_BRIDGE_DIR": str(settings.project_path(settings.bridge_dir)),
            "TONEVYRA_VISION_BACKEND": "mock",
            "TONEVYRA_LIGHTROOM_BACKEND": "fake",
            "TONEVYRA_MODEL_OFFLINE": "true",
            "TONEVYRA_WORKER_CONCURRENCY": "1",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "HF_HUB_DISABLE_TELEMETRY": "1",
            "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1",
            "HF_HUB_DISABLE_UPDATE_CHECK": "1",
        }
    )
    return subprocess.Popen(command, cwd=PROJECT_ROOT, env=env)


def _write_manifest(settings: Settings, *, task_id: str, final_status: str, final_export_path: Path) -> Path:
    manifest_path = settings.project_path(settings.runtime_dir) / SMOKE_MANIFEST_NAME
    payload = {
        "schema_version": "1.0",
        "ticket": "T-010",
        "runtime_dir": str(settings.project_path(settings.runtime_dir)),
        "task_id": task_id,
        "input_file_name": SMOKE_FILE_NAME,
        "final_status": final_status,
        "final_export_path": str(final_export_path.resolve()),
    }
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return manifest_path


def _fail(message: str) -> int:
    print(f"FAIL {message}")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one-image smoke pipeline using Mock Vision + Fake Lightroom.")
    parser.add_argument("--runtime-dir", default=str(SMOKE_RUNTIME_DIR))
    parser.add_argument("--skip-reset", action="store_true")
    args = parser.parse_args()

    runtime_dir = Path(args.runtime_dir).resolve()
    settings = _settings(runtime_dir)
    _cleanup_db(settings)

    if not args.skip_reset:
        _reset_runtime(settings)
    else:
        for path in settings.required_runtime_dirs():
            path.mkdir(parents=True, exist_ok=True)

    input_path = _copy_fixture(settings)
    print(f"OK fixture copied: {input_path}")

    fake_proc = _start_fake_lightroom(settings)
    try:
        result = AgentRunner(settings=settings).run_once(scan_input=True)
    finally:
        fake_proc.terminate()
        try:
            fake_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            fake_proc.kill()

    if result.scan_result is None:
        return _fail("runner did not scan input")
    if len(result.scan_result.created_task_ids) != 1:
        return _fail(f"expected one queued task, got {result.scan_result.created_task_ids}")
    if result.worker_result is None or not result.worker_result.processed:
        return _fail("worker did not process a queued task")
    if result.worker_result.final_status is None:
        return _fail("worker did not return a final status")
    if result.worker_result.final_status.value not in {item.value for item in QualityDecision}:
        return _fail(f"invalid final status: {result.worker_result.final_status.value}")
    if result.worker_result.final_export_path is None or not result.worker_result.final_export_path.exists():
        return _fail("final export does not exist")
    if "temp" in result.worker_result.final_export_path.parts:
        return _fail(f"final export was not moved out of output/temp: {result.worker_result.final_export_path}")

    manifest_path = _write_manifest(
        settings,
        task_id=str(result.worker_result.task_id),
        final_status=result.worker_result.final_status.value,
        final_export_path=result.worker_result.final_export_path,
    )

    print(f"OK smoke task finalized: {result.worker_result.task_id} -> {result.worker_result.final_status.value}")
    print(f"OK final export moved: {result.worker_result.final_export_path}")
    print(f"OK smoke manifest written: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
