from __future__ import annotations

import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tonevyra_agent.core.config import Settings
from tonevyra_agent.core.enums import ArtifactType, ErrorCode, Stage, StageStatus, TaskStatus
from tonevyra_agent.core.errors import TonevyraError
from tonevyra_agent.db.database import session_scope
from tonevyra_agent.db.repositories import (
    ImageTaskRepository,
    StageResultRepository,
    TaskArtifactRepository,
    TaskEventRepository,
)
from tonevyra_agent.images.metadata import create_metadata_and_preview_artifacts
from tonevyra_agent.storage.artifacts import ArtifactStorage
from tonevyra_agent.vision.analyzer import VisionAnalyzer
from tonevyra_agent.vision.model import MockVisionBackend


FIXTURE_IMAGE = PROJECT_ROOT / "harness" / "fixtures" / "images" / "sample_underwater_01.jpg"
VISION_FIXTURES = PROJECT_ROOT / "harness" / "fixtures" / "vision"
RUNTIME_DIR = PROJECT_ROOT / "runtime" / "harness" / "vision_t005"


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
        vision_mock_fixture=VISION_FIXTURES / "valid_underwater.json",
        vision_review_confidence_threshold=0.7,
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
        for name in ("valid.jpg", "low_confidence.jpg", "invalid_schema.jpg"):
            for task in task_repo.list_by_file_name(session, name):
                task_repo.delete(session, task)


def _prepare_source(settings: Settings, name: str) -> Path:
    source_path = settings.project_path(settings.input_dir) / name
    shutil.copy2(FIXTURE_IMAGE, source_path)
    return source_path


def _create_task_with_metadata_preview(settings: Settings, source_path: Path):
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
        return task.id, metadata_preview.metadata_artifact, metadata_preview.preview_artifact.artifact


def _run_analyzer(settings: Settings, *, task_id, metadata_ref, preview_ref, fixture_name: str):
    task_repo = ImageTaskRepository()
    storage = ArtifactStorage(settings=settings)
    backend = MockVisionBackend(VISION_FIXTURES / fixture_name)
    analyzer = VisionAnalyzer(settings=settings, backend=backend, storage=storage)
    with session_scope(settings) as session:
        task = task_repo.get(session, task_id)
        if task is None:
            raise RuntimeError(f"task disappeared before vision analysis: {task_id}")
        return analyzer.analyze(
            session,
            task=task,
            preview_artifact=preview_ref,
            metadata_artifact=metadata_ref,
        )


def _run_analyzer_expect_error(settings: Settings, *, task_id, metadata_ref, preview_ref, fixture_name: str) -> TonevyraError:
    task_repo = ImageTaskRepository()
    storage = ArtifactStorage(settings=settings)
    backend = MockVisionBackend(VISION_FIXTURES / fixture_name)
    analyzer = VisionAnalyzer(settings=settings, backend=backend, storage=storage)
    with session_scope(settings) as session:
        task = task_repo.get(session, task_id)
        if task is None:
            raise RuntimeError(f"task disappeared before vision analysis: {task_id}")
        try:
            analyzer.analyze(
                session,
                task=task,
                preview_artifact=preview_ref,
                metadata_artifact=metadata_ref,
            )
        except TonevyraError as exc:
            return exc
    raise RuntimeError("expected vision analyzer to raise TonevyraError")


def _fail(message: str) -> int:
    print(f"FAIL {message}")
    return 1


