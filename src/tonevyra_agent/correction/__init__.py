"""Correction plan schemas with optional local-test planner exports.

Production clients use the remote Planner API and intentionally do not package
the local planner implementation. Keep those exports lazy so importing the
shared correction schema never requires server-side planner code.
"""

from tonevyra_agent.correction.schemas import ADJUSTMENT_RANGES, CorrectionPlan

__all__ = [
    "ADJUSTMENT_RANGES",
    "CorrectionPlan",
    "CorrectionPlanner",
    "create_correction_plan",
    "plan_task_correction",
]


def __getattr__(name: str):  # pragma: no cover - thin lazy re-export
    if name in {"CorrectionPlanner", "create_correction_plan", "plan_task_correction"}:
        from tonevyra_agent.correction import planner

        return getattr(planner, name)
    if name in {"TargetBasedPlanner", "plan_with_targets"}:
        from tonevyra_agent.correction import target_based

        return getattr(target_based, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
