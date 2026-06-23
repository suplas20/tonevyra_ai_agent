from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageDraw
from pydantic import ValidationError

from tonevyra_agent.agent.plan_policy import get_plan_policy
from tonevyra_agent.agent.retry_controller import decide_quality_retry
from tonevyra_agent.agent.state_manager import validate_transition
from tonevyra_agent.core.config import Settings
from tonevyra_agent.providers.module_analysis import ModuleAnalysisProvider, analysis_to_vision_payload
from tonevyra_agent.providers.module_quality import ModuleQualityProvider
from tonevyra_agent.schemas.analysis import AnalysisRequest, AnalysisResult
from tonevyra_agent.schemas.job import AttemptContext
from tonevyra_agent.schemas.quality import QualityRequest, RetryRecommendation, T021QualityResult
from tonevyra_agent.vision.model import ModuleVisionBackend, create_vision_backend
from tonevyra_agent.vision.schemas import VisionAnalysisResult


def test_module_analysis_provider_keeps_general_warm_photo_out_of_underwater(tmp_path: Path) -> None:
    preview_path = tmp_path / "warm_portrait.jpg"
    _write_test_image(preview_path, base=(196, 104, 62))

    result = ModuleAnalysisProvider().analyze(
        AnalysisRequest(
            job_id="job-1",
            attempt_id="attempt-0",
            preview_path=preview_path,
            metadata={"file": {"name": "warm_portrait.jpg"}},
        )
    )

    assert result.provider_type == "module"
    assert result.scene["type"] == "general_photo"
    assert result.color_findings[0]["value"] == "warm"
    assert "develop_settings" not in result.model_dump()


def test_analysis_result_rejects_direct_lightroom_adjustment_fields() -> None:
    payload = {
        "job_id": "job-1",
        "attempt_id": "attempt-0",
        "provider_type": "model",
        "provider_version": "model-contract",
        "scene": {"type": "general_photo"},
        "subjects": [],
        "technical_findings": [],
        "color_findings": [],
        "quality_risks": [],
        "confidence": 0.75,
        "develop_settings": {"Exposure2012": 0.3},
    }

    with pytest.raises(ValidationError):
        AnalysisResult.model_validate(payload)


def test_module_analysis_adapts_to_existing_vision_schema(tmp_path: Path) -> None:
    preview_path = tmp_path / "preview.jpg"
    _write_test_image(preview_path, base=(114, 128, 142))
    result = ModuleVisionBackend().analyze(preview_path=preview_path, metadata={"file": {"name": "preview.jpg"}}, prompt="")

    validated = VisionAnalysisResult.model_validate(result)

    assert validated.model_backend == "module"
    assert validated.scene_type == "general_photo"


def test_create_vision_backend_supports_t021_module_backend() -> None:
    settings = Settings(vision_backend="module")

    backend = create_vision_backend(settings)

    assert isinstance(backend, ModuleVisionBackend)


def test_module_quality_provider_returns_normalized_contract(tmp_path: Path) -> None:
    export_path = tmp_path / "export.jpg"
    _write_test_image(export_path, base=(126, 132, 121), grid=True)
    analysis = ModuleAnalysisProvider().analyze(
        AnalysisRequest(
            job_id="job-1",
            attempt_id="attempt-0",
            preview_path=export_path,
            metadata={"file": {"name": "export.jpg"}},
        )
    )

    result = ModuleQualityProvider().evaluate(
        QualityRequest(
            job_id="job-1",
            attempt_id="attempt-0",
            source_path=export_path,
            export_path=export_path,
            analysis=analysis,
            applied_adjustment_plan={"schema_version": "test"},
        )
    )

    assert result.provider_type == "module"
    assert result.status in {"APPROVED", "RETRY_REQUIRED", "SOURCE_LIMITED", "FINAL_FAILED"}
    assert 0.0 <= result.scores["overall"] <= 1.0


def test_retry_controller_is_bounded_and_evidence_based() -> None:
    quality = T021QualityResult(
        job_id="job-1",
        attempt_id="attempt-0",
        provider_type="module",
        status="RETRY_REQUIRED",
        reason_codes=["COLOR_CAST"],
        retry_recommendation=RetryRecommendation(
            recommended=True,
            strategy=["rebalance_white_balance_and_color_cast"],
            expected_improvement=0.08,
        ),
    )
    policy = get_plan_policy("t021_mvp")
    context = AttemptContext(job_id="job-1", task_id="task-1", attempt_id="attempt-0", attempt_no=0)

    decision = decide_quality_retry(quality, context, policy)
    repeated = decide_quality_retry(quality, context, policy, previous_plan_delta_hashes={decision.plan_delta_hash or ""})
    exhausted = decide_quality_retry(
        quality,
        AttemptContext(job_id="job-1", task_id="task-1", attempt_id="attempt-2", attempt_no=2),
        policy,
    )

    assert decision.retry is True
    assert decision.next_attempt_no == 1
    assert repeated.retry is False
    assert exhausted.retry is False


def test_t021_state_guard_allows_only_contract_transitions() -> None:
    assert validate_transition("CREATED", "ANALYZING") == ("CREATED", "ANALYZING")
    with pytest.raises(ValueError):
        validate_transition("APPROVED", "RETRY_REQUIRED")


def test_plan_policy_keeps_mvp_on_module_providers() -> None:
    policy = get_plan_policy("t021_mvp")

    assert policy.analysis_provider == "module"
    assert policy.quality_provider == "module"
    assert policy.max_quality_retries == 2
    assert policy.allow_model_loading is False


def test_analysis_to_vision_payload_has_no_t021_forbidden_fields(tmp_path: Path) -> None:
    preview_path = tmp_path / "blue.jpg"
    _write_test_image(preview_path, base=(80, 120, 160))
    analysis = ModuleAnalysisProvider().analyze(
        AnalysisRequest(
            job_id="job-1",
            attempt_id="attempt-0",
            preview_path=preview_path,
            metadata={"file": {"name": "blue.jpg"}},
        )
    )

    payload = analysis_to_vision_payload(analysis)

    assert {"lightroom_adjustments", "develop_settings", "preset_path", "final_decision"}.isdisjoint(payload)
    VisionAnalysisResult.model_validate(payload)


def _write_test_image(path: Path, *, base: tuple[int, int, int], grid: bool = False) -> None:
    image = Image.new("RGB", (96, 96), base)
    draw = ImageDraw.Draw(image)
    if grid:
        for x in range(0, 96, 8):
            draw.line((x, 0, x, 95), fill=(220, 220, 220))
        for y in range(0, 96, 8):
            draw.line((0, y, 95, y), fill=(40, 40, 40))
    else:
        for index in range(0, 96, 12):
            draw.rectangle((index, index // 2, min(95, index + 18), min(95, index // 2 + 10)), fill=(base[0], base[1] + 10, base[2] + 8))
    image.save(path, quality=92)
