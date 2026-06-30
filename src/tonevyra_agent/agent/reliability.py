"""T-028 production reliability primitives for local agent operations."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from tonevyra_agent.core.config import Settings, get_settings
from tonevyra_agent.storage.artifacts import calculate_sha256


CHECKPOINT_SCHEMA_VERSION = "t028.operation.checkpoint.v1"
INCIDENT_SCHEMA_VERSION = "t028.incident.event.v1"
RUNTIME_EVIDENCE_SCHEMA_VERSION = "t028.runtime.evidence.v1"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_utc_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


class FaultClass(StrEnum):
    TRANSIENT = "TRANSIENT"
    RECOVERABLE_RESTART = "RECOVERABLE_RESTART"
    MANUAL_INTERVENTION = "MANUAL_INTERVENTION"
    TERMINAL = "TERMINAL"


class CheckpointState(StrEnum):
    PENDING = "PENDING"
    COMMITTED = "COMMITTED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


class LeaseDecision(StrEnum):
    ACQUIRED = "ACQUIRED"
    ALREADY_OWNED = "ALREADY_OWNED"
    BUSY = "BUSY"
    RECLAIMED = "RECLAIMED"


class ReconciliationStatus(StrEnum):
    OK = "OK"
    FILE_CREATED_DB_MISSING = "FILE_CREATED_DB_MISSING"
    DB_RECORDED_FILE_MISSING = "DB_RECORDED_FILE_MISSING"
    CHECKSUM_MISMATCH = "CHECKSUM_MISMATCH"


class OperationCheckpoint(BaseModel):
    """Durable checkpoint committed only after operation evidence exists."""

    model_config = ConfigDict(extra="allow", frozen=True)

    schema_version: Literal["t028.operation.checkpoint.v1"] = CHECKPOINT_SCHEMA_VERSION
    checkpoint_id: str
    job_id: str
    attempt_id: str
    stage: str
    state: Literal["PENDING", "COMMITTED", "RECONCILIATION_REQUIRED"]
    input_checksums: list[str] = Field(default_factory=list)
    output_checksums: list[str] = Field(default_factory=list)
    pending_command: dict[str, Any] | None = None
    idempotency_key: str
    lease_owner: str | None = None
    created_at: str
    committed_at: str | None = None

    @field_validator("checkpoint_id", "job_id", "attempt_id", "stage", "idempotency_key", "created_at")
    @classmethod
    def non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("checkpoint text fields must not be empty")
        return value

    @model_validator(mode="after")
    def validate_commit_evidence(self) -> "OperationCheckpoint":
        if self.state == CheckpointState.COMMITTED.value:
            if not self.output_checksums:
                raise ValueError("committed checkpoint requires output checksum evidence")
            if self.committed_at is None:
                raise ValueError("committed checkpoint requires committed_at")
        return self


class IncidentEvent(BaseModel):
    """Structured fault event without private image payloads."""

    model_config = ConfigDict(extra="allow", frozen=True)

    schema_version: Literal["t028.incident.event.v1"] = INCIDENT_SCHEMA_VERSION
    incident_id: str
    correlation_id: str
    job_id: str
    attempt_id: str | None = None
    stage: str
    component: str
    provider: str | None = None
    plan: str | None = None
    fault_class: Literal["TRANSIENT", "RECOVERABLE_RESTART", "MANUAL_INTERVENTION", "TERMINAL"]
    error_code: str
    recovery_action: str
    retry_count: int = Field(default=0, ge=0)
    checkpoint_id: str | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    created_at: str

    @field_validator("incident_id", "correlation_id", "job_id", "stage", "component", "error_code", "recovery_action")
    @classmethod
    def non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("incident text fields must not be empty")
        return value


class JobLease(BaseModel):
    """Single-worker lease with expiry and heartbeat evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["t028.job.lease.v1"] = "t028.job.lease.v1"
    lease_id: str
    job_id: str
    owner: str
    acquired_at: str
    expires_at: str
    heartbeat_at: str

    @property
    def is_expired(self) -> bool:
        return parse_utc_iso(self.expires_at) <= datetime.now(timezone.utc)


