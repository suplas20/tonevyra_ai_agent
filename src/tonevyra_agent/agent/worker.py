"""One-photo worker pipeline orchestration for Tonevyra AI."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from tonevyra_agent.core.config import Settings, get_settings
from tonevyra_agent.core.enums import ErrorCode, QualityDecision, Stage, TaskEventType, TaskStatus
from tonevyra_agent.core.errors import TonevyraError
from tonevyra_agent.correction.planner import CorrectionPlanner
from tonevyra_agent.db.database import session_scope
from tonevyra_agent.db.models import ImageTask
from tonevyra_agent.db.repositories import ImageTaskRepository, TaskEventRepository
from tonevyra_agent.images.metadata import create_metadata_and_preview_artifacts
from tonevyra_agent.lightroom.bridge import LightroomBridge
from tonevyra_agent.quality.analyzer import QualityGate
from tonevyra_agent.storage.artifacts import ArtifactRef, ArtifactStorage
from tonevyra_agent.vision.analyzer import VisionAnalyzer


PROCESSING_LOOP_NAME = "processing_loop"
FINAL_OUTPUT_DIRS: dict[QualityDecision, str] = {
    QualityDecision.PASS: "pass",
    QualityDecision.REVIEW_REQUIRED: "review_required",
    QualityDecision.FAILED: "failed",
}


@dataclass(frozen=True)
class WorkerPipelineResult:
    task_id: UUID
    processed: bool
    final_status: TaskStatus | None
    quality_decision: QualityDecision | None = None
    final_export_path: Path | None = None
    error_code: ErrorCode | None = None
    error_message: str | None = None


class AgentWorker:
    """Process one queued task through vision, Lightroom bridge, and quality gate."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        storage: ArtifactStorage | None = None,
        task_repository: ImageTaskRepository | None = None,
        event_repository: TaskEventRepository | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.storage = storage or ArtifactStorage(self.settings)
        self.task_repository = task_repository or ImageTaskRepository()
        self.event_repository = event_repository or TaskEventRepository()
        self._vision_analyzer: VisionAnalyzer | None = None
        self.correction_planner = CorrectionPlanner(settings=self.settings, storage=self.storage)
        self.lightroom_bridge = LightroomBridge(settings=self.settings, storage=self.storage)
        self.quality_gate = QualityGate(settings=self.settings, storage=self.storage)

    def process_next_queued(self) -> WorkerPipelineResult | None:
        with session_scope(self.settings) as session:
            tasks = self.task_repository.list_by_status(session, TaskStatus.QUEUED)
            task = tasks[0] if tasks else None
            if task is None:
                return None
            task_id = task.id

        return self.process_task(task_id)

    def process_task(self, task_id: UUID) -> WorkerPipelineResult:
        try:
            return self._process_task_inner(task_id)
        finally:
            self.release_resources()

    def release_resources(self) -> None:
        if self._vision_analyzer is not None:
            self._vision_analyzer.close()
            self._vision_analyzer = None

    def _process_task_inner(self, task_id: UUID) -> WorkerPipelineResult:
        try:
            metadata_artifact, preview_artifact = self._run_metadata_preview(task_id)
            vision_artifacts = self._run_vision(task_id, metadata_artifact=metadata_artifact, preview_artifact=preview_artifact)
            correction_plan = self._run_correction_plan(
                task_id,
                vision_artifact=vision_artifacts.structured_artifact,
                preview_artifact=preview_artifact,
            )
            request_result = self._write_lightroom_request(task_id, correction_plan_artifact=correction_plan)
            if self.settings.lightroom_backend == "lightroom":
                apply_result_path = self._wait_for_lightroom_response(task_id, request_id=request_result.payload.request_id)
                apply_result = self._ingest_lightroom_response(task_id, response_path=apply_result_path)
                if not apply_result.success:
                    return self._current_result(task_id, processed=True)
                mask_request = self._write_lightroom_mask_request(
                    task_id,
                    correction_plan_artifact=correction_plan,
                )
                if mask_request is not None:
                    try:
                        mask_result_path = self._wait_for_lightroom_mask_response(
                            task_id,
                            request_id=mask_request.payload.request_id,
                        )
                        self._ingest_lightroom_mask_response(task_id, response_path=mask_result_path)
                    except TonevyraError as exc:
                        self._record_lightroom_mask_fallback(
                            task_id,
                            request_id=mask_request.payload.request_id,
                            reason=exc.message,
                        )
                export_request = self._write_lightroom_export_request(task_id, apply_result=apply_result.payload)
                export_result_path = self._wait_for_lightroom_export_response(
                    task_id,
                    request_id=export_request.payload.request_id,
                )
                response_result = self._ingest_lightroom_export_response(task_id, response_path=export_result_path)
            else:
                response_path = self._wait_for_lightroom_response(task_id, request_id=request_result.payload.request_id)
                response_result = self._ingest_lightroom_response(task_id, response_path=response_path)
        except TonevyraError as exc:
            self._mark_failed_if_needed(
                task_id,
                error_code=exc.code,
                error_message=exc.message,
                failed_stage=self._stage_from_error(task_id, exc),
            )
            return self._current_result(task_id, processed=True)
        except Exception as exc:
            self._mark_failed(
                task_id,
                error_code=ErrorCode.DB_WRITE_FAILED,
                error_message=f"Worker pipeline failed unexpectedly: {exc}",
                failed_stage=self._current_stage_or_recovery(task_id),
            )
            return self._current_result(task_id, processed=True)

        if not response_result.success or response_result.export_artifact is None:
            return self._current_result(task_id, processed=True)

        try:
            quality_result = self._run_quality_gate(
                task_id,
                export_artifact=response_result.export_artifact,
                correction_plan_artifact=correction_plan,
            )
        except TonevyraError as exc:
            self._mark_failed_if_needed(
                task_id,
                error_code=exc.code,
                error_message=exc.message,
                failed_stage=self._stage_from_error(task_id, exc),
            )
            return self._current_result(task_id, processed=True)
        if not quality_result.success or quality_result.detail is None:
            return self._current_result(task_id, processed=True)

        try:
            final_export_path = self._move_final_export(
                task_id,
                source_path=Path(response_result.payload.export_path or response_result.export_artifact.absolute_path),
                decision=quality_result.decision,
            )
            self._record_task_finalized(
                task_id,
                decision=quality_result.decision,
                final_export_path=final_export_path,
                quality_artifact=quality_result.artifact,
            )
        except TonevyraError:
            return self._current_result(task_id, processed=True)
        return self._current_result(task_id, processed=True, final_export_path=final_export_path)

    def _run_metadata_preview(self, task_id: UUID) -> tuple[ArtifactRef, ArtifactRef]:
        with session_scope(self.settings) as session:
            task = self._require_task(session, task_id)
            from_status = task.status
            self.task_repository.update_status(session, task, status=TaskStatus.ANALYZING, current_stage=Stage.METADATA)
            self.event_repository.create(
                session,
                task_id=task.id,
                event_type=TaskEventType.VISION_STARTED,
                stage=Stage.METADATA,
                message="Worker picked queued task and started processing.",
                payload_json={
                    "loop_name": PROCESSING_LOOP_NAME,
                    "loop_iteration": 1,
                    "event_type": TaskEventType.VISION_STARTED.value,
                    "from_status": from_status,
                    "to_status": TaskStatus.ANALYZING.value,
                    "reason": "worker picked queued task",
                    "evidence_artifacts": [],
                },
            )
            result = create_metadata_and_preview_artifacts(
                session,
                task=task,
                settings=self.settings,
                storage=self.storage,
            )
            return result.metadata_artifact, result.preview_artifact.artifact

    def _run_vision(self, task_id: UUID, *, metadata_artifact: ArtifactRef, preview_artifact: ArtifactRef):
        with session_scope(self.settings) as session:
            task = self._require_task(session, task_id)
            try:
                return self._get_vision_analyzer().analyze(
                    session,
                    task=task,
                    preview_artifact=preview_artifact,
                    metadata_artifact=metadata_artifact,
                )
            except TonevyraError:
                session.commit()
                raise

    def _run_correction_plan(
        self,
        task_id: UUID,
        *,
        vision_artifact: ArtifactRef,
        preview_artifact: ArtifactRef | None = None,
    ) -> ArtifactRef:
        with session_scope(self.settings) as session:
            task = self._require_task(session, task_id)
            try:
                result = self.correction_planner.plan_from_artifact(
                    session,
                    task=task,
                    vision_artifact=vision_artifact,
                    preview_artifact=preview_artifact,
                )
                return result.artifact
            except TonevyraError:
                session.commit()
                raise

    def _write_lightroom_request(self, task_id: UUID, *, correction_plan_artifact: ArtifactRef):
        with session_scope(self.settings) as session:
            task = self._require_task(session, task_id)
            try:
                return self.lightroom_bridge.write_request(
                    session,
                    task=task,
                    correction_plan_artifact=correction_plan_artifact,
                )
            except TonevyraError:
                session.commit()
                raise

    def _wait_for_lightroom_response(self, task_id: UUID, *, request_id: str) -> Path:
        with session_scope(self.settings) as session:
            task = self._require_task(session, task_id)
            from_status = task.status
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
                message="Worker is waiting for a Lightroom bridge response.",
                payload_json={
                    "loop_name": PROCESSING_LOOP_NAME,
                    "loop_iteration": 1,
                    "event_type": TaskEventType.LIGHTROOM_REQUESTED.value,
                    "from_status": from_status,
                    "to_status": TaskStatus.LIGHTROOM_PROCESSING.value,
                    "reason": f"lightroom request handed to {self.settings.lightroom_backend} backend",
                    "request_id": request_id,
                    "evidence_artifacts": [],
                },
            )

        try:
            return self.lightroom_bridge.wait_for_response(request_id=request_id, poll_interval_seconds=0.25)
        except TonevyraError as exc:
            self._mark_failed(task_id, error_code=exc.code, error_message=exc.message, failed_stage=Stage.LIGHTROOM)
            raise

    def _ingest_lightroom_response(self, task_id: UUID, *, response_path: Path):
        with session_scope(self.settings) as session:
            task = self._require_task(session, task_id)
            try:
                return self.lightroom_bridge.ingest_response(session, task=task, response_path=response_path)
            except TonevyraError:
                session.commit()
                raise

    def _write_lightroom_mask_request(self, task_id: UUID, *, correction_plan_artifact: ArtifactRef):
        with session_scope(self.settings) as session:
            task = self._require_task(session, task_id)
            try:
                return self.lightroom_bridge.write_mask_request_from_correction_plan(
                    session,
                    task=task,
                    correction_plan_artifact=correction_plan_artifact,
                )
            except TonevyraError:
                session.commit()
                raise

    def _wait_for_lightroom_mask_response(self, task_id: UUID, *, request_id: str) -> Path:
        return self.lightroom_bridge.wait_for_mask_response(request_id=request_id, poll_interval_seconds=0.25)

    def _ingest_lightroom_mask_response(self, task_id: UUID, *, response_path: Path):
        with session_scope(self.settings) as session:
            task = self._require_task(session, task_id)
            try:
                return self.lightroom_bridge.ingest_mask_result(session, task=task, response_path=response_path)
            except TonevyraError:
                session.commit()
                raise

    def _record_lightroom_mask_fallback(self, task_id: UUID, *, request_id: str, reason: str) -> None:
        with session_scope(self.settings) as session:
            task = self._require_task(session, task_id)
            self.event_repository.create(
                session,
                task_id=task.id,
                event_type=TaskEventType.LIGHTROOM_RESPONSE_RECEIVED,
                stage=Stage.LIGHTROOM,
                message="Lightroom native mask execution was unavailable; continuing with global exposure fallback.",
                payload_json={
                    "loop_name": PROCESSING_LOOP_NAME,
                    "loop_iteration": 1,
                    "event_type": TaskEventType.LIGHTROOM_RESPONSE_RECEIVED.value,
                    "from_status": task.status,
                    "to_status": task.status,
                    "reason": reason,
                    "request_id": request_id,
                    "fallback_policy": "continue_with_global_high_exposure",
                    "evidence_artifacts": [],
                },
            )

    def _write_lightroom_export_request(self, task_id: UUID, *, apply_result):
        with session_scope(self.settings) as session:
            task = self._require_task(session, task_id)
            try:
                return self.lightroom_bridge.write_export_request(
                    session,
                    task=task,
                    apply_result=apply_result,
                )
            except TonevyraError:
                session.commit()
                raise

    def _wait_for_lightroom_export_response(self, task_id: UUID, *, request_id: str) -> Path:
        with session_scope(self.settings) as session:
            task = self._require_task(session, task_id)
            from_status = task.status
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
                message="Worker is waiting for a Lightroom export result.",
                payload_json={
                    "loop_name": PROCESSING_LOOP_NAME,
                    "loop_iteration": 1,
                    "event_type": TaskEventType.LIGHTROOM_REQUESTED.value,
                    "from_status": from_status,
                    "to_status": TaskStatus.LIGHTROOM_PROCESSING.value,
                    "reason": "lightroom export request handed to Lightroom plugin",
                    "request_id": request_id,
                    "evidence_artifacts": [],
                },
            )

        try:
            return self.lightroom_bridge.wait_for_export_response(request_id=request_id, poll_interval_seconds=0.25)
        except TonevyraError as exc:
            self._mark_failed(task_id, error_code=exc.code, error_message=exc.message, failed_stage=Stage.LIGHTROOM)
            raise

    def _ingest_lightroom_export_response(self, task_id: UUID, *, response_path: Path):
        with session_scope(self.settings) as session:
            task = self._require_task(session, task_id)
            try:
                return self.lightroom_bridge.ingest_export_result(session, task=task, response_path=response_path)
            except TonevyraError:
                session.commit()
                raise

    def _run_quality_gate(
        self,
        task_id: UUID,
        *,
        export_artifact: ArtifactRef,
        correction_plan_artifact: ArtifactRef,
    ):
        with session_scope(self.settings) as session:
            task = self._require_task(session, task_id)
            self.task_repository.update_status(session, task, status=TaskStatus.QUALITY_CHECK, current_stage=Stage.QUALITY)
            return self.quality_gate.evaluate_export(
                session,
                task=task,
                export_artifact=export_artifact,
                correction_plan_artifact=correction_plan_artifact,
            )

    def _move_final_export(self, task_id: UUID, *, source_path: Path, decision: QualityDecision) -> Path:
        source = source_path.resolve()
        if not source.exists():
            self._mark_failed(
                task_id,
                error_code=ErrorCode.EXPORT_FILE_MISSING,
                error_message=f"Final export move failed because source is missing: {source}",
                failed_stage=Stage.EXPORT,
            )
            raise TonevyraError(
                code=ErrorCode.EXPORT_FILE_MISSING,
                message=f"Final export move failed because source is missing: {source}",
                failed_stage=Stage.EXPORT.value,
            )

        output_dir = self.settings.project_path(self.settings.output_dir) / FINAL_OUTPUT_DIRS[decision]
        output_dir.mkdir(parents=True, exist_ok=True)
        final_path = (output_dir / f"{task_id}.jpg").resolve()
        os.replace(source, final_path)
        return final_path

    def _record_task_finalized(
        self,
        task_id: UUID,
        *,
        decision: QualityDecision,
        final_export_path: Path,
        quality_artifact: ArtifactRef | None,
    ) -> None:
        with session_scope(self.settings) as session:
            task = self._require_task(session, task_id)
            self.event_repository.create(
                session,
                task_id=task.id,
                event_type=TaskEventType.TASK_FINALIZED,
                stage=Stage.QUALITY,
                message="Worker finalized the one-photo processing pipeline.",
                payload_json={
                    "loop_name": PROCESSING_LOOP_NAME,
                    "loop_iteration": 1,
                    "event_type": TaskEventType.TASK_FINALIZED.value,
                    "from_status": task.status,
                    "to_status": task.status,
                    "reason": "final export moved to decision output folder",
                    "decision": decision.value,
                    "final_export_path": str(final_export_path),
                    "evidence_artifacts": [_artifact_summary(quality_artifact)] if quality_artifact else [],
                },
            )

    def _mark_failed(self, task_id: UUID, *, error_code: ErrorCode, error_message: str, failed_stage: Stage) -> None:
        with session_scope(self.settings) as session:
            task = self._require_task(session, task_id)
            from_status = task.status
            self.task_repository.mark_failed(
                session,
                task,
                error_code=error_code,
                error_message=error_message,
                failed_stage=failed_stage,
            )
            self.event_repository.create(
                session,
                task_id=task.id,
                event_type=TaskEventType.TASK_FAILED,
                stage=failed_stage,
                message="Worker failed the task with a structured error.",
                payload_json={
                    "loop_name": PROCESSING_LOOP_NAME,
                    "loop_iteration": 1,
                    "event_type": TaskEventType.TASK_FAILED.value,
                    "from_status": from_status,
                    "to_status": TaskStatus.FAILED.value,
                    "reason": error_message,
                    "error_code": error_code.value,
                    "evidence_artifacts": [],
                },
            )

    def _mark_failed_if_needed(self, task_id: UUID, *, error_code: ErrorCode, error_message: str, failed_stage: Stage) -> None:
        with session_scope(self.settings) as session:
            task = self._require_task(session, task_id)
            if task.status == TaskStatus.FAILED.value:
                return
        self._mark_failed(task_id, error_code=error_code, error_message=error_message, failed_stage=failed_stage)

    def _stage_from_error(self, task_id: UUID, error: TonevyraError) -> Stage:
        if error.failed_stage:
            try:
                return Stage(error.failed_stage)
            except ValueError:
                pass
        return self._current_stage_or_recovery(task_id)

    def _current_result(
        self,
        task_id: UUID,
        *,
        processed: bool,
        final_export_path: Path | None = None,
    ) -> WorkerPipelineResult:
        with session_scope(self.settings) as session:
            task = self._require_task(session, task_id)
            status = TaskStatus(task.status)
            decision = QualityDecision(task.quality_decision) if task.quality_decision else None
            error_code = ErrorCode(task.error_code) if task.error_code else None
            return WorkerPipelineResult(
                task_id=task.id,
                processed=processed,
                final_status=status,
                quality_decision=decision,
                final_export_path=final_export_path,
                error_code=error_code,
                error_message=task.error_message,
            )

    def _require_task(self, session: Session, task_id: UUID) -> ImageTask:
        task = self.task_repository.get(session, task_id)
        if task is None:
            raise RuntimeError(f"image task does not exist: {task_id}")
        return task

    def _current_stage_or_recovery(self, task_id: UUID) -> Stage:
        with session_scope(self.settings) as session:
            task = self.task_repository.get(session, task_id)
            if task is None or task.current_stage is None:
                return Stage.RECOVERY
            try:
                return Stage(task.current_stage)
            except ValueError:
                return Stage.RECOVERY

    def _get_vision_analyzer(self) -> VisionAnalyzer:
        if self._vision_analyzer is None:
            self._vision_analyzer = VisionAnalyzer(settings=self.settings, storage=self.storage)
        return self._vision_analyzer

def process_next_queued_task(*, settings: Settings | None = None) -> WorkerPipelineResult | None:
    return AgentWorker(settings=settings).process_next_queued()


def process_task(task_id: UUID, *, settings: Settings | None = None) -> WorkerPipelineResult:
    return AgentWorker(settings=settings).process_task(task_id)


def _artifact_summary(artifact: ArtifactRef | None) -> dict[str, object]:
    if artifact is None:
        return {}
    return {
        "artifact_id": str(artifact.artifact_id),
        "artifact_type": artifact.artifact_type,
        "artifact_path": artifact.relative_path,
        "sha256": artifact.sha256,
        "size_bytes": artifact.size_bytes,
    }
