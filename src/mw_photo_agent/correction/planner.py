"""Converts vision analysis into safe Lightroom adjustment plans."""

from mw_photo_agent.correction.schemas import CorrectionPlan
from mw_photo_agent.vision.schemas import VisionAnalysisResult


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def create_correction_plan(analysis: VisionAnalysisResult) -> CorrectionPlan:
    return CorrectionPlan(
        base_preset="mw_neutral",
        style_target=analysis.edit_intent or "neutral_cleanup",
        adjustments={},
        confidence=analysis.confidence,
        requires_review=analysis.confidence < 0.5 or not analysis.usable,
    )

