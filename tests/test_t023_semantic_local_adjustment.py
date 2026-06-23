from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from tonevyra_agent.schemas.analysis import AnalysisResult
from tonevyra_agent.semantic import LocalAdjustmentPlanner, MaskCapabilityRegistry, SemanticSubjectAnalyzer
from tonevyra_agent.semantic.schemas import LocalAdjustmentPlan, SemanticAnalysis


def _analysis(subjects: list[dict] | None = None, *, confidence: float = 0.94, scene_type: str = "portrait_sky") -> AnalysisResult:
    return AnalysisResult(
        job_id="job-023-test",
        attempt_id="attempt-1",
        provider_type="model",
        provider_version="model-test",
        scene={"type": scene_type},
        subjects=subjects or [{"type": "person", "priority": 1, "confidence": 0.96}],
        technical_findings=[{"code": "EXPOSURE", "value": "slightly_overexposed"}],
        color_findings=[{"code": "COLOR_CAST", "value": "neutral"}],
        quality_risks=["highlight_clipping", "over_saturation"],
        confidence=confidence,
    )


def test_semantic_analyzer_creates_stable_regions() -> None:
    semantic = SemanticSubjectAnalyzer().analyze(
        _analysis(
            [
                {"type": "person", "priority": 1, "confidence": 0.96},
                {"type": "sky", "priority": 2, "confidence": 0.91},
            ]
        )
    )

    region_ids = {region.region_id for region in semantic.regions}
    assert semantic.schema_version == "t023.semantic.analysis.v1"
    assert semantic.primary_region_id == "region-person-1"
    assert {"region-person-1", "region-sky-1"}.issubset(region_ids)
    assert all(region.source == "model-normalized" for region in semantic.regions)


def test_local_planner_creates_supported_bounded_plan() -> None:
    semantic = SemanticSubjectAnalyzer().analyze(
        _analysis(
            [
                {"type": "person", "priority": 1, "confidence": 0.96},
                {"type": "sky", "priority": 2, "confidence": 0.91},
            ]
        )
    )
    planner = LocalAdjustmentPlanner()
    plan = planner.plan(semantic, global_adjustment_intents={"clarity_delta": 0.3, "saturation_delta": 0.1})

    assert plan.schema_version == "t023.local.adjustment.plan.v1"
    assert plan.degraded_mode is False
    assert [item.supported_mask_type for item in plan.plans[:2]] == ["people", "sky"]
    assert "skin_texture_safety_applied" in plan.plans[0].conflict_resolution
    assert "skin_naturalness_wins_locally" in plan.plans[0].conflict_resolution
    assert "bounded_additive_delta" in plan.plans[1].conflict_resolution
    assert plan.plans[0].bounded_adjustment_intents["texture_delta"] <= 0


def test_low_confidence_region_is_degraded_not_executed() -> None:
    semantic = SemanticSubjectAnalyzer().analyze(
        _analysis([{"type": "person", "priority": 1, "confidence": 0.65}], scene_type="portrait")
    )
    plan = LocalAdjustmentPlanner().plan(semantic)

    assert plan.degraded_mode is True
    assert plan.plans == []


def test_no_mask_capability_uses_explicit_global_only_degraded_mode() -> None:
    semantic = SemanticSubjectAnalyzer().analyze(_analysis())
    planner = LocalAdjustmentPlanner(
        capability_registry=MaskCapabilityRegistry(
            capability_snapshot_id="lr-cap-none",
            supported_mask_types=(),
            degraded_reason="mask_capability_unavailable",
        )
    )
    plan = planner.plan(semantic)
    snapshot = planner.capability_snapshot()

    assert plan.degraded_mode is True
    assert plan.plans == []
    assert snapshot.degraded_mode is True
    assert snapshot.degraded_reason == "mask_capability_unavailable"


def test_t023_schemas_reject_forbidden_execution_fields() -> None:
    with pytest.raises(ValidationError):
        SemanticAnalysis(
            job_id="job-invalid",
            attempt_id="attempt-1",
            provider_type="model",
            primary_region_id=None,
            regions=[],
            plugin_command={"execute_mask": True},
        )


def test_t023_schema_rejects_unsupported_mask_type_fixture() -> None:
    fixture = Path("harness/fixtures/t023_semantic_local_adjustment/invalid_unsupported_mask_type.json")
    payload = json.loads(fixture.read_text(encoding="utf-8"))

    with pytest.raises(ValidationError):
        LocalAdjustmentPlan.model_validate(payload)
