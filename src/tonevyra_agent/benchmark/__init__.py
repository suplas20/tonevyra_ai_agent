"""T-026 quality benchmark and regression evaluation."""

from tonevyra_agent.benchmark.dataset import detect_split_leakage, validate_benchmark_case
from tonevyra_agent.benchmark.regression import evaluate_regression
from tonevyra_agent.benchmark.runner import build_benchmark_run_result, build_runtime_evidence
from tonevyra_agent.benchmark.schemas import (
    BenchmarkCase,
    BenchmarkRunResult,
    HumanBlindReview,
    RegressionDecision,
    RegressionThresholds,
    T026RuntimeEvidence,
)

__all__ = [
    "BenchmarkCase",
    "BenchmarkRunResult",
    "HumanBlindReview",
    "RegressionDecision",
    "RegressionThresholds",
    "T026RuntimeEvidence",
    "build_benchmark_run_result",
    "build_runtime_evidence",
    "detect_split_leakage",
    "evaluate_regression",
    "validate_benchmark_case",
]