class IdempotencyRecord(BaseModel):
    """Result cache for command boundaries that must execute once."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["t028.idempotency.record.v1"] = "t028.idempotency.record.v1"
    idempotency_key: str
    boundary: str
    state: Literal["COMMITTED", "FAILED"]
    external_execution_count: int = Field(ge=0, le=1)
    result: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    committed_at: str


class OperatorAuditEvent(BaseModel):
    """Audit record for operator-triggered actions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["t028.operator.audit.v1"] = "t028.operator.audit.v1"
    audit_id: str
    action: str
    target: str
    operator_id: str
    dry_run: bool
    confirmation_required: bool
    confirmed: bool
    created_at: str
    outcome: str


class HealthSnapshot(BaseModel):
    """Minimal local health and operations metrics snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["t028.health.snapshot.v1"] = "t028.health.snapshot.v1"
    status: Literal["OK", "DEGRADED"]
    queue_depth: int = Field(ge=0)
    active_job: str | None = None
    stale_lease_count: int = Field(ge=0)
    incident_count: int = Field(ge=0)
    checkpoint_count: int = Field(ge=0)
    idempotency_record_count: int = Field(ge=0)
    created_at: str


class RuntimeEvidence(BaseModel):
    """Strict harness evidence envelope for a T-028 implementation run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["t028.runtime.evidence.v1"] = RUNTIME_EVIDENCE_SCHEMA_VERSION
    ticket: Literal["T028"] = "T028"
    completed: bool
    regressions_passed: bool
    evidence: list[dict[str, Any]] = Field(default_factory=list)


@dataclass(frozen=True)
class LeaseAcquireResult:
    decision: LeaseDecision
    lease: JobLease | None


@dataclass(frozen=True)
class ReconciliationFinding:
    status: ReconciliationStatus
    artifact_path: str
    expected_sha256: str | None = None
    actual_sha256: str | None = None


