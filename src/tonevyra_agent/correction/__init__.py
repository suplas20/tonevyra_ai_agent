"""Correction Planner public API."""

from tonevyra_agent.correction.planner import CorrectionPlanner, create_correction_plan, plan_task_correction
from tonevyra_agent.correction.schemas import ADJUSTMENT_RANGES, CorrectionPlan

__all__ = [
    "ADJUSTMENT_RANGES",
    "CorrectionPlan",
    "CorrectionPlanner",
    "create_correction_plan",
    "plan_task_correction",
]


def __getattr__(name: str):  # pragma: no cover - thin lazy re-export
    # Lazy access keeps optional pixel deps (cv2/numpy) out of the import path for
    # callers that only need the legacy planner.
    if name in {"TargetBasedPlanner", "plan_with_targets"}:
        from tonevyra_agent.correction import target_based

        return getattr(target_based, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
