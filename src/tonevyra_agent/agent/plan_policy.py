"""T-021 plan policy definitions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlanPolicy:
    name: str
    analysis_provider: str
    quality_provider: str
    max_quality_retries: int
    allow_model_loading: bool
    allow_module_fallback: bool = False
    allow_set_consistency: bool = False
    output_profile: str = "jpeg_srgb"


PLAN_POLICIES: dict[str, PlanPolicy] = {
    "free": PlanPolicy("free", "module", "module", 1, False),
    "lite": PlanPolicy("lite", "module", "module", 2, False),
    "standard": PlanPolicy("standard", "model", "model", 2, True, allow_set_consistency=True),
    "pro": PlanPolicy("pro", "model", "model", 3, True, allow_set_consistency=True),
    "t021_mvp": PlanPolicy("t021_mvp", "module", "module", 2, False),
}


def get_plan_policy(name: str = "t021_mvp") -> PlanPolicy:
    try:
        return PLAN_POLICIES[name]
    except KeyError as exc:
        allowed = ", ".join(sorted(PLAN_POLICIES))
        raise ValueError(f"unknown plan policy {name!r}; allowed: {allowed}") from exc
