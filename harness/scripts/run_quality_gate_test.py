from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from harness.fake_lightroom.fake_lightroom_worker import process_request
from tonevyra_agent.core.config import Settings
from tonevyra_agent.core.enums import ArtifactType, ErrorCode, QualityDecision, Stage, StageStatus, TaskStatus
from tonevyra_agent.correction.planner import CorrectionPlanner
from tonevyra_agent.db.database import session_scope
from tonevyra_agent.db.repositories import (
    ImageTaskRepository,
    QualityResultRepository,
    StageResultRepository,
    TaskArtifactRepository,
    TaskEventRepository,
)
from tonevyra_agent.images.metadata import create_metadata_and_preview_artifacts
from tonevyra_agent.lightroom.bridge import LightroomBridge
from tonevyra_agent.quality.analyzer import QualityGate
from tonevyra_agent.storage.artifacts import ArtifactStorage
from tonevyra_agent.vision.analyzer import VisionAnalyzer
from tonevyra_agent.vision.model import MockVisionBackend


FIXTURE_IMAGE = PROJECT_ROOT / "harness" / "fixtures" / "images" / "sample_underwater_01.jpg"
VISION_FIXTURE = PROJECT_ROOT / "harness" / "fixtures" / "vision" / "valid_underwater.json"
RUNTIME_DIR = PROJECT_ROOT / "runtime" / "harness" / "quality_t008"


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
        for name in ("quality_success.jpg", "quality_missing_export.jpg"):
            for task in task_repo.list_by_file_name(session, name):
                task_repo.delete(session, task)


def _prepare_source(settings: Settings, name: str) -> Path:
    source_path = settings.project_path(settings.input_dir) / name
    shutil.copy2(FIXTURE_IMAGE, source_path)
    return source_path


def _create_task_with_plan(settings: Settings, source_path: Path):
    task_repo = ImageTaskRepository()
    storage = ArtifactStorage(settings=settings)
    with session_scope(settings) as session:
        task = task_repo.create(
            session,
            source_path=source_path,
            file_name=source_path.name,
            file_ext=source_path.suffix.lower(),
            file_size_bytes=source_path.stat().st_size,
            status=TaskStatus.QUEUED,
            current_stage=Stage.WATCH,
        )
        metadata_preview = create_metadata_and_preview_artifacts(
            session,
            task=task,
            settings=settings,
            storage=storage,
        )
        vision = VisionAnalyzer(
            settings=settings,
            backend=MockVisionBackend(VISION_FIXTURE),
            storage=storage,
        ).analyze(
            session,
            task=task,
            preview_artifact=metadata_preview.preview_artifact.artifact,
            metadata_artifact=metadata_preview.metadata_artifact,
        )
        plan = CorrectionPlanner(settings=settings, storage=storage).plan_from_artifact(
            session,
            task=task,
            vision_artifact=vision.structured_artifact,
        )
        return task.id, plan.artifact


def _write_request(settings: Settings, task_id, correction_artifact):
    task_repo = ImageTaskRepository()
    bridge = LightroomBridge(settings=settings, storage=ArtifactStorage(settings=settings))
    with session_scope(settings) as session:
        task = task_repo.get(session, task_id)
        if task is None:
            raise RuntimeError(f"task missing before Lightroom request: {task_id}")
        return bridge.write_request(session, task=task, correction_plan_artifact=correction_artifact)


def _ingest_response(settings: Settings, task_id, response_path: Path):
    task_repo = ImageTaskRepository()
    bridge = LightroomBridge(settings=settings, storage=ArtifactStorage(settings=settings))
    with session_scope(settings) as session:
        task = task_repo.get(session, task_id)
        if task is None:
            raise RuntimeError(f"task missing before Lightroom response: {task_id}")
        return bridge.ingest_response(session, task=task, response_path=response_path)


def _run_quality_gate(settings: Settings, task_id, *, export_artifact=None, export_path=None, correction_artifact=None):
    task_repo = ImageTaskRepository()
    gate = QualityGate(settings=settings, storage=ArtifactStorage(settings=settings))
    with session_scope(settings) as session:
        task = task_repo.get(session, task_id)
        if task is None:
            raise RuntimeError(f"task missing before quality gate: {task_id}")
        return gate.evaluate_export(
            session,
            task=task,
            export_path=export_path,
            export_artifact=export_artifact,
            correction_plan_artifact=correction_artifact,
        )


def _create_missing_export_task(settings: Settings, source_path: Path):
    task_repo = ImageTaskRepository()
    with session_scope(settings) as session:
        task = task_repo.create(
            session,
            source_path=source_path,
            file_name=source_path.name,
            file_ext=source_path.suffix.lower(),
            file_size_bytes=source_path.stat().st_size,
            status=TaskStatus.EXPORT_DONE,
            current_stage=Stage.EXPORT,
        )
        return task.id


def _fail(message: str) -> int:
    print(f"FAIL {message}")
    return 1


