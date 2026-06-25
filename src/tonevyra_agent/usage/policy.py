"""Versioned policy registry for T-027 plan routing."""

from __future__ import annotations

from collections.abc import Iterable

from tonevyra_agent.usage.schemas import PlanPolicy


DEFAULT_PLAN_POLICIES: tuple[PlanPolicy, ...] = (
    PlanPolicy(
        plan_id="free",
        version=1,
        status="ACTIVE",
        analysis_provider="module",
        quality_provider="module",
        max_quality_retries=1,
        max_batch_size=10,
        max_input_megapixels=24,
        priority_class="low",
        monthly_photo_quota=100,
        fallback_policy={"enabled": False},
    ),
    PlanPolicy(
        plan_id="lite",
        version=1,
        status="ACTIVE",
        analysis_provider="module",
        quality_provider="module",
        max_quality_retries=2,
        max_batch_size=50,
        max_input_megapixels=45,
        priority_class="normal",
        monthly_photo_quota=1000,
        fallback_policy={"enabled": False},
    ),
    PlanPolicy(
        plan_id="standard",
        version=1,
        status="ACTIVE",
        analysis_provider="model",
        quality_provider="model",
        max_quality_retries=2,
        max_batch_size=100,
        max_input_megapixels=60,
        priority_class="normal",
        monthly_photo_quota=3000,
        fallback_policy={"enabled": False},
        model_resource_budget={"runtime": "local", "network": "blocked"},
    ),
    PlanPolicy(
        plan_id="pro",
        version=1,
        status="ACTIVE",
        analysis_provider="model",
        quality_provider="model",
        max_quality_retries=3,
        max_batch_size=500,
        max_input_megapixels=100,
        priority_class="high",
        monthly_photo_quota=10000,
        fallback_policy={"enabled": True, "requires_evidence": True},
        output_capabilities=["jpeg_srgb", "photo_set_consistency", "style_profile"],
        model_resource_budget={"runtime": "local", "network": "blocked"},
    ),
)


class PlanPolicyRegistry:
    """Single entry point for active plan policies."""

    def __init__(self, policies: Iterable[PlanPolicy]) -> None:
        by_plan: dict[str, PlanPolicy] = {}
        for policy in policies:
            existing = by_plan.get(policy.plan_id)
            if existing is not None and existing.version >= policy.version:
                continue
            by_plan[policy.plan_id] = policy
        self._policies = dict(sorted(by_plan.items()))

    def get_active(self, plan_id: str) -> PlanPolicy | None:
        policy = self._policies.get(plan_id)
        if policy is None or policy.status != "ACTIVE":
            return None
        return policy

    def require_active(self, plan_id: str) -> PlanPolicy:
        policy = self.get_active(plan_id)
        if policy is None:
            raise ValueError(f"active plan policy not found for {plan_id!r}")
        return policy

    def list_active(self) -> list[PlanPolicy]:
        return [policy for policy in self._policies.values() if policy.status == "ACTIVE"]


def build_default_policy_registry() -> PlanPolicyRegistry:
    return PlanPolicyRegistry(DEFAULT_PLAN_POLICIES)
