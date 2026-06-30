from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from tonevyra_agent.agent.reliability import (
    FaultClass,
    IncidentEvent,
    LeaseDecision,
    OperationCheckpoint,
    ReliabilityStore,
    ReconciliationStatus,
)
from tonevyra_agent.core.config import Settings


FIXTURE_ROOT = Path("harness/fixtures/t028_operations")


def _load(name: str) -> dict:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def _store(tmp_path: Path) -> ReliabilityStore:
    return ReliabilityStore(Settings(runtime_dir=tmp_path / "runtime"), root=tmp_path / "operations")


def test_t028_fixture_schemas_match_contract() -> None:
    checkpoint = OperationCheckpoint.model_validate(_load("valid_checkpoint.json"))
    incident = IncidentEvent.model_validate(_load("valid_incident_event.json"))

    assert checkpoint.schema_version == "t028.operation.checkpoint.v1"
    assert checkpoint.state == "COMMITTED"
    assert checkpoint.output_checksums
    assert incident.fault_class in {item.value for item in FaultClass}

    invalid = dict(_load("valid_checkpoint.json"))
    invalid["output_checksums"] = []
    with pytest.raises(ValidationError):
        OperationCheckpoint.model_validate(invalid)


def test_checkpoint_commits_only_after_output_evidence_exists(tmp_path: Path) -> None:
    store = _store(tmp_path)
    output = tmp_path / "attempt_result.json"
    output.write_text('{"status":"exported"}\n', encoding="utf-8")

    checkpoint = store.commit_checkpoint(
        job_id="job-028",
        attempt_id="attempt-001",
        stage="export",
        idempotency_key="job-028:export:1",
        output_paths=[output],
        input_checksums=["sha256:input"],
        lease_owner="worker-1",
    )

    assert checkpoint.state == "COMMITTED"
    assert checkpoint.output_checksums[0].startswith("sha256:")
    assert store.latest_checkpoint("job-028") == checkpoint

    with pytest.raises(ValueError):
        store.commit_checkpoint(
            job_id="job-028",
            attempt_id="attempt-002",
            stage="quality",
            idempotency_key="job-028:quality:1",
            output_paths=[tmp_path / "missing.json"],
        )


def test_duplicate_command_executes_external_operation_once(tmp_path: Path) -> None:
    store = _store(tmp_path)
    calls = 0

    def operation() -> dict:
        nonlocal calls
        calls += 1
        return {"request_id": "export-1", "status": "exported"}

    first = store.execute_idempotent(boundary="Lightroom export", idempotency_key="job-028:export:1", operation=operation)
    second = store.execute_idempotent(boundary="Lightroom export", idempotency_key="job-028:export:1", operation=operation)

    assert first == second
    assert calls == _load("duplicate_command_case.json")["expected_external_executions"]
    assert second.external_execution_count == 1


def test_stale_lease_reclaims_only_when_previous_owner_is_not_alive(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first = store.acquire_lease(job_id="job-028", owner="worker-old", ttl_seconds=1)
    assert first.decision == LeaseDecision.ACQUIRED

    busy = store.acquire_lease(
        job_id="job-028",
        owner="worker-new",
        ttl_seconds=30,
        owner_process_alive=lambda owner: True,
    )
    assert busy.decision == LeaseDecision.BUSY

    lease_path = store.lease_dir / "job-028.json"
    payload = json.loads(lease_path.read_text(encoding="utf-8"))
    payload["expires_at"] = "2000-01-01T00:00:00+00:00"
    lease_path.write_text(json.dumps(payload), encoding="utf-8")

    reclaimed = store.acquire_lease(
        job_id="job-028",
        owner="worker-new",
        ttl_seconds=30,
        owner_process_alive=lambda owner: _load("stale_lease_case.json")["owner_process_alive"],
    )
    assert reclaimed.decision == LeaseDecision.RECLAIMED
    assert reclaimed.lease is not None
    assert reclaimed.lease.owner == "worker-new"


def test_reconciliation_never_silently_overwrites_partial_commits(tmp_path: Path) -> None:
    store = _store(tmp_path)
    db_missing_file = tmp_path / "db_missing.json"
    db_changed = tmp_path / "db_changed.json"
    file_only = tmp_path / "file_only.json"
    db_changed.write_text("changed", encoding="utf-8")
    file_only.write_text("file only", encoding="utf-8")

    findings = store.reconcile_artifacts(
        db_artifacts=[
            {"artifact_path": str(db_missing_file), "sha256": "expected"},
            {"artifact_path": str(db_changed), "sha256": "wrong"},
        ],
        file_paths=[file_only],
    )
    statuses = {finding.status for finding in findings}

    assert ReconciliationStatus.DB_RECORDED_FILE_MISSING in statuses
    assert ReconciliationStatus.CHECKSUM_MISMATCH in statuses
    assert ReconciliationStatus.FILE_CREATED_DB_MISSING in statuses


def test_operator_actions_are_audited_and_dangerous_actions_require_confirmation(tmp_path: Path) -> None:
    store = _store(tmp_path)
    dry_run = store.audit_operator_action(
        action="release_stale_lease",
        target="job-028",
        operator_id="operator-local",
        dry_run=True,
        confirmation_required=True,
    )

    assert dry_run.outcome == "DRY_RUN"
    assert _load("operator_action_audit_case.json")["audit_event_required"] is True
    with pytest.raises(ValueError):
        store.audit_operator_action(
            action="release_stale_lease",
            target="job-028",
            operator_id="operator-local",
            dry_run=False,
            confirmation_required=True,
            confirmed=False,
        )


def test_health_incident_and_runtime_evidence_are_machine_readable(tmp_path: Path) -> None:
    store = _store(tmp_path)
    incident = store.record_incident(
        correlation_id="corr-028",
        job_id="job-028",
        attempt_id="attempt-001",
        stage="lightroom",
        component="lightroom_bridge",
        fault_class=FaultClass.RECOVERABLE_RESTART,
        error_code="LIGHTROOM_RESPONSE_TIMEOUT",
        recovery_action="resume_from_checkpoint",
        retry_count=1,
        duration_ms=1200,
    )
    health = store.health_snapshot(queue_depth=2, active_job="job-028")
    evidence = store.build_runtime_evidence(
        regressions_passed=True,
        evidence=[
            {"kind": "incident", "path": str(store.incident_dir / f"{incident.incident_id}.json")},
            {"kind": "health", "status": health.status},
        ],
    )

    assert incident.fault_class == FaultClass.RECOVERABLE_RESTART.value
    assert health.incident_count == 1
    assert evidence.schema_version == "t028.runtime.evidence.v1"
    assert evidence.completed is True
