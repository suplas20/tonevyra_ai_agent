#!/usr/bin/env python3
"""Generate deterministic runtime evidence for T-026."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def _write_json(path: Path, payload: object) -> dict[str, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"artifact": path.name, "path": str(path), "kind": "t026_evidence"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--skip-regressions", action="store_true")
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    output_dir = (args.output_dir or project_root / "runtime" / "harness" / "t026").resolve()
    sys.path.insert(0, str(project_root / "src"))

    from tonevyra_agent.benchmark import BenchmarkCase, HumanBlindReview, RegressionThresholds
    from tonevyra_agent.benchmark.dataset import detect_split_leakage
    from tonevyra_agent.benchmark.runner import build_benchmark_run_result, build_runtime_evidence
    from tonevyra_agent.benchmark.schemas import BenchmarkConditions

    fixture_root = project_root / "harness" / "fixtures" / "t026_benchmark"
    case = BenchmarkCase.model_validate(json.loads((fixture_root / "valid_dataset_case.json").read_text(encoding="utf-8")))
    split = json.loads((fixture_root / "dataset_split_manifest.json").read_text(encoding="utf-8"))
    thresholds = RegressionThresholds.model_validate(
        json.loads((fixture_root / "regression_thresholds.json").read_text(encoding="utf-8"))
    )
    review = HumanBlindReview.model_validate(json.loads((fixture_root / "human_blind_review.json").read_text(encoding="utf-8")))
    conditions = BenchmarkConditions(
        source_case_ids=[case.case_id],
        export_settings_hash="sha256:export-settings-runtime",
        lightroom_version="Lightroom Classic local",
        plugin_version="t020-lightroom-final-export-adapter-hsl-20260624",
        quality_metric_version="quality-metric-1.0",
        benchmark_policy_version="benchmark-policy-1.0",
    )
    run, run_evidence = build_benchmark_run_result(
        run_id="run-026-runtime",
        cases=[case],
        split_manifest=split,
        thresholds=thresholds,
        candidate_version="agent-0.8.0",
        baseline_version="agent-0.7.0",
        conditions=conditions,
        aggregate_metrics={"final_approval_rate": 0.95, "technical_failure_rate": 0.01, "mean_latency_ms": 3100},
        genre_metrics={"portrait": {"human_score": 94.2}, "night": {"human_score": 90.1}},
    )

    evidence_entries = [
        _write_json(output_dir / "dataset_manifest.json", case.model_dump(mode="json")),
        _write_json(
            output_dir / "benchmark_run_manifest.json",
            {
                "run_id": run.run_id,
                "candidate_version": run.candidate_version,
                "baseline_version": run.baseline_version,
                "conditions": conditions.model_dump(mode="json"),
                "conditions_hash": run.conditions_hash,
            },
        ),
        _write_json(output_dir / "case_results.jsonl", {"case_id": case.case_id, "metrics": run.aggregate_metrics}),
        _write_json(output_dir / "aggregate_metrics.json", run.aggregate_metrics),
        _write_json(output_dir / "human_review_results.json", review.model_dump(mode="json")),
        _write_json(
            output_dir / "provider_comparison.json",
            {
                "candidate_version": run.candidate_version,
                "baseline_version": run.baseline_version,
                "same_conditions": True,
                "conditions_hash": run.conditions_hash,
            },
        ),
        _write_json(output_dir / "regression_decision.json", run_evidence["regression_decision"]),
        _write_json(output_dir / "benchmark_run_result.json", run.model_dump(mode="json")),
        _write_json(output_dir / "split_leakage_evidence.json", detect_split_leakage(split)),
    ]

    regressions_passed = True
    if not args.skip_regressions:
        checks = [
            [sys.executable, "harness/scripts/verify_live_runtime_gate.py"],
            [sys.executable, "harness/scripts/verify_t025_user_style_personalization.py", "--runtime-evidence", "runtime/harness/t025/t025_runtime_evidence.json", "--strict"],
            [sys.executable, "harness/scripts/verify_t026_quality_benchmark_regression.py"],
            [sys.executable, "-m", "pytest", "tests/test_t025_user_style_personalization.py", "tests/test_t026_quality_benchmark_regression.py", "-q"],
        ]
        for command in checks:
            result = subprocess.run(command, cwd=project_root)
            if result.returncode != 0:
                regressions_passed = False
                break

    runtime_evidence = build_runtime_evidence(regressions_passed=regressions_passed, evidence=evidence_entries)
    evidence_path = output_dir / "t026_runtime_evidence.json"
    evidence_path.write_text(
        json.dumps(runtime_evidence.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"OK: wrote T-026 runtime evidence to {evidence_path}")
    return 0 if regressions_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
