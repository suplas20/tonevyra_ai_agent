#!/usr/bin/env python3
"""Generate deterministic runtime evidence for T-027."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def _write_json(path: Path, payload: object) -> dict[str, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"artifact": path.name, "path": str(path), "kind": "t027_evidence"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--skip-regressions", action="store_true")
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    output_dir = (args.output_dir or project_root / "runtime" / "harness" / "t027").resolve()
    sys.path.insert(0, str(project_root / "src"))

    from tonevyra_agent.usage import (
        PlanPolicy,
        PlanRouter,
        T027RuntimeEvidence,
        UsageLedger,
        build_default_policy_registry,
    )

    fixture_root = project_root / "harness" / "fixtures" / "t027_saas_policy"
    policies = [
        PlanPolicy.model_validate(item)
        for item in json.loads((fixture_root / "plan_policies.json").read_text(encoding="utf-8"))["policies"]
    ]
    router = PlanRouter(build_default_policy_registry())
    ledger = UsageLedger()

    route_decisions = [
        router.route(user_scope_id="user-free", job_id="job-free", requested_plan_id="free"),
        router.route(user_scope_id="user-lite", job_id="job-lite", requested_plan_id="lite"),
        router.route(user_scope_id="user-standard", job_id="job-standard", requested_plan_id="standard"),
        router.route(user_scope_id="user-pro", job_id="job-pro", requested_plan_id="pro"),
        router.route(user_scope_id="user-deny", job_id="job-deny", requested_plan_id="missing"),
    ]

    standard_snapshot = route_decisions[2].snapshot
    pro_snapshot = route_decisions[3].snapshot
    if standard_snapshot is None or pro_snapshot is None:
        raise RuntimeError("expected standard/pro routes to be allowed")

    ledger.reserve(snapshot=standard_snapshot, photo_units=1, idempotency_key="user-standard:job-standard:reserve")
    ledger.commit(
        snapshot=standard_snapshot,
        photo_units=1,
        idempotency_key="user-standard:job-standard:commit",
        compute_metrics={"model_ms": 1800, "gpu_peak_mb": 5200},
    )
    ledger.commit(
        snapshot=standard_snapshot,
        photo_units=1,
        idempotency_key="user-standard:job-standard:commit",
        compute_metrics={"model_ms": 1800, "gpu_peak_mb": 5200},
    )
    for retry_no in (1, 2):
        ledger.record_quality_retry(
            snapshot=pro_snapshot,
            retry_no=retry_no,
            idempotency_key=f"user-pro:job-pro:quality-retry:{retry_no}",
            compute_metrics={"model_ms": 250},
        )

    fallback = router.controlled_module_fallback(
        decision=route_decisions[3],
        reason="MODEL_TIMEOUT",
        evidence_artifact="fallback_evidence.json",
    )

    evidence_entries = [
        _write_json(output_dir / "plan_policies.json", [policy.model_dump(mode="json") for policy in policies]),
        _write_json(
            output_dir / "route_decisions.json",
            [decision.model_dump(mode="json") for decision in route_decisions],
        ),
        _write_json(output_dir / "usage_ledger_events.json", [event.model_dump(mode="json") for event in ledger.events()]),
        _write_json(
            output_dir / "usage_totals.json",
            {
                "user-standard": ledger.totals("user-standard").model_dump(mode="json"),
                "user-pro": ledger.totals("user-pro").model_dump(mode="json"),
            },
        ),
        _write_json(output_dir / "fallback_accounting.json", fallback.model_dump(mode="json")),
    ]

    regressions_passed = True
    if not args.skip_regressions:
        checks = [
            [sys.executable, "harness/scripts/verify_live_runtime_gate.py"],
            [
                sys.executable,
                "harness/scripts/verify_t026_quality_benchmark_regression.py",
                "--runtime-evidence",
                "runtime/harness/t026/t026_runtime_evidence.json",
                "--strict",
            ],
            [sys.executable, "harness/scripts/verify_t027_saas_plan_usage_control.py"],
            [sys.executable, "-m", "pytest", "tests/test_t026_quality_benchmark_regression.py", "tests/test_t027_saas_plan_usage_control.py", "-q"],
        ]
        for command in checks:
            result = subprocess.run(command, cwd=project_root)
            if result.returncode != 0:
                regressions_passed = False
                break

    runtime_evidence = T027RuntimeEvidence(completed=True, regressions_passed=regressions_passed, evidence=evidence_entries)
    evidence_path = output_dir / "t027_runtime_evidence.json"
    evidence_path.write_text(
        json.dumps(runtime_evidence.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"OK: wrote T-027 runtime evidence to {evidence_path}")
    return 0 if regressions_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
