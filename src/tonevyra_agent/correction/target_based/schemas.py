"""Internal schemas for the measurement-driven target-based Correction Planner.

These models are local-only planner evidence. They never carry executable
Lightroom commands; the planner still emits the final bounded values through the
existing :class:`~tonevyra_agent.correction.schemas.CorrectionPlan` contract.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# Canonical Lightroom HSL hue bands used for per-hue coverage analysis.
HUE_BANDS: tuple[str, ...] = (
    "red",
    "orange",
    "yellow",
    "green",
    "aqua",
    "blue",
    "purple",
    "magenta",
)


class HueStat(BaseModel):
    """Per-hue coverage and saturation evidence."""

    model_config = ConfigDict(extra="forbid")

    coverage: float = Field(ge=0.0, le=1.0)
    mean_saturation: float = Field(ge=0.0, le=1.0)


class ImageMeasurement(BaseModel):
    """Quantitative measurement of a preview image (stage 1)."""

    model_config = ConfigDict(extra="forbid")

    width: int
    height: int
    mean_luma: float
    luma_p05: float
    luma_p50: float
    luma_p95: float
    contrast_std: float
    clipped_shadow_ratio: float
    clipped_highlight_ratio: float
    red_mean: float
    green_mean: float
    blue_mean: float
    channel_spread: float
    blue_green_minus_red: float
    mean_saturation: float
    colored_pixel_ratio: float
    dominant_hue: str
    dominant_hue_coverage: float
    hue_stats: dict[str, HueStat] = Field(default_factory=dict)
    sharpness_laplacian_var: float
    noise_residual_std: float

    def summary(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        # hue_stats can be large; keep a compact view in the decision log.
        data["hue_stats"] = {
            name: {
                "coverage": round(stat.coverage, 4),
                "mean_saturation": round(stat.mean_saturation, 4),
            }
            for name, stat in self.hue_stats.items()
        }
        return data


class TargetState(BaseModel):
    """Scene-specific target envelope the planner aims the image toward (stage 3)."""

    model_config = ConfigDict(extra="forbid")

    scene_type: str
    target_luma_low: float
    target_luma_high: float
    target_saturation_low: float
    target_saturation_high: float
    saturation_floor: float
    target_channel_spread: float
    allow_warm_bias: bool
    max_shadow_clip: float
    max_highlight_clip: float
    notes: list[str] = Field(default_factory=list)

    @property
    def target_luma_mid(self) -> float:
        return (self.target_luma_low + self.target_luma_high) / 2.0

    @property
    def target_saturation_mid(self) -> float:
        return (self.target_saturation_low + self.target_saturation_high) / 2.0

    def summary(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class CandidateScore(BaseModel):
    """Scored, simulated correction candidate (stages 5-7)."""

    model_config = ConfigDict(extra="forbid")

    name: str
    strategy: str
    adjustments: dict[str, float] = Field(default_factory=dict)
    clamped: bool = False
    rejected: bool = False
    reject_reason: str | None = None
    score: float = 0.0
    penalties: dict[str, float] = Field(default_factory=dict)
    predicted_summary: dict[str, Any] = Field(default_factory=dict)

    def to_log(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class PlannerDecisionLog(BaseModel):
    """Full target-based planner decision evidence (stage 10)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "tonevyra.target_planner.decision_log.v1"
    planner_version: str
    # Honesty: simulation values are predictions, not real Lightroom renders.
    predicted_not_actual: bool = True
    ground_truth_source: str = "closed_loop_quality_gate"
    degraded_mode: bool = False
    degraded_reason: str | None = None
    scene_type: str
    model_backend: str
    model_name: str
    measurement: dict[str, Any] = Field(default_factory=dict)
    model_measurement_reconciliation: list[dict[str, Any]] = Field(default_factory=list)
    target_state: dict[str, Any] = Field(default_factory=dict)
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    selected_candidate: str
    secondary_correction: dict[str, Any] = Field(default_factory=dict)
    predicted_before: dict[str, Any] = Field(default_factory=dict)
    predicted_after: dict[str, Any] = Field(default_factory=dict)
    final_adjustments: dict[str, float] = Field(default_factory=dict)
    requires_review: bool = False
    reasons: list[str] = Field(default_factory=list)

    def to_log(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
