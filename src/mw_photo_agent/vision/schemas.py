"""Vision analysis schemas."""

from pydantic import BaseModel, Field


class VisionIssue(BaseModel):
    name: str
    severity: float = Field(ge=0, le=1)


class VisionAnalysisResult(BaseModel):
    scene_type: str
    main_subject: str | None = None
    usable: bool
    issues: list[VisionIssue] = Field(default_factory=list)
    edit_intent: str | None = None
    confidence: float = Field(ge=0, le=1)
    risk_flags: list[str] = Field(default_factory=list)

