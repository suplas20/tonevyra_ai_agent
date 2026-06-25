from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from tonevyra_agent.usage import (
    PlanPolicy,
    PlanPolicyRegistry,
    PlanRouter,
    UsageLedger,
    UsageLedgerEvent,
    build_default_policy_registry,
)


FIXTURE_ROOT = Path("harness/fixtures/t027_saas_policy")


def _load(name: str) -> dict:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def test_plan_policy_fixture_matches_contract_and_forbidden_fields_are_rejected() -> None:
    policies = [PlanPolicy.model_validate(item) for item in _load("plan_policies.json")["policies"]]
    by_plan = {policy.plan_id: policy for policy in policies}

    assert by_plan["free"].analysis_provider == "module"
    assert by_plan["lite"].quality_provider == "module"
    assert by_plan["standard"].analysis_provider == "model"
    assert by_plan["pro"].fallback_policy["requires_evidence"] is True

    with pytest.raises(ValidationError):
        PlanPolicy.model_validate(_load("invalid_free_quality_degradation.json"))


def test_route_creates_immutable_snapshot_and_prevents_free_lite_model_initialization() -> None:
    router = PlanRouter(build_default_policy_registry())

    free = router.route(user_scope_id="user-1", job_id="job-free", requested_plan_id="free")
    lite = router.route(user_scope_id="user-1", job_id="job-lite", requested_plan_id="lite")
    standard = router.route(user_scope_id="user-1", job_id="job-standard", requested_plan_id="standard")

    assert free.decision == "ALLOW"
    assert free.snapshot is not None
    assert free.snapshot.policy_hash == free.snapshot.plan.policy_hash
    assert free.model_initialization_allowed is False
    assert lite.model_initialization_allowed is False
    assert standard.model_initialization_allowed is True

    with pytest.raises(ValidationError):
        free.snapshot.user_scope_id = "different-user"  # type: ignore[misc]


def test_quota_boundary_and_fail_closed_routing() -> None:
    router = PlanRouter(build_default_policy_registry())
    quota_case = _load("quota_boundary_cases.json")

    allowed = router.route(
        user_scope_id="user-1",
        job_id="job-allow",
        requested_plan_id="free",
        requested_photo_units=quota_case["cases"][0]["requested"],
        used_photo_units=quota_case["used"],
    )
    denied = router.route(
        user_scope_id="user-1",
        job_id="job-deny",
        requested_plan_id="free",
        requested_photo_units=quota_case["cases"][1]["requested"],
        used_photo_units=quota_case["used"],
    )
    missing = router.route(user_scope_id="user-1", job_id="job-missing", requested_plan_id="missing-plan")

    assert allowed.decision == quota_case["cases"][0]["expected"]
    assert denied.decision == quota_case["cases"][1]["expected"]
    assert denied.reason == "QUOTA_EXCEEDED"
    assert missing.decision == _load("fail_closed_case.json")["expected_route"]
    assert missing.audit["fail_closed"] is True


def test_usage_ledger_event_fixture_matches_schema() -> None:
    event = UsageLedgerEvent.model_validate(_load("valid_usage_ledger_event.json"))

    assert event.schema_version == "t027.usage.ledger.v1"
    assert event.state == "COMMITTED"
    assert event.photo_units == 1
    assert event.compute_metrics["quality_retries"] == 1


def test_usage_ledger_is_user_scoped_and_idempotent() -> None:
    router = PlanRouter(build_default_policy_registry())
    snapshot = router.route(user_scope_id="user-1", job_id="job-1", requested_plan_id="standard").snapshot
    assert snapshot is not None
    ledger = UsageLedger()
    duplicate_case = _load("idempotent_usage_cases.json")

    first = ledger.commit(
        snapshot=snapshot,
        photo_units=duplicate_case["events"][0]["photo_units"],
        idempotency_key=duplicate_case["events"][0]["idempotency_key"],
    )
    second = ledger.commit(
        snapshot=snapshot,
        photo_units=duplicate_case["events"][1]["photo_units"],
        idempotency_key=duplicate_case["events"][1]["idempotency_key"],
    )

    assert first == second
    assert ledger.totals("user-1").committed_photo_units == duplicate_case["expected_committed_photo_units"]

    cross_user = _load("cross_user_quota_case.json")
    user_b_snapshot = router.route(user_scope_id="user-b", job_id="job-b", requested_plan_id="free").snapshot
    assert user_b_snapshot is not None
    ledger.reserve(snapshot=user_b_snapshot, photo_units=10, idempotency_key="user-b:job-b:reserve")
    same_text_key = ledger.commit(snapshot=user_b_snapshot, photo_units=1, idempotency_key="same-key")

    assert ledger.totals("user-b").active_photo_units == cross_user["expected_used_for_check"]
    assert same_text_key.user_scope_id == "user-b"
    assert ledger.totals("user-1").committed_photo_units == 1
    assert ledger.totals("user-b").committed_photo_units == 1


def test_quality_retries_do_not_double_count_photo_units() -> None:
    router = PlanRouter(build_default_policy_registry())
    snapshot = router.route(user_scope_id="user-1", job_id="job-retry", requested_plan_id="pro").snapshot
    assert snapshot is not None
    ledger = UsageLedger()
    retry_case = _load("retry_accounting_case.json")

    ledger.reserve(snapshot=snapshot, photo_units=1, idempotency_key="job-retry:reserve")
    ledger.commit(snapshot=snapshot, photo_units=1, idempotency_key="job-retry:commit")
    for retry_no in range(1, retry_case["quality_attempts"]):
        ledger.record_quality_retry(
            snapshot=snapshot,
            retry_no=retry_no,
            idempotency_key=f"job-retry:quality-retry:{retry_no}",
            compute_metrics={"model_ms": 100},
        )

    totals = ledger.totals("user-1")
    assert totals.committed_photo_units == retry_case["expected_photo_units"]
    assert totals.compute_metrics["quality_retries"] == retry_case["expected_compute_retry_count"]
    assert totals.compute_metrics["model_ms"] == 200


def test_controlled_fallback_requires_explicit_policy_and_evidence() -> None:
    router = PlanRouter(build_default_policy_registry())
    standard = router.route(user_scope_id="user-1", job_id="job-standard", requested_plan_id="standard")
    pro = router.route(user_scope_id="user-1", job_id="job-pro", requested_plan_id="pro")

    with pytest.raises(ValueError):
        router.controlled_module_fallback(decision=standard, reason="MODEL_TIMEOUT", evidence_artifact=None)
    with pytest.raises(ValueError):
        router.controlled_module_fallback(decision=pro, reason="MODEL_TIMEOUT", evidence_artifact=None)

    fallback = router.controlled_module_fallback(
        decision=pro,
        reason="MODEL_TIMEOUT",
        evidence_artifact="fallback_evidence.json",
    )
    assert fallback.fallback_used is True
    assert fallback.executed_analysis_provider == "module"
    assert fallback.audit["degraded_mode"] is True
