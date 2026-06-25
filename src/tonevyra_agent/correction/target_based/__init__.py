"""Measurement-driven target-based Correction Planner (PLANNER_MODE=target_based)."""

from __future__ import annotations

from pathlib import Path

from tonevyra_agent.correction.schemas import CorrectionPlan
from tonevyra_agent.correction.target_based.engine import (
    PLANNER_VERSION,
    plan_from_rgb,
    plan_with_targets,
)
from tonevyra_agent.correction.target_based.schemas import PlannerDecisionLog
from tonevyra_agent.vision.schemas import VisionAnalysisResult


class TargetBasedPlanner:
    """Thin entry point wrapping the target-based pipeline."""

    def __init__(self, *, review_confidence_threshold: float = 0.7) -> None:
        self.review_confidence_threshold = review_confidence_threshold

    def plan(
        self,
        analysis: VisionAnalysisResult,
        preview_path: str | Path,
    ) -> tuple[CorrectionPlan, PlannerDecisionLog]:
        return plan_with_targets(
            analysis=analysis,
            preview_path=preview_path,
            review_confidence_threshold=self.review_confidence_threshold,
        )


__all__ = [
    "PLANNER_VERSION",
    "PlannerDecisionLog",
    "TargetBasedPlanner",
    "plan_from_rgb",
    "plan_with_targets",
]
