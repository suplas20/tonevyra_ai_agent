#!/usr/bin/env python3
"""Generate deterministic runtime evidence for T-028."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def _write_json(path: Path, payload: object, *, kind: str) -> dict[str, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"artifact": path.name, "path": str(path), "kind": kind}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--skip-regressions", action="store_true")
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    output_dir = (args.output_dir or project_root / "runtime" / "harness" / "t028").resolve()
    sys.path.insert(0, str(project_root / "src"))

    from tonevyra_agent.agent.reliability import FaultClass, ReliabilityStore
    from tonevyra_agent.core.config import Settings

    operations_root = output_dir / "operations"
    if operations_root.exists():
        shutil.rmtree(operations_root)
    store = ReliabilityStore(
        settings=Settings(runtime_dir=output_dir / "runtime"),
        root=operations_root,
    )

    operation_calls = 0

    def export_operation() -> dict:
        nonlocal operation_calls
        operation_calls += 1
        export_result = output_dir / "export_result.json"
        export_result.write_text('{"status":"exported","output_path":"corrected.jpg"}\n', encoding="utf-8")
        return {"request_id": "export-028", "status": "exported", "result_path": str(export_result)}

    first_export = store.execute_idempotent(
        boundary="Lightroom export",
        idempotency_key="job-028:export:1",
        operation=export_operation,
    )
    duplicate_export = store.execute_idempotent(
        boundary="Lightroom export",
        idempotency_key="job-028:export:1",
        operation=export_operation,
    )

    export_result_path = Path(first_export.result["result_path"])
    checkpoint = store.commit_checkpoint(
        job_id="job-028",
        attempt_id="attempt-001",
        stage="export",
        idempotency_key="job-028:export:1",
        output_paths=[export_result_path],
        lease_owner="worker-runtime",
    )

    lease = store.acquire_lease(job_id="job-028", owner="worker-runtime", ttl_seconds=30)
    incident = store.record_incident(
        correlation_id="corr-028-runtime",
        job_id="job-028",
        attempt_id="attempt-001",
        stage="lightroom",
        component="lightroom_bridge",
        fault_class=FaultClass.RECOVERABLE_RESTART,
        error_code="LIGHTROOM_RESPONSE_TIMEOUT",
        recovery_action="resume_from_checkpoint",
        retry_count=1,
        checkpoint_id=checkpoint.checkpoint_id,
    )
    audit = store.audit_operator_action(
        action="release_stale_lease",
        target="job-028",
        operator_id="operator-local",
        dry_run=True,
        confirmation_required=True,
    )
    health = store.health_snapshot(queue_depth=0, active_job="job-028")

    evidence_entries = [
        _write_json(output_dir / "idempotency_export.json", duplicate_export, kind="idempotency"),
        _write_json(output_dir / "checkpoint_export.json", checkpoint, kind="checkpoint"),
        _write_json(output_dir / "lease.json", lease.lease, kind="lease"),
        _write_json(output_dir / "incident.json", incident, kind="incident"),
        _write_json(output_dir / "operator_audit.json", audit, kind="operator_audit"),
        _write_json(output_dir / "health_snapshot.json", health, kind="health"),
        _write_json(
            output_dir / "duplicate_external_execution_count.json",
            {"operation_calls": operation_calls, "expected_external_executions": 1},
            kind="idempotency",
        ),
    ]

    regressions_passed = operation_calls == 1 and first_export == duplicate_export
    if not args.skip_regressions:
        checks = [
            [sys.executable, "harness/scripts/verify_t028_production_reliability_operations.py"],
            [sys.executable, "-m", "pytest", "tests/test_t028_production_reliability_operations.py", "-q"],
        ]
        for command in checks:
            result = subprocess.run(command, cwd=project_root)
            if result.returncode != 0:
                regressions_passed = False
                break

    runtime_evidence = store.build_runtime_evidence(regressions_passed=regressions_passed, evidence=evidence_entries)
    evidence_path = output_dir / "t028_runtime_evidence.json"
    evidence_path.write_text(
        json.dumps(runtime_evidence.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"OK: wrote T-028 runtime evidence to {evidence_path}")
    return 0 if regressions_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
