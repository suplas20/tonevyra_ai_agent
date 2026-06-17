"""Repository helpers for the current Tonevyra MVP tables."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tonevyra_agent.core.enums import (
    ArtifactType,
    ErrorCode,
    FeedbackUserAction,
    LearningSampleStatus,
    LearningSampleType,
    QualityDecision,
    Stage,
    StageStatus,
    TaskEventType,
    TaskStatus,
)
from tonevyra_agent.db.models import FeedbackRecord, ImageTask, LearningSample, QualityResult, StageResult, TaskArtifact, TaskEvent


def _value(value: str | Any) -> str:
    return value.value if hasattr(value, "value") else str(value)


class ImageTaskRepository:
    def create(
        self,
        session: Session,
        *,
        source_path: str | Path,
        file_name: str,
        file_ext: str,
        source_hash: str | None = None,
        file_size_bytes: int | None = None,
        status: TaskStatus = TaskStatus.DETECTED,
        current_stage: Stage | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        failed_stage: Stage | str | None = None,
        completed_at: datetime | None = None,
    ) -> ImageTask:
        task = ImageTask(
            source_path=str(source_path),
            source_hash=source_hash,
            file_name=file_name,
            file_ext=file_ext,
            file_size_bytes=file_size_bytes,
            status=status.value,
            current_stage=current_stage.value if current_stage else None,
            error_code=error_code,
            error_message=error_message,
            failed_stage=_value(failed_stage) if failed_stage else None,
            completed_at=completed_at,
        )
        session.add(task)
        session.flush()
        return task

    def get(self, session: Session, task_id: UUID) -> ImageTask | None:
        return session.get(ImageTask, task_id)

    def list_by_status(self, session: Session, status: TaskStatus) -> list[ImageTask]:
        return list(session.scalars(select(ImageTask).where(ImageTask.status == status.value)))

    def list_recent(self, session: Session, *, limit: int = 20, status: TaskStatus | None = None) -> list[ImageTask]:
        statement = select(ImageTask).order_by(ImageTask.updated_at.desc(), ImageTask.created_at.desc()).limit(limit)
        if status is not None:
            statement = (
                select(ImageTask)
                .where(ImageTask.status == status.value)
                .order_by(ImageTask.updated_at.desc(), ImageTask.created_at.desc())
                .limit(limit)
            )
        return list(session.scalars(statement))

    def count_by_status(self, session: Session) -> dict[str, int]:
        statement = select(ImageTask.status, func.count(ImageTask.id)).group_by(ImageTask.status)
        counts = {status.value: 0 for status in TaskStatus}
        for status, count in session.execute(statement):
            counts[str(status)] = int(count)
        return counts

    def list_by_file_name(self, session: Session, file_name: str) -> list[ImageTask]:
        return list(session.scalars(select(ImageTask).where(ImageTask.file_name == file_name)))

    def get_by_source_path_hash(self, session: Session, source_path: str | Path, source_hash: str) -> ImageTask | None:
        statement = select(ImageTask).where(
            ImageTask.source_path == str(source_path),
            ImageTask.source_hash == source_hash,
        )
        return session.scalar(statement)

    def get_non_failed_by_source_hash(self, session: Session, source_hash: str) -> ImageTask | None:
        statement = select(ImageTask).where(
            ImageTask.source_hash == source_hash,
            ImageTask.status != TaskStatus.FAILED.value,
        )
        return session.scalar(statement)

    def update_status(
        self,
        session: Session,
        task: ImageTask,
        *,
        status: TaskStatus,
        current_stage: Stage | None = None,
    ) -> ImageTask:
        task.status = status.value
        task.current_stage = current_stage.value if current_stage else None
        session.flush()
        return task

    def mark_failed(
        self,
        session: Session,
        task: ImageTask,
        *,
        error_code: ErrorCode | str,
        error_message: str,
        failed_stage: Stage | str,
    ) -> ImageTask:
        task.status = TaskStatus.FAILED.value
        task.current_stage = _value(failed_stage)
        task.error_code = _value(error_code)
        task.error_message = error_message
        task.failed_stage = _value(failed_stage)
        session.flush()
        return task

    def finalize_quality(
        self,
        session: Session,
        task: ImageTask,
        *,
        decision: QualityDecision | str,
        overall_score: float | Decimal,
    ) -> ImageTask:
        decision_value = _value(decision)
        task.status = TaskStatus(decision_value).value
        task.current_stage = Stage.QUALITY.value
        task.overall_score = Decimal(str(round(float(overall_score), 2)))
        task.quality_decision = QualityDecision(decision_value).value
        task.error_code = None
        task.error_message = None
        task.failed_stage = None
        task.completed_at = datetime.utcnow()
        session.flush()
        return task

    def requeue_for_retry(self, session: Session, task: ImageTask) -> ImageTask:
        task.retry_count += 1
        task.status = TaskStatus.QUEUED.value
        task.current_stage = Stage.WATCH.value
        task.error_code = None
        task.error_message = None
        task.failed_stage = None
        task.overall_score = None
        task.quality_decision = None
        task.completed_at = None
        session.flush()
        return task

    def delete(self, session: Session, task: ImageTask) -> None:
        session.delete(task)
        session.flush()


class TaskEventRepository:
    def create(
        self,
        session: Session,
        *,
        task_id: UUID,
        event_type: TaskEventType | str,
        stage: Stage | None = None,
        message: str | None = None,
        payload_json: dict[str, Any] | None = None,
    ) -> TaskEvent:
        event = TaskEvent(
            task_id=task_id,
            event_type=_value(event_type),
            stage=stage.value if stage else None,
            message=message,
            payload_json=payload_json or {},
        )
        session.add(event)
        session.flush()
        return event

    def list_for_task(self, session: Session, task_id: UUID) -> list[TaskEvent]:
        statement = select(TaskEvent).where(TaskEvent.task_id == task_id).order_by(TaskEvent.created_at)
        return list(session.scalars(statement))


class TaskArtifactRepository:
    def get_for_task_type_version(
        self,
        session: Session,
        *,
        task_id: UUID,
        artifact_type: ArtifactType | str,
        version: int = 1,
    ) -> TaskArtifact | None:
        statement = select(TaskArtifact).where(
            TaskArtifact.task_id == task_id,
            TaskArtifact.artifact_type == _value(artifact_type),
            TaskArtifact.version == version,
        )
        return session.scalar(statement)

    def create(
        self,
        session: Session,
        *,
        task_id: UUID,
        artifact_type: ArtifactType | str,
        artifact_path: str | Path,
        sha256: str | None = None,
        size_bytes: int | None = None,
        mime_type: str | None = None,
        version: int = 1,
    ) -> TaskArtifact:
        artifact = TaskArtifact(
            task_id=task_id,
            artifact_type=_value(artifact_type),
            artifact_path=str(artifact_path),
            sha256=sha256,
            size_bytes=size_bytes,
            mime_type=mime_type,
            version=version,
        )
        session.add(artifact)
        session.flush()
        return artifact

    def register_or_update(
        self,
        session: Session,
        *,
        task_id: UUID,
        artifact_type: ArtifactType | str,
        artifact_path: str | Path,
        sha256: str | None = None,
        size_bytes: int | None = None,
        mime_type: str | None = None,
        version: int = 1,
    ) -> TaskArtifact:
        existing = self.get_for_task_type_version(
            session,
            task_id=task_id,
            artifact_type=artifact_type,
            version=version,
        )
        if existing is None:
            return self.create(
                session,
                task_id=task_id,
                artifact_type=artifact_type,
                artifact_path=artifact_path,
                sha256=sha256,
                size_bytes=size_bytes,
                mime_type=mime_type,
                version=version,
            )

        existing.artifact_path = str(artifact_path)
        existing.sha256 = sha256
        existing.size_bytes = size_bytes
        existing.mime_type = mime_type
        session.flush()
        return existing

    def get(self, session: Session, artifact_id: UUID) -> TaskArtifact | None:
        return session.get(TaskArtifact, artifact_id)

    def list_for_task(self, session: Session, task_id: UUID) -> list[TaskArtifact]:
        statement = select(TaskArtifact).where(TaskArtifact.task_id == task_id).order_by(TaskArtifact.created_at)
        return list(session.scalars(statement))


class StageResultRepository:
    def create(
        self,
        session: Session,
        *,
        task_id: UUID,
        stage: Stage | str,
        stage_status: StageStatus | str,
        summary_json: dict[str, Any] | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
        duration_ms: int | None = None,
    ) -> StageResult:
        stage_value = _value(stage)
        existing = session.scalar(select(StageResult).where(StageResult.task_id == task_id, StageResult.stage == stage_value))
        if existing is not None:
            existing.stage_status = _value(stage_status)
            existing.summary_json = summary_json or {}
            existing.started_at = started_at
            existing.finished_at = finished_at
            existing.duration_ms = duration_ms
            session.flush()
            return existing

        result = StageResult(
            task_id=task_id,
            stage=stage_value,
            stage_status=_value(stage_status),
            summary_json=summary_json or {},
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
        )
        session.add(result)
        session.flush()
        return result

    def list_for_task(self, session: Session, task_id: UUID) -> list[StageResult]:
        statement = select(StageResult).where(StageResult.task_id == task_id).order_by(StageResult.created_at)
        return list(session.scalars(statement))


class QualityResultRepository:
    def create(
        self,
        session: Session,
        *,
        task_id: UUID,
        exposure_score: float | Decimal,
        color_score: float | Decimal,
        sharpness_score: float | Decimal,
        noise_score: float | Decimal,
        saturation_score: float | Decimal,
        underwater_cast_score: float | Decimal,
        overall_score: float | Decimal,
        decision: QualityDecision | str,
        reason_summary: str | None = None,
        detail_json: dict[str, Any] | None = None,
    ) -> QualityResult:
        existing = session.scalar(select(QualityResult).where(QualityResult.task_id == task_id))
        if existing is not None:
            existing.exposure_score = _decimal_score(exposure_score)
            existing.color_score = _decimal_score(color_score)
            existing.sharpness_score = _decimal_score(sharpness_score)
            existing.noise_score = _decimal_score(noise_score)
            existing.saturation_score = _decimal_score(saturation_score)
            existing.underwater_cast_score = _decimal_score(underwater_cast_score)
            existing.overall_score = _decimal_score(overall_score)
            existing.decision = QualityDecision(_value(decision)).value
            existing.reason_summary = reason_summary
            existing.detail_json = detail_json or {}
            session.flush()
            return existing

        result = QualityResult(
            task_id=task_id,
            exposure_score=_decimal_score(exposure_score),
            color_score=_decimal_score(color_score),
            sharpness_score=_decimal_score(sharpness_score),
            noise_score=_decimal_score(noise_score),
            saturation_score=_decimal_score(saturation_score),
            underwater_cast_score=_decimal_score(underwater_cast_score),
            overall_score=_decimal_score(overall_score),
            decision=QualityDecision(_value(decision)).value,
            reason_summary=reason_summary,
            detail_json=detail_json or {},
        )
        session.add(result)
        session.flush()
        return result

    def list_for_task(self, session: Session, task_id: UUID) -> list[QualityResult]:
        statement = select(QualityResult).where(QualityResult.task_id == task_id).order_by(QualityResult.created_at)
        return list(session.scalars(statement))


class FeedbackRecordRepository:
    def create(
        self,
        session: Session,
        *,
        task_id: UUID,
        user_action: FeedbackUserAction | str,
        rating: int | None = None,
        reason_tags: list[str] | None = None,
        ai_settings_json: dict[str, Any] | None = None,
        final_settings_json: dict[str, Any] | None = None,
        manual_edit_delta_json: dict[str, Any] | None = None,
        accepted: bool | None = None,
    ) -> FeedbackRecord:
        record = FeedbackRecord(
            task_id=task_id,
            user_action=FeedbackUserAction(_value(user_action)).value,
            rating=rating,
            reason_tags=reason_tags or [],
            ai_settings_json=ai_settings_json or {},
            final_settings_json=final_settings_json or {},
            manual_edit_delta_json=manual_edit_delta_json or {},
            accepted=accepted,
        )
        session.add(record)
        session.flush()
        return record

    def list_for_task(self, session: Session, task_id: UUID) -> list[FeedbackRecord]:
        statement = select(FeedbackRecord).where(FeedbackRecord.task_id == task_id).order_by(FeedbackRecord.created_at)
        return list(session.scalars(statement))


class LearningSampleRepository:
    def create(
        self,
        session: Session,
        *,
        task_id: UUID,
        sample_type: LearningSampleType | str,
        sample_status: LearningSampleStatus | str = LearningSampleStatus.PENDING,
        feedback_id: UUID | None = None,
        dataset_path: str | Path | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> LearningSample:
        sample = LearningSample(
            task_id=task_id,
            feedback_id=feedback_id,
            sample_type=LearningSampleType(_value(sample_type)).value,
            sample_status=LearningSampleStatus(_value(sample_status)).value,
            dataset_path=str(dataset_path) if dataset_path is not None else None,
            metadata_json=metadata_json or {},
        )
        session.add(sample)
        session.flush()
        return sample

    def list_for_task(self, session: Session, task_id: UUID) -> list[LearningSample]:
        statement = select(LearningSample).where(LearningSample.task_id == task_id).order_by(LearningSample.created_at)
        return list(session.scalars(statement))


def _decimal_score(value: float | Decimal) -> Decimal:
    return Decimal(str(round(float(value), 2)))


@dataclass(frozen=True)
class DbSmokeResult:
    task_id: UUID
    event_id: UUID
    read_back_ok: bool
    deleted: bool


def run_db_smoke_test(session: Session) -> DbSmokeResult:
    task_repo = ImageTaskRepository()
    event_repo = TaskEventRepository()

    task = task_repo.create(
        session,
        source_path="runtime/input/__tonevyra_db_smoke_test__.jpg",
        file_name="__tonevyra_db_smoke_test__.jpg",
        file_ext=".jpg",
        file_size_bytes=0,
        current_stage=Stage.WATCH,
    )
    event = event_repo.create(
        session,
        task_id=task.id,
        event_type=TaskEventType.TASK_CREATED,
        stage=Stage.WATCH,
        message="DB smoke test task created.",
        payload_json={"smoke_test": True},
    )

    fetched_task = task_repo.get(session, task.id)
    fetched_events = event_repo.list_for_task(session, task.id)
    read_back_ok = fetched_task is not None and any(item.id == event.id for item in fetched_events)

    task_repo.delete(session, task)
    deleted = task_repo.get(session, task.id) is None
    return DbSmokeResult(task_id=task.id, event_id=event.id, read_back_ok=read_back_ok, deleted=deleted)
