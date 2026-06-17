"""Correction planner schemas."""

from pydantic import BaseModel, Field


class CorrectionPlan(BaseModel):
    base_preset: str
    style_target: str
    adjustments: dict[str, float] = Field(default_factory=dict)
    confidence: float = Field(ge=0, le=1)
    requires_review: bool = False

