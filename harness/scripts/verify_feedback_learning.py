from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tonevyra_agent.agent.loops import FEEDBACK_LOOP, validate_loop_payload
from tonevyra_agent.core.config import Settings
from tonevyra_agent.core.enums import ArtifactType, FeedbackUserAction, LearningSampleStatus, LearningSampleType, Stage, TaskStatus
from tonevyra_agent.db.database import session_scope
from tonevyra_agent.db.repositories import (
    FeedbackRecordRepository,
    ImageTaskRepository,
    LearningSampleRepository,
    TaskArtifactRepository,
    TaskEventRepository,
)
from tonevyra_agent.learning.feedback import FeedbackCaptureService
from tonevyra_agent.learning.schemas import DevelopSettingsSnapshot, FeedbackCaptureRequest
from tonevyra_agent.storage.artifacts import ArtifactStorage

FIXTURE_IMAGE = PROJECT_ROOT / "harness" / "fixtures" / "images" / "sample_underwater_01.jpg"
FEEDBACK_RUNTIME_DIR = PROJECT_ROOT / "runtime" / "harness" / "feedback_t013"
APPROVED_FILE = "feedback_approved_sample.jpg"
REJECTED_FILE = "feedback_rejected_sample.jpg"


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
        lightroom_backend="fake",
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
        for file_name in (APPROVED_FILE, REJECTED_FILE):
            for task in task_repo.list_by_file_name(session, file_name):
                task_repo.delete(session, task)


def _copy_input(settings: Settings, file_name: str) -> Path:
    path = settings.project_path(settings.input_dir) / file_name
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(FIXTURE_IMAGE, path)
    return path


def _create_final_task(settings: Settings, file_name: str):
    task_repo = ImageTaskRepository()
    input_path = _copy_input(settings, file_name)
    with session_scope(settings) as session:
        task = task_repo.create(
            session,
            source_path=input_path,
            file_name=file_name,
            file_ext=".jpg",
            file_size_bytes=input_path.stat().st_size,
            status=TaskStatus.PASS,
            current_stage=Stage.QUALITY,
            completed_at=datetime.utcnow(),
        )
        task.overall_score = Decimal("91.00")
        task.quality_decision = TaskStatus.PASS.value
        return task.id


def _approved_request() -> FeedbackCaptureRequest:
    return FeedbackCaptureRequest(
        user_action=FeedbackUserAction.MANUAL_EDITED,
        rating=5,
        reason_tags=["too_blue", "too_dark"],
        accepted=True,
        approved_for_learning=True,
        comment="Local harness feedback sample.",
        ai_settings=DevelopSettingsSnapshot(
            source="fake_lightroom_ai_applied",
            settings={
                "temperature_delta": 800,
                "tint": 12,
                "exposure": 0.2,
                "dehaze": 12,
            },
        ),
        final_settings=DevelopSettingsSnapshot(
            source="fake_lightroom_user_reviewed",
            settings={
                "temperature_delta": 1100,
                "tint": 18,
                "exposure": 0.35,
                "dehaze": 8,
            },
        ),
        sample_type=LearningSampleType.PLANNER_CALIBRATION,
    )


def _rejected_request() -> FeedbackCaptureRequest:
    return FeedbackCaptureRequest(
        user_action=FeedbackUserAction.REJECTED,
        rating=2,
        reason_tags=["oversaturated"],
        accepted=False,
        approved_for_learning=False,
        ai_settings=DevelopSettingsSnapshot(source="fake_lightroom_ai_applied", settings={"saturation": 12}),
        final_settings=DevelopSettingsSnapshot(source="fake_lightroom_user_reviewed", settings={"saturation": -4}),
    )


def _capture(settings: Settings, task_id, request: FeedbackCaptureRequest) -> None:
    task_repo = ImageTaskRepository()
    with session_scope(settings) as session:
        task = task_repo.get(session, task_id)
        if task is None:
            raise RuntimeError(f"task does not exist: {task_id}")
        FeedbackCaptureService(settings=settings).capture_feedback(session, task=task, request=request)


def _verify_artifact(storage: ArtifactStorage, row, *, expected_name: str) -> dict:
    if row is None:
        raise RuntimeError(f"missing artifact row for {expected_name}")
    if not row.artifact_path.endswith(expected_name):
        raise RuntimeError(f"artifact row has wrong path for {expected_name}: {row.artifact_path}")
    if not storage.exists(row):
        raise RuntimeError(f"artifact file is missing: {row.artifact_path}")
    if not storage.verify_checksum(row):
        raise RuntimeError(f"artifact checksum mismatch: {row.artifact_path}")
    return storage.load_json(row)


