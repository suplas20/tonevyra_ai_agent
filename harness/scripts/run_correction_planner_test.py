from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tonevyra_agent.core.config import Settings
from tonevyra_agent.core.enums import ArtifactType, Stage, StageStatus, TaskStatus
from tonevyra_agent.correction.planner import CorrectionPlanner
from tonevyra_agent.correction.schemas import ADJUSTMENT_RANGES
from tonevyra_agent.db.database import session_scope
from tonevyra_agent.db.repositories import (
    ImageTaskRepository,
    StageResultRepository,
    TaskArtifactRepository,
    TaskEventRepository,
)
from tonevyra_agent.images.metadata import create_metadata_and_preview_artifacts
from tonevyra_agent.storage.artifacts import ArtifactRef, ArtifactStorage
from tonevyra_agent.vision.analyzer import VisionAnalyzer
from tonevyra_agent.vision.model import MockVisionBackend


FIXTURE_IMAGE = PROJECT_ROOT / "harness" / "fixtures" / "images" / "sample_underwater_01.jpg"
VISION_FIXTURES = PROJECT_ROOT / "harness" / "fixtures" / "vision"
CORRECTION_FIXTURES = PROJECT_ROOT / "harness" / "fixtures" / "correction"
RUNTIME_DIR = PROJECT_ROOT / "runtime" / "harness" / "correction_t006"


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
        for name in ("valid_plan.jpg", "low_plan.jpg", "clamped_plan.jpg"):
            for task in task_repo.list_by_file_name(session, name):
                task_repo.delete(session, task)


def _create_source(settings: Settings, name: str) -> Path:
    source_path = settings.project_path(settings.input_dir) / name
    shutil.copy2(FIXTURE_IMAGE, source_path)
    return source_path


def _create_task_with_vision(settings: Settings, source_path: Path, fixture_path: Path):
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
        analyzer = VisionAnalyzer(
            settings=settings,
            backend=MockVisionBackend(fixture_path),
            storage=storage,
        )
        vision = analyzer.analyze(
            session,
            task=task,
            preview_artifact=metadata_preview.preview_artifact.artifact,
            metadata_artifact=metadata_preview.metadata_artifact,
        )
        return task.id, vision.structured_artifact


def _create_task_with_structured_fixture(settings: Settings, source_path: Path, fixture_path: Path):
    task_repo = ImageTaskRepository()
    storage = ArtifactStorage(settings=settings)
    with session_scope(settings) as session:
        task = task_repo.create(
            session,
            source_path=source_path,
            file_name=source_path.name,
            file_ext=source_path.suffix.lower(),
            file_size_bytes=source_path.stat().st_size,
            status=TaskStatus.ANALYSIS_DONE,
            current_stage=Stage.VISION,
        )
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
        artifact = storage.save_json(
            session,
            task_id=task.id,
            artifact_type=ArtifactType.VISION_STRUCTURED,
            name="vision_structured.json",
            data=payload,
        )
        return task.id, artifact


def _run_planner(settings: Settings, *, task_id, vision_artifact: ArtifactRef):
    task_repo = ImageTaskRepository()
    storage = ArtifactStorage(settings=settings)
    planner = CorrectionPlanner(settings=settings, storage=storage)
    with session_scope(settings) as session:
        task = task_repo.get(session, task_id)
        if task is None:
            raise RuntimeError(f"task disappeared before correction planning: {task_id}")
        return planner.plan_from_artifact(session, task=task, vision_artifact=vision_artifact)


def _fail(message: str) -> int:
    print(f"FAIL {message}")
    return 1


