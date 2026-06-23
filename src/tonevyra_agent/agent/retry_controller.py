"""T-021 bounded quality retry decisions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from tonevyra_agent.agent.plan_policy import PlanPolicy
from tonevyra_agent.schemas.job import AttemptContext
from tonevyra_agent.schemas.quality import T021QualityResult


@dataclass(frozen=True)
class RetryDecision:
    retry: bool
    next_attempt_no: int | None
    reason: str
    strategy: list[str] | None = None
    expected_improvement: float = 0.0
    plan_delta_hash: str | None = None


def decide_quality_retry(
    quality: T021QualityResult,
    context: AttemptContext,
    policy: PlanPolicy,
    *,
    previous_plan_delta_hashes: set[str] | None = None,
) -> RetryDecision:
    """Return a bounded retry decision; never retries technical or source-limited failures."""

    if quality.status != "RETRY_REQUIRED":
        return RetryDecision(False, None, f"quality status is terminal or non-retry: {quality.status}")
    if context.attempt_no >= policy.max_quality_retries:
        return RetryDecision(False, None, "quality retry budget exhausted")
    recommendation = quality.retry_recommendation
    if not recommendation.recommended or not recommendation.strategy:
        return RetryDecision(False, None, "retry recommendation is missing a strategy")
    if recommendation.expected_improvement <= 0:
        return RetryDecision(False, None, "retry recommendation has no expected improvement")

    plan_delta_hash = _strategy_hash(
        {
            "strategy": recommendation.strategy,
            "reason_codes": quality.reason_codes,
            "attempt_no": context.attempt_no + 1,
        }
    )
    if previous_plan_delta_hashes and plan_delta_hash in previous_plan_delta_hashes:
        return RetryDecision(False, None, "retry strategy repeated a previous plan delta", recommendation.strategy)

    return RetryDecision(
        True,
        context.attempt_no + 1,
        "retry budget remains and strategy is actionable",
        recommendation.strategy,
        recommendation.expected_improvement,
        plan_delta_hash,
    )


def _strategy_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
