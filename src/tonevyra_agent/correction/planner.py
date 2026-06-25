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
# Disabled by product decision: model/recipe numeric suggestions must not overwrite
# planner-owned correction values after the planner has judged the analysis.
# from tonevyra_agent.learning.recipe_calibration import apply_underwater_recipe_calibration
from tonevyra_agent.semantic.local_adjustment import LocalAdjustmentPlanner
from tonevyra_agent.semantic.schemas import SemanticAnalysis, SemanticRegion
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
    comparison_artifact: ArtifactRef | None = None


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
        preview_artifact: ArtifactRef | None = None,
    ) -> CorrectionPlannerResult:
        started_at = datetime.utcnow()
        from_status = task.status
        payload = self.storage.load_json(vision_artifact)
        analysis = VisionAnalysisResult.model_validate(payload)

        use_target = (self.settings.planner_mode or "legacy").lower() == "target_based"
        plan: CorrectionPlan | None = None
        decision_log_data: dict[str, Any] | None = None
        degraded_reason: str | None = None

        if use_target and preview_artifact is not None:
            try:
                from tonevyra_agent.correction.target_based import plan_with_targets

                preview_path = self.storage.resolve_path(preview_artifact)
                plan, decision_log = plan_with_targets(
                    analysis=analysis,
                    preview_path=preview_path,
                    review_confidence_threshold=self.settings.planner_review_confidence_threshold,
                )
                decision_log_data = decision_log.to_log()
            except Exception as exc:  # noqa: BLE001 - degrade to legacy, never crash planning
                plan = None
                degraded_reason = f"target_based planner unavailable; degraded to legacy: {exc}"
        elif use_target and preview_artifact is None:
            degraded_reason = "target_based planner requires a preview artifact; degraded to legacy"

        if plan is None:
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
            if degraded_reason is not None:
                # A degraded target_based run must surface for human review.
                plan = plan.model_copy(
                    update={
                        "requires_review": True,
                        "reason_summary": f"{plan.reason_summary}; {degraded_reason}",
                    }
                )

        artifact = self.storage.save_json(
            session,
            task_id=task.id,
            artifact_type=ArtifactType.CORRECTION_PLAN,
            name="correction_plan.json",
            data=plan.model_dump(mode="json"),
        )
        if decision_log_data is not None:
            comparison_artifact = self.storage.save_json(
                session,
                task_id=task.id,
                artifact_type=ArtifactType.CORRECTION_PLAN,
                name="correction_decision_log.json",
                data=decision_log_data,
                version=2,
            )
            secondary_summary_key = "correction_decision_log_artifact"
        else:
            comparison_log = build_model_planner_comparison_log(analysis=analysis, plan=plan)
            comparison_artifact = self.storage.save_json(
                session,
                task_id=task.id,
                artifact_type=ArtifactType.CORRECTION_PLAN,
                name="model_planner_comparison_log.json",
                data=comparison_log,
                version=2,
            )
            secondary_summary_key = "model_planner_comparison_log_artifact"

        finished_at = datetime.utcnow()
        stage_summary = {
            **plan.summary(),
            "planner_mode": "target_based" if decision_log_data is not None else "legacy",
            "correction_plan_artifact": _artifact_summary(artifact),
            secondary_summary_key: _artifact_summary(comparison_artifact),
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
                    _artifact_summary(comparison_artifact),
                ],
            },
        )
        return CorrectionPlannerResult(plan=plan, artifact=artifact, comparison_artifact=comparison_artifact)


def create_correction_plan(
    analysis: VisionAnalysisResult,
    *,
    review_confidence_threshold: float = 0.7,
) -> CorrectionPlan:
    raw_adjustments, reason_parts = _map_analysis_to_adjustments(analysis)
    adjustments, clamped = _clamp_adjustments(raw_adjustments)
    local_adjustments = _build_local_adjustments(analysis=analysis, global_adjustments=adjustments)
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
        local_adjustments_json=local_adjustments,
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