def _verify_feedback_task(settings: Settings, task_id, *, approved: bool) -> None:
    task_repo = ImageTaskRepository()
    feedback_repo = FeedbackRecordRepository()
    learning_repo = LearningSampleRepository()
    artifact_repo = TaskArtifactRepository()
    event_repo = TaskEventRepository()
    storage = ArtifactStorage(settings=settings)

    with session_scope(settings) as session:
        task = task_repo.get(session, task_id)
        if task is None:
            raise RuntimeError(f"feedback task does not exist: {task_id}")
        if task.status != TaskStatus.PASS.value:
            raise RuntimeError(f"feedback capture changed final task status: {task.status}")

        feedback_rows = feedback_repo.list_for_task(session, task_id)
        if len(feedback_rows) != 1:
            raise RuntimeError(f"expected one feedback_records row, got {len(feedback_rows)}")
        feedback = feedback_rows[0]
        if approved and not feedback.accepted:
            raise RuntimeError("approved feedback should be accepted")
        if not approved and feedback.accepted:
            raise RuntimeError("rejected feedback should not be accepted")

        ai_payload = _verify_artifact(
            storage,
            artifact_repo.get_for_task_type_version(session, task_id=task_id, artifact_type=ArtifactType.AI_SETTINGS),
            expected_name="ai_settings.json",
        )
        final_payload = _verify_artifact(
            storage,
            artifact_repo.get_for_task_type_version(session, task_id=task_id, artifact_type=ArtifactType.FINAL_SETTINGS),
            expected_name="final_settings.json",
        )
        delta_payload = _verify_artifact(
            storage,
            artifact_repo.get_for_task_type_version(session, task_id=task_id, artifact_type=ArtifactType.MANUAL_EDIT_DELTA),
            expected_name="manual_edit_delta.json",
        )
        user_feedback_payload = _verify_artifact(
            storage,
            artifact_repo.get_for_task_type_version(session, task_id=task_id, artifact_type=ArtifactType.FEEDBACK_RECORD),
            expected_name="user_feedback.json",
        )
        if not ai_payload.get("settings") or not final_payload.get("settings"):
            raise RuntimeError("settings snapshot artifacts are missing settings payload")
        if not delta_payload.get("changed"):
            raise RuntimeError("manual_edit_delta should report changed settings")
        if user_feedback_payload.get("approved_for_learning") is not approved:
            raise RuntimeError("user_feedback approved_for_learning mismatch")

        samples = learning_repo.list_for_task(session, task_id)
        manifest_row = artifact_repo.get_for_task_type_version(
            session,
            task_id=task_id,
            artifact_type=ArtifactType.TRAINING_SAMPLE_MANIFEST,
        )
        if approved:
            if len(samples) != 1:
                raise RuntimeError(f"approved feedback should create one learning sample, got {len(samples)}")
            sample = samples[0]
            if sample.sample_type != LearningSampleType.PLANNER_CALIBRATION.value:
                raise RuntimeError(f"unexpected learning sample type: {sample.sample_type}")
            if sample.sample_status != LearningSampleStatus.APPROVED.value:
                raise RuntimeError(f"unexpected learning sample status: {sample.sample_status}")
            manifest_payload = _verify_artifact(storage, manifest_row, expected_name="training_sample_manifest.json")
            if manifest_payload.get("feedback_id") != str(feedback.id):
                raise RuntimeError("training sample manifest feedback_id mismatch")
            if sample.dataset_path != manifest_row.artifact_path:
                raise RuntimeError("learning sample dataset_path should point to manifest artifact")
        else:
            if samples:
                raise RuntimeError("unapproved feedback should not create learning_samples rows")
            if manifest_row is not None:
                raise RuntimeError("unapproved feedback should not create training sample manifest")

        feedback_events = [
            event
            for event in event_repo.list_for_task(session, task_id)
            if (event.payload_json or {}).get("loop_name") == FEEDBACK_LOOP
        ]
        if len(feedback_events) != 1:
            raise RuntimeError(f"expected one feedback_loop event, got {len(feedback_events)}")
        validation = validate_loop_payload(feedback_events[0].payload_json, event_type=feedback_events[0].event_type)
        if not validation.ok:
            raise RuntimeError(f"invalid feedback_loop payload: {list(validation.errors)}")


def _print_ok(message: str) -> None:
    print(f"OK {message}")


def _fail(message: str) -> int:
    print(f"FAIL {message}")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Tonevyra AI local feedback and learning sample storage.")
    parser.add_argument("--runtime-dir", type=Path, default=FEEDBACK_RUNTIME_DIR)
    parser.add_argument("--skip-reset", action="store_true")
    args = parser.parse_args()

    try:
        settings = _settings(args.runtime_dir.resolve())
        _cleanup_db(settings)
        if not args.skip_reset:
            _reset_runtime(settings)
        else:
            for path in settings.required_runtime_dirs():
                path.mkdir(parents=True, exist_ok=True)

        approved_task_id = _create_final_task(settings, APPROVED_FILE)
        rejected_task_id = _create_final_task(settings, REJECTED_FILE)
        _capture(settings, approved_task_id, _approved_request())
        _capture(settings, rejected_task_id, _rejected_request())

        _verify_feedback_task(settings, approved_task_id, approved=True)
        _print_ok("approved feedback stored with learning sample manifest")
        _verify_feedback_task(settings, rejected_task_id, approved=False)
        _print_ok("unapproved feedback stored without learning sample")
        print("Feedback-learning verification complete.")
        return 0
    except Exception as exc:
        return _fail(f"Feedback-learning verification failed: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
