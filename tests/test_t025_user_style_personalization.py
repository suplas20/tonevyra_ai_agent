from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from tonevyra_agent.learning.style_profile import (
    StyleApplicationEvidence,
    StyleProfile,
    StyleProfileStore,
    apply_style_profile_to_planner,
    build_calibration_candidate,
)


FIXTURE_ROOT = Path("harness/fixtures/t025_personalization")


def test_style_profile_fixture_matches_contract() -> None:
    payload = json.loads((FIXTURE_ROOT / "valid_style_profile.json").read_text(encoding="utf-8"))
    profile = StyleProfile.model_validate(payload)

    assert profile.schema_version == "t025.style.profile.v1"
    assert profile.status == "ACTIVE"
    assert profile.version == 2
    assert profile.preferences["mood_tags"] == ["clean", "natural"]


def test_style_application_fixture_matches_contract() -> None:
    payload = json.loads((FIXTURE_ROOT / "valid_style_application.json").read_text(encoding="utf-8"))
    evidence = StyleApplicationEvidence.model_validate(payload)

    assert evidence.schema_version == "t025.style.application.v1"
    assert evidence.applied is True
    assert evidence.mapping_version == "style-map-1.0"
    assert "saturation_clamped" in evidence.safety_overrides


def test_style_profile_rejects_direct_execution_fields() -> None:
    payload = json.loads((FIXTURE_ROOT / "invalid_direct_preset_execution.json").read_text(encoding="utf-8"))

    with pytest.raises(ValidationError):
        StyleProfile.model_validate(payload)


def test_one_active_profile_per_user_scope_and_rollback_is_versioned() -> None:
    fixture = json.loads((FIXTURE_ROOT / "profile_versioning_case.json").read_text(encoding="utf-8"))
    store = StyleProfileStore()
    user_scope_id = "user-versioned"
    profile_v1 = StyleProfile(
        profile_id="profile-versioned",
        user_scope_id=user_scope_id,
        version=1,
        status="ACTIVE",
        source="explicit",
        preferences={"contrast_strength": 0.1},
        constraints={},
        confidence=0.8,
        minimum_evidence_count=5,
    )
    profile_v2 = StyleProfile(
        profile_id="profile-versioned",
        user_scope_id=user_scope_id,
        version=2,
        status="ACTIVE",
        source="explicit",
        preferences={"contrast_strength": 0.2},
        constraints={},
        confidence=0.9,
        minimum_evidence_count=5,
    )

    store.add_profile(profile_v1, activate=True)
    active = store.add_profile(profile_v2, activate=True)
    restored, rollback = store.rollback(user_scope_id, target_version=fixture["rollback_target"])

    assert active.version == fixture["versions"][1]["version"]
    assert store.active_profile(user_scope_id) == restored
    assert restored.version == fixture["expected_new_version"]
    assert restored.preferences["contrast_strength"] == 0.1
    assert rollback.source == fixture["expected_source"]


def test_opt_out_disables_profile_load_and_feedback_collection() -> None:
    fixture = json.loads((FIXTURE_ROOT / "opt_out_case.json").read_text(encoding="utf-8"))
    store = StyleProfileStore()
    policy = store.set_opt_out(fixture["user_scope_id"], opt_out=fixture["opt_out"])

    assert store.active_profile(fixture["user_scope_id"]) is None
    assert policy.allows_profile_load() is fixture["expected_profile_loaded"]
    assert policy.allows_feedback_collection() is fixture["expected_feedback_collected"]
    with pytest.raises(PermissionError):
        store.add_profile(
            StyleProfile(
                profile_id="blocked",
                user_scope_id=fixture["user_scope_id"],
                version=1,
                status="ACTIVE",
                source="explicit",
                preferences={},
                constraints={},
                confidence=1,
                minimum_evidence_count=0,
            )
        )


def test_cross_user_profile_access_is_denied() -> None:
    fixture = json.loads((FIXTURE_ROOT / "cross_user_isolation_case.json").read_text(encoding="utf-8"))
    store = StyleProfileStore()
    profile = StyleProfile(
        profile_id="profile-b",
        user_scope_id=fixture["profile_owner"],
        version=1,
        status="ACTIVE",
        source="explicit",
        preferences={"contrast_strength": 0.1},
        constraints={},
        confidence=0.9,
        minimum_evidence_count=5,
    )

    with pytest.raises(PermissionError):
        store.require_owner_access(fixture["requesting_user"], profile)
    assert fixture["expected_access"] == "DENY"


def test_style_application_is_bounded_and_safety_overrides_win() -> None:
    profile = StyleProfile(
        profile_id="profile-safe",
        user_scope_id="user-safe",
        version=1,
        status="ACTIVE",
        source="explicit",
        preferences={
            "contrast_strength": 0.2,
            "saturation_strength": 0.3,
            "texture_clarity_balance": 0.2,
            "skin_warmth": 0.1,
        },
        constraints={"max_saturation_strength": 0.12, "preserve_skin_naturalness": True},
        confidence=0.94,
        minimum_evidence_count=5,
    )

    evidence = apply_style_profile_to_planner(profile, job_id="job-025-safe")

    assert evidence.applied is True
    assert evidence.bounded_deltas["contrast_intent"] == 0.2
    assert evidence.bounded_deltas["saturation_intent"] == 0.12
    assert evidence.bounded_deltas["texture_clarity_balance_intent"] == 0.0
    assert "saturation_clamped" in evidence.safety_overrides
    assert "skin_naturalness_overrode_texture" in evidence.safety_overrides


def test_source_limited_photo_skips_style_application() -> None:
    profile = StyleProfile(
        profile_id="profile-source-limited",
        user_scope_id="user-safe",
        version=1,
        status="ACTIVE",
        source="explicit",
        preferences={"contrast_strength": 0.2},
        constraints={},
        confidence=0.94,
        minimum_evidence_count=5,
    )

    evidence = apply_style_profile_to_planner(profile, job_id="job-source-limited", source_limited=True)

    assert evidence.applied is False
    assert evidence.bounded_deltas == {}
    assert "source_limited_style_skipped" in evidence.safety_overrides


def test_feedback_calibration_gate_creates_bounded_candidate() -> None:
    fixture = json.loads((FIXTURE_ROOT / "feedback_calibration_case.json").read_text(encoding="utf-8"))

    candidate = build_calibration_candidate(
        user_scope_id="user-local-1",
        sample_count=fixture["sample_count"],
        minimum_evidence_count=fixture["minimum_evidence_count"],
        direction_consistency=fixture["direction_consistency"],
        confidence=fixture["confidence"],
        candidate_delta=fixture["candidate_delta"],
    )

    assert candidate.created is fixture["expected_candidate_created"]
    assert candidate.automatic_model_finetune is fixture["automatic_model_finetune"]
    assert candidate.bounded_delta == fixture["candidate_delta"]


def test_feedback_calibration_rejects_insufficient_evidence() -> None:
    candidate = build_calibration_candidate(
        user_scope_id="user-local-1",
        sample_count=2,
        minimum_evidence_count=5,
        direction_consistency=0.9,
        confidence=0.9,
        candidate_delta={"contrast_strength": 0.05},
    )

    assert candidate.created is False
    assert candidate.reason == "insufficient_evidence_count"
    assert candidate.automatic_model_finetune is False