def build_model_planner_comparison_log(
    *,
    analysis: VisionAnalysisResult,
    plan: CorrectionPlan,
) -> dict[str, Any]:
    """Build a durable comparison between model numeric suggestions and Planner output.

    This is evidence for temporary A/B analysis only. The model values remain
    advisory and are never marked as directly executable Lightroom settings.
    """

    model_suggested = (
        analysis.correction_intents.model_dump(exclude_none=True) if analysis.correction_intents is not None else {}
    )
    planner_validated = dict(plan.adjustments_json)
    compared_keys = sorted(set(model_suggested) | set(planner_validated))
    differences = []
    for key in compared_keys:
        model_value = model_suggested.get(key)
        planner_value = planner_validated.get(key)
        if model_value is None:
            status = "planner_added"
        elif planner_value is None:
            status = "planner_removed_or_translated"
        elif float(model_value) == float(planner_value):
            status = "unchanged"
        else:
            status = _comparison_status(key=key, model_value=float(model_value), planner_value=float(planner_value))
        differences.append(
            {
                "key": key,
                "model_suggested_value": model_value,
                "planner_validated_value": planner_value,
                "status": status,
            }
        )

    return {
        "schema_version": "tonevyra.model_planner_comparison_log.v1",
        "purpose": "temporary_quality_comparison",
        "direct_model_application_allowed": False,
        "model_suggestions_used_by_planner": False,
        "lightroom_applied_source": "planner_validated_adjustments",
        "model_backend": analysis.model_backend,
        "model_name": analysis.model_name,
        "scene_type": analysis.scene_type,
        "confidence": analysis.confidence,
        "model_suggested_adjustments": model_suggested,
        "planner_validated_adjustments": planner_validated,
        "planner_version": plan.planner_version,
        "planner_clamped": plan.clamped,
        "requires_review": plan.requires_review,
        "reason_summary": plan.reason_summary,
        "differences": differences,
    }


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
    is_underwater = "underwater" in analysis.scene_type.lower()
    reasons: list[str] = [f"scene={analysis.scene_type}", f"confidence={analysis.confidence:.2f}"]

    exposure = _issue_value(issues, "exposure")
    if "severely_underexposed" in exposure:
        adjustments["exposure"] += 2.8
        adjustments["shadows"] += 100
        adjustments["highlights"] -= 90
        reasons.append("severe underexposure recovery")
    elif "slightly_underexposed" in exposure:
        adjustments["exposure"] += 0.45
        adjustments["shadows"] += 34
        adjustments["highlights"] -= 12
        reasons.append("slightly underexposed image")
    elif "underexposed" in exposure:
        adjustments["exposure"] += 1.15
        adjustments["shadows"] += 65
        adjustments["highlights"] -= 18
        adjustments["whites"] += 8
        reasons.append("underexposed image; stronger exposure recovery applied")
    elif "severely_overexposed" in exposure:
        adjustments["exposure"] -= 0.9
        adjustments["highlights"] -= 70
        adjustments["whites"] -= 25
        reasons.append("severe overexposure recovery")
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

    # color_cast: canonical vocabulary (cool/strong_cool/warm/strong_warm/green/magenta)
    # plus legacy blue_green_* tokens. Lightroom convention:
    #   temperature_delta +  -> warmer (removes cool/blue cast)
    #   temperature_delta -  -> cooler (removes warm cast)
    #   tint +  -> magenta (removes green cast); tint -  -> green (removes magenta cast)
    color_cast = _issue_value(issues, "color_cast")
    if _match(color_cast, "strong_cool", "blue_green_strong", "blue_green_extreme") or (
        is_underwater and "cool" in color_cast
    ):
        # Underwater scenes lose the red channel; push warm white balance hard and
        # add magenta tint + vibrance to recover what white balance can restore.
        adjustments["temperature_delta"] += 3000
        adjustments["tint"] += 20
        adjustments["vibrance"] += 30
        reasons.append("strong cool/underwater cast correction (warm up)")
    elif _match(color_cast, "cool", "blue_green"):
        adjustments["temperature_delta"] += 950
        adjustments["tint"] += 8
        adjustments["vibrance"] += 14
        reasons.append("cool cast correction (warm up)")
    elif "strong_warm" in color_cast:
        adjustments["temperature_delta"] -= 650
        reasons.append("strong warm cast correction (cool down)")
    elif "warm" in color_cast:
        adjustments["temperature_delta"] -= 320
        reasons.append("warm cast correction (cool down)")
    elif "magenta" in color_cast:
        adjustments["tint"] -= 16
        reasons.append("magenta cast correction (toward green)")
    elif "green" in color_cast:
        adjustments["tint"] += 16
        reasons.append("green cast correction (toward magenta)")

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
    if "very_soft" in sharpness:
        adjustments["sharpening"] += 75
        adjustments["texture"] += 15
        reasons.append("very soft image")
    elif "soft" in sharpness:
        adjustments["sharpening"] += 45
        adjustments["texture"] += 10
        reasons.append("soft image")
    elif "acceptable" in sharpness:
        adjustments["sharpening"] += 25

    noise = _issue_value(issues, "noise")
    if "high" in noise:
        adjustments["noise_reduction"] += 55
        reasons.append("high noise")
    elif _match(noise, "moderate", "medium"):
        adjustments["noise_reduction"] += 30
        reasons.append("moderate noise")
    elif "low" in noise:
        adjustments["noise_reduction"] += 10

    if is_underwater:
        adjustments["saturation"] -= 2
        adjustments["whites"] += 8

    _apply_scene_quality_floor(
        analysis=analysis,
        issues=issues,
        adjustments=adjustments,
        reasons=reasons,
        is_underwater=is_underwater,
    )
    # Product rule: model/recipe values are evidence only. Keep this disabled so
    # planner-owned values are not overwritten after semantic issue mapping.
    # recipe_calibration = apply_underwater_recipe_calibration(analysis, adjustments, settings=get_settings())
    # if recipe_calibration is not None:
    #     summary = recipe_calibration.summary()
    #     reasons.append(
    #         "80-point underwater reference recipe validation "
    #         f"{'passed' if summary['within_tolerance'] else 'corrected'} "
    #         f"({summary['recipe_name']}, corrected_keys={','.join(summary['corrected_keys'])})"
    #     )

    return adjustments, reasons


