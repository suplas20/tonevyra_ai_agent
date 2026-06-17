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
from tonevyra_agent.core.enums import ArtifactType, ErrorCode, Stage, StageStatus, TaskStatus
from tonevyra_agent.correction.planner import CorrectionPlanner
from tonevyra_agent.db.database import session_scope
from tonevyra_agent.db.repositories import ImageTaskRepository, StageResultRepository, TaskArtifactRepository, TaskEventRepository
from tonevyra_agent.images.metadata import create_metadata_and_preview_artifacts
from tonevyra_agent.lightroom.bridge import LightroomBridge
from tonevyra_agent.lightroom.schemas import LightroomRequestPayload, LightroomResponsePayload
from tonevyra_agent.storage.artifacts import ArtifactStorage
from tonevyra_agent.vision.analyzer import VisionAnalyzer
from tonevyra_agent.vision.model import MockVisionBackend


FIXTURE_IMAGE = PROJECT_ROOT / "harness" / "fixtures" / "images" / "sample_underwater_01.jpg"
VISION_FIXTURE = PROJECT_ROOT / "harness" / "fixtures" / "vision" / "valid_underwater.json"
RUNTIME_DIR = PROJECT_ROOT / "runtime" / "harness" / "lightroom_t007"


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
        for name in ("lightroom_success.jpg", "lightroom_failure.jpg"):
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
        return task.id, plan.artifact, source_path


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


def _fail(message: str) -> int:
    print(f"FAIL {message}")
    return 1


def _assert_absolute_paths(payload: LightroomRequestPayload) -> str | None:
    for field in ("source_path", "export_path", "correction_plan_path"):
        if not Path(getattr(payload, field)).is_absolute():
            return f"{field} is not absolute"
    return None


