"""Quality Gate orchestration for exported Tonevyra AI images."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from tonevyra_agent.core.config import Settings, get_settings
from tonevyra_agent.core.enums import ArtifactType, ErrorCode, QualityDecision, Stage, StageStatus, TaskEventType, TaskStatus
from tonevyra_agent.core.errors import TonevyraError
from tonevyra_agent.correction.schemas import CorrectionPlan
from tonevyra_agent.db.models import ImageTask
from tonevyra_agent.db.repositories import (
    ImageTaskRepository,
    QualityResultRepository,
    StageResultRepository,
    TaskEventRepository,
)
from tonevyra_agent.quality.schemas import QualityDetail
from tonevyra_agent.quality.scoring import decide_from_score, score_export_image, thresholds_from_settings, weights_from_settings
from tonevyra_agent.storage.artifacts import ArtifactRef, ArtifactStorage


QUALITY_LOOP_NAME = "quality_loop"


@dataclass(frozen=True)
class QualityGateResult:
    detail: QualityDetail | None
    artifact: ArtifactRef | None
    success: bool
    decision: QualityDecision
    error_code: ErrorCode | None = None
    error_message: str | None = None


class QualityGate:
    """Evaluate a local export and finalize the task with a bounded quality decision."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        storage: ArtifactStorage | None = None,
        task_repository: ImageTaskRepository | None = None,
        stage_repository: StageResultRepository | None = None,
        event_repository: TaskEventRepository | None = None,
        quality_repository: QualityResultRepository | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.storage = storage or ArtifactStorage(self.settings)
        self.task_repository = task_repository or ImageTaskRepository()
        self.stage_repository = stage_repository or StageResultRepository()
        self.event_repository = event_repository or TaskEventRepository()
        self.quality_repository = quality_repository or QualityResultRepository()

    def evaluate_export(
        self,
        session: Session,
        *,
        task: ImageTask,
        export_path: str | Path | None = None,
        export_artifact: ArtifactRef | None = None,
        correction_plan_artifact: ArtifactRef | None = None,
    ) -> QualityGateResult:
        """Score the export, persist quality evidence, and set the final task status."""

        started_at = datetime.utcnow()
        from_status = task.status
        resolved_export_path = self._resolve_export_path(export_path=export_path, export_artifact=export_artifact)

        try:
            scores, metrics, score_reasons = score_export_image(resolved_export_path, settings=self.settings)
            thresholds = thresholds_from_settings(self.settings)
            weights = weights_from_settings(self.settings)
            decision = decide_from_score(scores.overall_score, thresholds=thresholds)
            source, override_reasons = self._source_context(correction_plan_artifact)
            decision = _apply_review_cap(decision, override_reasons)
            reasons = [*score_reasons, *override_reasons]
            # AGENTS.md 32.7: legacy worker path expresses SOURCE_LIMITED as
            # FAILED + failure_class (no new status enum / DB constraint).
            failure_class = _detect_failure_class(decision, metrics)
            if failure_class:
                source = {**source, "failure_class": failure_class}
                reasons.append(_failure_class_reason(failure_class))
            reason_summary = _reason_summary(decision, scores.overall_score, reasons)
            detail = QualityDetail(
                task_id=str(task.id),
                export_path=str(resolved_export_path.resolve()),
                scores=scores,
                decision=decision,
                reason_summary=reason_summary,
                reasons=reasons,
                thresholds=thresholds,
                weights=weights,
                metrics=metrics,
                source=source,
            )
        except TonevyraError as exc:
            return self._record_failure(
                session,
                task=task,
                started_at=started_at,
                from_status=from_status,
                error_code=exc.code,
                error_message=exc.message,
            )
        except Exception as exc:
            return self._record_failure(
                session,
                task=task,
                started_at=started_at,
                from_status=from_status,
                error_code=ErrorCode.QUALITY_CHECK_FAILED,
                error_message=f"Quality Gate failed: {exc}",
            )

        artifact = self.storage.save_json(
            session,
            task_id=task.id,
            artifact_type=ArtifactType.QUALITY_DETAIL,
            name="quality_detail.json",
            data=detail.model_dump(mode="json"),
        )
        finished_at = datetime.utcnow()

        self.quality_repository.create(
            session,
            task_id=task.id,
            exposure_score=detail.scores.exposure_score,
            color_score=detail.scores.color_score,
            sharpness_score=detail.scores.sharpness_score,
            noise_score=detail.scores.noise_score,
            saturation_score=detail.scores.saturation_score,
            underwater_cast_score=detail.scores.underwater_cast_score,
            overall_score=detail.scores.overall_score,
            decision=detail.decision,
            reason_summary=detail.reason_summary,
            detail_json={
                "quality_detail_artifact": _artifact_summary(artifact),
                "scores": detail.scores.model_dump(mode="json"),
                "reasons": detail.reasons,
            },
        )
        self.stage_repository.create(
            session,
            task_id=task.id,
            stage=Stage.QUALITY,
            stage_status=StageStatus.SUCCEEDED,
            summary_json={
                "decision": detail.decision.value,
                "overall_score": detail.scores.overall_score,
                "reason_summary": detail.reason_summary,
                "quality_detail_artifact": _artifact_summary(artifact),
                "export_artifact": _artifact_summary(export_artifact) if export_artifact else None,
            },
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=_duration_ms(started_at, finished_at),
        )
        self.task_repository.finalize_quality(
            session,
            task,
            decision=detail.decision,
            overall_score=detail.scores.overall_score,
        )
        self.event_repository.create(
            session,
            task_id=task.id,
            event_type=TaskEventType.QUALITY_CHECK_DONE,
            stage=Stage.QUALITY,
            message="Quality Gate scored the export and finalized the task.",
            payload_json={
                "loop_name": QUALITY_LOOP_NAME,
                "loop_iteration": 1,
                "event_type": TaskEventType.QUALITY_CHECK_DONE.value,
                "from_status": from_status,
                "to_status": detail.decision.value,
                "reason": detail.reason_summary,
                "overall_score": detail.scores.overall_score,
                "decision": detail.decision.value,
                "evidence_artifacts": [_artifact_summary(artifact)],
            },
        )
        return QualityGateResult(detail=detail, artifact=artifact, success=True, decision=detail.decision)

    def _resolve_export_path(
        self,
        *,
        export_path: str | Path | None,
        export_artifact: ArtifactRef | None,
    ) -> Path:
        if export_path is not None:
            return Path(export_path)
        if export_artifact is not None:
            return export_artifact.absolute_path
        raise TonevyraError(
            code=ErrorCode.EXPORT_FILE_MISSING,
            message="Quality Gate requires an export path or export artifact.",
            failed_stage=Stage.QUALITY.value,
        )

    def _source_context(self, correction_plan_artifact: ArtifactRef | None) -> tuple[dict[str, Any], list[str]]:
        if correction_plan_artifact is None:
            return {}, []

        payload = self.storage.load_json(correction_plan_artifact)
        plan = CorrectionPlan.model_validate(payload)
        reasons: list[str] = []
        if plan.requires_review:
            reasons.append("correction plan requires review")
        if plan.clamped:
            reasons.append("correction plan contains clamped adjustments")
        return {
            "correction_plan_artifact": _artifact_summary(correction_plan_artifact),
            "planner_version": plan.planner_version,
            "planner_confidence": plan.confidence,
            "requires_review": plan.requires_review,
            "clamped": plan.clamped,
        }, reasons

    def _record_failure(
        self,
        session: Session,
        *,
        task: ImageTask,
        started_at: datetime,
        from_status: str,
        error_code: ErrorCode,
        error_message: str,
    ) -> QualityGateResult:
        finished_at = datetime.utcnow()
        self.stage_repository.create(
            session,
            task_id=task.id,
            stage=Stage.QUALITY,
            stage_status=StageStatus.FAILED,
            summary_json={
                "error_code": error_code.value,
                "error_message": error_message,
            },
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=_duration_ms(started_at, finished_at),
        )
        self.task_repository.mark_failed(
            session,
            task,
            error_code=error_code,
            error_message=error_message,
            failed_stage=Stage.QUALITY,
        )
        self.event_repository.create(
            session,
            task_id=task.id,
            event_type=TaskEventType.TASK_FAILED,
            stage=Stage.QUALITY,
            message="Quality Gate failed before producing a final quality result.",
            payload_json={
                "loop_name": QUALITY_LOOP_NAME,
                "loop_iteration": 1,
                "event_type": TaskEventType.TASK_FAILED.value,
                "from_status": from_status,
                "to_status": TaskStatus.FAILED.value,
                "reason": error_message,
                "error_code": error_code.value,
                "evidence_artifacts": [],
            },
        )
        return QualityGateResult(
            detail=None,
            artifact=None,
            success=False,
            decision=QualityDecision.FAILED,
            error_code=error_code,
            error_message=error_message,
        )


