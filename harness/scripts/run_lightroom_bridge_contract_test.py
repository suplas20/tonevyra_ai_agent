#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tonevyra_agent.core.config import Settings
from tonevyra_agent.core.enums import ArtifactType, Stage, StageStatus, TaskEventType, TaskStatus
from tonevyra_agent.correction.schemas import CorrectionPlan
from tonevyra_agent.db.database import session_scope
from tonevyra_agent.db.repositories import ImageTaskRepository, StageResultRepository, TaskArtifactRepository, TaskEventRepository
from tonevyra_agent.lightroom.bridge import LightroomBridge
from tonevyra_agent.lightroom.schemas import LightroomApplyRequestPayload, LightroomApplyResultPayload
from tonevyra_agent.storage.artifacts import ArtifactStorage

FIXTURE_DIR = ROOT / "harness" / "fixtures" / "lightroom_plugin"
FIXTURE_IMAGE = ROOT / "harness" / "fixtures" / "images" / "sample_underwater_01.jpg"
RUNTIME_DIR = ROOT / "runtime" / "harness" / "lightroom_t019_contract"
ALLOWED_SETTINGS = {
    "exposure", "contrast", "highlights", "shadows", "whites", "blacks",
    "temp", "tint", "vibrance", "saturation", "texture", "clarity", "dehaze",
    "sharpening", "noise_reduction",
}
BANNED_KEYS = {"selected" + "_count", "selected" + "_photo_detected"}

def fail(msg: str) -> int:
    print(f"FAIL {msg}")
    return 1

def require(obj, path: str):
    cur = obj
    for part in path.split('.'):
        if not isinstance(cur, dict) or part not in cur:
            raise ValueError(f"missing required field: {path}")
        cur = cur[part]
    return cur

def check_no_banned(obj):
    stack = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            for k, v in cur.items():
                if k in BANNED_KEYS:
                    raise ValueError(f"banned selected-photo key present: {k}")
                stack.append(v)
        elif isinstance(cur, list):
            stack.extend(cur)

def validate_request(obj):
    check_no_banned(obj)
    if require(obj, "schema_version") != "t019.lightroom_apply.request.v1":
        raise ValueError("invalid apply request schema_version")
    if require(obj, "request_origin") != "tonevyra_agent":
        raise ValueError("apply request must originate from tonevyra_agent")
    if require(obj, "command") != "APPLY_LIGHTROOM_SETTINGS":
        raise ValueError("invalid apply request command")
    for field in ["request_id", "task_id", "source_path", "created_at", "develop_settings", "safety.non_destructive_required"]:
        require(obj, field)
    if obj["safety"]["non_destructive_required"] is not True:
        raise ValueError("non_destructive_required must be true")
    settings = require(obj, "develop_settings")
    if not isinstance(settings, dict) or not settings:
        raise ValueError("develop_settings must be a non-empty object")
    unsupported = set(settings) - ALLOWED_SETTINGS
    if unsupported:
        raise ValueError(f"unsupported develop setting in request: {sorted(unsupported)}")

def validate_result(obj):
    check_no_banned(obj)
    if require(obj, "schema_version") != "t019.lightroom_apply.result.v1":
        raise ValueError("invalid apply result schema_version")
    if require(obj, "request_origin") != "lightroom_plugin":
        raise ValueError("apply result must originate from lightroom_plugin")
    if require(obj, "command") != "APPLY_LIGHTROOM_SETTINGS":
        raise ValueError("invalid apply result command")
    status = require(obj, "status")
    if status not in {"applied", "partial", "failed"}:
        raise ValueError("status must be applied, partial, or failed")
    for field in ["request_id", "task_id", "source_path", "applied_settings", "skipped_settings", "lightroom_result.worker_running"]:
        require(obj, field)
    if status in {"applied", "partial"}:
        if not require(obj, "lightroom_result.develop_settings_applied"):
            raise ValueError("successful result must set develop_settings_applied=true")
    if status == "applied" and not obj["applied_settings"]:
        raise ValueError("applied status requires non-empty applied_settings")
    if status == "failed":
        for field in ["error.code", "error.message", "error.recoverable"]:
            require(obj, field)

def load(name):
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))

def settings() -> Settings:
    return Settings(
        runtime_dir=RUNTIME_DIR,
        input_dir=RUNTIME_DIR / "input",
        output_dir=RUNTIME_DIR / "output",
        artifact_dir=RUNTIME_DIR / "artifacts",
        preview_dir=RUNTIME_DIR / "previews",
        bridge_dir=RUNTIME_DIR / "bridge",
        log_dir=RUNTIME_DIR / "logs",
        models_dir=ROOT / "models",
        lightroom_backend="lightroom",
        vision_backend="mock",
    )

def reset_runtime(config: Settings) -> None:
    runtime_dir = config.project_path(config.runtime_dir)
    if runtime_dir.exists():
        shutil.rmtree(runtime_dir)
    for path in config.required_runtime_dirs():
        path.mkdir(parents=True, exist_ok=True)

def cleanup_db(config: Settings) -> None:
    task_repo = ImageTaskRepository()
    with session_scope(config) as session:
        for task in task_repo.list_by_file_name(session, "lightroom_t019_contract.jpg"):
            task_repo.delete(session, task)