def main() -> int:
    settings = _settings()
    _cleanup_db(settings)
    _reset_runtime(settings)

    storage = ArtifactStorage(settings=settings)
    task_repo = ImageTaskRepository()
    artifact_repo = TaskArtifactRepository()
    stage_repo = StageResultRepository()
    event_repo = TaskEventRepository()
    quality_repo = QualityResultRepository()

    success_id, success_plan = _create_task_with_plan(
        settings,
        _prepare_source(settings, "quality_success.jpg"),
    )
    request_result = _write_request(settings, success_id, success_plan)
    response_path = process_request(request_result.request_path, bridge_dir=settings.project_path(settings.bridge_dir))
    lightroom_result = _ingest_response(settings, success_id, response_path)
    if not lightroom_result.success or lightroom_result.export_artifact is None:
        return _fail("fake Lightroom did not produce an export for quality gate")

    quality_result = _run_quality_gate(
        settings,
        success_id,
        export_artifact=lightroom_result.export_artifact,
        correction_artifact=success_plan,
    )
    if not quality_result.success or quality_result.artifact is None or quality_result.detail is None:
        return _fail("quality gate did not return a successful result")
    if not storage.exists(quality_result.artifact) or not storage.verify_checksum(quality_result.artifact):
        return _fail("quality_detail artifact is missing or checksum-invalid")
    quality_payload = json.loads(quality_result.artifact.absolute_path.read_text(encoding="utf-8"))
    if quality_payload["decision"] not in {item.value for item in QualityDecision}:
        return _fail(f"invalid quality decision in artifact: {quality_payload['decision']}")
    print("OK quality_detail.json exists and is schema-readable")

    missing_source = _prepare_source(settings, "quality_missing_export.jpg")
    missing_id = _create_missing_export_task(settings, missing_source)
    missing_export_path = settings.project_path(settings.output_dir) / "temp" / "missing_quality_export.jpg"
    missing_result = _run_quality_gate(settings, missing_id, export_path=missing_export_path)
    if missing_result.success:
        return _fail("missing export should not produce a successful quality result")
    if missing_result.error_code != ErrorCode.EXPORT_FILE_MISSING:
        return _fail(f"missing export should use EXPORT_FILE_MISSING, got {missing_result.error_code}")
    print("OK missing export failure path is handled")

    with session_scope(settings) as session:
        success_task = task_repo.get(session, success_id)
        missing_task = task_repo.get(session, missing_id)
        if success_task is None or missing_task is None:
            return _fail("quality gate test tasks are missing")
        if success_task.status not in {item.value for item in QualityDecision}:
            return _fail(f"success task final status is invalid: {success_task.status}")
        if success_task.current_stage != Stage.QUALITY.value:
            return _fail(f"success task current_stage should be quality, got {success_task.current_stage}")
        if success_task.quality_decision != success_task.status:
            return _fail("success task quality_decision should match final status")
        if success_task.overall_score is None:
            return _fail("success task overall_score was not saved")
        if missing_task.status != TaskStatus.FAILED.value:
            return _fail(f"missing export task should be FAILED, got {missing_task.status}")
        if missing_task.error_code != ErrorCode.EXPORT_FILE_MISSING.value:
            return _fail(f"missing export error_code should be EXPORT_FILE_MISSING, got {missing_task.error_code}")

        artifact_types = {artifact.artifact_type for artifact in artifact_repo.list_for_task(session, success_id)}
        if ArtifactType.QUALITY_DETAIL.value not in artifact_types:
            return _fail(f"success task missing QUALITY_DETAIL artifact: {sorted(artifact_types)}")
        quality_rows = quality_repo.list_for_task(session, success_id)
        if len(quality_rows) != 1:
            return _fail(f"expected one quality_results row, got {len(quality_rows)}")
        if quality_rows[0].decision != success_task.status:
            return _fail("quality_results decision should match final task status")

        success_stages = {(row.stage, row.stage_status) for row in stage_repo.list_for_task(session, success_id)}
        if (Stage.QUALITY.value, StageStatus.SUCCEEDED.value) not in success_stages:
            return _fail("success task missing quality SUCCEEDED stage_result")
        missing_stages = {(row.stage, row.stage_status) for row in stage_repo.list_for_task(session, missing_id)}
        if (Stage.QUALITY.value, StageStatus.FAILED.value) not in missing_stages:
            return _fail("missing export task missing quality FAILED stage_result")

        success_events = event_repo.list_for_task(session, success_id)
        if not any(event.payload_json.get("loop_name") == "quality_loop" for event in success_events):
            return _fail("success task missing quality_loop evidence")
        if not any(event.event_type == "QUALITY_CHECK_DONE" for event in success_events):
            return _fail("success task missing QUALITY_CHECK_DONE event")
        missing_events = event_repo.list_for_task(session, missing_id)
        if not any(event.payload_json.get("loop_name") == "quality_loop" for event in missing_events):
            return _fail("missing export task missing quality_loop evidence")

        task_repo.delete(session, success_task)
        task_repo.delete(session, missing_task)
    print("OK quality DB state verified")

    with session_scope(settings) as session:
        for task_id in (success_id, missing_id):
            if artifact_repo.list_for_task(session, task_id):
                return _fail(f"task_artifacts rows were not cleaned up for {task_id}")

    shutil.rmtree(settings.project_path(settings.runtime_dir), ignore_errors=True)
    print("OK quality gate test database cleanup complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
