"""Local feedback capture and learning sample candidate registration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from tonevyra_agent.agent.loops import FEEDBACK_LOOP, make_loop_payload
from tonevyra_agent.core.config import Settings, get_settings
from tonevyra_agent.core.enums import (
    ArtifactType,
    FeedbackUserAction,
    LearningSampleStatus,
    LearningSampleType,
    Stage,
    TaskEventType,
    TaskStatus,
)
from tonevyra_agent.db.models import ImageTask
from tonevyra_agent.db.repositories import (
    FeedbackRecordRepository,
    ImageTaskRepository,
    LearningSampleRepository,
    StageResultRepository,
    TaskEventRepository,
)
from tonevyra_agent.learning.dataset_builder import build_training_sample_manifest
from tonevyra_agent.learning.schemas import (
    DevelopSettingsSnapshot,
    FeedbackCaptureRequest,
    FeedbackCaptureResult,
    ManualEditDelta,
    UserFeedback,
)
from tonevyra_agent.storage.artifacts import ArtifactRef, ArtifactStorage


@dataclass(frozen=True)
class PersistedFeedback:
    result: FeedbackCaptureResult
    feedback_artifact: ArtifactRef
    manual_edit_delta_artifact: ArtifactRef
    training_manifest_artifact: ArtifactRef | None


class FeedbackCaptureService:
    """Persist local user feedback and optional learning candidate evidence."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        storage: ArtifactStorage | None = None,
        task_repository: ImageTaskRepository | None = None,
        feedback_repository: FeedbackRecordRepository | None = None,
        learning_repository: LearningSampleRepository | None = None,
        stage_repository: StageResultRepository | None = None,
        event_repository: TaskEventRepository | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.storage = storage or ArtifactStorage(self.settings)
        self.task_repository = task_repository or ImageTaskRepository()
        self.feedback_repository = feedback_repository or FeedbackRecordRepository()
        self.learning_repository = learning_repository or LearningSampleRepository()
        self.stage_repository = stage_repository or StageResultRepository()
        self.event_repository = event_repository or TaskEventRepository()

    def capture_feedback(
        self,
        session: Session,
        *,
        task: ImageTask,
        request: FeedbackCaptureRequest,
    ) -> PersistedFeedback:
        """Store feedback artifacts, feedback_records row, and optional learning sample."""

        started_at = datetime.utcnow()
        task_status = TaskStatus(task.status)
        ai_settings_artifact = self.storage.save_json(
            session,
            task_id=task.id,
            artifact_type=ArtifactType.AI_SETTINGS,
            name="ai_settings.json",
            data=request.ai_settings.model_dump(mode="json"),
        )
        final_settings_artifact = self.storage.save_json(
            session,
            task_id=task.id,
            artifact_type=ArtifactType.FINAL_SETTINGS,
            name="final_settings.json",
            data=request.final_settings.model_dump(mode="json"),
        )
        delta = compute_manual_edit_delta(
            request.ai_settings,
            request.final_settings,
            ai_settings_ref=_artifact_summary(ai_settings_artifact),
            final_settings_ref=_artifact_summary(final_settings_artifact),
        )
        delta_artifact = self.storage.save_json(
            session,
            task_id=task.id,
            artifact_type=ArtifactType.MANUAL_EDIT_DELTA,
            name="manual_edit_delta.json",
            data=delta.model_dump(mode="json"),
        )

        feedback_payload = UserFeedback(
            task_id=str(task.id),
            user_action=request.user_action,
            rating=request.rating,
            reason_tags=request.reason_tags,
            accepted=request.accepted,
            approved_for_learning=request.approved_for_learning,
            comment=request.comment,
        )
        feedback_artifact = self.storage.save_json(
            session,
            task_id=task.id,
            artifact_type=ArtifactType.FEEDBACK_RECORD,
            name="user_feedback.json",
            data=feedback_payload.model_dump(mode="json"),
        )

        feedback_record = self.feedback_repository.create(
            session,
            task_id=task.id,
            user_action=request.user_action,
            rating=request.rating,
            reason_tags=feedback_payload.reason_tags,
            ai_settings_json=request.ai_settings.model_dump(mode="json"),
            final_settings_json=request.final_settings.model_dump(mode="json"),
            manual_edit_delta_json=delta.model_dump(mode="json"),
            accepted=request.accepted,
        )

        training_manifest_artifact: ArtifactRef | None = None
        learning_sample_id: str | None = None
        artifact_refs = {
            "ai_settings": ai_settings_artifact,
            "final_settings": final_settings_artifact,
            "manual_edit_delta": delta_artifact,
            "user_feedback": feedback_artifact,
        }

        if request.approved_for_learning:
            manifest = build_training_sample_manifest(
                task_id=str(task.id),
                feedback_id=str(feedback_record.id),
                sample_type=request.sample_type,
                approved_for_learning=True,
                artifacts=artifact_refs,
                metadata={
                    "user_action": request.user_action.value,
                    "reason_tags": feedback_payload.reason_tags,
                    "accepted": request.accepted,
                    "quality_decision": task.quality_decision,
                    "overall_score": float(task.overall_score) if task.overall_score is not None else None,
                },
            )
            training_manifest_artifact = self.storage.save_json(
                session,
                task_id=task.id,
                artifact_type=ArtifactType.TRAINING_SAMPLE_MANIFEST,
                name="training_sample_manifest.json",
                data=manifest.model_dump(mode="json"),
            )
            sample = self.learning_repository.create(
                session,
                task_id=task.id,
                feedback_id=feedback_record.id,
                sample_type=request.sample_type,
                sample_status=LearningSampleStatus.APPROVED,
                dataset_path=training_manifest_artifact.relative_path,
                metadata_json=manifest.model_dump(mode="json"),
            )
            learning_sample_id = str(sample.id)
            artifact_refs["training_sample_manifest"] = training_manifest_artifact

        finished_at = datetime.utcnow()
        artifact_payload_refs = {name: _artifact_summary(ref) for name, ref in artifact_refs.items()}
        self.stage_repository.create(
            session,
            task_id=task.id,
            stage=Stage.FEEDBACK,
            stage_status="SUCCEEDED",
            summary_json={
                "feedback_id": str(feedback_record.id),
                "learning_sample_id": learning_sample_id,
                "approved_for_learning": request.approved_for_learning,
                "artifact_refs": artifact_payload_refs,
            },
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=_duration_ms(started_at, finished_at),
        )
        self.event_repository.create(
            session,
            task_id=task.id,
            event_type=TaskEventType.TASK_FINALIZED,
            stage=Stage.FEEDBACK,
            message="Explicit local user feedback was captured.",
            payload_json=make_loop_payload(
                loop_name=FEEDBACK_LOOP,
                event_type=TaskEventType.TASK_FINALIZED.value,
                from_status=task_status,
                to_status=task_status,
                reason="explicit local feedback captured",
                evidence_artifacts=list(artifact_payload_refs.values()),
                user_action=request.user_action.value,
                approved_for_learning=request.approved_for_learning,
                learning_sample_id=learning_sample_id,
            ),
        )
        result = FeedbackCaptureResult(
            task_id=str(task.id),
            feedback_id=str(feedback_record.id),
            learning_sample_id=learning_sample_id,
            artifact_refs=artifact_payload_refs,
        )
        return PersistedFeedback(
            result=result,
            feedback_artifact=feedback_artifact,
            manual_edit_delta_artifact=delta_artifact,
            training_manifest_artifact=training_manifest_artifact,
        )