def evaluate_export_quality(
    session: Session,
    *,
    task: ImageTask,
    export_path: str | Path | None = None,
    export_artifact: ArtifactRef | None = None,
    correction_plan_artifact: ArtifactRef | None = None,
    settings: Settings | None = None,
    storage: ArtifactStorage | None = None,
) -> QualityGateResult:
    gate = QualityGate(settings=settings, storage=storage)
    return gate.evaluate_export(
        session,
        task=task,
        export_path=export_path,
        export_artifact=export_artifact,
        correction_plan_artifact=correction_plan_artifact,
    )


def _apply_review_cap(decision: QualityDecision, review_reasons: list[str]) -> QualityDecision:
    if decision == QualityDecision.PASS and review_reasons:
        return QualityDecision.REVIEW_REQUIRED
    return decision


# Thresholds for classifying an unrecoverable source. Deep-water captures lose the
# red channel entirely; once red is this low with a strong residual blue-green cast,
# white balance cannot restore color and the failure is the source's, not the agent's.
_SOURCE_LIMITED_RED_MAX = 45.0
_SOURCE_LIMITED_CAST_MIN = 55.0


def _detect_failure_class(decision: QualityDecision, metrics: dict[str, Any]) -> str | None:
    """Return a failure_class for a FAILED export, or None.

    Distinguishes a source limitation (irrecoverable capture) from a correctable
    quality miss, without introducing a new status value.
    """

    if decision != QualityDecision.FAILED:
        return None
    underwater = metrics.get("underwater_cast", {}) if isinstance(metrics, dict) else {}
    red_mean = float(underwater.get("red_mean", 255.0))
    blue_green_minus_red = float(underwater.get("blue_green_minus_red", 0.0))
    if red_mean <= _SOURCE_LIMITED_RED_MAX and blue_green_minus_red >= _SOURCE_LIMITED_CAST_MIN:
        return "SOURCE_LIMITED_UNDERWATER_RED_CHANNEL_LOSS"
    return None


def _failure_class_reason(failure_class: str) -> str:
    if failure_class == "SOURCE_LIMITED_UNDERWATER_RED_CHANNEL_LOSS":
        return (
            "source-limited: underwater red-channel loss is not recoverable by white "
            "balance (failure_class=SOURCE_LIMITED_UNDERWATER_RED_CHANNEL_LOSS)"
        )
    return f"failure_class={failure_class}"


def _reason_summary(decision: QualityDecision, overall_score: float, reasons: list[str]) -> str:
    prefix = f"{decision.value} from overall_score={overall_score:.2f}"
    if not reasons:
        return prefix
    return f"{prefix}; " + "; ".join(reasons)


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
