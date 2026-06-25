"""Idempotent user-scoped usage ledger for T-027."""

from __future__ import annotations

from collections import defaultdict
from typing import Any
from uuid import uuid4

from tonevyra_agent.usage.schemas import PlanPolicySnapshot, UsageLedgerEvent, UsageTotals


class UsageLedger:
    """In-memory ledger used by the MVP harness and domain tests.

    The class keeps the T-027 accounting rules explicit. A later PostgreSQL
    repository can persist the same event schema without changing callers.
    """

    def __init__(self) -> None:
        self._events_by_key: dict[tuple[str, str], UsageLedgerEvent] = {}
        self._reserved_jobs: dict[tuple[str, str], int] = defaultdict(int)
        self._committed_jobs: dict[tuple[str, str], int] = defaultdict(int)
        self._released_jobs: dict[tuple[str, str], int] = defaultdict(int)
        self._compute_metrics: dict[str, dict[str, float]] = defaultdict(dict)

    def can_reserve(self, *, user_scope_id: str, snapshot: PlanPolicySnapshot, photo_units: int) -> bool:
        if snapshot.user_scope_id != user_scope_id:
            return False
        if photo_units < 1:
            return False
        return self.totals(user_scope_id).active_photo_units + photo_units <= snapshot.plan.monthly_photo_quota

    def reserve(
        self,
        *,
        snapshot: PlanPolicySnapshot,
        photo_units: int,
        idempotency_key: str,
        reason: str = "job_reserved",
    ) -> UsageLedgerEvent:
        ledger_key = (snapshot.user_scope_id, idempotency_key)
        existing = self._events_by_key.get(ledger_key)
        if existing is not None:
            return existing
        if not self.can_reserve(user_scope_id=snapshot.user_scope_id, snapshot=snapshot, photo_units=photo_units):
            raise ValueError("quota exceeded or invalid reservation")
        event = self._event(
            snapshot=snapshot,
            state="RESERVED",
            photo_units=photo_units,
            idempotency_key=idempotency_key,
            reason=reason,
        )
        self._events_by_key[ledger_key] = event
        self._reserved_jobs[(snapshot.user_scope_id, snapshot.job_id)] += photo_units
        return event

    def commit(
        self,
        *,
        snapshot: PlanPolicySnapshot,
        photo_units: int,
        idempotency_key: str,
        compute_metrics: dict[str, Any] | None = None,
        reason: str = "job_completed",
    ) -> UsageLedgerEvent:
        ledger_key = (snapshot.user_scope_id, idempotency_key)
        existing = self._events_by_key.get(ledger_key)
        if existing is not None:
            return existing
        event = self._event(
            snapshot=snapshot,
            state="COMMITTED",
            photo_units=photo_units,
            idempotency_key=idempotency_key,
            compute_metrics=compute_metrics,
            reason=reason,
        )
        self._events_by_key[ledger_key] = event
        job_key = (snapshot.user_scope_id, snapshot.job_id)
        self._committed_jobs[job_key] += photo_units
        self._reserved_jobs[job_key] = max(0, self._reserved_jobs[job_key] - photo_units)
        self._add_compute_metrics(snapshot.user_scope_id, compute_metrics or {})
        return event

    def release(
        self,
        *,
        snapshot: PlanPolicySnapshot,
        photo_units: int,
        idempotency_key: str,
        reason: str = "job_released",
    ) -> UsageLedgerEvent:
        ledger_key = (snapshot.user_scope_id, idempotency_key)
        existing = self._events_by_key.get(ledger_key)
        if existing is not None:
            return existing
        event = self._event(
            snapshot=snapshot,
            state="RELEASED",
            photo_units=photo_units,
            idempotency_key=idempotency_key,
            reason=reason,
        )
        self._events_by_key[ledger_key] = event
        job_key = (snapshot.user_scope_id, snapshot.job_id)
        self._released_jobs[job_key] += photo_units
        self._reserved_jobs[job_key] = max(0, self._reserved_jobs[job_key] - photo_units)
        return event

    def record_quality_retry(
        self,
        *,
        snapshot: PlanPolicySnapshot,
        retry_no: int,
        idempotency_key: str,
        compute_metrics: dict[str, Any] | None = None,
    ) -> UsageLedgerEvent:
        metrics = {"quality_retries": 1, **(compute_metrics or {})}
        return self.commit(
            snapshot=snapshot,
            photo_units=0,
            idempotency_key=idempotency_key,
            compute_metrics=metrics,
            reason=f"quality_retry_{retry_no}",
        )

    def totals(self, user_scope_id: str) -> UsageTotals:
        reserved = sum(units for (scope, _), units in self._reserved_jobs.items() if scope == user_scope_id)
        committed = sum(units for (scope, _), units in self._committed_jobs.items() if scope == user_scope_id)
        released = sum(units for (scope, _), units in self._released_jobs.items() if scope == user_scope_id)
        return UsageTotals(
            user_scope_id=user_scope_id,
            reserved_photo_units=reserved,
            committed_photo_units=committed,
            released_photo_units=released,
            compute_metrics=dict(self._compute_metrics.get(user_scope_id, {})),
        )

    def events(self) -> list[UsageLedgerEvent]:
        return list(self._events_by_key.values())

    @staticmethod
    def _event(
        *,
        snapshot: PlanPolicySnapshot,
        state: str,
        photo_units: int,
        idempotency_key: str,
        reason: str,
        compute_metrics: dict[str, Any] | None = None,
    ) -> UsageLedgerEvent:
        return UsageLedgerEvent(
            usage_event_id=f"usage-{uuid4()}",
            idempotency_key=idempotency_key,
            user_scope_id=snapshot.user_scope_id,
            job_id=snapshot.job_id,
            plan_id=snapshot.plan.plan_id,
            plan_version=snapshot.plan.version,
            state=state,  # type: ignore[arg-type]
            photo_units=photo_units,
            compute_metrics=compute_metrics or {},
            reason=reason,
        )

    def _add_compute_metrics(self, user_scope_id: str, metrics: dict[str, Any]) -> None:
        if not metrics:
            return
        target = self._compute_metrics[user_scope_id]
        for key, value in metrics.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            target[key] = target.get(key, 0.0) + float(value)
