"""Quality gate schemas."""

from pydantic import BaseModel, Field

from mw_photo_agent.core.enums import QualityDecision


class QualityResult(BaseModel):
    exposure_score: float = Field(ge=0, le=100)
    color_score: float = Field(ge=0, le=100)
    sharpness_score: float = Field(ge=0, le=100)
    noise_score: float = Field(ge=0, le=100)
    saturation_score: float = Field(ge=0, le=100)
    underwater_cast_score: float = Field(ge=0, le=100)
    overall_score: float = Field(ge=0, le=100)
    decision: QualityDecision
    reason_summary: str

