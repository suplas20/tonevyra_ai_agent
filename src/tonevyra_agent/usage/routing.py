"""Deterministic plan routing for T-027."""

from __future__ import annotations

from tonevyra_agent.usage.policy import PlanPolicyRegistry, build_default_policy_registry
from tonevyra_agent.usage.schemas import PlanPolicy, PlanPolicySnapshot, PlanRouteDecision, stable_sha256, utc_now_iso


class PlanRouter:
    """Resolve a validated immutable policy snapshot for each job."""

    def __init__(self, registry: PlanPolicyRegistry | None = None) -> None:
        self._registry = registry or build_default_policy_registry()

    def route(
        self,
        *,
        user_scope_id: str,
        job_id: str,
        requested_plan_id: str,
        requested_photo_units: int = 1,
        used_photo_units: int = 0,
        batch_size: int = 1,
        input_megapixels: float = 1.0,
    ) -> PlanRouteDecision:
        policy = self._registry.get_active(requested_plan_id)
        if policy is None:
            return self._deny(user_scope_id, job_id, requested_plan_id, "POLICY_NOT_FOUND_OR_INACTIVE")
        if requested_photo_units < 1:
            return self._deny(user_scope_id, job_id, requested_plan_id, "PHOTO_UNITS_MUST_BE_POSITIVE")
        if used_photo_units + requested_photo_units > policy.monthly_photo_quota:
            return self._deny(user_scope_id, job_id, requested_plan_id, "QUOTA_EXCEEDED")
        if batch_size > policy.max_batch_size:
            return self._deny(user_scope_id, job_id, requested_plan_id, "BATCH_SIZE_EXCEEDED")
        if input_megapixels > policy.max_input_megapixels:
            return self._deny(user_scope_id, job_id, requested_plan_id, "INPUT_MEGAPIXELS_EXCEEDED")

        snapshot = create_policy_snapshot(policy=policy, user_scope_id=user_scope_id, job_id=job_id)
        return PlanRouteDecision(
            decision="ALLOW",
            reason="POLICY_ROUTE_ALLOWED",
            user_scope_id=user_scope_id,
            job_id=job_id,
            requested_plan_id=requested_plan_id,
            snapshot=snapshot,
            requested_analysis_provider=policy.analysis_provider,
            executed_analysis_provider=policy.analysis_provider,
            requested_quality_provider=policy.quality_provider,
            executed_quality_provider=policy.quality_provider,
            model_initialization_allowed=policy.analysis_provider == "model" or policy.quality_provider == "model",
            fallback_used=False,
            audit={
                "plan_version": policy.version,
                "policy_hash": policy.policy_hash,
                "priority_class": policy.priority_class,
                "max_quality_retries": policy.max_quality_retries,
            },
        )

    def controlled_module_fallback(
        self,
        *,
        decision: PlanRouteDecision,
        reason: str,
        evidence_artifact: str | None,
    ) -> PlanRouteDecision:
        """Apply explicit model-to-module fallback only when snapshot policy allows it."""

        if decision.snapshot is None:
            raise ValueError("fallback requires an allowed route decision with a policy snapshot")
        policy = decision.snapshot.plan
        fallback_policy = policy.fallback_policy
        if not fallback_policy.get("enabled"):
            raise ValueError("controlled module fallback is not enabled for this policy")
        if fallback_policy.get("requires_evidence") and not evidence_artifact:
            raise ValueError("controlled module fallback requires evidence")
        return decision.model_copy(
            update={
                "reason": f"CONTROLLED_FALLBACK:{reason}",
                "executed_analysis_provider": "module",
                "executed_quality_provider": "module",
                "model_initialization_allowed": False,
                "fallback_used": True,
                "audit": {
                    **decision.audit,
                    "requested_analysis_provider": decision.requested_analysis_provider,
                    "requested_quality_provider": decision.requested_quality_provider,
                    "fallback_reason": reason,
                    "fallback_evidence_artifact": evidence_artifact,
                    "degraded_mode": True,
                },
            }
        )

    @staticmethod
    def _deny(user_scope_id: str, job_id: str, requested_plan_id: str, reason: str) -> PlanRouteDecision:
        return PlanRouteDecision(
            decision="DENY",
            reason=reason,
            user_scope_id=user_scope_id,
            job_id=job_id,
            requested_plan_id=requested_plan_id,
            audit={"fail_closed": True},
        )


def create_policy_snapshot(*, policy: PlanPolicy, user_scope_id: str, job_id: str) -> PlanPolicySnapshot:
    snapshot_seed = {
        "user_scope_id": user_scope_id,
        "job_id": job_id,
        "plan_id": policy.plan_id,
        "plan_version": policy.version,
        "policy_hash": policy.policy_hash,
    }
    return PlanPolicySnapshot(
        snapshot_id=stable_sha256(snapshot_seed),
        user_scope_id=user_scope_id,
        job_id=job_id,
        captured_at=utc_now_iso(),
        plan=policy,
        policy_hash=policy.policy_hash,
    )
