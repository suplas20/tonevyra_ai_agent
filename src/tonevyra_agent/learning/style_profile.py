"""T-025 local user style profile and personalization policy."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


STYLE_PROFILE_SCHEMA_VERSION = "t025.style.profile.v1"
STYLE_APPLICATION_SCHEMA_VERSION = "t025.style.application.v1"
RUNTIME_EVIDENCE_SCHEMA_VERSION = "t025.runtime.evidence.v1"
STYLE_MAPPING_VERSION = "style-map-1.0"

FORBIDDEN_T025_KEYS = {
    "plugin_command",
    "external_upload",
    "develop_settings",
    "auto_model_finetune",
    "preset_path",
}

ProfileStatus = Literal["DRAFT", "ACTIVE", "SUPERSEDED", "DISABLED"]
ProfileSource = Literal["explicit", "feedback_calibration", "imported_approved"]

PREFERENCE_BOUNDS: dict[str, tuple[float, float]] = {
    "exposure_bias": (-0.35, 0.35),
    "contrast_strength": (-0.35, 0.35),
    "highlight_rolloff": (0.0, 0.5),
    "shadow_openness": (-0.25, 0.45),
    "white_balance_bias": (-0.3, 0.3),
    "saturation_strength": (-0.3, 0.3),
    "vibrance_strength": (-0.3, 0.35),
    "skin_warmth": (-0.25, 0.25),
    "skin_smoothing_strength": (0.0, 0.35),
    "texture_clarity_balance": (-0.35, 0.35),
    "sharpening_strength": (-0.2, 0.3),
    "noise_reduction_strength": (0.0, 0.35),
}

STYLE_TO_PLANNER_KEYS: dict[str, str] = {
    "exposure_bias": "exposure_intent",
    "contrast_strength": "contrast_intent",
    "highlight_rolloff": "highlight_rolloff_intent",
    "shadow_openness": "shadow_openness_intent",
    "white_balance_bias": "white_balance_bias_intent",
    "saturation_strength": "saturation_intent",
    "vibrance_strength": "vibrance_intent",
    "skin_warmth": "skin_warmth_intent",
    "skin_smoothing_strength": "skin_smoothing_intent",
    "texture_clarity_balance": "texture_clarity_balance_intent",
    "sharpening_strength": "sharpening_intent",
    "noise_reduction_strength": "noise_reduction_intent",
}


def utc_now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


class StyleProfile(BaseModel):
    """High-level local user preference evidence for the Planner."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["t025.style.profile.v1"] = STYLE_PROFILE_SCHEMA_VERSION
    profile_id: str
    user_scope_id: str
    version: int = Field(ge=1)
    status: ProfileStatus
    source: ProfileSource
    preferences: dict[str, Any] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)
    minimum_evidence_count: int = Field(ge=0)

    @field_validator("profile_id", "user_scope_id")
    @classmethod
    def non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be empty")
        return value

    @field_validator("preferences")
    @classmethod
    def validate_preferences(cls, value: dict[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        for key, raw in value.items():
            if key == "mood_tags":
                if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
                    raise ValueError("mood_tags must be a list of strings")
                normalized[key] = sorted({item.strip() for item in raw if item.strip()})
                continue
            if key not in PREFERENCE_BOUNDS:
                raise ValueError(f"unsupported style preference: {key}")
            low, high = PREFERENCE_BOUNDS[key]
            amount = float(raw)
            if amount < low or amount > high:
                raise ValueError(f"{key} must be between {low} and {high}")
            normalized[key] = round(amount, 4)
        return normalized

    @model_validator(mode="before")
    @classmethod
    def reject_forbidden_keys(cls, data: Any) -> Any:
        _raise_forbidden(data)
        return data


class StyleApplicationEvidence(BaseModel):
    """Audit record for applying a style profile as bounded Planner intent."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["t025.style.application.v1"] = STYLE_APPLICATION_SCHEMA_VERSION
    job_id: str
    profile_id: str
    profile_version: int = Field(ge=1)
    mapping_version: str = STYLE_MAPPING_VERSION
    applied: bool
    bounded_deltas: dict[str, float] = Field(default_factory=dict)
    safety_overrides: list[str] = Field(default_factory=list)

    @field_validator("job_id", "profile_id", "mapping_version")
    @classmethod
    def non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be empty")
        return value

    @model_validator(mode="before")
    @classmethod
    def reject_forbidden_keys(cls, data: Any) -> Any:
        _raise_forbidden(data)
        return data


class RollbackEvidence(BaseModel):
    """Evidence that rollback created a new immutable version."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["t025.rollback.evidence.v1"] = "t025.rollback.evidence.v1"
    user_scope_id: str
    profile_id: str
    rollback_target_version: int
    new_version: int
    source: Literal["rollback"] = "rollback"


class OptOutPolicy(BaseModel):
    """Local user opt-out state."""

    model_config = ConfigDict(extra="forbid")

    user_scope_id: str
    opt_out: bool

    def allows_profile_load(self) -> bool:
        return not self.opt_out

    def allows_feedback_collection(self) -> bool:
        return not self.opt_out


class CalibrationCandidate(BaseModel):
    """Bounded local candidate derived from explicit feedback evidence."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["t025.calibration.candidate.v1"] = "t025.calibration.candidate.v1"
    user_scope_id: str
    created: bool
    reason: str
    sample_count: int = Field(ge=0)
    minimum_evidence_count: int = Field(ge=0)
    direction_consistency: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    bounded_delta: dict[str, float] = Field(default_factory=dict)
    automatic_model_finetune: Literal[False] = False


class T025RuntimeEvidence(BaseModel):
    """Strict harness evidence envelope for a T-025 implementation run."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["t025.runtime.evidence.v1"] = RUNTIME_EVIDENCE_SCHEMA_VERSION
    ticket: Literal["T025"] = "T025"
    completed: bool
    regressions_passed: bool
    evidence: list[dict[str, Any]] = Field(default_factory=list)


@dataclass
class StyleProfileStore:
    """In-memory policy store used by harnesses and deterministic unit tests."""

    _profiles: dict[str, list[StyleProfile]] = field(default_factory=dict)
    _opt_out: dict[str, bool] = field(default_factory=dict)

    def add_profile(self, profile: StyleProfile, *, activate: bool = False) -> StyleProfile:
        if self._opt_out.get(profile.user_scope_id):
            raise PermissionError("user has opted out of style personalization")
        profiles = list(self._profiles.get(profile.user_scope_id, []))
        if activate or profile.status == "ACTIVE":
            profiles = [_with_status(item, "SUPERSEDED") if item.status == "ACTIVE" else item for item in profiles]
            profile = _with_status(profile, "ACTIVE")
        profiles.append(profile)
        self._profiles[profile.user_scope_id] = sorted(profiles, key=lambda item: item.version)
        return profile

    def active_profile(self, user_scope_id: str) -> StyleProfile | None:
        if self._opt_out.get(user_scope_id):
            return None
        active = [profile for profile in self._profiles.get(user_scope_id, []) if profile.status == "ACTIVE"]
        if len(active) > 1:
            raise ValueError("more than one active style profile for user scope")
        return active[0] if active else None

    def require_owner_access(self, requesting_user: str, profile: StyleProfile) -> None:
        if requesting_user != profile.user_scope_id:
            raise PermissionError("cross-user style profile access denied")

    def set_opt_out(self, user_scope_id: str, opt_out: bool = True) -> OptOutPolicy:
        self._opt_out[user_scope_id] = opt_out
        if opt_out:
            disabled: list[StyleProfile] = []
            for profile in self._profiles.get(user_scope_id, []):
                disabled.append(_with_status(profile, "DISABLED") if profile.status == "ACTIVE" else profile)
            self._profiles[user_scope_id] = disabled
        return OptOutPolicy(user_scope_id=user_scope_id, opt_out=opt_out)

    def rollback(self, user_scope_id: str, *, target_version: int) -> tuple[StyleProfile, RollbackEvidence]:
        if self._opt_out.get(user_scope_id):
            raise PermissionError("user has opted out of style personalization")
        profiles = list(self._profiles.get(user_scope_id, []))
        target = next((profile for profile in profiles if profile.version == target_version), None)
        if target is None:
            raise ValueError(f"rollback target version not found: {target_version}")
        next_version = max((profile.version for profile in profiles), default=0) + 1
        restored = StyleProfile(
            profile_id=target.profile_id,
            user_scope_id=user_scope_id,
            version=next_version,
            status="ACTIVE",
            source=target.source,
            preferences=target.preferences,
            constraints=target.constraints,
            confidence=target.confidence,
            minimum_evidence_count=target.minimum_evidence_count,
        )
        restored = self.add_profile(restored, activate=True)
        evidence = RollbackEvidence(
            user_scope_id=user_scope_id,
            profile_id=target.profile_id,
            rollback_target_version=target_version,
            new_version=next_version,
        )
        return restored, evidence


def apply_style_profile_to_planner(
    profile: StyleProfile | None,
    *,
    job_id: str,
    source_limited: bool = False,
    safety_flags: list[str] | None = None,
) -> StyleApplicationEvidence:
    """Map style preferences into bounded Planner intent; never executable settings."""

    if profile is None or profile.status != "ACTIVE" or source_limited:
        overrides = list(safety_flags or [])
        if source_limited:
            overrides.append("source_limited_style_skipped")
        return StyleApplicationEvidence(
            job_id=job_id,
            profile_id=profile.profile_id if profile else "none",
            profile_version=profile.version if profile else 1,
            applied=False,
            bounded_deltas={},
            safety_overrides=sorted(set(overrides)),
        )

    safety_overrides = list(safety_flags or [])
    bounded: dict[str, float] = {}
    for preference, raw in profile.preferences.items():
        if preference == "mood_tags":
            continue
        planner_key = STYLE_TO_PLANNER_KEYS[preference]
        low, high = PREFERENCE_BOUNDS[preference]
        amount = max(low, min(high, float(raw)))
        if preference == "saturation_strength":
            max_saturation = profile.constraints.get("max_saturation_strength")
            if isinstance(max_saturation, (int, float)) and amount > float(max_saturation):
                amount = float(max_saturation)
                safety_overrides.append("saturation_clamped")
        if preference == "texture_clarity_balance" and profile.constraints.get("preserve_skin_naturalness") is True:
            if amount > 0:
                amount = 0.0
                safety_overrides.append("skin_naturalness_overrode_texture")
        bounded[planner_key] = round(amount, 4)

    return StyleApplicationEvidence(
        job_id=job_id,
        profile_id=profile.profile_id,
        profile_version=profile.version,
        applied=bool(bounded),
        bounded_deltas=bounded,
        safety_overrides=sorted(set(safety_overrides)),
    )


def build_calibration_candidate(
    *,
    user_scope_id: str,
    sample_count: int,
    minimum_evidence_count: int,
    direction_consistency: float,
    confidence: float,
    candidate_delta: dict[str, float],
) -> CalibrationCandidate:
    if sample_count < minimum_evidence_count:
        return CalibrationCandidate(
            user_scope_id=user_scope_id,
            created=False,
            reason="insufficient_evidence_count",
            sample_count=sample_count,
            minimum_evidence_count=minimum_evidence_count,
            direction_consistency=direction_consistency,
            confidence=confidence,
        )
    if direction_consistency < 0.75:
        return CalibrationCandidate(
            user_scope_id=user_scope_id,
            created=False,
            reason="inconsistent_direction",
            sample_count=sample_count,
            minimum_evidence_count=minimum_evidence_count,
            direction_consistency=direction_consistency,
            confidence=confidence,
        )
    if confidence < 0.7:
        return CalibrationCandidate(
            user_scope_id=user_scope_id,
            created=False,
            reason="low_confidence",
            sample_count=sample_count,
            minimum_evidence_count=minimum_evidence_count,
            direction_consistency=direction_consistency,
            confidence=confidence,
        )

    bounded_delta = {}
    for key, value in candidate_delta.items():
        if key not in PREFERENCE_BOUNDS:
            raise ValueError(f"unsupported calibration preference: {key}")
        low, high = PREFERENCE_BOUNDS[key]
        bounded_delta[key] = round(max(low, min(high, float(value))), 4)
    return CalibrationCandidate(
        user_scope_id=user_scope_id,
        created=True,
        reason="minimum_evidence_confidence_and_direction_met",
        sample_count=sample_count,
        minimum_evidence_count=minimum_evidence_count,
        direction_consistency=direction_consistency,
        confidence=confidence,
        bounded_delta=bounded_delta,
    )


def find_forbidden_t025_keys(value: Any, prefix: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{prefix}.{key}"
            if key in FORBIDDEN_T025_KEYS:
                found.append(child_path)
            found.extend(find_forbidden_t025_keys(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(find_forbidden_t025_keys(child, f"{prefix}[{index}]"))
    return found


def _raise_forbidden(value: Any) -> None:
    forbidden = find_forbidden_t025_keys(value)
    if forbidden:
        raise ValueError(f"T-025 style personalization payload contains forbidden fields: {forbidden}")


def _with_status(profile: StyleProfile, status: ProfileStatus) -> StyleProfile:
    data = profile.model_dump(mode="json")
    data["status"] = status
    return StyleProfile.model_validate(data)
