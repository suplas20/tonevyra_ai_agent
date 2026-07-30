"""Adapter from the Planner API contract to the current rule planner."""

from __future__ import annotations

from typing import Any

from tonevyra_agent.correction.planner import create_correction_plan
from tonevyra_agent.planner_api.contracts import PlannerRequest
from tonevyra_agent.vision.schemas import VisionAnalysisResult, VisionIssues


class PlannerEngine:
    def create_plan(self, request: PlannerRequest) -> dict[str, Any]:
        analysis = request.analysis
        vision = VisionAnalysisResult(
            model_backend="planner-api-input",
            model_name="Tonevyra local analysis",
            scene_type=str(analysis.get("scene_type") or "unknown"),
            main_subject=_optional_text(analysis.get("subject_type")),
            usable=bool(analysis.get("usable", True)),
            issues=VisionIssues(
                exposure=str(analysis.get("exposure_state") or "normal"),
                color_cast=str(analysis.get("dominant_color_cast") or "neutral"),
                contrast=str(analysis.get("contrast_state") or "normal"),
                sharpness=str(analysis.get("sharpness_state") or "normal"),
                noise=str(analysis.get("noise_state") or "low"),
                haze=_optional_text(analysis.get("haze_state")),
            ),
            confidence=float(analysis.get("confidence", 0.0)),
            risk_flags=[str(item) for item in analysis.get("risk_flags", [])],
            requires_review=bool(analysis.get("requires_review", False)),
        )
        plan = create_correction_plan(vision)
        return {
            "global_adjustments": dict(plan.adjustments_json),
            "local_adjustments": dict(plan.local_adjustments_json),
            "base_preset": plan.base_preset,
            "confidence": plan.confidence,
            "requires_review": plan.requires_review,
            "clamped": plan.clamped,
            "reason_summary": plan.reason_summary,
        }


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None
