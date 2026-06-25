"""Regression threshold evaluation for T-026 release gates."""

from __future__ import annotations

from tonevyra_agent.benchmark.schemas import RegressionDecision, RegressionThresholds


def evaluate_regression(
    *,
    aggregate_metrics: dict[str, float],
    genre_metrics: dict[str, dict[str, float]],
    thresholds: RegressionThresholds,
) -> RegressionDecision:
    """Apply versioned thresholds and return a machine-readable gate decision."""

    blocking: list[str] = []
    checked: dict[str, float] = {}

    failure_rate = float(aggregate_metrics.get("technical_failure_rate", 1.0))
    checked["technical_failure_rate"] = failure_rate
    max_failure = thresholds.critical.get("technical_failure_rate_max")
    if max_failure is not None and failure_rate > float(max_failure):
        blocking.append(f"technical_failure_rate {failure_rate} > {max_failure}")

    approval_rate = float(aggregate_metrics.get("final_approval_rate", 0.0))
    checked["final_approval_rate"] = approval_rate
    min_approval = thresholds.critical.get("final_approval_rate_min")
    if min_approval is not None and approval_rate < float(min_approval):
        blocking.append(f"final_approval_rate {approval_rate} < {min_approval}")

    for threshold_name, threshold_value in thresholds.genre.items():
        if not threshold_name.endswith("_human_score_min"):
            continue
        genre_name = threshold_name[: -len("_human_score_min")]
        genre_score = float(genre_metrics.get(genre_name, {}).get("human_score", 0.0))
        checked[threshold_name] = genre_score
        if genre_score < float(threshold_value):
            blocking.append(f"{threshold_name} {genre_score} < {threshold_value}")

    return RegressionDecision(
        decision="FAIL" if blocking else "PASS",
        threshold_version=thresholds.version,
        blocking_reasons=blocking,
        checked_metrics=checked,
    )


def compare_threshold_versions(*, baseline: RegressionThresholds, candidate: RegressionThresholds) -> None:
    """Reject silent threshold relaxation."""

    if candidate.silent_relaxation_allowed:
        raise ValueError("silent threshold relaxation is forbidden")
    baseline_failure = baseline.critical.get("technical_failure_rate_max")
    candidate_failure = candidate.critical.get("technical_failure_rate_max")
    if baseline_failure is not None and candidate_failure is not None and candidate_failure > baseline_failure:
        raise ValueError("technical failure threshold was relaxed")
    baseline_approval = baseline.critical.get("final_approval_rate_min")
    candidate_approval = candidate.critical.get("final_approval_rate_min")
    if baseline_approval is not None and candidate_approval is not None and candidate_approval < baseline_approval:
        raise ValueError("final approval threshold was relaxed")