class ReliabilityStore:
    """File-backed T-028 operational evidence store.

    The store is intentionally local and JSON-based for MVP operations. It gives
    the agent durable evidence without adding new PostgreSQL tables before the
    Alembic contract for this ticket is finalized.
    """

    def __init__(self, settings: Settings | None = None, root: Path | None = None) -> None:
        self.settings = settings or get_settings()
        base = root or self.settings.project_path(self.settings.runtime_dir) / "operations"
        self.root = base.resolve()
        self.checkpoint_dir = self.root / "checkpoints"
        self.idempotency_dir = self.root / "idempotency"
        self.lease_dir = self.root / "leases"
        self.incident_dir = self.root / "incidents"
        self.audit_dir = self.root / "audit"
        self.health_dir = self.root / "health"
        for path in (
            self.checkpoint_dir,
            self.idempotency_dir,
            self.lease_dir,
            self.incident_dir,
            self.audit_dir,
            self.health_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def commit_checkpoint(
        self,
        *,
        job_id: str,
        attempt_id: str,
        stage: str,
        idempotency_key: str,
        output_paths: list[Path],
        input_checksums: list[str] | None = None,
        pending_command: dict[str, Any] | None = None,
        lease_owner: str | None = None,
    ) -> OperationCheckpoint:
        output_checksums = [f"sha256:{calculate_sha256(path)}" for path in output_paths if path.exists()]
        if len(output_checksums) != len(output_paths):
            missing = [str(path) for path in output_paths if not path.exists()]
            raise ValueError(f"cannot commit checkpoint; output evidence missing: {missing}")
        checkpoint = OperationCheckpoint(
            checkpoint_id=f"ckpt-{uuid4()}",
            job_id=job_id,
            attempt_id=attempt_id,
            stage=stage,
            state=CheckpointState.COMMITTED.value,
            input_checksums=input_checksums or [],
            output_checksums=output_checksums,
            pending_command=pending_command,
            idempotency_key=idempotency_key,
            lease_owner=lease_owner,
            created_at=utc_now_iso(),
            committed_at=utc_now_iso(),
        )
        self._write_model(self.checkpoint_dir / f"{checkpoint.checkpoint_id}.json", checkpoint)
        return checkpoint

    def latest_checkpoint(self, job_id: str) -> OperationCheckpoint | None:
        checkpoints = [
            OperationCheckpoint.model_validate(self._read_json(path))
            for path in self.checkpoint_dir.glob("*.json")
            if self._read_json(path).get("job_id") == job_id
        ]
        if not checkpoints:
            return None
        return max(checkpoints, key=lambda item: parse_utc_iso(item.committed_at or item.created_at))

    def execute_idempotent(
        self,
        *,
        boundary: str,
        idempotency_key: str,
        operation: Callable[[], dict[str, Any]],
    ) -> IdempotencyRecord:
        path = self.idempotency_dir / f"{_safe_name(boundary)}--{_safe_name(idempotency_key)}.json"
        if path.exists():
            return IdempotencyRecord.model_validate(self._read_json(path))
        result = operation()
        record = IdempotencyRecord(
            idempotency_key=idempotency_key,
            boundary=boundary,
            state="COMMITTED",
            external_execution_count=1,
            result=result,
            created_at=utc_now_iso(),
            committed_at=utc_now_iso(),
        )
        self._write_model(path, record, fail_if_exists=True)
        return record

    def acquire_lease(
        self,
        *,
        job_id: str,
        owner: str,
        ttl_seconds: int,
        owner_process_alive: Callable[[str], bool] | None = None,
    ) -> LeaseAcquireResult:
        if ttl_seconds < 1:
            raise ValueError("lease ttl_seconds must be >= 1")
        path = self.lease_dir / f"{_safe_name(job_id)}.json"
        now = datetime.now(timezone.utc).replace(microsecond=0)
        existing = JobLease.model_validate(self._read_json(path)) if path.exists() else None
        if existing is not None:
            if existing.owner == owner and not existing.is_expired:
                return LeaseAcquireResult(LeaseDecision.ALREADY_OWNED, existing)
            owner_alive = owner_process_alive(existing.owner) if owner_process_alive else True
            if not existing.is_expired or owner_alive:
                return LeaseAcquireResult(LeaseDecision.BUSY, existing)
            decision = LeaseDecision.RECLAIMED
        else:
            decision = LeaseDecision.ACQUIRED
        lease = JobLease(
            lease_id=f"lease-{uuid4()}",
            job_id=job_id,
            owner=owner,
            acquired_at=now.isoformat(),
            expires_at=(now + timedelta(seconds=ttl_seconds)).isoformat(),
            heartbeat_at=now.isoformat(),
        )
        self._write_model(path, lease)
        return LeaseAcquireResult(decision, lease)

    def heartbeat(self, *, job_id: str, owner: str, ttl_seconds: int) -> JobLease:
        path = self.lease_dir / f"{_safe_name(job_id)}.json"
        if not path.exists():
            raise ValueError(f"lease not found for job {job_id}")
        current = JobLease.model_validate(self._read_json(path))
        if current.owner != owner:
            raise ValueError(f"lease owner mismatch for job {job_id}")
        now = datetime.now(timezone.utc).replace(microsecond=0)
        lease = current.model_copy(
            update={
                "heartbeat_at": now.isoformat(),
                "expires_at": (now + timedelta(seconds=ttl_seconds)).isoformat(),
            }
        )
        self._write_model(path, lease)
        return lease

    def record_incident(
        self,
        *,
        correlation_id: str,
        job_id: str,
        stage: str,
        component: str,
        fault_class: FaultClass | str,
        error_code: str,
        recovery_action: str,
        attempt_id: str | None = None,
        provider: str | None = None,
        plan: str | None = None,
        retry_count: int = 0,
        checkpoint_id: str | None = None,
        duration_ms: int | None = None,
    ) -> IncidentEvent:
        event = IncidentEvent(
            incident_id=f"incident-{uuid4()}",
            correlation_id=correlation_id,
            job_id=job_id,
            attempt_id=attempt_id,
            stage=stage,
            component=component,
            provider=provider,
            plan=plan,
            fault_class=FaultClass(fault_class).value,
            error_code=error_code,
            recovery_action=recovery_action,
            retry_count=retry_count,
            checkpoint_id=checkpoint_id,
            duration_ms=duration_ms,
            created_at=utc_now_iso(),
        )
        self._write_model(self.incident_dir / f"{event.incident_id}.json", event)
        return event

    def audit_operator_action(
        self,
        *,
        action: str,
        target: str,
        operator_id: str,
        dry_run: bool,
        confirmation_required: bool,
        confirmed: bool = False,
    ) -> OperatorAuditEvent:
        if confirmation_required and not dry_run and not confirmed:
            raise ValueError("dangerous operator action requires confirmation")
        event = OperatorAuditEvent(
            audit_id=f"audit-{uuid4()}",
            action=action,
            target=target,
            operator_id=operator_id,
            dry_run=dry_run,
            confirmation_required=confirmation_required,
            confirmed=confirmed,
            created_at=utc_now_iso(),
            outcome="DRY_RUN" if dry_run else "RECORDED",
        )
        self._write_model(self.audit_dir / f"{event.audit_id}.json", event)
        return event

    def reconcile_artifacts(self, db_artifacts: list[dict[str, Any]], file_paths: list[Path]) -> list[ReconciliationFinding]:
        findings: list[ReconciliationFinding] = []
        db_by_path = {str(Path(item["artifact_path"])): item for item in db_artifacts}
        file_by_path = {str(path): path for path in file_paths}
        for artifact_path, row in db_by_path.items():
            path = Path(artifact_path)
            if not path.exists():
                findings.append(
                    ReconciliationFinding(
                        status=ReconciliationStatus.DB_RECORDED_FILE_MISSING,
                        artifact_path=artifact_path,
                        expected_sha256=row.get("sha256"),
                    )
                )
                continue
            expected = row.get("sha256")
            actual = calculate_sha256(path)
            if expected and expected != actual:
                findings.append(
                    ReconciliationFinding(
                        status=ReconciliationStatus.CHECKSUM_MISMATCH,
                        artifact_path=artifact_path,
                        expected_sha256=expected,
                        actual_sha256=actual,
                    )
                )
        for artifact_path, path in file_by_path.items():
            if artifact_path not in db_by_path:
                findings.append(ReconciliationFinding(status=ReconciliationStatus.FILE_CREATED_DB_MISSING, artifact_path=str(path)))
        if not findings:
            findings.append(ReconciliationFinding(status=ReconciliationStatus.OK, artifact_path="*"))
        return findings

    def health_snapshot(self, *, queue_depth: int = 0, active_job: str | None = None) -> HealthSnapshot:
        stale_count = 0
        for path in self.lease_dir.glob("*.json"):
            try:
                if JobLease.model_validate(self._read_json(path)).is_expired:
                    stale_count += 1
            except ValueError:
                stale_count += 1
        status: Literal["OK", "DEGRADED"] = "DEGRADED" if stale_count else "OK"
        snapshot = HealthSnapshot(
            status=status,
            queue_depth=queue_depth,
            active_job=active_job,
            stale_lease_count=stale_count,
            incident_count=len(list(self.incident_dir.glob("*.json"))),
            checkpoint_count=len(list(self.checkpoint_dir.glob("*.json"))),
            idempotency_record_count=len(list(self.idempotency_dir.glob("*.json"))),
            created_at=utc_now_iso(),
        )
        self._write_model(self.health_dir / "latest.json", snapshot)
        return snapshot

    def build_runtime_evidence(self, *, regressions_passed: bool, evidence: list[dict[str, Any]]) -> RuntimeEvidence:
        return RuntimeEvidence(completed=True, regressions_passed=regressions_passed, evidence=evidence)

    def _write_model(self, path: Path, model: BaseModel, *, fail_if_exists: bool = False) -> None:
        self._write_json(path, model.model_dump(mode="json"), fail_if_exists=fail_if_exists)

    def _write_json(self, path: Path, payload: dict[str, Any], *, fail_if_exists: bool = False) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                delete=False,
                dir=path.parent,
                encoding="utf-8",
                prefix=f".{path.name}.",
                suffix=".tmp",
            ) as handle:
                temp_path = Path(handle.name)
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            if fail_if_exists and path.exists():
                temp_path.unlink()
                return
            os.replace(temp_path, path)
        except Exception:
            if temp_path and temp_path.exists():
                temp_path.unlink()
            raise

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))


def _safe_name(value: str) -> str:
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")
    cleaned = "".join(char if char in allowed else "_" for char in value)
    if not cleaned.strip("._"):
        raise ValueError("unsafe empty operation key")
    return cleaned