def _apply_scene_quality_floor(
    *,
    analysis: VisionAnalysisResult,
    issues: dict[str, Any],
    adjustments: dict[str, float],
    reasons: list[str],
    is_underwater: bool,
) -> None:
    color_cast = _issue_value(issues, "color_cast")
    exposure = _issue_value(issues, "exposure")
    subject_text = f"{analysis.scene_type} {analysis.main_subject} {analysis.edit_intent or ''}".lower()

    if "underexposed" in exposure:
        _apply_dark_photo_recovery_floor(adjustments, exposure=exposure)
        reasons.append("dark photo planner exposure floor applied")

    if is_underwater and _match(color_cast, "strong_cool", "blue_green_strong", "blue_green_extreme", "cool"):
        _apply_underwater_recovery_floor(adjustments)
        reasons.append("underwater planner-owned quality recovery floor applied")

    if _match(subject_text, "fire", "flame", "campfire", "bonfire", "embers", "cooking pot"):
        _apply_warm_fire_reference_style(adjustments)
        reasons.append("warm fire reference style applied")


def _apply_dark_photo_recovery_floor(adjustments: dict[str, float], *, exposure: str) -> None:
    """Give dark captures enough global lift before scene-specific styling."""

    if "severely_underexposed" in exposure:
        adjustments["exposure"] = max(adjustments["exposure"], 2.2)
        adjustments["shadows"] = max(adjustments["shadows"], 90.0)
        adjustments["highlights"] = min(adjustments["highlights"], -60.0)
        adjustments["whites"] = max(adjustments["whites"], 18.0)
        return

    if "slightly_underexposed" in exposure:
        adjustments["exposure"] = max(adjustments["exposure"], 0.85)
        adjustments["shadows"] = max(adjustments["shadows"], 50.0)
        adjustments["highlights"] = min(adjustments["highlights"], -20.0)
        adjustments["whites"] = max(adjustments["whites"], 8.0)
        return

    adjustments["exposure"] = max(adjustments["exposure"], 1.35)
    adjustments["shadows"] = max(adjustments["shadows"], 75.0)
    adjustments["highlights"] = min(adjustments["highlights"], -35.0)
    adjustments["whites"] = max(adjustments["whites"], 12.0)


