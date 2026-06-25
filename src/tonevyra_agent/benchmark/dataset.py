"""Dataset integrity helpers for T-026 benchmark runs."""

from __future__ import annotations

from typing import Iterable

from tonevyra_agent.benchmark.schemas import BenchmarkCase


def validate_benchmark_case(payload: dict) -> BenchmarkCase:
    """Validate one benchmark case and its provenance fields."""

    return BenchmarkCase.model_validate(payload)


def detect_split_leakage(split_manifest: dict[str, Iterable[str]]) -> dict[str, object]:
    """Return leakage evidence across train/calibration/test splits."""

    train = set(split_manifest.get("train", []))
    calibration = set(split_manifest.get("calibration", []))
    test = set(split_manifest.get("test", []))
    overlaps = {
        "train_calibration": sorted(train & calibration),
        "train_test": sorted(train & test),
        "calibration_test": sorted(calibration & test),
    }
    overlap_count = sum(len(value) for value in overlaps.values())
    return {
        "valid": overlap_count == 0,
        "overlap_count": overlap_count,
        "overlaps": overlaps,
    }


def assert_no_test_leakage(split_manifest: dict[str, Iterable[str]]) -> None:
    evidence = detect_split_leakage(split_manifest)
    if not evidence["valid"]:
        raise ValueError(f"benchmark split leakage detected: {evidence['overlaps']}")