def run_python_bridge_roundtrip() -> None:
    config = settings()
    cleanup_db(config)
    reset_runtime(config)

    source_path = config.project_path(config.input_dir) / "lightroom_t019_contract.jpg"
    shutil.copy2(FIXTURE_IMAGE, source_path)

    task_repo = ImageTaskRepository()
    artifact_repo = TaskArtifactRepository()
    event_repo = TaskEventRepository()
    stage_repo = StageResultRepository()
    storage = ArtifactStorage(config)
    bridge = LightroomBridge(settings=config, storage=storage)

    with session_scope(config) as session:
        task = task_repo.create(
            session,
            source_path=source_path,
            file_name=source_path.name,
            file_ext=source_path.suffix.lower(),
            source_hash="t019-contract-source-hash",
            file_size_bytes=source_path.stat().st_size,
            status=TaskStatus.CORRECTION_PLANNED,
            current_stage=Stage.CORRECTION_PLAN,
        )
        plan = CorrectionPlan(
            base_preset="underwater-clean",
            style_target="natural",
            adjustments_json={
                "exposure": 0.25,
                "contrast": 12,
                "temperature_delta": 350,
                "vibrance": 10,
            },
            confidence=0.91,
            requires_review=False,
            clamped=True,
            reason_summary="T-019 bridge contract roundtrip fixture.",
            source={"harness": "lightroom_t019_contract"},
        )
        plan_artifact = storage.save_json(
            session,
            task_id=task.id,
            artifact_type=ArtifactType.CORRECTION_PLAN,
            name="correction_plan.json",
            data=plan.model_dump(mode="json"),
        )
        request = bridge.write_request(session, task=task, correction_plan_artifact=plan_artifact)
        request_payload = LightroomApplyRequestPayload.model_validate(json.loads(request.request_path.read_text(encoding="utf-8")))
        if request_payload.command != "APPLY_LIGHTROOM_SETTINGS":
            raise ValueError("Python bridge wrote the wrong command")
        if request_payload.develop_settings.get("temp") != 350:
            raise ValueError("temperature_delta was not mapped to temp")
        if "temperature_delta" in request_payload.develop_settings:
            raise ValueError("internal planner key leaked into apply request")

        result_payload = LightroomApplyResultPayload(
            request_id=request_payload.request_id,
            task_id=request_payload.task_id,
            source_path=request_payload.source_path,
            status="applied",
            applied_settings=request_payload.develop_settings,
            skipped_settings={},
            lightroom_result={
                "plugin_loaded": True,
                "worker_running": True,
                "source_photo_found": True,
                "source_photo_imported": False,
                "develop_settings_applied": True,
            },
            evidence={"harness": "lightroom_t019_contract"},
        )
        result_path = bridge.apply_result_path(request_payload.request_id)
        result_path.write_text(json.dumps(result_payload.model_dump(mode="json"), indent=2), encoding="utf-8")
        response = bridge.ingest_response(session, task=task, response_path=result_path)
        if not response.success:
            raise ValueError("Lightroom apply result was not ingested as success")

        refreshed = task_repo.get(session, task.id)
        if refreshed is None or refreshed.status != TaskStatus.REVIEW_REQUIRED.value:
            raise ValueError("Lightroom apply success should end in REVIEW_REQUIRED for manual Lightroom review")

        artifact_types = {artifact.artifact_type for artifact in artifact_repo.list_for_task(session, task.id)}
        if ArtifactType.LIGHTROOM_REQUEST.value not in artifact_types:
            raise ValueError("LIGHTROOM_REQUEST artifact was not registered")
        if ArtifactType.LIGHTROOM_RESPONSE.value not in artifact_types:
            raise ValueError("LIGHTROOM_RESPONSE artifact was not registered")

        stages = {(row.stage, row.stage_status) for row in stage_repo.list_for_task(session, task.id)}
        if (Stage.LIGHTROOM.value, StageStatus.SUCCEEDED.value) not in stages:
            raise ValueError("Lightroom SUCCEEDED stage_result was not recorded")

        events = event_repo.list_for_task(session, task.id)
        if not any(
            event.event_type == TaskEventType.LIGHTROOM_REQUESTED.value
            and event.payload_json.get("command") == "APPLY_LIGHTROOM_SETTINGS"
            and event.payload_json.get("develop_settings", {}).get("temp") == 350
            for event in events
        ):
            raise ValueError("apply request event payload_json evidence is missing")
        if not any(
            event.event_type == TaskEventType.LIGHTROOM_RESPONSE_RECEIVED.value
            and event.payload_json.get("applied_settings", {}).get("exposure") == 0.25
            and event.payload_json.get("lightroom_result", {}).get("worker_running") is True
            for event in events
        ):
            raise ValueError("apply result event payload_json evidence is missing")

        task_repo.delete(session, task)

    with session_scope(config) as session:
        if artifact_repo.list_for_task(session, task.id):
            raise ValueError("T-019 contract task cleanup left artifact rows behind")
    shutil.rmtree(config.project_path(config.runtime_dir), ignore_errors=True)

def main():
    try:
        validate_request(load("valid_apply_request.json"))
        validate_result(load("valid_apply_result.json"))
        validate_result(load("failed_apply_result.json"))
        try:
            validate_request(load("invalid_lightroom_origin_flow.json"))
        except Exception:
            pass
        else:
            return fail("invalid selected-photo flow fixture unexpectedly passed")
        run_python_bridge_roundtrip()
    except Exception as exc:
        return fail(str(exc))
    print("OK folder-driven Lightroom bridge contract fixtures and Python DB evidence are valid")
    return 0

if __name__ == "__main__":
    sys.exit(main())
