"""Deterministic Correction Planner with safe Lightroom adjustment clamps."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from tonevyra_agent.core.config import Settings, get_settings
from tonevyra_agent.core.enums import ArtifactType, ErrorCode, Stage, StageStatus, TaskEventType, TaskStatus
from tonevyra_agent.core.errors import TonevyraError
from tonevyra_agent.correction.schemas import ADJUSTMENT_RANGES, CorrectionPlan
from tonevyra_agent.db.models import ImageTask
from tonevyra_agent.db.repositories import ImageTaskRepository, StageResultRepository, TaskEventRepository
from tonevyra_agent.storage.artifacts import ArtifactRef, ArtifactStorage
from tonevyra_agent.vision.schemas import VisionAnalysisResult


PROCESSING_LOOP_NAME = "processing_loop"
SEVERE_RISK_FLAGS = {
    "damaged_file",
    "corrupted_image",
    "heavy_haze",
    "severe_recovery_required",
}


@dataclass(frozen=True)
class CorrectionPlannerResult:
    plan: CorrectionPlan
    artifact: ArtifactRef


class CorrectionPlanner:
    """Convert validated vision analysis into a safe, clamped correction plan."""

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

    def create_plan(self, analysis: VisionAnalysisResult) -> CorrectionPlan:
        return create_correction_plan(
            analysis,
            review_confidence_threshold=self.settings.planner_review_confidence_threshold,
        )

    def plan_from_artifact(
        self,
        session: Session,
        *,
        task: ImageTask,
        vision_artifact: ArtifactRef,
    ) -> CorrectionPlannerResult:
        started_at = datetime.utcnow()
        from_status = task.status
        payload = self.storage.load_json(vision_artifact)
        analysis = VisionAnalysisResult.model_validate(payload)

        try:
            plan = self.create_plan(analysis)
        except Exception as exc:
            self.task_repository.mark_failed(
                session,
                task,
                error_code=ErrorCode.CORRECTION_PLAN_FAILED,
                error_message="Correction Planner failed to produce a valid plan.",
                failed_stage=Stage.CORRECTION_PLAN,
            )
            raise TonevyraError(
                code=ErrorCode.CORRECTION_PLAN_FAILED,
                message="Correction Planner failed to produce a valid plan.",
                failed_stage=Stage.CORRECTION_PLAN.value,
            ) from exc

        artifact = self.storage.save_json(
            session,
            task_id=task.id,
            artifact_type=ArtifactType.CORRECTION_PLAN,
            name="correction_plan.json",
            data=plan.model_dump(mode="json"),
        )

        finished_at = datetime.utcnow()
        stage_summary = {
            **plan.summary(),
            "correction_plan_artifact": _artifact_summary(artifact),
            "vision_structured_artifact": _artifact_summary(vision_artifact),
        }
        self.stage_repository.create(
            session,
            task_id=task.id,
            stage=Stage.CORRECTION_PLAN,
            stage_status=StageStatus.SUCCEEDED,
            summary_json=stage_summary,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=_duration_ms(started_at, finished_at),
        )
        self.task_repository.update_status(
            session,
            task,
            status=TaskStatus.CORRECTION_PLANNED,
            current_stage=Stage.CORRECTION_PLAN,
        )
        self.event_repository.create(
            session,
            task_id=task.id,
            event_type=TaskEventType.CORRECTION_PLANNED,
            stage=Stage.CORRECTION_PLAN,
            message="Correction Planner created a safe clamped Lightroom adjustment plan.",
            payload_json={
                "loop_name": PROCESSING_LOOP_NAME,
                "loop_iteration": 1,
                "event_type": TaskEventType.CORRECTION_PLANNED.value,
                "from_status": from_status,
                "to_status": TaskStatus.CORRECTION_PLANNED.value,
                "reason": "correction_plan artifact saved",
                "requires_review": plan.requires_review,
                "clamped": plan.clamped,
                "evidence_artifacts": [
                    _artifact_summary(vision_artifact),
                    _artifact_summary(artifact),
                ],
            },
        )
        return CorrectionPlannerResult(plan=plan, artifact=artifact)


def create_correction_plan(
    analysis: VisionAnalysisResult,
    *,
    review_confidence_threshold: float = 0.7,
) -> CorrectionPlan:
    raw_adjustments, reason_parts = _map_analysis_to_adjustments(analysis)
    adjustments, clamped = _clamp_adjustments(raw_adjustments)
    severe_risk = any(flag in SEVERE_RISK_FLAGS for flag in analysis.risk_flags)
    requires_review = (
        analysis.requires_review
        or not analysis.usable
        or analysis.confidence < review_confidence_threshold
        or severe_risk
        or clamped
    )
    if analysis.risk_flags:
        reason_parts.append(f"risk_flags={','.join(analysis.risk_flags)}")
    if clamped:
        reason_parts.append("one or more adjustments were clamped")
    if requires_review:
        reason_parts.append("human review required")

    return CorrectionPlan(
        base_preset=_base_preset(analysis),
        style_target=_style_target(analysis),
        adjustments_json=adjustments,
        confidence=analysis.confidence,
        requires_review=requires_review,
        clamped=clamped,
        reason_summary="; ".join(reason_parts),
        source={
            "scene_type": analysis.scene_type,
            "main_subject": analysis.main_subject,
            "model_backend": analysis.model_backend,
            "model_name": analysis.model_name,
        },
    )


def plan_task_correction(
    session: Session,
    *,
    task: ImageTask,
    vision_artifact: ArtifactRef,
    settings: Settings | None = None,
    storage: ArtifactStorage | None = None,
) -> CorrectionPlannerResult:
    planner = CorrectionPlanner(settings=settings, storage=storage)
    return planner.plan_from_artifact(session, task=task, vision_artifact=vision_artifact)


def _map_analysis_to_adjustments(analysis: VisionAnalysisResult) -> tuple[dict[str, float], list[str]]:
    issues = analysis.issues.model_dump(exclude_none=True)
    adjustments = _zero_adjustments()
    reasons: list[str] = [f"scene={analysis.scene_type}", f"confidence={analysis.confidence:.2f}"]

    exposure = _issue_value(issues, "exposure")
    if "severely_underexposed" in exposure:
        adjustments["exposure"] += 2.8
        adjustments["shadows"] += 100
        adjustments["highlights"] -= 90
        reasons.append("severe underexposure recovery")
    elif "slightly_underexposed" in exposure:
        adjustments["exposure"] += 0.25
        adjustments["shadows"] += 24
        adjustments["highlights"] -= 16
        reasons.append("slightly underexposed image")
    elif "underexposed" in exposure:
        adjustments["exposure"] += 0.45
        adjustments["shadows"] += 38
        adjustments["highlights"] -= 22
        reasons.append("underexposed image")
    elif "overexposed" in exposure:
        adjustments["exposure"] -= 0.35
        adjustments["highlights"] -= 35
        reasons.append("overexposed image")

    contrast = _issue_value(issues, "contrast")
    if "very_low" in contrast:
        adjustments["contrast"] += 75
        adjustments["blacks"] -= 20
        reasons.append("very low contrast")
    elif "low" in contrast:
        adjustments["contrast"] += 18
        adjustments["blacks"] -= 8
        reasons.append("low contrast")
    elif "high" in contrast:
        adjustments["contrast"] -= 10
        reasons.append("high contrast")

    color_cast = _issue_value(issues, "color_cast")
    if "blue_green_extreme" in color_cast:
        adjustments["temperature_delta"] += 2600
        adjustments["tint"] += 70
        adjustments["vibrance"] += 75
        reasons.append("extreme blue-green cast")
    elif "blue_green_strong" in color_cast:
        adjustments["temperature_delta"] += 1200
        adjustments["tint"] += 18
        adjustments["vibrance"] += 24
        reasons.append("strong blue-green cast")
    elif "blue_green" in color_cast:
        adjustments["temperature_delta"] += 800
        adjustments["tint"] += 12
        adjustments["vibrance"] += 18
        reasons.append("blue-green cast")
    elif "warm" in color_cast:
        adjustments["temperature_delta"] -= 350
        reasons.append("warm color cast")

    haze = _issue_value(issues, "haze") or _issue_value(issues, "haze_turbidity")
    if "extreme" in haze:
        adjustments["dehaze"] += 50
        adjustments["clarity"] += 42
        adjustments["texture"] += 42
        reasons.append("extreme haze")
    elif "heavy" in haze:
        adjustments["dehaze"] += 24
        adjustments["clarity"] += 14
        adjustments["texture"] += 10
        reasons.append("heavy haze")
    elif "medium" in haze:
        adjustments["dehaze"] += 12
        adjustments["clarity"] += 8
        adjustments["texture"] += 5
        reasons.append("medium haze")

    sharpness = _issue_value(issues, "sharpness")
    if "soft" in sharpness:
        adjustments["sharpening"] += 95
        adjustments["texture"] += 12
        reasons.append("soft image")
    elif "acceptable" in sharpness:
        adjustments["sharpening"] += 25

    noise = _issue_value(issues, "noise")
    if "high" in noise:
        adjustments["noise_reduction"] += 75
        reasons.append("high noise")
    elif "medium" in noise:
        adjustments["noise_reduction"] += 25
        reasons.append("medium noise")
    elif "low" in noise:
        adjustments["noise_reduction"] += 10

    if "underwater" in analysis.scene_type:
        adjustments["saturation"] -= 2
        adjustments["whites"] += 8

    return adjustments, reasons


def _clamp_adjustments(adjustments: dict[str, float]) -> tuple[dict[str, float], bool]:
    clamped = False
    result: dict[str, float] = {}
    for key, value in adjustments.items():
        minimum, maximum = ADJUSTMENT_RANGES[key]
        safe_value = max(minimum, min(maximum, value))
        if safe_value != value:
            clamped = True
        result[key] = round(safe_value, 3)
    return result, clamped


def _zero_adjustments() -> dict[str, float]:
    return {key: 0.0 for key in ADJUSTMENT_RANGES}


def _base_preset(analysis: VisionAnalysisResult) -> str:
    if "underwater" in analysis.scene_type:
        return "Tonevyra Underwater Standard"
    return "Tonevyra Neutral Standard"


def _style_target(analysis: VisionAnalysisResult) -> str:
    if analysis.edit_intent:
        return analysis.edit_intent
    if "underwater" in analysis.scene_type:
        return "natural_clean_underwater_recovery"
    return "natural_clean"


def _issue_value(issues: dict[str, Any], key: str) -> str:
    value = issues.get(key)
    return str(value).lower() if value is not None else ""


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
