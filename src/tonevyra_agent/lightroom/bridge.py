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
    LIGHTROOM_COMMAND_PING,
    LIGHTROOM_RESPONSE_FAILED,
    LIGHTROOM_RESPONSE_SUCCESS,
    LightroomRequestPayload,
    LightroomResponsePayload,
)
from tonevyra_agent.storage.artifacts import ArtifactRef, ArtifactStorage


PROCESSING_LOOP_NAME = "processing_loop"


@dataclass(frozen=True)
class LightroomRequestResult:
    payload: LightroomRequestPayload
    request_path: Path
    request_artifact: ArtifactRef


@dataclass(frozen=True)
class LightroomResponseResult:
    payload: LightroomResponsePayload
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
        response_path = self.response_path(request_id)
        while time.monotonic() <= deadline:
            if response_path.exists():
                return response_path
            time.sleep(poll_interval_seconds)
        raise TonevyraError(
            code=ErrorCode.LIGHTROOM_RESPONSE_TIMEOUT,
            message=f"Timed out waiting for Lightroom response: {response_path}",
            failed_stage=Stage.LIGHTROOM.value,
        )

    def request_path(self, request_id: str) -> Path:
        return (self.settings.project_path(self.settings.bridge_dir) / "requests" / f"{request_id}.json").resolve()

    def response_path(self, request_id: str) -> Path:
        return (self.settings.project_path(self.settings.bridge_dir) / "responses" / f"{request_id}.json").resolve()


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
