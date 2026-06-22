"""File-based fake Lightroom bridge for Tonevyra AI."""

from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from tonevyra_agent.core.config import PROJECT_ROOT, Settings, get_settings
from tonevyra_agent.core.enums import ArtifactType, ErrorCode, Stage, StageStatus, TaskEventType, TaskStatus
from tonevyra_agent.core.errors import TonevyraError
from tonevyra_agent.correction.schemas import CorrectionPlan
from tonevyra_agent.db.models import ImageTask
from tonevyra_agent.db.repositories import ImageTaskRepository, StageResultRepository, TaskEventRepository
from tonevyra_agent.lightroom.schemas import (
    LIGHTROOM_APPLY_ALLOWED_SETTINGS,
    LIGHTROOM_COMMAND_PING,
    LIGHTROOM_RESPONSE_FAILED,
    LIGHTROOM_RESPONSE_SUCCESS,
    LightroomApplyRequestPayload,
    LightroomApplyResultPayload,
    LightroomExportRequestPayload,
    LightroomExportResultPayload,
    LightroomRequestPayload,
    LightroomResponsePayload,
)
from tonevyra_agent.storage.artifacts import ArtifactRef, ArtifactStorage


PROCESSING_LOOP_NAME = "processing_loop"


@dataclass(frozen=True)
class LightroomRequestResult:
    payload: Any
    request_path: Path
    request_artifact: ArtifactRef


@dataclass(frozen=True)
class LightroomResponseResult:
    payload: Any
    response_path: Path
    response_artifact: ArtifactRef
    export_artifact: ArtifactRef | None
    success: bool


@dataclass(frozen=True)
class LightroomPingResult:
    payload: LightroomRequestPayload
    request_path: Path
    response_path: Path | None = None
    response_payload: LightroomResponsePayload | None = None