def _apply_underwater_recovery_floor(adjustments: dict[str, float]) -> None:
    """Push severe blue/green RAW captures toward recoverable color and score.

    The model often underestimates how much Lightroom WB and saturation control
    are needed for underwater files. This floor keeps the edit bounded but avoids
    the previous weak "blue but slightly brighter" result.
    """

    adjustments["temperature_delta"] = max(adjustments["temperature_delta"], 3500.0)
    adjustments["tint"] = max(adjustments["tint"], 35.0)
    adjustments["exposure"] = max(adjustments["exposure"], 1.35)
    adjustments["highlights"] = min(adjustments["highlights"], -45.0)
    adjustments["shadows"] = max(adjustments["shadows"], 75.0)
    adjustments["whites"] = max(adjustments["whites"], 18.0)
    adjustments["blacks"] = min(adjustments["blacks"], -12.0)
    adjustments["saturation"] = min(adjustments["saturation"], -28.0)
    adjustments["vibrance"] = min(max(adjustments["vibrance"], 6.0), 14.0)
    adjustments["texture"] = max(adjustments["texture"], 20.0)
    adjustments["clarity"] = max(adjustments["clarity"], 22.0)
    adjustments["dehaze"] = max(adjustments["dehaze"], 22.0)
    adjustments["noise_reduction"] = max(adjustments["noise_reduction"], 12.0)
    adjustments["sharpening"] = max(adjustments["sharpening"], 35.0)
    adjustments["red_saturation"] = max(adjustments["red_saturation"], 55.0)
    adjustments["orange_saturation"] = max(adjustments["orange_saturation"], 25.0)
    adjustments["yellow_saturation"] = max(adjustments["yellow_saturation"], 10.0)
    adjustments["green_saturation"] = min(adjustments["green_saturation"], -35.0)
    adjustments["aqua_saturation"] = min(adjustments["aqua_saturation"], -75.0)
    adjustments["blue_saturation"] = min(adjustments["blue_saturation"], -82.0)
    adjustments["red_luminance"] = max(adjustments["red_luminance"], 38.0)
    adjustments["orange_luminance"] = max(adjustments["orange_luminance"], 20.0)
    adjustments["aqua_luminance"] = min(adjustments["aqua_luminance"], -15.0)
    adjustments["blue_luminance"] = min(adjustments["blue_luminance"], -20.0)


def _apply_warm_fire_reference_style(adjustments: dict[str, float]) -> None:
    """Apply the expert-reference direction for campfire/flame scenes."""

    adjustments["exposure"] = max(adjustments["exposure"], 0.22)
    adjustments["contrast"] = max(adjustments["contrast"], 12.0)
    adjustments["highlights"] = min(adjustments["highlights"], -24.0)
    adjustments["shadows"] = max(adjustments["shadows"], 28.0)
    adjustments["whites"] = max(adjustments["whites"], 10.0)
    adjustments["blacks"] = min(adjustments["blacks"], -14.0)
    adjustments["temperature_delta"] = max(adjustments["temperature_delta"], 320.0)
    adjustments["tint"] = max(adjustments["tint"], 4.0)
    adjustments["vibrance"] = max(adjustments["vibrance"], 22.0)
    adjustments["saturation"] = max(adjustments["saturation"], 8.0)
    adjustments["texture"] = max(adjustments["texture"], 22.0)
    adjustments["clarity"] = max(adjustments["clarity"], 18.0)
    adjustments["dehaze"] = max(adjustments["dehaze"], 8.0)
    adjustments["sharpening"] = max(adjustments["sharpening"], 28.0)
    adjustments["red_saturation"] = max(adjustments["red_saturation"], 35.0)
    adjustments["orange_saturation"] = max(adjustments["orange_saturation"], 45.0)
    adjustments["yellow_saturation"] = max(adjustments["yellow_saturation"], 20.0)
    adjustments["red_luminance"] = max(adjustments["red_luminance"], 18.0)
    adjustments["orange_luminance"] = max(adjustments["orange_luminance"], 26.0)
    adjustments["yellow_luminance"] = max(adjustments["yellow_luminance"], 12.0)
    adjustments["blue_saturation"] = min(adjustments["blue_saturation"], -12.0)
    adjustments["aqua_saturation"] = min(adjustments["aqua_saturation"], -10.0)


