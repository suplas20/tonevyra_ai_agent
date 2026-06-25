"""T-023 Lightroom local adjustment planner."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tonevyra_agent.semantic.schemas import (
    ConflictResolutionEvidence,
    LocalAdjustmentPlan,
    MaskCapabilitySnapshot,
    SemanticAnalysis,
    SemanticRegion,
    SupportedMaskType,
    clamp_local_adjustments,
)


DEFAULT_SUPPORTED_MASK_TYPES: tuple[SupportedMaskType, ...] = (
    "subject",
    "people",
    "face_skin",
    "sky",
    "background",
    "linear_gradient",
    "radial_gradient",
)


@dataclass(frozen=True)
class MaskCapabilityRegistry:
    """Lightroom/plugin local mask capability snapshot provider."""

    capability_snapshot_id: str = "lr-cap-1"
    supported_mask_types: tuple[SupportedMaskType, ...] = DEFAULT_SUPPORTED_MASK_TYPES
    plugin_version: str = "TonevyraAI.lrplugin"
    degraded_reason: str | None = None

    def snapshot(self) -> MaskCapabilitySnapshot:
        return MaskCapabilitySnapshot(
            capability_snapshot_id=self.capability_snapshot_id,
            supported_mask_types=list(self.supported_mask_types),
            plugin_version=self.plugin_version,
            degraded_mode=not bool(self.supported_mask_types),
            degraded_reason=self.degraded_reason if not self.supported_mask_types else None,
        )

    def supports(self, mask_type: str) -> bool:
        return mask_type in set(self.supported_mask_types)


@dataclass
class LocalAdjustmentPlanner:
    """Convert semantic evidence into bounded local adjustment plans."""

    capability_registry: MaskCapabilityRegistry = field(default_factory=MaskCapabilityRegistry)
    planner_version: str = "local-planner-1.0"
    min_execution_confidence: float = 0.7
    conflict_decisions: list[dict[str, Any]] = field(default_factory=list, init=False)
    degraded_reasons: list[str] = field(default_factory=list, init=False)

    def plan(
        self,
        semantic_analysis: SemanticAnalysis,
        *,
        global_adjustment_intents: dict[str, float] | None = None,
    ) -> LocalAdjustmentPlan:
        self.conflict_decisions = []
        self.degraded_reasons = []
        global_intents = dict(global_adjustment_intents or {})
        capability = self.capability_registry.snapshot()
        items: list[dict[str, Any]] = []

        if not capability.supported_mask_types:
            self.degraded_reasons.append("mask_capability_unavailable")
            return LocalAdjustmentPlan(
                job_id=semantic_analysis.job_id,
                attempt_id=semantic_analysis.attempt_id,
                planner_version=self.planner_version,
                capability_snapshot_id=capability.capability_snapshot_id,
                degraded_mode=True,
                plans=[],
            )

        for region in sorted(semantic_analysis.regions, key=lambda item: item.priority):
            mask_type = _mask_type_for_region(region)
            if region.confidence < self.min_execution_confidence:
                self.degraded_reasons.append(f"{region.region_id}:confidence_below_threshold")
                continue
            if not self.capability_registry.supports(mask_type):
                self.degraded_reasons.append(f"{region.region_id}:unsupported_mask_type:{mask_type}")
                continue

            bounded = clamp_local_adjustments(_intents_for_region(region))
            conflict_resolution = self._resolve_conflicts(region, bounded, global_intents)
            items.append(
                {
                    "mask_plan_id": f"mask-plan-{len(items) + 1}",
                    "region_id": region.region_id,
                    "supported_mask_type": mask_type,
                    "bounded_adjustment_intents": bounded,
                    "conflict_resolution": conflict_resolution,
                    "fallback_behavior": _fallback_for_region(region),
                }
            )

        plan = LocalAdjustmentPlan(
            job_id=semantic_analysis.job_id,
            attempt_id=semantic_analysis.attempt_id,
            planner_version=self.planner_version,
            capability_snapshot_id=capability.capability_snapshot_id,
            degraded_mode=bool(self.degraded_reasons),
            plans=items,
        )
        plan.validate_region_references(semantic_analysis)
        return plan

    def capability_snapshot(self) -> MaskCapabilitySnapshot:
        return self.capability_registry.snapshot()

    def conflict_evidence(self, semantic_analysis: SemanticAnalysis) -> ConflictResolutionEvidence:
        return ConflictResolutionEvidence(
            job_id=semantic_analysis.job_id,
            attempt_id=semantic_analysis.attempt_id,
            planner_version=self.planner_version,
            decisions=list(self.conflict_decisions),
        )

    def _resolve_conflicts(
        self,
        region: SemanticRegion,
        local_intents: dict[str, float],
        global_intents: dict[str, float],
    ) -> list[str]:
        rules: list[str] = []

        if region.region_type in {"person", "face", "skin"}:
            rules.append("skin_texture_safety_applied")
            if float(global_intents.get("clarity_delta", 0.0)) > 0:
                rules.append("skin_naturalness_wins_locally")
                self.conflict_decisions.append(
                    {
                        "case_id": "skin-vs-global-clarity",
                        "region_id": region.region_id,
                        "winning_intent": "skin_naturalness",
                        "suppressed_intent": "positive_global_clarity",
                        "rule": "skin_naturalness_wins_locally",
                        "final_bounded_delta": local_intents.get("texture_delta", 0.0),
                    }
                )

        if region.region_type == "sky" and "saturation_delta" in global_intents:
            rules.append("bounded_additive_delta")
            self.conflict_decisions.append(
                {
                    "case_id": "sky-vs-global-saturation",
                    "region_id": region.region_id,
                    "winning_intent": "bounded_sky_saturation",
                    "suppressed_intent": "unbounded_global_saturation_stack",
                    "rule": "bounded_additive_delta",
                    "final_bounded_delta": local_intents.get("saturation_delta", 0.0),
                }
            )

        return rules


def _mask_type_for_region(region: SemanticRegion) -> SupportedMaskType:
    if region.region_type == "person":
        return "people"
    if region.region_type in {"face", "skin", "hair"}:
        return "face_skin"
    if region.region_type == "sky":
        return "sky"
    if region.region_type == "background":
        return "background"
    return "subject"


def _intents_for_region(region: SemanticRegion) -> dict[str, float]:
    risks = {str(risk).lower() for risk in region.quality_risks}
    exposure_issue = str(region.attributes.get("exposure_issue", "")).lower()
    is_underexposed = "underexposed" in exposure_issue or any("underexposed" in risk for risk in risks)
    if is_underexposed and region.region_type in {"primary_subject", "person", "face", "skin", "product", "object"}:
        return {
            "exposure_delta": 0.7,
            "shadows_delta": 0.5,
            "texture_delta": 0.08,
            "noise_reduction_delta": 8.0,
            "sharpening_delta": 10.0,
        }
    if is_underexposed and region.region_type == "background":
        return {"exposure_delta": 0.25, "shadows_delta": 0.2, "saturation_delta": -0.02}
    if region.region_type in {"person", "face", "skin"}:
        return {"exposure_delta": 0.2, "highlights_delta": -0.15, "texture_delta": -0.1}
    if region.region_type == "sky":
        return {"highlights_delta": -0.2, "saturation_delta": -0.05}
    if region.region_type == "background":
        return {"exposure_delta": -0.05, "saturation_delta": -0.02}
    if region.region_type == "product":
        return {"exposure_delta": 0.12, "texture_delta": 0.08, "saturation_delta": 0.03}
    return {"exposure_delta": 0.15, "texture_delta": 0.06}


def _fallback_for_region(region: SemanticRegion) -> str:
    if region.region_type in {"person", "face", "skin", "primary_subject", "product", "object"}:
        return "global_only"
    return "skip"