def _assert_plan_adjustments_safe(adjustments: dict[str, float]) -> str | None:
    for key, value in adjustments.items():
        if key not in ADJUSTMENT_RANGES:
            return f"unsupported adjustment emitted: {key}"
        minimum, maximum = ADJUSTMENT_RANGES[key]
        if value < minimum or value > maximum:
            return f"adjustment {key}={value} outside range {minimum}..{maximum}"
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

    valid_id, valid_vision = _create_task_with_vision(
        settings,
        _create_source(settings, "valid_plan.jpg"),
        VISION_FIXTURES / "valid_underwater.json",
    )
    valid = _run_planner(settings, task_id=valid_id, vision_artifact=valid_vision)
    if valid.plan.requires_review:
        return _fail("valid correction plan should not require review")
    if valid.plan.clamped:
        return _fail("valid correction plan should not be clamped")
    error = _assert_plan_adjustments_safe(valid.plan.adjustments_json)
    if error:
        return _fail(error)
    if not storage.exists(valid.artifact) or not storage.verify_checksum(valid.artifact):
        return _fail("valid correction_plan artifact missing or checksum-invalid")
    print("OK valid correction plan created")

    low_id, low_vision = _create_task_with_vision(
        settings,
        _create_source(settings, "low_plan.jpg"),
        VISION_FIXTURES / "low_confidence.json",
    )
    low = _run_planner(settings, task_id=low_id, vision_artifact=low_vision)
    if not low.plan.requires_review:
        return _fail("low confidence correction plan should require review")
    error = _assert_plan_adjustments_safe(low.plan.adjustments_json)
    if error:
        return _fail(error)
    print("OK low confidence correction plan requires review")

    clamped_id, clamped_vision = _create_task_with_structured_fixture(
        settings,
        _create_source(settings, "clamped_plan.jpg"),
        CORRECTION_FIXTURES / "clamp_required_analysis.json",
    )
    clamped = _run_planner(settings, task_id=clamped_id, vision_artifact=clamped_vision)
    if not clamped.plan.clamped:
        return _fail("clamp fixture should produce clamped=true")
    if not clamped.plan.requires_review:
        return _fail("clamped correction plan should require review")
    error = _assert_plan_adjustments_safe(clamped.plan.adjustments_json)
    if error:
        return _fail(error)
    if clamped.plan.adjustments_json["temperature_delta"] != 2000.0:
        return _fail("temperature_delta should be clamped to 2000")
    if clamped.plan.adjustments_json["dehaze"] != 35.0:
        return _fail("dehaze should be clamped to 35")
    print("OK clamped correction plan is safe and requires review")

    with session_scope(settings) as session:
        for task_id in (valid_id, low_id, clamped_id):
            task = task_repo.get(session, task_id)
            if task is None:
                return _fail(f"task missing before cleanup: {task_id}")
            if task.status != TaskStatus.CORRECTION_PLANNED.value:
                return _fail(f"task should be CORRECTION_PLANNED, got {task.status}")
            if task.current_stage != Stage.CORRECTION_PLAN.value:
                return _fail(f"task current_stage should be correction_plan, got {task.current_stage}")

            artifact_types = {artifact.artifact_type for artifact in artifact_repo.list_for_task(session, task_id)}
            if ArtifactType.CORRECTION_PLAN.value not in artifact_types:
                return _fail(f"task missing CORRECTION_PLAN artifact: {task_id}")

            stage_status = {(row.stage, row.stage_status) for row in stage_repo.list_for_task(session, task_id)}
            if (Stage.CORRECTION_PLAN.value, StageStatus.SUCCEEDED.value) not in stage_status:
                return _fail(f"task missing correction_plan stage_result: {task_id}")

            events = event_repo.list_for_task(session, task_id)
            if not any(event.payload_json.get("loop_name") == "processing_loop" for event in events):
                return _fail(f"task missing processing_loop evidence: {task_id}")
            task_repo.delete(session, task)
    print("OK correction plan artifacts, stage_results, events, and task statuses verified")

    with session_scope(settings) as session:
        for task_id in (valid_id, low_id, clamped_id):
            if artifact_repo.list_for_task(session, task_id):
                return _fail(f"task_artifacts rows were not cleaned up for {task_id}")

    shutil.rmtree(settings.project_path(settings.runtime_dir), ignore_errors=True)
    print("OK correction planner test database cleanup complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