def main() -> int:
    settings = _settings()
    _cleanup_db(settings)
    _reset_runtime(settings)

    artifact_repo = TaskArtifactRepository()
    stage_repo = StageResultRepository()
    event_repo = TaskEventRepository()
    task_repo = ImageTaskRepository()
    storage = ArtifactStorage(settings=settings)

    valid_id, valid_metadata, valid_preview = _create_task_with_metadata_preview(
        settings,
        _prepare_source(settings, "valid.jpg"),
    )
    valid = _run_analyzer(
        settings,
        task_id=valid_id,
        metadata_ref=valid_metadata,
        preview_ref=valid_preview,
        fixture_name="valid_underwater.json",
    )
    if valid.result.requires_review:
        return _fail("valid fixture should not require review")
    if not storage.exists(valid.structured_artifact) or not storage.verify_checksum(valid.structured_artifact):
        return _fail("valid structured artifact is missing or checksum-invalid")
    print("OK valid mock vision fixture passed")

    low_id, low_metadata, low_preview = _create_task_with_metadata_preview(
        settings,
        _prepare_source(settings, "low_confidence.jpg"),
    )
    low = _run_analyzer(
        settings,
        task_id=low_id,
        metadata_ref=low_metadata,
        preview_ref=low_preview,
        fixture_name="low_confidence.json",
    )
    if not low.result.requires_review:
        return _fail("low confidence fixture should require review")
    print("OK low confidence mock vision fixture requires review")

    invalid_id, invalid_metadata, invalid_preview = _create_task_with_metadata_preview(
        settings,
        _prepare_source(settings, "invalid_schema.jpg"),
    )
    exc = _run_analyzer_expect_error(
        settings,
        task_id=invalid_id,
        metadata_ref=invalid_metadata,
        preview_ref=invalid_preview,
        fixture_name="invalid_schema.json",
    )
    if exc.code != ErrorCode.MODEL_OUTPUT_INVALID:
        return _fail(f"expected MODEL_OUTPUT_INVALID, got {exc.code.value}")
    print("OK invalid mock vision fixture failed with MODEL_OUTPUT_INVALID")

    with session_scope(settings) as session:
        valid_task = task_repo.get(session, valid_id)
        low_task = task_repo.get(session, low_id)
        invalid_task = task_repo.get(session, invalid_id)
        if valid_task is None or low_task is None or invalid_task is None:
            return _fail("one or more vision test tasks are missing")
        if valid_task.status != TaskStatus.ANALYSIS_DONE.value:
            return _fail(f"valid task should be ANALYSIS_DONE, got {valid_task.status}")
        if low_task.status != TaskStatus.ANALYSIS_DONE.value:
            return _fail(f"low confidence task should be ANALYSIS_DONE, got {low_task.status}")
        if invalid_task.status != TaskStatus.FAILED.value:
            return _fail(f"invalid task should be FAILED, got {invalid_task.status}")
        if invalid_task.error_code != ErrorCode.MODEL_OUTPUT_INVALID.value:
            return _fail(f"invalid task error_code should be MODEL_OUTPUT_INVALID, got {invalid_task.error_code}")

        valid_artifacts = artifact_repo.list_for_task(session, valid_id)
        valid_artifact_types = {artifact.artifact_type for artifact in valid_artifacts}
        required_vision_artifacts = {
            ArtifactType.VISION_PROMPT.value,
            ArtifactType.VISION_RAW_RESPONSE.value,
            ArtifactType.VISION_STRUCTURED.value,
        }
        if not required_vision_artifacts.issubset(valid_artifact_types):
            return _fail(f"valid task missing vision artifacts: {sorted(valid_artifact_types)}")

        invalid_artifact_types = {artifact.artifact_type for artifact in artifact_repo.list_for_task(session, invalid_id)}
        if ArtifactType.VISION_RAW_RESPONSE.value not in invalid_artifact_types:
            return _fail("invalid task should keep raw response artifact")
        if ArtifactType.VISION_STRUCTURED.value in invalid_artifact_types:
            return _fail("invalid task should not create structured artifact")

        valid_stage_status = {(row.stage, row.stage_status) for row in stage_repo.list_for_task(session, valid_id)}
        if (Stage.VISION.value, StageStatus.SUCCEEDED.value) not in valid_stage_status:
            return _fail("valid task is missing successful vision stage_result")
        invalid_stage_status = {(row.stage, row.stage_status) for row in stage_repo.list_for_task(session, invalid_id)}
        if (Stage.VISION.value, StageStatus.FAILED.value) not in invalid_stage_status:
            return _fail("invalid task is missing failed vision stage_result")

        valid_events = event_repo.list_for_task(session, valid_id)
        if not any(event.payload_json.get("loop_name") == "processing_loop" for event in valid_events):
            return _fail("valid task is missing processing_loop event evidence")

        for task in (valid_task, low_task, invalid_task):
            task_repo.delete(session, task)
    print("OK vision artifacts, stage_results, events, and task statuses verified")

    with session_scope(settings) as session:
        for task_id in (valid_id, low_id, invalid_id):
            if artifact_repo.list_for_task(session, task_id):
                return _fail(f"task_artifacts rows were not cleaned up for {task_id}")

    shutil.rmtree(settings.project_path(settings.runtime_dir), ignore_errors=True)
    print("OK mock vision test database cleanup complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
