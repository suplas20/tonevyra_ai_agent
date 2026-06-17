from __future__ import annotations

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
from tonevyra_agent.core.enums import ArtifactType, QualityDecision, Stage, StageStatus
from tonevyra_agent.db.database import session_scope
from tonevyra_agent.db.repositories import (
    ImageTaskRepository,
    QualityResultRepository,
    StageResultRepository,
    TaskArtifactRepository,
    TaskEventRepository,
)


FIXTURE_IMAGE = PROJECT_ROOT / "harness" / "fixtures" / "images" / "sample_underwater_01.jpg"
VISION_FIXTURE = PROJECT_ROOT / "harness" / "fixtures" / "vision" / "valid_underwater.json"
RUNTIME_DIR = PROJECT_ROOT / "runtime" / "harness" / "worker_t009"
PIPELINE_FILE_NAME = "worker_pipeline_success.jpg"


def _settings() -> Settings:
    return Settings(
        runtime_dir=RUNTIME_DIR,
        input_dir=RUNTIME_DIR / "input",
        output_dir=RUNTIME_DIR / "output",
        artifact_dir=RUNTIME_DIR / "artifacts",
        preview_dir=RUNTIME_DIR / "previews",
        bridge_dir=RUNTIME_DIR / "bridge",
        log_dir=RUNTIME_DIR / "logs",
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
        for task in task_repo.list_by_file_name(session, PIPELINE_FILE_NAME):
            task_repo.delete(session, task)


def _copy_fixture(settings: Settings) -> Path:
    input_path = settings.project_path(settings.input_dir) / PIPELINE_FILE_NAME
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
    env["TONEVYRA_BRIDGE_DIR"] = str(settings.project_path(settings.bridge_dir))
    return subprocess.Popen(command, cwd=PROJECT_ROOT, env=env)


def _fail(message: str) -> int:
    print(f"FAIL {message}")
    return 1


def main() -> int:
    settings = _settings()
    _cleanup_db(settings)
    _reset_runtime(settings)
    source_path = _copy_fixture(settings)
    print(f"OK fixture copied to {source_path}")

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
        return _fail(f"expected one created task, got {result.scan_result.created_task_ids}")
    if result.worker_result is None or not result.worker_result.processed:
        return _fail("worker did not process one queued task")
    if result.worker_result.final_status is None or result.worker_result.final_status.value not in {item.value for item in QualityDecision}:
        return _fail(f"worker ended in invalid final status: {result.worker_result.final_status}")
    if result.worker_result.final_export_path is None or not result.worker_result.final_export_path.exists():
        return _fail("final export was not moved to decision output folder")
    if "temp" in result.worker_result.final_export_path.parts:
        return _fail(f"final export should not remain in output/temp: {result.worker_result.final_export_path}")
    print(f"OK worker finalized task {result.worker_result.task_id} as {result.worker_result.final_status.value}")

    task_id = result.worker_result.task_id
    task_repo = ImageTaskRepository()
    artifact_repo = TaskArtifactRepository()
    stage_repo = StageResultRepository()
    event_repo = TaskEventRepository()
    quality_repo = QualityResultRepository()

    with session_scope(settings) as session:
        task = task_repo.get(session, task_id)
        if task is None:
            return _fail("worker task is missing before verification")
        if task.status not in {item.value for item in QualityDecision}:
            return _fail(f"task final status is invalid: {task.status}")
        if task.current_stage != Stage.QUALITY.value:
            return _fail(f"task current_stage should be quality, got {task.current_stage}")
        if task.quality_decision != task.status:
            return _fail("task quality_decision should match final status")
        if task.overall_score is None:
            return _fail("task overall_score was not saved")

        artifact_types = {artifact.artifact_type for artifact in artifact_repo.list_for_task(session, task_id)}
        required_artifacts = {
            ArtifactType.EXIF_JSON.value,
            ArtifactType.PREVIEW_JPEG.value,
            ArtifactType.VISION_PROMPT.value,
            ArtifactType.VISION_RAW_RESPONSE.value,
            ArtifactType.VISION_STRUCTURED.value,
            ArtifactType.CORRECTION_PLAN.value,
            ArtifactType.LIGHTROOM_REQUEST.value,
            ArtifactType.LIGHTROOM_RESPONSE.value,
            ArtifactType.EXPORTED_IMAGE.value,
            ArtifactType.QUALITY_DETAIL.value,
        }
        missing_artifacts = required_artifacts - artifact_types
        if missing_artifacts:
            return _fail(f"task missing required artifacts: {sorted(missing_artifacts)}")

        stage_statuses = {(row.stage, row.stage_status) for row in stage_repo.list_for_task(session, task_id)}
        required_stages = {
            (Stage.METADATA.value, StageStatus.SUCCEEDED.value),
            (Stage.PREVIEW.value, StageStatus.SUCCEEDED.value),
            (Stage.VISION.value, StageStatus.SUCCEEDED.value),
            (Stage.CORRECTION_PLAN.value, StageStatus.SUCCEEDED.value),
            (Stage.LIGHTROOM.value, StageStatus.SUCCEEDED.value),
            (Stage.EXPORT.value, StageStatus.SUCCEEDED.value),
            (Stage.QUALITY.value, StageStatus.SUCCEEDED.value),
        }
        missing_stages = required_stages - stage_statuses
        if missing_stages:
            return _fail(f"task missing required stage_results: {sorted(missing_stages)}")

        quality_rows = quality_repo.list_for_task(session, task_id)
        if len(quality_rows) != 1:
            return _fail(f"expected one quality_results row, got {len(quality_rows)}")

        events = event_repo.list_for_task(session, task_id)
        seen_loops = {event.payload_json.get("loop_name") for event in events}
        if "processing_loop" not in seen_loops:
            return _fail("task missing processing_loop event evidence")
        if "quality_loop" not in seen_loops:
            return _fail("task missing quality_loop event evidence")
        if not any(event.event_type == "TASK_FINALIZED" for event in events):
            return _fail("task missing TASK_FINALIZED event")

        task_repo.delete(session, task)
    print("OK worker pipeline DB state verified")

    with session_scope(settings) as session:
        if artifact_repo.list_for_task(session, task_id):
            return _fail(f"task_artifacts rows were not cleaned up for {task_id}")

    shutil.rmtree(settings.project_path(settings.runtime_dir), ignore_errors=True)
    print("OK worker pipeline test database cleanup complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
