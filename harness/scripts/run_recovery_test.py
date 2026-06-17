from __future__ import annotations

import argparse
import json
import sys
import shutil
from pathlib import Path
from uuid import UUID

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tonevyra_agent.agent.recovery import RecoveryManager
from tonevyra_agent.core.config import Settings
from tonevyra_agent.core.enums import ArtifactType, ErrorCode, QualityDecision, Stage, TaskEventType, TaskStatus
from tonevyra_agent.db.database import session_scope
from tonevyra_agent.db.repositories import ImageTaskRepository, TaskArtifactRepository, TaskEventRepository
from tonevyra_agent.lightroom.schemas import LightroomResponsePayload
from tonevyra_agent.storage.artifacts import ArtifactStorage

FIXTURE_IMAGE = PROJECT_ROOT / "harness" / "fixtures" / "images" / "sample_underwater_01.jpg"
VISION_FIXTURE = PROJECT_ROOT / "harness" / "fixtures" / "vision" / "valid_underwater.json"
RECOVERY_RUNTIME_DIR = PROJECT_ROOT / "runtime" / "harness" / "recovery_t011"
ANALYZING_FILE = "recovery_analysis_has_vision.jpg"
LIGHTROOM_FILE = "recovery_lightroom_response.jpg"
MISSING_EXPORT_FILE = "recovery_missing_export.jpg"
TERMINAL_FILE = "recovery_terminal_pass.jpg"


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
        lightroom_response_timeout_seconds=1,
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
        for file_name in (ANALYZING_FILE, LIGHTROOM_FILE, MISSING_EXPORT_FILE, TERMINAL_FILE):
            for task in task_repo.list_by_file_name(session, file_name):
                task_repo.delete(session, task)


def _copy_input(settings: Settings, file_name: str) -> Path:
    path = settings.project_path(settings.input_dir) / file_name
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(FIXTURE_IMAGE, path)
    return path


def _seed_tasks(settings: Settings) -> dict[str, UUID]:
    task_repo = ImageTaskRepository()
    storage = ArtifactStorage(settings=settings)
    seeded: dict[str, UUID] = {}

    with session_scope(settings) as session:
        analysis_input = _copy_input(settings, ANALYZING_FILE)
        analysis_task = task_repo.create(
            session,
            source_path=analysis_input,
            file_name=ANALYZING_FILE,
            file_ext=".jpg",
            file_size_bytes=analysis_input.stat().st_size,
            status=TaskStatus.ANALYZING,
            current_stage=Stage.VISION,
        )
        storage.save_json(
            session,
            task_id=analysis_task.id,
            artifact_type=ArtifactType.VISION_STRUCTURED,
            name="vision_structured.json",
            data=json.loads(VISION_FIXTURE.read_text(encoding="utf-8")),
        )
        seeded["analysis_has_vision"] = analysis_task.id

        lightroom_input = _copy_input(settings, LIGHTROOM_FILE)
        lightroom_task = task_repo.create(
            session,
            source_path=lightroom_input,
            file_name=LIGHTROOM_FILE,
            file_ext=".jpg",
            file_size_bytes=lightroom_input.stat().st_size,
            status=TaskStatus.LIGHTROOM_REQUESTED,
            current_stage=Stage.LIGHTROOM,
        )
        export_path = settings.project_path(settings.output_dir) / "temp" / f"{lightroom_task.id}.jpg"
        export_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(FIXTURE_IMAGE, export_path)
        storage.save_json(
            session,
            task_id=lightroom_task.id,
            artifact_type=ArtifactType.LIGHTROOM_REQUEST,
            name="lightroom_request.json",
            data={
                "schema_version": "1.0",
                "request_id": str(lightroom_task.id),
                "task_id": str(lightroom_task.id),
                "source_path": str(lightroom_input.resolve()),
                "export_path": str(export_path.resolve()),
            },
        )
        response = LightroomResponsePayload(
            request_id=str(lightroom_task.id),
            task_id=str(lightroom_task.id),
            status="success",
            export_path=str(export_path.resolve()),
        )
        response_path = settings.project_path(settings.bridge_dir) / "responses" / f"{lightroom_task.id}.json"
        response_path.write_text(json.dumps(response.model_dump(mode="json"), indent=2, sort_keys=True), encoding="utf-8")
        seeded["lightroom_response_exists"] = lightroom_task.id

        missing_input = _copy_input(settings, MISSING_EXPORT_FILE)
        missing_task = task_repo.create(
            session,
            source_path=missing_input,
            file_name=MISSING_EXPORT_FILE,
            file_ext=".jpg",
            file_size_bytes=missing_input.stat().st_size,
            status=TaskStatus.EXPORT_DONE,
            current_stage=Stage.EXPORT,
        )
        seeded["missing_export"] = missing_task.id

        terminal_input = _copy_input(settings, TERMINAL_FILE)
        terminal_task = task_repo.create(
            session,
            source_path=terminal_input,
            file_name=TERMINAL_FILE,
            file_ext=".jpg",
            file_size_bytes=terminal_input.stat().st_size,
            status=TaskStatus.PASS,
            current_stage=Stage.QUALITY,
        )
        seeded["terminal_pass"] = terminal_task.id

    return seeded


def _fail(message: str) -> int:
    print(f"FAIL {message}")
    return 1


def _print_ok(message: str) -> None:
    print(f"OK {message}")