def _build_local_adjustments(
    *,
    analysis: VisionAnalysisResult,
    global_adjustments: dict[str, float],
) -> dict[str, Any]:
    """Create planner-owned Lightroom local adjustment evidence.

    The model/module only supplies image evidence. This helper creates the mask
    plan from the validated analysis and records degraded/fallback state when
    local masks cannot be planned.
    """

    if not _needs_local_adjustments(analysis):
        return {}

    semantic = _semantic_analysis_from_vision(analysis)
    planner = LocalAdjustmentPlanner()
    global_intents = {
        "clarity_delta": _normalized_delta(global_adjustments.get("clarity", 0.0), 35.0),
        "saturation_delta": _normalized_delta(global_adjustments.get("saturation", 0.0), 30.0),
        "exposure_delta": _normalized_delta(global_adjustments.get("exposure", 0.0), 2.0),
    }
    local_plan = planner.plan(semantic, global_adjustment_intents=global_intents)
    capability = planner.capability_snapshot()
    conflict = planner.conflict_evidence(semantic)
    return {
        "schema_version": "tonevyra.local_adjustments.bundle.v1",
        "execution_intent": "request_lightroom_classic_masks_when_supported",
        "semantic_analysis": semantic.model_dump(mode="json"),
        "mask_capability_snapshot": capability.model_dump(mode="json"),
        "local_adjustment_plan": local_plan.model_dump(mode="json"),
        "conflict_resolution": conflict.model_dump(mode="json"),
        "degraded_mode": local_plan.degraded_mode,
        "fallback_policy": "global_only_when_mask_unavailable",
    }


def _needs_local_adjustments(analysis: VisionAnalysisResult) -> bool:
    issues = analysis.issues.model_dump(exclude_none=True)
    exposure = _issue_value(issues, "exposure")
    if "underexposed" in exposure or "overexposed" in exposure:
        return True
    if analysis.main_subject and _match(str(analysis.main_subject).lower(), "person", "portrait", "product", "subject"):
        return True
    return False


def _semantic_analysis_from_vision(analysis: VisionAnalysisResult) -> SemanticAnalysis:
    issues = analysis.issues.model_dump(exclude_none=True)
    exposure = _issue_value(issues, "exposure")
    color_cast = _issue_value(issues, "color_cast")
    risks = list(dict.fromkeys([*analysis.risk_flags, exposure, color_cast]))
    provider_type = "model" if "model" in analysis.model_backend.lower() or "qwen" in analysis.model_backend.lower() else "module"
    region_type = "person" if _match(str(analysis.main_subject or "").lower(), "person", "people", "portrait") else "primary_subject"
    regions = [
        SemanticRegion(
            region_id=f"region-{region_type.replace('_', '-')}-1",
            region_type=region_type,
            priority=1,
            confidence=max(min(analysis.confidence, 0.98), 0.72),
            attributes={
                "inferred_from_scene": True,
                "scene_type": analysis.scene_type,
                "main_subject": analysis.main_subject,
                "exposure_issue": exposure,
                "global_mask_intent": "recover_dark_primary_subject" if "underexposed" in exposure else "preserve_subject_detail",
            },
            quality_risks=risks,
            recommended_intents=["recover_subject_exposure", "preserve_subject_detail"],
            source=f"{provider_type}-vision-normalized",
        )
    ]
    if "underexposed" in exposure:
        regions.append(
            SemanticRegion(
                region_id="region-background-1",
                region_type="background",
                priority=2,
                confidence=max(min(analysis.confidence - 0.08, 0.9), 0.72),
                attributes={
                    "context_region": True,
                    "exposure_issue": exposure,
                    "global_mask_intent": "lift_context_without_flattening_subject",
                },
                quality_risks=risks,
                recommended_intents=["recover_context_shadows"],
                source=f"{provider_type}-vision-normalized",
            )
        )
    return SemanticAnalysis(
        job_id=f"vision-{analysis.model_backend}",
        attempt_id=f"vision-{analysis.model_backend}-attempt-0",
        provider_type=provider_type,  # type: ignore[arg-type]
        primary_region_id=regions[0].region_id,
        regions=regions,
    )


def _normalized_delta(value: float, scale: float) -> float:
    if scale == 0:
        return 0.0
    return round(float(value) / scale, 4)


def _match(text: str, *needles: str) -> bool:
    return any(needle in text for needle in needles)


def _comparison_status(*, key: str, model_value: float, planner_value: float) -> str:
    if key in ADJUSTMENT_RANGES:
        minimum, maximum = ADJUSTMENT_RANGES[key]
        if model_value < minimum or model_value > maximum:
            return "ignored_out_of_range_model_suggestion"
    return "ignored_by_normal_planner"


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
    return {key: 0.0 for key in ADJUSTMENT_RANGES if key != "temp"}


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