def main() -> int:
    settings = _settings()
    _cleanup_db(settings)
    _reset_runtime(settings)

    storage = ArtifactStorage(settings=settings)
    task_repo = ImageTaskRepository()
    artifact_repo = TaskArtifactRepository()
    stage_repo = StageResultRepository()
    event_repo = TaskEventRepository()

    success_id, success_plan, _success_source = _create_task_with_plan(
        settings,
        _prepare_source(settings, "lightroom_success.jpg"),
    )
    request_result = _write_request(settings, success_id, success_plan)
    if not request_result.request_path.exists():
        return _fail("request JSON was not written to bridge/requests")
    request_payload = LightroomRequestPayload.model_validate(json.loads(request_result.request_path.read_text(encoding="utf-8")))
    path_error = _assert_absolute_paths(request_payload)
    if path_error:
        return _fail(path_error)
    print("OK request JSON is valid and uses absolute paths")

    success_response_path = process_request(request_result.request_path, bridge_dir=settings.project_path(settings.bridge_dir))
    response_payload = LightroomResponsePayload.model_validate(json.loads(success_response_path.read_text(encoding="utf-8")))
    if response_payload.status != "success":
        return _fail(f"success request returned {response_payload.status}")
    if response_payload.export_path is None or not Path(response_payload.export_path).exists():
        return _fail("fake export file was not created")
    print("OK fake worker created response and fake export")

    success_response = _ingest_response(settings, success_id, success_response_path)
    if not success_response.success or success_response.export_artifact is None:
        return _fail("successful Lightroom response was not ingested as success")
    if not storage.exists(success_response.response_artifact) or not storage.verify_checksum(success_response.response_artifact):
        return _fail("lightroom_response artifact is missing or checksum-invalid")
    if not storage.exists(success_response.export_artifact) or not storage.verify_checksum(success_response.export_artifact):
        return _fail("fake_export artifact is missing or checksum-invalid")
    print("OK response and fake export artifacts registered")

    failure_id, failure_plan, failure_source = _create_task_with_plan(
        settings,
        _prepare_source(settings, "lightroom_failure.jpg"),
    )
    failure_request = _write_request(settings, failure_id, failure_plan)
    failure_source.unlink()
    failure_response_path = process_request(failure_request.request_path, bridge_dir=settings.project_path(settings.bridge_dir))
    failure_payload = LightroomResponsePayload.model_validate(json.loads(failure_response_path.read_text(encoding="utf-8")))
    if failure_payload.status != "failed":
        return _fail("missing source should produce failed Lightroom response")
    if failure_payload.error_code != ErrorCode.LIGHTROOM_EXPORT_FAILED.value:
        return _fail(f"expected LIGHTROOM_EXPORT_FAILED, got {failure_payload.error_code}")
    failure_response = _ingest_response(settings, failure_id, failure_response_path)
    if failure_response.success:
        return _fail("failed Lightroom response was not handled as failure")
    print("OK failure response is handled")

    with session_scope(settings) as session:
        success_task = task_repo.get(session, success_id)
        failure_task = task_repo.get(session, failure_id)
        if success_task is None or failure_task is None:
            return _fail("Lightroom test tasks are missing")
        if success_task.status != TaskStatus.EXPORT_DONE.value:
            return _fail(f"success task should be EXPORT_DONE, got {success_task.status}")
        if success_task.current_stage != Stage.EXPORT.value:
            return _fail(f"success task should be at export stage, got {success_task.current_stage}")
        if failure_task.status != TaskStatus.FAILED.value:
            return _fail(f"failure task should be FAILED, got {failure_task.status}")
        if failure_task.error_code != ErrorCode.LIGHTROOM_EXPORT_FAILED.value:
            return _fail(f"failure task error_code should be LIGHTROOM_EXPORT_FAILED, got {failure_task.error_code}")

        success_artifact_types = {artifact.artifact_type for artifact in artifact_repo.list_for_task(session, success_id)}
        required_types = {
            ArtifactType.LIGHTROOM_REQUEST.value,
            ArtifactType.LIGHTROOM_RESPONSE.value,
            ArtifactType.EXPORTED_IMAGE.value,
        }
        if not required_types.issubset(success_artifact_types):
            return _fail(f"success task missing Lightroom artifacts: {sorted(success_artifact_types)}")
        failure_artifact_types = {artifact.artifact_type for artifact in artifact_repo.list_for_task(session, failure_id)}
        if ArtifactType.LIGHTROOM_RESPONSE.value not in failure_artifact_types:
            return _fail("failure task should register LIGHTROOM_RESPONSE artifact")
        if ArtifactType.EXPORTED_IMAGE.value in failure_artifact_types:
            return _fail("failure task should not register EXPORTED_IMAGE artifact")

        success_stages = {(row.stage, row.stage_status) for row in stage_repo.list_for_task(session, success_id)}
        if (Stage.LIGHTROOM.value, StageStatus.SUCCEEDED.value) not in success_stages:
            return _fail("success task missing Lightroom SUCCEEDED stage_result")
        if (Stage.EXPORT.value, StageStatus.SUCCEEDED.value) not in success_stages:
            return _fail("success task missing export SUCCEEDED stage_result")

        success_events = event_repo.list_for_task(session, success_id)
        if not any(event.payload_json.get("loop_name") == "processing_loop" for event in success_events):
            return _fail("success task missing processing_loop evidence")
        if not any(event.event_type == "EXPORT_DONE" for event in success_events):
            return _fail("success task missing EXPORT_DONE event")

        task_repo.delete(session, success_task)
        task_repo.delete(session, failure_task)
    print("OK Lightroom DB state verified")

    with session_scope(settings) as session:
        for task_id in (success_id, failure_id):
            if artifact_repo.list_for_task(session, task_id):
                return _fail(f"task_artifacts rows were not cleaned up for {task_id}")

    shutil.rmtree(settings.project_path(settings.runtime_dir), ignore_errors=True)
    print("OK fake Lightroom test database cleanup complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
