"""Schemas for local feedback and learning sample candidates."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from tonevyra_agent.core.enums import FeedbackUserAction, LearningSampleType


class DevelopSettingsSnapshot(BaseModel):
    """Lightroom develop settings snapshot captured through the JSON bridge."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(default="unknown")
    captured_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    settings: dict[str, float | int | str | bool | None] = Field(default_factory=dict)
    artifact_refs: list[dict[str, Any]] = Field(default_factory=list)


class ManualEditDelta(BaseModel):
    """Difference between AI-applied and final user-reviewed develop settings."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    changed: bool
    numeric_delta: dict[str, float] = Field(default_factory=dict)
    changed_values: dict[str, dict[str, Any]] = Field(default_factory=dict)
    ai_settings_ref: dict[str, Any] | None = None
    final_settings_ref: dict[str, Any] | None = None


class UserFeedback(BaseModel):
    """Explicit local user feedback persisted as user_feedback.json."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    task_id: str
    user_action: FeedbackUserAction
    rating: int | None = Field(default=None, ge=1, le=5)
    reason_tags: list[str] = Field(default_factory=list)
    accepted: bool | None = None
    approved_for_learning: bool = False
    comment: str | None = None

    @field_validator("task_id")
    @classmethod
    def non_empty_task_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("task_id must not be empty")
        return value

    @field_validator("reason_tags")
    @classmethod
    def normalize_reason_tags(cls, value: list[str]) -> list[str]:
        return sorted({item.strip() for item in value if item.strip()})


class FeedbackCaptureRequest(BaseModel):
    """Input contract for capturing feedback for one finalized task."""

    model_config = ConfigDict(extra="forbid")

    user_action: FeedbackUserAction
    rating: int | None = Field(default=None, ge=1, le=5)
    reason_tags: list[str] = Field(default_factory=list)
    accepted: bool | None = None
    approved_for_learning: bool = False
    comment: str | None = None
    ai_settings: DevelopSettingsSnapshot = Field(default_factory=DevelopSettingsSnapshot)
    final_settings: DevelopSettingsSnapshot = Field(default_factory=DevelopSettingsSnapshot)
    sample_type: LearningSampleType = LearningSampleType.PLANNER_CALIBRATION

    @model_validator(mode="after")
    def accepted_matches_user_action(self) -> "FeedbackCaptureRequest":
        if self.accepted is None and self.user_action == FeedbackUserAction.ACCEPTED:
            self.accepted = True
        if self.accepted is None and self.user_action == FeedbackUserAction.REJECTED:
            self.accepted = False
        return self


class TrainingSampleManifest(BaseModel):
    """Local candidate manifest for future offline planner/model learning."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    task_id: str
    feedback_id: str
    sample_type: LearningSampleType
    approved_for_learning: bool
    artifacts: dict[str, dict[str, Any]]
    metadata: dict[str, Any] = Field(default_factory=dict)


class FeedbackCaptureResult(BaseModel):
    """Result returned after feedback evidence has been persisted."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    task_id: str
    feedback_id: str
    learning_sample_id: str | None = None
    artifact_refs: dict[str, dict[str, Any]]
