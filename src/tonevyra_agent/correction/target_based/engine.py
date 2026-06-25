"""Target-based Correction Planner engine.

Orchestrates the measurement-driven pipeline:

    1. measure preview            (measurement.py)
    2. reconcile model + measure  (this module)
    3. build scene target state   (targets.py)
    4. global / local split       (this module + legacy local adjustment builder)
    5. generate candidates        (candidates.py)
    6. constraint validation      (constraints.py)
    7. score + select             (this module + simulation.py)
    8. re-measure selected        (simulation.py)
    9. bounded secondary pass     (this module)
   10. decision log + plan        (this module)

The simulation output is a *prediction*; the real corrected pixels still come
from Lightroom and are scored by the Quality Gate. The decision log marks this.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from tonevyra_agent.correction.schemas import ADJUSTMENT_RANGES, CorrectionPlan
from tonevyra_agent.correction.target_based import candidates as candidates_mod
from tonevyra_agent.correction.target_based import constraints as constraints_mod
from tonevyra_agent.correction.target_based import simulation as simulation_mod
from tonevyra_agent.correction.target_based import targets as targets_mod
from tonevyra_agent.correction.target_based.measurement import _load_rgb_array, measure_array
from tonevyra_agent.correction.target_based.schemas import (
    ImageMeasurement,
    PlannerDecisionLog,
    TargetState,
)
from tonevyra_agent.vision.schemas import VisionAnalysisResult


PLANNER_VERSION = "target-planner-v1"
_SECONDARY_LUMA_TOLERANCE = 8.0
_SECONDARY_SAT_TOLERANCE = 0.04


def plan_with_targets(
    *,
    analysis: VisionAnalysisResult,
    preview_path: str | Path,
    review_confidence_threshold: float = 0.7,
) -> tuple[CorrectionPlan, PlannerDecisionLog]:
    """Run the full target-based pipeline and return the plan + decision log."""

    rgb = _load_rgb_array(preview_path)
    return plan_from_rgb(
        analysis=analysis,
        rgb=rgb,
        review_confidence_threshold=review_confidence_threshold,
    )


def plan_from_rgb(
    *,
    analysis: VisionAnalysisResult,
    rgb: np.ndarray,
    review_confidence_threshold: float = 0.7,
) -> tuple[CorrectionPlan, PlannerDecisionLog]:
    # Lazy import avoids a circular import with the legacy planner module.
    from tonevyra_agent.correction.planner import (
        SEVERE_RISK_FLAGS,
        _base_preset,
        _build_local_adjustments,
        _style_target,
    )

    is_underwater = "underwater" in analysis.scene_type.lower()
    issues = analysis.issues.model_dump(exclude_none=True)
    model_intents = (
        analysis.correction_intents.model_dump(exclude_none=True)
        if analysis.correction_intents is not None
        else {}
    )

    # Stage 1
    measurement = measure_array(rgb)
    # Stage 2
    reconciliation = _reconcile(analysis=analysis, issues=issues, measurement=measurement)
    # Stage 3
    target = targets_mod.build_target_state(
        scene_type=analysis.scene_type,
        measurement=measurement,
        main_subject=analysis.main_subject,
    )
    # Stage 5
    raw_candidates = candidates_mod.generate_candidates(
        measurement=measurement,
        target=target,
        is_underwater=is_underwater,
        model_intents=model_intents,
    )
    # Stages 6 + 7
    scored = [
        _score_candidate(rgb=rgb, candidate=raw, measurement=measurement, target=target)
        for raw in raw_candidates
    ]
    selected = min(scored, key=lambda item: item["score"])

    # Stages 8 + 9
    secondary = _secondary_correction(
        rgb=rgb,
        selected=selected,
        measurement=measurement,
        target=target,
    )

    # Measured-deficit floors: guarantee enough exposure/WB/tone for severe
    # darkness or strong cast even when the simulation under-rates the need.
    # Saturation is intentionally untouched so this cannot cause monochrome.
    floored, floor_deltas = candidates_mod.apply_measured_deficit_floors(
        adjustments=secondary["adjustments"],
        measurement=measurement,
        target=target,
        is_underwater=is_underwater,
    )
    final_adjustments, floor_clamped = constraints_mod.clamp_adjustments(floored)
    if floor_deltas:
        predicted_after = simulation_mod.predict_measurement(rgb, final_adjustments)
    else:
        predicted_after = secondary["predicted"]
    secondary["log"]["measured_deficit_floors"] = floor_deltas

    # Stage 4 (local adjustments) reuse legacy planner-owned builder.
    local_adjustments = _build_local_adjustments(analysis=analysis, global_adjustments=final_adjustments)

    severe_risk = any(flag in SEVERE_RISK_FLAGS for flag in analysis.risk_flags)
    requires_review = (
        analysis.requires_review
        or not analysis.usable
        or analysis.confidence < review_confidence_threshold
        or severe_risk
        or selected["rejected"]
        or secondary["rejected"]
    )

    reasons = _build_reasons(
        analysis=analysis,
        target=target,
        selected=selected,
        secondary=secondary,
        requires_review=requires_review,
    )

    decision_log = PlannerDecisionLog(
        planner_version=PLANNER_VERSION,
        scene_type=analysis.scene_type,
        model_backend=analysis.model_backend,
        model_name=analysis.model_name,
        measurement=measurement.summary(),
        model_measurement_reconciliation=reconciliation,
        target_state=target.summary(),
        candidates=[item["log"] for item in scored],
        selected_candidate=selected["name"],
        secondary_correction=secondary["log"],
        predicted_before=_predicted_summary(selected["predicted"]),
        predicted_after=_predicted_summary(predicted_after),
        final_adjustments=final_adjustments,
        requires_review=requires_review,
        reasons=reasons,
    )

    plan = CorrectionPlan(
        planner_version=PLANNER_VERSION,
        base_preset=_base_preset(analysis),
        style_target=_style_target(analysis),
        adjustments_json=final_adjustments,
        local_adjustments_json=local_adjustments,
        confidence=analysis.confidence,
        requires_review=requires_review,
        clamped=selected["clamped"] or secondary["clamped"] or floor_clamped,
        reason_summary="; ".join(reasons),
        source={
            "scene_type": analysis.scene_type,
            "main_subject": analysis.main_subject,
            "model_backend": analysis.model_backend,
            "model_name": analysis.model_name,
            "planner_mode": "target_based",
        },
    )
    return plan, decision_log


def _score_candidate(
    *,
    rgb: np.ndarray,
    candidate: dict[str, Any],
    measurement: ImageMeasurement,
    target: TargetState,
) -> dict[str, Any]:
    adjustments, clamped = constraints_mod.clamp_adjustments(candidate["adjustments"])
    predicted = simulation_mod.predict_measurement(rgb, adjustments)
    constraint = constraints_mod.evaluate(
        predicted=predicted, measurement=measurement, target=target, adjustments=adjustments
    )
    distance = _target_distance(predicted=predicted, target=target)
    penalties = dict(constraint["penalties"])
    score = distance + sum(penalties.values())
    log = {
        "name": candidate["name"],
        "strategy": candidate["strategy"],
        "adjustments": adjustments,
        "clamped": clamped,
        "rejected": constraint["rejected"],
        "reject_reasons": constraint["reasons"],
        "distance": round(distance, 4),
        "penalties": {key: round(value, 4) for key, value in penalties.items()},
        "score": round(score, 4),
        "predicted_summary": _predicted_summary(predicted),
    }
    return {
        "name": candidate["name"],
        "adjustments": adjustments,
        "clamped": clamped,
        "rejected": constraint["rejected"],
        "score": score,
        "predicted": predicted,
        "log": log,
    }


def _secondary_correction(
    *,
    rgb: np.ndarray,
    selected: dict[str, Any],
    measurement: ImageMeasurement,
    target: TargetState,
) -> dict[str, Any]:
    """Single bounded second pass that nudges residual luma/saturation error."""

    predicted = selected["predicted"]
    luma_residual = _band_residual(predicted.mean_luma, target.target_luma_low, target.target_luma_high)
    sat_residual = _band_residual(
        predicted.mean_saturation, target.target_saturation_low, target.target_saturation_high
    )

    base_log = {
        "applied": False,
        "luma_residual": round(luma_residual, 3),
        "saturation_residual": round(sat_residual, 4),
    }
    if abs(luma_residual) <= _SECONDARY_LUMA_TOLERANCE and abs(sat_residual) <= _SECONDARY_SAT_TOLERANCE:
        base_log["reason"] = "within tolerance; no secondary correction"
        return {
            "adjustments": selected["adjustments"],
            "predicted": predicted,
            "clamped": False,
            "rejected": selected["rejected"],
            "log": base_log,
        }

    delta: dict[str, float] = {}
    candidate = dict(selected["adjustments"])
    if abs(luma_residual) > _SECONDARY_LUMA_TOLERANCE:
        # Positive residual means still too dark -> add a small exposure nudge.
        nudge = max(-0.4, min(0.4, luma_residual / 80.0))
        candidate["exposure"] = candidate.get("exposure", 0.0) + nudge
        delta["exposure"] = round(nudge, 3)
    if abs(sat_residual) > _SECONDARY_SAT_TOLERANCE:
        nudge = max(-15.0, min(15.0, sat_residual * 120.0))
        candidate["vibrance"] = candidate.get("vibrance", 0.0) + nudge
        delta["vibrance"] = round(nudge, 3)

    adjustments, clamped = constraints_mod.clamp_adjustments(candidate)
    new_predicted = simulation_mod.predict_measurement(rgb, adjustments)
    constraint = constraints_mod.evaluate(
        predicted=new_predicted, measurement=measurement, target=target, adjustments=adjustments
    )
    new_score = _target_distance(predicted=new_predicted, target=target) + sum(constraint["penalties"].values())

    if new_score < selected["score"]:
        base_log.update(
            {
                "applied": True,
                "delta": delta,
                "previous_score": round(selected["score"], 4),
                "new_score": round(new_score, 4),
                "reason": "secondary correction improved target distance",
            }
        )
        return {
            "adjustments": adjustments,
            "predicted": new_predicted,
            "clamped": clamped,
            "rejected": constraint["rejected"],
            "log": base_log,
        }

    base_log.update(
        {
            "applied": False,
            "delta": delta,
            "previous_score": round(selected["score"], 4),
            "new_score": round(new_score, 4),
            "reason": "secondary correction did not improve; kept primary candidate",
        }
    )
    return {
        "adjustments": selected["adjustments"],
        "predicted": predicted,
        "clamped": False,
        "rejected": selected["rejected"],
        "log": base_log,
    }


def _reconcile(
    *,
    analysis: VisionAnalysisResult,
    issues: dict[str, Any],
    measurement: ImageMeasurement,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []

    model_exposure = str(issues.get("exposure", "")).lower()
    measured_dark = measurement.mean_luma < 100.0
    model_dark = "underexposed" in model_exposure
    entries.append(
        {
            "dimension": "exposure",
            "model_says": model_exposure or "unspecified",
            "measured": {"mean_luma": measurement.mean_luma},
            "agreement": model_dark == measured_dark,
        }
    )

    model_cast = str(issues.get("color_cast", "")).lower()
    measured_cool = measurement.blue_green_minus_red > 6.0
    model_cool = "cool" in model_cast or "blue" in model_cast
    entries.append(
        {
            "dimension": "color_cast",
            "model_says": model_cast or "unspecified",
            "measured": {"blue_green_minus_red": measurement.blue_green_minus_red},
            "agreement": model_cool == measured_cool,
        }
    )

    entries.append(
        {
            "dimension": "saturation",
            "model_says": "n/a (categorical)",
            "measured": {
                "mean_saturation": measurement.mean_saturation,
                "dominant_hue": measurement.dominant_hue,
                "colored_pixel_ratio": measurement.colored_pixel_ratio,
            },
            "agreement": None,
        }
    )
    return entries


def _build_reasons(
    *,
    analysis: VisionAnalysisResult,
    target: TargetState,
    selected: dict[str, Any],
    secondary: dict[str, Any],
    requires_review: bool,
) -> list[str]:
    reasons = [
        f"scene={analysis.scene_type}",
        f"confidence={analysis.confidence:.2f}",
        f"target_luma={target.target_luma_low:.0f}..{target.target_luma_high:.0f}",
        f"target_saturation={target.target_saturation_low:.2f}..{target.target_saturation_high:.2f}",
        f"selected_candidate={selected['name']} (score={selected['score']:.3f})",
    ]
    if selected["rejected"]:
        reasons.append("selected candidate violated a constraint (monochrome/clipping guard)")
    if secondary["log"].get("applied"):
        reasons.append("bounded secondary correction applied")
    if secondary["log"].get("measured_deficit_floors"):
        keys = ",".join(secondary["log"]["measured_deficit_floors"].keys())
        reasons.append(f"measured-deficit floors applied ({keys})")
    if analysis.risk_flags:
        reasons.append(f"risk_flags={','.join(analysis.risk_flags)}")
    if selected["clamped"] or secondary["clamped"]:
        reasons.append("one or more adjustments were clamped")
    if requires_review:
        reasons.append("human review required")
    return reasons


def _target_distance(*, predicted: ImageMeasurement, target: TargetState) -> float:
    luma_dev = abs(_band_residual(predicted.mean_luma, target.target_luma_low, target.target_luma_high)) / 30.0
    sat_dev = abs(
        _band_residual(predicted.mean_saturation, target.target_saturation_low, target.target_saturation_high)
    ) / 0.10
    spread_dev = max(0.0, predicted.channel_spread - target.target_channel_spread) / 20.0
    return 2.0 * luma_dev + 2.0 * sat_dev + 1.0 * spread_dev


def _band_residual(value: float, low: float, high: float) -> float:
    """Signed distance outside [low, high]; positive means below the band."""

    if value < low:
        return low - value
    if value > high:
        return high - value  # negative
    return 0.0


def _predicted_summary(predicted: ImageMeasurement) -> dict[str, Any]:
    return {
        "mean_luma": predicted.mean_luma,
        "mean_saturation": predicted.mean_saturation,
        "channel_spread": predicted.channel_spread,
        "blue_green_minus_red": predicted.blue_green_minus_red,
        "clipped_highlight_ratio": predicted.clipped_highlight_ratio,
        "clipped_shadow_ratio": predicted.clipped_shadow_ratio,
        "colored_pixel_ratio": predicted.colored_pixel_ratio,
    }
