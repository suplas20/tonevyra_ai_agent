from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from tonevyra_agent.benchmark import (
    BenchmarkCase,
    BenchmarkRunResult,
    HumanBlindReview,
    RegressionThresholds,
    detect_split_leakage,
)
from tonevyra_agent.benchmark.dataset import assert_no_test_leakage
from tonevyra_agent.benchmark.regression import compare_threshold_versions, evaluate_regression
from tonevyra_agent.benchmark.runner import build_benchmark_run_result
from tonevyra_agent.benchmark.schemas import BenchmarkConditions, QualityClaim


FIXTURE_ROOT = Path("harness/fixtures/t026_benchmark")


def _load(name: str) -> dict:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def test_benchmark_case_fixture_matches_contract() -> None:
    case = BenchmarkCase.model_validate(_load("valid_dataset_case.json"))

    assert case.schema_version == "t026.benchmark.case.v1"
    assert case.split == "test"
    assert case.source_checksum.startswith("sha256:")
    assert case.license_or_consent == "internal-consent-v1"


def test_benchmark_run_fixture_matches_contract() -> None:
    run = BenchmarkRunResult.model_validate(_load("valid_benchmark_run.json"))

    assert run.schema_version == "t026.benchmark.run.v1"
    assert run.regression_decision == "PASS"
    assert run.aggregate_metrics["final_approval_rate"] == 0.95


def test_dataset_split_manifest_detects_leakage() -> None:
    valid = detect_split_leakage(_load("dataset_split_manifest.json"))
    invalid = detect_split_leakage(_load("invalid_dataset_leakage.json"))

    assert valid["valid"] is True
    assert valid["overlap_count"] == 0
    assert invalid["valid"] is False
    with pytest.raises(ValueError):
        assert_no_test_leakage(_load("invalid_dataset_leakage.json"))


def test_human_review_must_be_blind_and_randomized() -> None:
    review = HumanBlindReview.model_validate(_load("human_blind_review.json"))

    assert review.randomized_order is True
    assert review.provider_labels_hidden is True
    with pytest.raises(ValidationError):
        HumanBlindReview(
            review_session_id="review-bad",
            blind_pair_id="pair-bad",
            randomized_order=False,
            provider_labels_hidden=False,
            criteria_scores={},
            preference="A",
            confidence=0.5,
        )


def test_regression_gate_applies_critical_and_genre_thresholds() -> None:
    thresholds = RegressionThresholds.model_validate(_load("regression_thresholds.json"))
    decision = evaluate_regression(
        aggregate_metrics={"final_approval_rate": 0.95, "technical_failure_rate": 0.01},
        genre_metrics={"portrait": {"human_score": 94.2}, "night": {"human_score": 90.1}},
        thresholds=thresholds,
    )
    failing = evaluate_regression(
        aggregate_metrics={"final_approval_rate": 0.88, "technical_failure_rate": 0.04},
        genre_metrics={"portrait": {"human_score": 94.2}, "night": {"human_score": 80.0}},
        thresholds=thresholds,
    )

    assert decision.decision == "PASS"
    assert failing.decision == "FAIL"
    assert len(failing.blocking_reasons) == 3


def test_threshold_relaxation_is_rejected() -> None:
    baseline = RegressionThresholds.model_validate(_load("regression_thresholds.json"))
    relaxed = RegressionThresholds(
        version="threshold-relaxed",
        critical={"technical_failure_rate_max": 0.05, "final_approval_rate_min": 0.8},
        genre={"portrait_human_score_min": 80},
        silent_relaxation_allowed=False,
    )

    with pytest.raises(ValueError):
        compare_threshold_versions(baseline=baseline, candidate=relaxed)


def test_unsubstantiated_quality_claim_is_rejected() -> None:
    claim = QualityClaim.model_validate(_load("unsubstantiated_quality_claim.json"))

    assert claim.is_substantiated() is False
    assert _load("unsubstantiated_quality_claim.json")["expected_validation"] == "FAIL"


def test_build_benchmark_run_result_is_traceable_and_machine_readable() -> None:
    case = BenchmarkCase.model_validate(_load("valid_dataset_case.json"))
    thresholds = RegressionThresholds.model_validate(_load("regression_thresholds.json"))
    conditions = BenchmarkConditions(
        source_case_ids=[case.case_id],
        export_settings_hash="sha256:export-settings",
        lightroom_version="Lightroom Classic local",
        plugin_version="t020-lightroom-final-export-adapter-hsl-20260624",
        quality_metric_version="quality-metric-1.0",
        benchmark_policy_version="benchmark-policy-1.0",
    )

    run, evidence = build_benchmark_run_result(
        run_id="run-026-test",
        cases=[case],
        split_manifest=_load("dataset_split_manifest.json"),
        thresholds=thresholds,
        candidate_version="agent-0.8.0",
        baseline_version="agent-0.7.0",
        conditions=conditions,
        aggregate_metrics={"final_approval_rate": 0.95, "technical_failure_rate": 0.01, "mean_latency_ms": 3100},
        genre_metrics={"portrait": {"human_score": 94.2}, "night": {"human_score": 90.1}},
    )

    assert run.regression_decision == "PASS"
    assert run.conditions_hash.startswith("sha256:")
    assert evidence["split_leakage"] is False
    assert evidence["regression_decision"]["decision"] == "PASS"


def test_forbidden_comparison_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        BenchmarkRunResult(
            schema_version="t026.benchmark.run.v1",
            run_id="run-bad",
            dataset_id="tonevyra-benchmark",
            dataset_version="1.0.0",
            candidate_version="candidate",
            baseline_version="baseline",
            conditions_hash="sha256:conditions",
            aggregate_metrics={},
            genre_metrics={},
            regression_decision="PASS",
            provider_labels_visible=True,
        )
