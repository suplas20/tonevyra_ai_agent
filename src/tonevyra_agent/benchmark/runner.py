"""Deterministic T-026 benchmark run assembly."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from tonevyra_agent.benchmark.dataset import assert_no_test_leakage
from tonevyra_agent.benchmark.regression import evaluate_regression
from tonevyra_agent.benchmark.schemas import (
    BenchmarkCase,
    BenchmarkConditions,
    BenchmarkRunResult,
    RegressionThresholds,
    T026RuntimeEvidence,
)


def conditions_hash(conditions: BenchmarkConditions) -> str:
    encoded = json.dumps(conditions.model_dump(mode="json"), ensure_ascii=False, sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def build_benchmark_run_result(
    *,
    run_id: str,
    cases: list[BenchmarkCase],
    split_manifest: dict[str, list[str]],
    thresholds: RegressionThresholds,
    candidate_version: str,
    baseline_version: str,
    conditions: BenchmarkConditions,
    aggregate_metrics: dict[str, float],
    genre_metrics: dict[str, dict[str, float]],
) -> tuple[BenchmarkRunResult, dict[str, Any]]:
    """Build a comparable benchmark run and release gate decision."""

    if not cases:
        raise ValueError("benchmark run requires at least one case")
    assert_no_test_leakage(split_manifest)
    dataset_ids = {case.dataset_id for case in cases}
    dataset_versions = {case.dataset_version for case in cases}
    if len(dataset_ids) != 1 or len(dataset_versions) != 1:
        raise ValueError("benchmark run cases must use one dataset id/version")

    decision = evaluate_regression(
        aggregate_metrics=aggregate_metrics,
        genre_metrics=genre_metrics,
        thresholds=thresholds,
    )
    run = BenchmarkRunResult(
        run_id=run_id,
        dataset_id=next(iter(dataset_ids)),
        dataset_version=next(iter(dataset_versions)),
        candidate_version=candidate_version,
        baseline_version=baseline_version,
        conditions_hash=conditions_hash(conditions),
        aggregate_metrics={
            **aggregate_metrics,
            "automated_metrics_version": conditions.quality_metric_version,
            "human_scores_included": True,
        },
        genre_metrics=genre_metrics,
        regression_decision=decision.decision,
        threshold_version=thresholds.version,
    )
    evidence = {
        "dataset_case_count": len(cases),
        "split_leakage": False,
        "conditions": conditions.model_dump(mode="json"),
        "regression_decision": decision.model_dump(mode="json"),
    }
    return run, evidence


def build_runtime_evidence(*, regressions_passed: bool, evidence: list[dict[str, Any]]) -> T026RuntimeEvidence:
    return T026RuntimeEvidence(completed=True, regressions_passed=regressions_passed, evidence=evidence)