def _artifact_row(session, task_id: UUID, artifact_type: ArtifactType):
    return TaskArtifactRepository().get_for_task_type_version(session, task_id=task_id, artifact_type=artifact_type)


def _has_recovery_event(session, task_id: UUID) -> bool:
    events = TaskEventRepository().list_for_task(session, task_id)
    return any(
        event.event_type == TaskEventType.RECOVERY_RESUMED.value
        and event.payload_json.get("loop_name") == "recovery_loop"
        for event in events
    )


def _verify_recovery_artifact(storage: ArtifactStorage, row) -> int:
    if row is None:
        return _fail("recovery_decision artifact row is missing")
    if not row.artifact_path.endswith("recovery_decision.json"):
        return _fail(f"recovery artifact has wrong file name: {row.artifact_path}")
    if not storage.exists(row):
        return _fail(f"recovery_decision artifact file is missing: {row.artifact_path}")
    if not storage.verify_checksum(row):
        return _fail(f"recovery_decision checksum mismatch: {row.artifact_path}")
    payload = storage.load_json(row)
    if payload.get("decision") not in {"resume", "fail", "requeue", "skip", "no_action"}:
        return _fail(f"invalid recovery decision: {payload.get('decision')}")
    return 0


def _verify_results(settings: Settings, seeded: dict[str, UUID]) -> int:
    task_repo = ImageTaskRepository()
    artifact_repo = TaskArtifactRepository()
    storage = ArtifactStorage(settings=settings)
    final_statuses = {item.value for item in QualityDecision}

    with session_scope(settings) as session:
        analysis_task = task_repo.get(session, seeded["analysis_has_vision"])
        if analysis_task is None or analysis_task.status != TaskStatus.ANALYSIS_DONE.value:
            return _fail("ANALYZING task did not resume to ANALYSIS_DONE")
        if analysis_task.current_stage != Stage.VISION.value:
            return _fail("ANALYZING task current_stage was not preserved at vision")
        if _verify_recovery_artifact(storage, _artifact_row(session, analysis_task.id, ArtifactType.RECOVERY_DECISION)):
            return 1
        if not _has_recovery_event(session, analysis_task.id):
            return _fail("ANALYZING task did not record recovery_loop event")
        _print_ok("ANALYZING task resumed from persisted vision evidence")

        lightroom_task = task_repo.get(session, seeded["lightroom_response_exists"])
        if lightroom_task is None or lightroom_task.status not in final_statuses:
            return _fail("LIGHTROOM_REQUESTED task did not reach a final quality status")
        required = {
            ArtifactType.RECOVERY_DECISION,
            ArtifactType.LIGHTROOM_RESPONSE,
            ArtifactType.EXPORTED_IMAGE,
            ArtifactType.QUALITY_DETAIL,
        }
        for artifact_type in required:
            row = artifact_repo.get_for_task_type_version(session, task_id=lightroom_task.id, artifact_type=artifact_type)
            if row is None:
                return _fail(f"LIGHTROOM_REQUESTED task missing {artifact_type.value} artifact")
            if not storage.exists(row) or not storage.verify_checksum(row):
                return _fail(f"LIGHTROOM_REQUESTED task invalid artifact: {row.artifact_path}")
        if not _has_recovery_event(session, lightroom_task.id):
            return _fail("LIGHTROOM_REQUESTED task did not record recovery_loop event")
        _print_ok(f"LIGHTROOM_REQUESTED task recovered through quality gate: {lightroom_task.status}")

        missing_task = task_repo.get(session, seeded["missing_export"])
        if missing_task is None or missing_task.status != TaskStatus.FAILED.value:
            return _fail("EXPORT_DONE task with missing export did not fail safely")
        if missing_task.error_code != ErrorCode.EXPORT_FILE_MISSING.value:
            return _fail(f"EXPORT_DONE task used wrong error_code: {missing_task.error_code}")
        if _verify_recovery_artifact(storage, _artifact_row(session, missing_task.id, ArtifactType.RECOVERY_DECISION)):
            return 1
        if not _has_recovery_event(session, missing_task.id):
            return _fail("EXPORT_DONE failure did not record recovery_loop event")
        _print_ok("EXPORT_DONE task failed safely when export evidence was missing")

        terminal_task = task_repo.get(session, seeded["terminal_pass"])
        if terminal_task is None or terminal_task.status != TaskStatus.PASS.value:
            return _fail("terminal PASS task was changed by recovery")
        if _artifact_row(session, terminal_task.id, ArtifactType.RECOVERY_DECISION) is not None:
            return _fail("terminal PASS task should not receive recovery_decision artifact")
        if _has_recovery_event(session, terminal_task.id):
            return _fail("terminal PASS task should not record recovery_loop event")
        _print_ok("terminal PASS task was not resumed automatically")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run T-011 recovery loop harness scenarios.")
    parser.add_argument("--runtime-dir", default=str(RECOVERY_RUNTIME_DIR))
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

    seeded = _seed_tasks(settings)
    result = RecoveryManager(settings=settings).recover_all()
    if result.inspected_count != 3:
        return _fail(f"expected 3 unfinished tasks inspected, got {result.inspected_count}")
    _print_ok(f"recovery inspected unfinished tasks: {result.inspected_count}")

    verification = _verify_results(settings, seeded)
    if verification != 0:
        return verification

    print("Recovery harness verification complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