def compute_manual_edit_delta(
    ai_settings: DevelopSettingsSnapshot,
    final_settings: DevelopSettingsSnapshot,
    *,
    ai_settings_ref: dict[str, Any] | None = None,
    final_settings_ref: dict[str, Any] | None = None,
) -> ManualEditDelta:
    numeric_delta: dict[str, float] = {}
    changed_values: dict[str, dict[str, Any]] = {}
    keys = sorted(set(ai_settings.settings) | set(final_settings.settings))

    for key in keys:
        ai_value = ai_settings.settings.get(key)
        final_value = final_settings.settings.get(key)
        if ai_value == final_value:
            continue
        changed_values[key] = {"ai": ai_value, "final": final_value}
        if isinstance(ai_value, (int, float)) and isinstance(final_value, (int, float)):
            numeric_delta[key] = round(float(final_value) - float(ai_value), 6)

    return ManualEditDelta(
        changed=bool(changed_values),
        numeric_delta=numeric_delta,
        changed_values=changed_values,
        ai_settings_ref=ai_settings_ref,
        final_settings_ref=final_settings_ref,
    )


def capture_task_feedback(
    session: Session,
    *,
    task: ImageTask,
    request: FeedbackCaptureRequest,
    settings: Settings | None = None,
    storage: ArtifactStorage | None = None,
) -> PersistedFeedback:
    return FeedbackCaptureService(settings=settings, storage=storage).capture_feedback(
        session,
        task=task,
        request=request,
    )


def _artifact_summary(artifact: ArtifactRef) -> dict[str, Any]:
    return {
        "artifact_id": str(artifact.artifact_id),
        "artifact_type": artifact.artifact_type,
        "artifact_path": artifact.relative_path,
        "sha256": artifact.sha256,
        "size_bytes": artifact.size_bytes,
    }


def _duration_ms(started_at: datetime, finished_at: datetime) -> int:
    return int((finished_at - started_at).total_seconds() * 1000)