class LightroomBridge:
    """Write Lightroom requests and ingest fake Lightroom responses."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        storage: ArtifactStorage | None = None,
        task_repository: ImageTaskRepository | None = None,
        stage_repository: StageResultRepository | None = None,
        event_repository: TaskEventRepository | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.storage = storage or ArtifactStorage(self.settings)
        self.task_repository = task_repository or ImageTaskRepository()
        self.stage_repository = stage_repository or StageResultRepository()
        self.event_repository = event_repository or TaskEventRepository()

    def write_request(
        self,
        session: Session,
        *,
        task: ImageTask,
        correction_plan_artifact: ArtifactRef,
        export_path: str | Path | None = None,
    ) -> LightroomRequestResult:
        """Write a validated fake-Lightroom request and register it as an artifact."""

        if self.settings.lightroom_backend not in {"fake", "lightroom"}:
            raise TonevyraError(
                code=ErrorCode.LIGHTROOM_REQUEST_FAILED,
                message="Lightroom bridge supports only TONEVYRA_LIGHTROOM_BACKEND=fake or lightroom.",
                failed_stage=Stage.LIGHTROOM.value,
            )
        if self.settings.lightroom_backend == "lightroom":
            return self.write_apply_request(
                session,
                task=task,
                correction_plan_artifact=correction_plan_artifact,
            )

        from_status = task.status
        try:
            correction_payload = self.storage.load_json(correction_plan_artifact)
            correction_plan = CorrectionPlan.model_validate(correction_payload)
            payload = LightroomRequestPayload(
                request_id=str(task.id),
                task_id=str(task.id),
                source_path=str(_absolute_project_path(task.source_path)),
                export_path=str(_default_export_path(self.settings, task) if export_path is None else _absolute_project_path(export_path)),
                correction_plan_path=str(correction_plan_artifact.absolute_path.resolve()),
                adjustments=correction_plan.adjustments_json,
            )
        except Exception as exc:
            self.task_repository.mark_failed(
                session,
                task,
                error_code=ErrorCode.LIGHTROOM_REQUEST_FAILED,
                error_message="Failed to create Lightroom request payload.",
                failed_stage=Stage.LIGHTROOM,
            )
            raise TonevyraError(
                code=ErrorCode.LIGHTROOM_REQUEST_FAILED,
                message="Failed to create Lightroom request payload.",
                failed_stage=Stage.LIGHTROOM.value,
            ) from exc

        request_path = self.request_path(payload.request_id)
        _write_json_atomic(request_path, payload.model_dump(mode="json"))
        request_artifact = self.storage.save_json(
            session,
            task_id=task.id,
            artifact_type=ArtifactType.LIGHTROOM_REQUEST,
            name="lightroom_request.json",
            data=payload.model_dump(mode="json"),
        )

        self.task_repository.update_status(
            session,
            task,
            status=TaskStatus.LIGHTROOM_REQUESTED,
            current_stage=Stage.LIGHTROOM,
        )
        self.event_repository.create(
            session,
            task_id=task.id,
            event_type=TaskEventType.LIGHTROOM_REQUESTED,
            stage=Stage.LIGHTROOM,
            message="Fake Lightroom request JSON was written.",
            payload_json={
                "loop_name": PROCESSING_LOOP_NAME,
                "loop_iteration": 1,
                "event_type": TaskEventType.LIGHTROOM_REQUESTED.value,
                "from_status": from_status,
                "to_status": TaskStatus.LIGHTROOM_REQUESTED.value,
                "reason": "lightroom_request artifact and bridge request saved",
                "request_id": payload.request_id,
                "request_path": _project_relative_or_absolute(request_path),
                "evidence_artifacts": [
                    _artifact_summary(correction_plan_artifact),
                    _artifact_summary(request_artifact),
                ],
            },
        )
        return LightroomRequestResult(payload=payload, request_path=request_path, request_artifact=request_artifact)

    def write_apply_request(
        self,
        session: Session,
        *,
        task: ImageTask,
        correction_plan_artifact: ArtifactRef,
    ) -> LightroomRequestResult:
        """Write a T-019 folder-driven apply request for the real Lightroom plugin."""

        from_status = task.status
        try:
            correction_payload = self.storage.load_json(correction_plan_artifact)
            correction_plan = CorrectionPlan.model_validate(correction_payload)
            develop_settings = _develop_settings_from_plan(correction_plan)
            payload = LightroomApplyRequestPayload(
                request_id=str(task.id),
                task_id=str(task.id),
                source_path=str(_absolute_project_path(task.source_path)),
                correction_plan_id=str(correction_plan_artifact.artifact_id),
                created_at=datetime.utcnow().isoformat(timespec="seconds") + "Z",
                develop_settings=develop_settings,
                safety={
                    "clamped": correction_plan.clamped,
                    "source_hash": task.source_hash,
                    "non_destructive_required": True,
                },
                runtime_context={
                    "input_folder": str(self.settings.project_path(self.settings.input_dir).resolve()),
                    "runtime_dir": str(self.settings.project_path(self.settings.runtime_dir).resolve()),
                },
            )
        except Exception as exc:
            self.task_repository.mark_failed(
                session,
                task,
                error_code=ErrorCode.LIGHTROOM_REQUEST_FAILED,
                error_message="Failed to create Lightroom apply request payload.",
                failed_stage=Stage.LIGHTROOM,
            )
            raise TonevyraError(
                code=ErrorCode.LIGHTROOM_REQUEST_FAILED,
                message="Failed to create Lightroom apply request payload.",
                failed_stage=Stage.LIGHTROOM.value,
            ) from exc

        request_path = self.apply_request_path(payload.request_id)
        _clear_stale_apply_files(self.settings, payload.request_id)
        _write_json_atomic(request_path, payload.model_dump(mode="json"))
        request_artifact = self.storage.save_json(
            session,
            task_id=task.id,
            artifact_type=ArtifactType.LIGHTROOM_REQUEST,
            name="lightroom_apply_request.json",
            data=payload.model_dump(mode="json"),
        )

        self.task_repository.update_status(
            session,
            task,
            status=TaskStatus.LIGHTROOM_REQUESTED,
            current_stage=Stage.LIGHTROOM,
        )
        self.event_repository.create(
            session,
            task_id=task.id,
            event_type=TaskEventType.LIGHTROOM_REQUESTED,
            stage=Stage.LIGHTROOM,
            message="Folder-driven Lightroom apply request JSON was written.",
            payload_json={
                "loop_name": PROCESSING_LOOP_NAME,
                "loop_iteration": 1,
                "event_type": TaskEventType.LIGHTROOM_REQUESTED.value,
                "from_status": from_status,
                "to_status": TaskStatus.LIGHTROOM_REQUESTED.value,
                "reason": "lightroom_apply_request artifact and bridge request saved",
                "request_id": payload.request_id,
                "request_path": _project_relative_or_absolute(request_path),
                "request_origin": payload.request_origin,
                "command": payload.command,
                "operation": payload.operation,
                "develop_settings": payload.develop_settings,
                "evidence_artifacts": [
                    _artifact_summary(correction_plan_artifact),
                    _artifact_summary(request_artifact),
                ],
            },
        )
        return LightroomRequestResult(payload=payload, request_path=request_path, request_artifact=request_artifact)

    def write_ping_request(self, *, request_id: str = "tonevyra-ping") -> LightroomPingResult:
        """Write a lightweight PING request for real Lightroom plugin smoke checks."""

        payload = LightroomRequestPayload(
            request_id=request_id,
            task_id=request_id,
            command=LIGHTROOM_COMMAND_PING,
        )
        request_path = self.request_path(payload.request_id)
        _write_json_atomic(request_path, payload.model_dump(mode="json", exclude_none=True))
        return LightroomPingResult(payload=payload, request_path=request_path)

    def read_ping_response(self, *, request_id: str = "tonevyra-ping", response_path: str | Path | None = None) -> LightroomPingResult:
        """Read and validate a PING response written by Lightroom."""

        path = Path(response_path) if response_path is not None else self.response_path(request_id)
        path = _absolute_project_path(path)
        if not path.exists():
            raise TonevyraError(
                code=ErrorCode.LIGHTROOM_RESPONSE_TIMEOUT,
                message=f"Lightroom PING response file was not found: {path}",
                failed_stage=Stage.LIGHTROOM.value,
            )
        response = LightroomResponsePayload.model_validate(_read_json(path))
        if response.status != LIGHTROOM_RESPONSE_SUCCESS or response.command != LIGHTROOM_COMMAND_PING:
            raise TonevyraError(
                code=ErrorCode.LIGHTROOM_REQUEST_FAILED,
                message="Lightroom PING response was not successful.",
                failed_stage=Stage.LIGHTROOM.value,
            )
        request_payload = LightroomRequestPayload(request_id=request_id, task_id=request_id, command=LIGHTROOM_COMMAND_PING)
        return LightroomPingResult(payload=request_payload, request_path=self.request_path(request_id), response_path=path, response_payload=response)

    def ingest_response(
        self,
        session: Session,
        *,
        task: ImageTask,
        response_path: str | Path | None = None,
    ) -> LightroomResponseResult:
        """Read a Lightroom response, register artifacts, and update task state."""

        if self.settings.lightroom_backend == "lightroom":
            return self.ingest_apply_result(session, task=task, response_path=response_path)

        started_at = datetime.utcnow()
        from_status = task.status
        path = Path(response_path) if response_path is not None else self.response_path(str(task.id))
        path = _absolute_project_path(path)
        if not path.exists():
            self.task_repository.mark_failed(
                session,
                task,
                error_code=ErrorCode.LIGHTROOM_RESPONSE_TIMEOUT,
                error_message=f"Lightroom response file was not found: {path}",
                failed_stage=Stage.LIGHTROOM,
            )
            raise TonevyraError(
                code=ErrorCode.LIGHTROOM_RESPONSE_TIMEOUT,
                message=f"Lightroom response file was not found: {path}",
                failed_stage=Stage.LIGHTROOM.value,
            )

        raw_payload = _read_json(path)
        try:
            response = LightroomResponsePayload.model_validate(raw_payload)
        except ValidationError as exc:
            self.task_repository.mark_failed(
                session,
                task,
                error_code=ErrorCode.LIGHTROOM_EXPORT_FAILED,
                error_message="Lightroom response payload is invalid.",
                failed_stage=Stage.LIGHTROOM,
            )
            raise TonevyraError(
                code=ErrorCode.LIGHTROOM_EXPORT_FAILED,
                message="Lightroom response payload is invalid.",
                failed_stage=Stage.LIGHTROOM.value,
            ) from exc

        response_artifact = self.storage.save_json(
            session,
            task_id=task.id,
            artifact_type=ArtifactType.LIGHTROOM_RESPONSE,
            name="lightroom_response.json",
            data=response.model_dump(mode="json"),
        )
        self.event_repository.create(
            session,
            task_id=task.id,
            event_type=TaskEventType.LIGHTROOM_RESPONSE_RECEIVED,
            stage=Stage.LIGHTROOM,
            message="Fake Lightroom response JSON was read.",
            payload_json={
                "loop_name": PROCESSING_LOOP_NAME,
                "loop_iteration": 1,
                "event_type": TaskEventType.LIGHTROOM_RESPONSE_RECEIVED.value,
                "from_status": from_status,
                "to_status": task.status,
                "reason": "lightroom_response artifact saved",
                "request_id": response.request_id,
                "response_status": response.status,
                "evidence_artifacts": [_artifact_summary(response_artifact)],
            },
        )

        if response.status == LIGHTROOM_RESPONSE_FAILED:
            finished_at = datetime.utcnow()
            error_code = ErrorCode(response.error_code or ErrorCode.LIGHTROOM_EXPORT_FAILED.value)
            self.stage_repository.create(
                session,
                task_id=task.id,
                stage=Stage.LIGHTROOM,
                stage_status=StageStatus.FAILED,
                summary_json={
                    "backend": "fake",
                    "request_id": response.request_id,
                    "error_code": error_code.value,
                    "error_message": response.error_message,
                    "lightroom_response_artifact": _artifact_summary(response_artifact),
                },
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=_duration_ms(started_at, finished_at),
            )
            self.task_repository.mark_failed(
                session,
                task,
                error_code=error_code,
                error_message=response.error_message or "Fake Lightroom export failed.",
                failed_stage=Stage.LIGHTROOM,
            )
            self.event_repository.create(
                session,
                task_id=task.id,
                event_type=TaskEventType.TASK_FAILED,
                stage=Stage.LIGHTROOM,
                message="Fake Lightroom returned a failed response.",
                payload_json={
                    "loop_name": PROCESSING_LOOP_NAME,
                    "loop_iteration": 1,
                    "event_type": TaskEventType.TASK_FAILED.value,
                    "from_status": from_status,
                    "to_status": TaskStatus.FAILED.value,
                    "reason": "lightroom response status failed",
                    "error_code": error_code.value,
                    "evidence_artifacts": [_artifact_summary(response_artifact)],
                },
            )
            return LightroomResponseResult(
                payload=response,
                response_path=path,
                response_artifact=response_artifact,
                export_artifact=None,
                success=False,
            )

        export_path = Path(response.export_path or "")
        if not export_path.exists():
            self.task_repository.mark_failed(
                session,
                task,
                error_code=ErrorCode.EXPORT_FILE_MISSING,
                error_message=f"Lightroom response succeeded but export is missing: {export_path}",
                failed_stage=Stage.EXPORT,
            )
            raise TonevyraError(
                code=ErrorCode.EXPORT_FILE_MISSING,
                message=f"Lightroom response succeeded but export is missing: {export_path}",
                failed_stage=Stage.EXPORT.value,
            )

        export_artifact = self.storage.save_bytes(
            session,
            task_id=task.id,
            artifact_type=ArtifactType.EXPORTED_IMAGE,
            name="fake_export.jpg",
            data=export_path.read_bytes(),
            mime_type="image/jpeg",
        )
        finished_at = datetime.utcnow()
        self.stage_repository.create(
            session,
            task_id=task.id,
            stage=Stage.LIGHTROOM,
            stage_status=StageStatus.SUCCEEDED,
            summary_json={
                "backend": "fake",
                "request_id": response.request_id,
                "response_path": _project_relative_or_absolute(path),
                "export_path": str(export_path.resolve()),
                "lightroom_response_artifact": _artifact_summary(response_artifact),
            },
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=_duration_ms(started_at, finished_at),
        )
        self.stage_repository.create(
            session,
            task_id=task.id,
            stage=Stage.EXPORT,
            stage_status=StageStatus.SUCCEEDED,
            summary_json={
                "backend": "fake",
                "export_path": str(export_path.resolve()),
                "export_artifact": _artifact_summary(export_artifact),
            },
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=_duration_ms(started_at, finished_at),
        )
        self.task_repository.update_status(
            session,
            task,
            status=TaskStatus.EXPORT_DONE,
            current_stage=Stage.EXPORT,
        )
        self.event_repository.create(
            session,
            task_id=task.id,
            event_type=TaskEventType.EXPORT_DONE,
            stage=Stage.EXPORT,
            message="Fake Lightroom export file was created and registered.",
            payload_json={
                "loop_name": PROCESSING_LOOP_NAME,
                "loop_iteration": 1,
                "event_type": TaskEventType.EXPORT_DONE.value,
                "from_status": from_status,
                "to_status": TaskStatus.EXPORT_DONE.value,
                "reason": "fake export artifact saved",
                "request_id": response.request_id,
                "evidence_artifacts": [
                    _artifact_summary(response_artifact),
                    _artifact_summary(export_artifact),
                ],
            },
        )
        return LightroomResponseResult(
            payload=response,
            response_path=path,
            response_artifact=response_artifact,
            export_artifact=export_artifact,
            success=True,
        )

    def ingest_apply_result(
        self,
        session: Session,
        *,
        task: ImageTask,
        response_path: str | Path | None = None,
    ) -> LightroomResponseResult:
        """Read a T-019 Lightroom apply result and record DB/artifact evidence."""

        started_at = datetime.utcnow()
        from_status = task.status
        path = Path(response_path) if response_path is not None else self.apply_result_path(str(task.id))
        path = _absolute_project_path(path)
        if not path.exists():
            self.task_repository.mark_failed(
                session,
                task,
                error_code=ErrorCode.LIGHTROOM_RESPONSE_TIMEOUT,
                error_message=f"Lightroom apply result file was not found: {path}",
                failed_stage=Stage.LIGHTROOM,
            )
            raise TonevyraError(
                code=ErrorCode.LIGHTROOM_RESPONSE_TIMEOUT,
                message=f"Lightroom apply result file was not found: {path}",
                failed_stage=Stage.LIGHTROOM.value,
            )

        raw_payload = _read_json(path)
        try:
            response = LightroomApplyResultPayload.model_validate(raw_payload)
        except ValidationError as exc:
            self.task_repository.mark_failed(
                session,
                task,
                error_code=ErrorCode.LIGHTROOM_EXPORT_FAILED,
                error_message="Lightroom apply result payload is invalid.",
                failed_stage=Stage.LIGHTROOM,
            )
            raise TonevyraError(
                code=ErrorCode.LIGHTROOM_EXPORT_FAILED,
                message="Lightroom apply result payload is invalid.",
                failed_stage=Stage.LIGHTROOM.value,
            ) from exc

        response_artifact = self.storage.save_json(
            session,
            task_id=task.id,
            artifact_type=ArtifactType.LIGHTROOM_RESPONSE,
            name="lightroom_apply_result.json",
            data=response.model_dump(mode="json"),
        )
        self.event_repository.create(
            session,
            task_id=task.id,
            event_type=TaskEventType.LIGHTROOM_RESPONSE_RECEIVED,
            stage=Stage.LIGHTROOM,
            message="Folder-driven Lightroom apply result JSON was read.",
            payload_json={
                "loop_name": PROCESSING_LOOP_NAME,
                "loop_iteration": 1,
                "event_type": TaskEventType.LIGHTROOM_RESPONSE_RECEIVED.value,
                "from_status": from_status,
                "to_status": task.status,
                "reason": "lightroom_apply_result artifact saved",
                "request_id": response.request_id,
                "response_status": response.status,
                "request_origin": response.request_origin,
                "command": response.command,
                "catalog_action": response.catalog_action,
                "applied_parameters": response.applied_parameters,
                "skipped_parameters": response.skipped_parameters,
                "applied_settings": response.applied_settings,
                "skipped_settings": response.skipped_settings,
                "lightroom_result": response.lightroom_result,
                "evidence_artifacts": [_artifact_summary(response_artifact)],
            },
        )

        finished_at = datetime.utcnow()
        if response.status == "failed":
            plugin_error = response.error or {}
            self.stage_repository.create(
                session,
                task_id=task.id,
                stage=Stage.LIGHTROOM,
                stage_status=StageStatus.FAILED,
                summary_json={
                    "backend": "lightroom",
                    "request_id": response.request_id,
                    "apply_status": response.status,
                    "catalog_action": response.catalog_action,
                    "plugin_error": plugin_error,
                    "lightroom_result": response.lightroom_result,
                    "lightroom_response_artifact": _artifact_summary(response_artifact),
                },
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=_duration_ms(started_at, finished_at),
            )
            self.task_repository.mark_failed(
                session,
                task,
                error_code=ErrorCode.LIGHTROOM_EXPORT_FAILED,
                error_message=str(plugin_error.get("message") or "Lightroom plugin apply failed."),
                failed_stage=Stage.LIGHTROOM,
            )
            self.event_repository.create(
                session,
                task_id=task.id,
                event_type=TaskEventType.TASK_FAILED,
                stage=Stage.LIGHTROOM,
                message="Folder-driven Lightroom plugin returned a failed apply result.",
                payload_json={
                    "loop_name": PROCESSING_LOOP_NAME,
                    "loop_iteration": 1,
                    "event_type": TaskEventType.TASK_FAILED.value,
                    "from_status": from_status,
                    "to_status": TaskStatus.FAILED.value,
                    "reason": "lightroom apply result status failed",
                    "error_code": ErrorCode.LIGHTROOM_EXPORT_FAILED.value,
                    "plugin_error": plugin_error,
                    "evidence_artifacts": [_artifact_summary(response_artifact)],
                },
            )
            return LightroomResponseResult(
                payload=response,
                response_path=path,
                response_artifact=response_artifact,
                export_artifact=None,
                success=False,
            )

        if response.status != "applied":
            self.stage_repository.create(
                session,
                task_id=task.id,
                stage=Stage.LIGHTROOM,
                stage_status=StageStatus.SUCCEEDED,
                summary_json={
                    "backend": "lightroom",
                    "request_id": response.request_id,
                    "apply_status": response.status,
                    "catalog_action": response.catalog_action,
                    "lightroom_result": response.lightroom_result,
                    "lightroom_response_artifact": _artifact_summary(response_artifact),
                    "export_eligible": False,
                },
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=_duration_ms(started_at, finished_at),
            )
            self.task_repository.update_status(
                session,
                task,
                status=TaskStatus.REVIEW_REQUIRED,
                current_stage=Stage.LIGHTROOM,
            )
            self.event_repository.create(
                session,
                task_id=task.id,
                event_type=TaskEventType.TASK_FINALIZED,
                stage=Stage.LIGHTROOM,
                message="Lightroom apply result was not eligible for automatic export.",
                payload_json={
                    "loop_name": PROCESSING_LOOP_NAME,
                    "loop_iteration": 1,
                    "event_type": TaskEventType.TASK_FINALIZED.value,
                    "from_status": from_status,
                    "to_status": TaskStatus.REVIEW_REQUIRED.value,
                    "reason": "lightroom apply result was not status=applied",
                    "request_id": response.request_id,
                    "apply_status": response.status,
                    "evidence_artifacts": [_artifact_summary(response_artifact)],
                },
            )
            return LightroomResponseResult(
                payload=response,
                response_path=path,
                response_artifact=response_artifact,
                export_artifact=None,
                success=False,
            )

        self.stage_repository.create(
            session,
            task_id=task.id,
            stage=Stage.LIGHTROOM,
            stage_status=StageStatus.SUCCEEDED,
            summary_json={
                "backend": "lightroom",
                "request_id": response.request_id,
                "apply_status": response.status,
                "applied_settings": response.applied_settings,
                "skipped_settings": response.skipped_settings,
                "applied_parameters": response.applied_parameters,
                "skipped_parameters": response.skipped_parameters,
                "catalog_action": response.catalog_action,
                "lightroom_result": response.lightroom_result,
                "lightroom_response_artifact": _artifact_summary(response_artifact),
            },
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=_duration_ms(started_at, finished_at),
        )
        self.task_repository.update_status(
            session,
            task,
            status=TaskStatus.LIGHTROOM_PROCESSING,
            current_stage=Stage.LIGHTROOM,
        )
        self.event_repository.create(
            session,
            task_id=task.id,
            event_type=TaskEventType.LIGHTROOM_RESPONSE_RECEIVED,
            stage=Stage.LIGHTROOM,
            message="Lightroom plugin applied Develop settings; final export can be requested.",
            payload_json={
                "loop_name": PROCESSING_LOOP_NAME,
                "loop_iteration": 1,
                "event_type": TaskEventType.LIGHTROOM_RESPONSE_RECEIVED.value,
                "from_status": from_status,
                "to_status": TaskStatus.LIGHTROOM_PROCESSING.value,
                "reason": "folder-driven Lightroom apply completed and is export eligible",
                "request_id": response.request_id,
                "applied_settings": response.applied_settings,
                "skipped_settings": response.skipped_settings,
                "applied_parameters": response.applied_parameters,
                "skipped_parameters": response.skipped_parameters,
                "catalog_action": response.catalog_action,
                "lightroom_result": response.lightroom_result,
                "evidence_artifacts": [_artifact_summary(response_artifact)],
            },
        )
        return LightroomResponseResult(
            payload=response,
            response_path=path,
            response_artifact=response_artifact,
            export_artifact=None,
            success=True,
        )

    def write_export_request(
        self,
        session: Session,
        *,
        task: ImageTask,
        apply_result: LightroomApplyResultPayload,
    ) -> LightroomRequestResult:
        """Write a T-020 export request after a verified T-019 apply result."""

        from_status = task.status
        try:
            _validate_apply_result_for_export(apply_result)
            source_path = _absolute_project_path(apply_result.source_path)
            export_path = _default_lightroom_export_path(self.settings, task)
            _validate_export_output_path(self.settings, source_path=source_path, export_path=export_path)
            payload = LightroomExportRequestPayload(
                request_id=_export_request_id(task.id),
                task_id=str(task.id),
                apply_request_id=apply_result.request_id,
                source_path=str(source_path),
                export_path=str(export_path),
                created_at=datetime.utcnow().isoformat(timespec="seconds") + "Z",
            )
        except Exception as exc:
            self.task_repository.mark_failed(
                session,
                task,
                error_code=ErrorCode.LIGHTROOM_REQUEST_FAILED,
                error_message="Failed to create Lightroom export request payload.",
                failed_stage=Stage.LIGHTROOM,
            )
            raise TonevyraError(
                code=ErrorCode.LIGHTROOM_REQUEST_FAILED,
                message="Failed to create Lightroom export request payload.",
                failed_stage=Stage.LIGHTROOM.value,
            ) from exc

        request_path = self.export_request_path(payload.request_id)
        _clear_stale_export_files(self.settings, payload.request_id)
        _write_json_atomic(request_path, payload.model_dump(mode="json"))
        request_artifact = self.storage.save_json(
            session,
            task_id=task.id,
            artifact_type=ArtifactType.LIGHTROOM_REQUEST,
            name="lightroom_export_request.json",
            data=payload.model_dump(mode="json"),
            version=2,
        )

        self.task_repository.update_status(
            session,
            task,
            status=TaskStatus.LIGHTROOM_PROCESSING,
            current_stage=Stage.LIGHTROOM,
        )
        self.event_repository.create(
            session,
            task_id=task.id,
            event_type=TaskEventType.LIGHTROOM_REQUESTED,
            stage=Stage.LIGHTROOM,
            message="Folder-driven Lightroom export request JSON was written.",
            payload_json={
                "loop_name": PROCESSING_LOOP_NAME,
                "loop_iteration": 1,
                "event_type": TaskEventType.LIGHTROOM_REQUESTED.value,
                "from_status": from_status,
                "to_status": TaskStatus.LIGHTROOM_PROCESSING.value,
                "reason": "lightroom_export_request artifact and bridge request saved",
                "request_id": payload.request_id,
                "apply_request_id": payload.apply_request_id,
                "request_path": _project_relative_or_absolute(request_path),
                "export_path": payload.export_path,
                "command": payload.command,
                "evidence_artifacts": [_artifact_summary(request_artifact)],
            },
        )
        return LightroomRequestResult(payload=payload, request_path=request_path, request_artifact=request_artifact)

    def ingest_export_result(
        self,
        session: Session,
        *,
        task: ImageTask,
        response_path: str | Path | None = None,
    ) -> LightroomResponseResult:
        """Read a T-020 Lightroom export result and verify the actual output file."""

        started_at = datetime.utcnow()
        from_status = task.status
        path = Path(response_path) if response_path is not None else self.export_result_path(_export_request_id(task.id))
        path = _absolute_project_path(path)
        if not path.exists():
            self.task_repository.mark_failed(
                session,
                task,
                error_code=ErrorCode.LIGHTROOM_RESPONSE_TIMEOUT,
                error_message=f"Lightroom export result file was not found: {path}",
                failed_stage=Stage.LIGHTROOM,
            )
            raise TonevyraError(
                code=ErrorCode.LIGHTROOM_RESPONSE_TIMEOUT,
                message=f"Lightroom export result file was not found: {path}",
                failed_stage=Stage.LIGHTROOM.value,
            )

        raw_payload = _read_json(path)
        try:
            response = LightroomExportResultPayload.model_validate(raw_payload)
        except ValidationError as exc:
            self.task_repository.mark_failed(
                session,
                task,
                error_code=ErrorCode.LIGHTROOM_EXPORT_FAILED,
                error_message="Lightroom export result payload is invalid.",
                failed_stage=Stage.LIGHTROOM,
            )
            raise TonevyraError(
                code=ErrorCode.LIGHTROOM_EXPORT_FAILED,
                message="Lightroom export result payload is invalid.",
                failed_stage=Stage.LIGHTROOM.value,
            ) from exc

        response_artifact = self.storage.save_json(
            session,
            task_id=task.id,
            artifact_type=ArtifactType.LIGHTROOM_RESPONSE,
            name="lightroom_export_result.json",
            data=response.model_dump(mode="json"),
            version=2,
        )
        self.event_repository.create(
            session,
            task_id=task.id,
            event_type=TaskEventType.LIGHTROOM_RESPONSE_RECEIVED,
            stage=Stage.LIGHTROOM,
            message="Folder-driven Lightroom export result JSON was read.",
            payload_json={
                "loop_name": PROCESSING_LOOP_NAME,
                "loop_iteration": 1,
                "event_type": TaskEventType.LIGHTROOM_RESPONSE_RECEIVED.value,
                "from_status": from_status,
                "to_status": task.status,
                "reason": "lightroom_export_result artifact saved",
                "request_id": response.request_id,
                "response_status": response.status,
                "file_result": response.file_result,
                "lightroom_result": response.lightroom_result,
                "evidence_artifacts": [_artifact_summary(response_artifact)],
            },
        )

        finished_at = datetime.utcnow()
        if response.status == "failed":
            error_code = ErrorCode(response.error_code or ErrorCode.LIGHTROOM_EXPORT_FAILED.value)
            self.stage_repository.create(
                session,
                task_id=task.id,
                stage=Stage.EXPORT,
                stage_status=StageStatus.FAILED,
                summary_json={
                    "backend": "lightroom",
                    "request_id": response.request_id,
                    "error_code": error_code.value,
                    "error_message": response.message,
                    "lightroom_result": response.lightroom_result,
                    "lightroom_response_artifact": _artifact_summary(response_artifact),
                },
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=_duration_ms(started_at, finished_at),
            )
            self.task_repository.mark_failed(
                session,
                task,
                error_code=error_code,
                error_message=response.message or "Lightroom export failed.",
                failed_stage=Stage.EXPORT,
            )
            self.event_repository.create(
                session,
                task_id=task.id,
                event_type=TaskEventType.TASK_FAILED,
                stage=Stage.EXPORT,
                message="Folder-driven Lightroom plugin returned a failed export result.",
                payload_json={
                    "loop_name": PROCESSING_LOOP_NAME,
                    "loop_iteration": 1,
                    "event_type": TaskEventType.TASK_FAILED.value,
                    "from_status": from_status,
                    "to_status": TaskStatus.FAILED.value,
                    "reason": "lightroom export result status failed",
                    "error_code": error_code.value,
                    "evidence_artifacts": [_artifact_summary(response_artifact)],
                },
            )
            return LightroomResponseResult(
                payload=response,
                response_path=path,
                response_artifact=response_artifact,
                export_artifact=None,
                success=False,
            )

        source_path = Path(response.source_path).resolve()
        export_path = Path(response.export_path).resolve()
        try:
            _validate_export_output_path(self.settings, source_path=source_path, export_path=export_path)
        except ValueError as exc:
            self.task_repository.mark_failed(
                session,
                task,
                error_code=ErrorCode.LIGHTROOM_EXPORT_FAILED,
                error_message=str(exc),
                failed_stage=Stage.EXPORT,
            )
            raise TonevyraError(
                code=ErrorCode.LIGHTROOM_EXPORT_FAILED,
                message=str(exc),
                failed_stage=Stage.EXPORT.value,
            ) from exc

        if not export_path.exists() or not export_path.is_file() or export_path.stat().st_size <= 0:
            self.task_repository.mark_failed(
                session,
                task,
                error_code=ErrorCode.EXPORT_FILE_MISSING,
                error_message=f"Lightroom export result succeeded but export is missing or empty: {export_path}",
                failed_stage=Stage.EXPORT,
            )
            raise TonevyraError(
                code=ErrorCode.EXPORT_FILE_MISSING,
                message=f"Lightroom export result succeeded but export is missing or empty: {export_path}",
                failed_stage=Stage.EXPORT.value,
            )

        export_artifact = self.storage.save_bytes(
            session,
            task_id=task.id,
            artifact_type=ArtifactType.EXPORTED_IMAGE,
            name="lightroom_export.jpg",
            data=export_path.read_bytes(),
            mime_type="image/jpeg",
        )
        self.stage_repository.create(
            session,
            task_id=task.id,
            stage=Stage.EXPORT,
            stage_status=StageStatus.SUCCEEDED,
            summary_json={
                "backend": "lightroom",
                "request_id": response.request_id,
                "response_path": _project_relative_or_absolute(path),
                "export_path": str(export_path),
                "file_result": response.file_result,
                "lightroom_result": response.lightroom_result,
                "lightroom_response_artifact": _artifact_summary(response_artifact),
                "export_artifact": _artifact_summary(export_artifact),
            },
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=_duration_ms(started_at, finished_at),
        )
        self.task_repository.update_status(
            session,
            task,
            status=TaskStatus.EXPORT_DONE,
            current_stage=Stage.EXPORT,
        )
        self.event_repository.create(
            session,
            task_id=task.id,
            event_type=TaskEventType.EXPORT_DONE,
            stage=Stage.EXPORT,
            message="Lightroom export file was verified and registered.",
            payload_json={
                "loop_name": PROCESSING_LOOP_NAME,
                "loop_iteration": 1,
                "event_type": TaskEventType.EXPORT_DONE.value,
                "from_status": from_status,
                "to_status": TaskStatus.EXPORT_DONE.value,
                "reason": "lightroom export result and output file verified",
                "request_id": response.request_id,
                "export_path": str(export_path),
                "evidence_artifacts": [
                    _artifact_summary(response_artifact),
                    _artifact_summary(export_artifact),
                ],
            },
        )
        return LightroomResponseResult(
            payload=response,
            response_path=path,
            response_artifact=response_artifact,
            export_artifact=export_artifact,
            success=True,
        )

    def wait_for_response(
        self,
        *,
        request_id: str,
        timeout_seconds: int | None = None,
        poll_interval_seconds: float = 2.0,
    ) -> Path:
        """Wait for a response file using a bounded timeout."""

        timeout = timeout_seconds or self.settings.lightroom_response_timeout_seconds
        deadline = time.monotonic() + timeout
        response_path = self.apply_result_path(request_id) if self.settings.lightroom_backend == "lightroom" else self.response_path(request_id)
        while time.monotonic() <= deadline:
            if response_path.exists():
                return response_path
            time.sleep(poll_interval_seconds)
        raise TonevyraError(
            code=ErrorCode.LIGHTROOM_RESPONSE_TIMEOUT,
            message=f"Timed out waiting for Lightroom response: {response_path}",
            failed_stage=Stage.LIGHTROOM.value,
        )

    def wait_for_export_response(
        self,
        *,
        request_id: str,
        timeout_seconds: int | None = None,
        poll_interval_seconds: float = 2.0,
    ) -> Path:
        """Wait for a T-020 export result file using a bounded timeout."""

        timeout = timeout_seconds or self.settings.lightroom_response_timeout_seconds
        deadline = time.monotonic() + timeout
        response_path = self.export_result_path(request_id)
        while time.monotonic() <= deadline:
            if response_path.exists():
                return response_path
            time.sleep(poll_interval_seconds)
        raise TonevyraError(
            code=ErrorCode.LIGHTROOM_RESPONSE_TIMEOUT,
            message=f"Timed out waiting for Lightroom export result: {response_path}",
            failed_stage=Stage.LIGHTROOM.value,
        )

    def request_path(self, request_id: str) -> Path:
        return (self.settings.project_path(self.settings.bridge_dir) / "requests" / f"{request_id}.json").resolve()

    def response_path(self, request_id: str) -> Path:
        return (self.settings.project_path(self.settings.bridge_dir) / "responses" / f"{request_id}.json").resolve()

    def apply_request_path(self, request_id: str) -> Path:
        return (self.settings.project_path(self.settings.bridge_dir) / "lightroom_apply_requests" / f"{request_id}.json").resolve()

    def apply_result_path(self, request_id: str) -> Path:
        return (self.settings.project_path(self.settings.bridge_dir) / "lightroom_apply_results" / f"{request_id}.json").resolve()

    def export_request_path(self, request_id: str) -> Path:
        return (self.settings.project_path(self.settings.bridge_dir) / "lightroom_export_requests" / f"{request_id}.json").resolve()

    def export_result_path(self, request_id: str) -> Path:
        return (self.settings.project_path(self.settings.bridge_dir) / "lightroom_export_results" / f"{request_id}.json").resolve()


def write_lightroom_request(
    session: Session,
    *,
    task: ImageTask,
    correction_plan_artifact: ArtifactRef,
    settings: Settings | None = None,
    storage: ArtifactStorage | None = None,
) -> LightroomRequestResult:
    bridge = LightroomBridge(settings=settings, storage=storage)
    return bridge.write_request(session, task=task, correction_plan_artifact=correction_plan_artifact)


def ingest_lightroom_response(
    session: Session,
    *,
    task: ImageTask,
    response_path: str | Path | None = None,
    settings: Settings | None = None,
    storage: ArtifactStorage | None = None,
) -> LightroomResponseResult:
    bridge = LightroomBridge(settings=settings, storage=storage)
    return bridge.ingest_response(session, task=task, response_path=response_path)


def _default_export_path(settings: Settings, task: ImageTask) -> Path:
    return (settings.project_path(settings.output_dir) / "temp" / f"{task.id}.jpg").resolve()


def _clear_stale_apply_files(settings: Settings, request_id: str) -> None:
    bridge_dir = settings.project_path(settings.bridge_dir)
    for subdir in (
        "lightroom_apply_processing",
        "lightroom_apply_processed",
        "lightroom_apply_results",
        "lightroom_apply_errors",
        "lightroom_live_evidence",
    ):
        path = (bridge_dir / subdir / f"{request_id}.json").resolve()
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def _clear_stale_export_files(settings: Settings, request_id: str) -> None:
    bridge_dir = settings.project_path(settings.bridge_dir)
    for subdir in (
        "lightroom_export_processing",
        "lightroom_export_processed",
        "lightroom_export_results",
        "lightroom_export_errors",
    ):
        path = (bridge_dir / subdir / f"{request_id}.json").resolve()
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def _export_request_id(task_id: object) -> str:
    return f"export-{task_id}"


def _default_lightroom_export_path(settings: Settings, task: ImageTask) -> Path:
    source_name = Path(task.file_name).stem or str(task.id)
    safe_stem = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in source_name).strip("_")
    if not safe_stem:
        safe_stem = str(task.id)
    return (settings.project_path(settings.output_dir) / "temp" / str(task.id) / f"{safe_stem}_tonevyra.jpg").resolve()


def _validate_export_output_path(settings: Settings, *, source_path: Path, export_path: Path) -> None:
    source = source_path.resolve()
    export = export_path.resolve()
    if source == export:
        raise ValueError("Lightroom export_path must not equal source_path.")
    output_temp = (settings.project_path(settings.output_dir) / "temp").resolve()
    try:
        export.relative_to(output_temp)
    except ValueError as exc:
        raise ValueError(f"Lightroom export_path must stay under runtime output temp: {output_temp}") from exc


def _validate_apply_result_for_export(response: LightroomApplyResultPayload) -> None:
    if response.status != "applied":
        raise ValueError("Lightroom export requires apply result status=applied.")
    if response.catalog_action not in {"imported", "found_existing"}:
        raise ValueError("Lightroom export requires catalog_action imported or found_existing.")
    if response.lightroom_result.get("develop_settings_applied") is not True:
        raise ValueError("Lightroom export requires develop_settings_applied=true.")
    if not (
        response.lightroom_result.get("source_photo_imported") is True
        or response.lightroom_result.get("source_photo_found") is True
    ):
        raise ValueError("Lightroom export requires source photo imported or found in catalog.")


def _develop_settings_from_plan(plan: CorrectionPlan) -> dict[str, float]:
    """Translate planner keys to the T-019 Lightroom apply contract."""

    key_map = {"temperature_delta": "temp"}
    develop_settings: dict[str, float] = {}
    for key, value in plan.adjustments_json.items():
        apply_key = key_map.get(key, key)
        if apply_key not in LIGHTROOM_APPLY_ALLOWED_SETTINGS:
            continue
        develop_settings[apply_key] = float(value)
    if not develop_settings:
        raise ValueError("correction plan did not contain any Lightroom apply settings")
    return develop_settings


def _absolute_project_path(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate.resolve()


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            delete=False,
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except Exception:
        if temp_path and temp_path.exists():
            temp_path.unlink()
        raise


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _artifact_summary(artifact: ArtifactRef) -> dict[str, Any]:
    return {
        "artifact_id": str(artifact.artifact_id),
        "artifact_type": artifact.artifact_type,
        "artifact_path": artifact.relative_path,
        "sha256": artifact.sha256,
        "size_bytes": artifact.size_bytes,
    }


def _project_relative_or_absolute(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def _duration_ms(started_at: datetime, finished_at: datetime) -> int:
    return int((finished_at - started_at).total_seconds() * 1000)
