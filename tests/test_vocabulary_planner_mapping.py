"""Tests for model-vocabulary normalization and planner adjustment mapping.

These cover the integration gap found during real ARW testing: the model emits
free-text issue words (e.g. "cool"), which must normalize to canonical tokens and
then drive concrete Lightroom Classic adjustment values via the Correction Planner.
"""

from __future__ import annotations

import pytest

from tonevyra_agent.correction.planner import build_model_planner_comparison_log, create_correction_plan
from tonevyra_agent.vision import vocabulary as vocab
from tonevyra_agent.vision.model import _coerce_vision_result
from tonevyra_agent.vision.schemas import VisionAnalysisResult, VisionCorrectionIntents, VisionIssues


def _analysis(*, scene_type: str = "general_photo", **issue_overrides: str) -> VisionAnalysisResult:
    issues = {
        "exposure": "none",
        "color_cast": "none",
        "contrast": "none",
        "sharpness": "ok",
        "noise": "none",
    }
    issues.update(issue_overrides)
    return VisionAnalysisResult(
        model_backend="qwen",
        model_name="Qwen3-VL-4B-Instruct",
        scene_type=scene_type,
        main_subject="subject",
        usable=True,
        issues=VisionIssues(**issues),
        edit_intent="test",
        confidence=0.85,
    )


# ---- normalization ---------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("cool", vocab.CAST_COOL),
        ("bluish", vocab.CAST_COOL),
        ("blue-green", vocab.CAST_COOL),
        ("strong blue-green", vocab.CAST_STRONG_COOL),
        ("very cool", vocab.CAST_STRONG_COOL),
        ("warm", vocab.CAST_WARM),
        ("strong warm", vocab.CAST_STRONG_WARM),
        ("magenta", vocab.CAST_MAGENTA),
        ("green", vocab.CAST_GREEN),
        ("none", vocab.CAST_NONE),
        ("neutral", vocab.CAST_NONE),
    ],
)
def test_normalize_color_cast(raw: str, expected: str) -> None:
    assert vocab.normalize_color_cast(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("low", vocab.EXP_UNDER),
        ("dark", vocab.EXP_UNDER),
        ("slightly dark", vocab.EXP_SLIGHTLY_UNDER),
        ("very dark", vocab.EXP_SEVERELY_UNDER),
        ("high", vocab.EXP_OVER),
        ("very bright", vocab.EXP_SEVERELY_OVER),
        ("good", vocab.EXP_NONE),
    ],
)
def test_normalize_exposure(raw: str, expected: str) -> None:
    assert vocab.normalize_exposure(raw) == expected


# ---- planner mapping -------------------------------------------------------


def test_cool_cast_warms_temperature() -> None:
    plan = create_correction_plan(_analysis(color_cast="cool"))
    assert plan.adjustments_json["temperature_delta"] > 0


def test_underwater_cool_cast_is_stronger_than_generic_cool() -> None:
    underwater = create_correction_plan(_analysis(scene_type="underwater swimming", color_cast="cool"))
    generic = create_correction_plan(_analysis(scene_type="portrait", color_cast="cool"))
    assert "temp" not in underwater.adjustments_json
    assert underwater.adjustments_json["temperature_delta"] == 3500
    assert underwater.adjustments_json["temperature_delta"] > generic.adjustments_json["temperature_delta"]


def test_warm_cast_cools_temperature() -> None:
    plan = create_correction_plan(_analysis(color_cast="warm"))
    assert plan.adjustments_json["temperature_delta"] < 0


def test_green_and_magenta_use_tint_opposite_directions() -> None:
    green = create_correction_plan(_analysis(color_cast="green"))
    magenta = create_correction_plan(_analysis(color_cast="magenta"))
    assert green.adjustments_json["tint"] > 0
    assert magenta.adjustments_json["tint"] < 0


def test_underexposed_raises_exposure_and_shadows() -> None:
    plan = create_correction_plan(_analysis(exposure="underexposed"))
    assert plan.adjustments_json["exposure"] >= 1.35
    assert plan.adjustments_json["shadows"] >= 75
    assert "stronger exposure recovery applied" in plan.reason_summary
    assert "dark photo planner exposure floor applied" in plan.reason_summary


def test_slightly_underexposed_gets_visible_exposure_floor() -> None:
    plan = create_correction_plan(_analysis(exposure="slightly_underexposed"))

    assert plan.adjustments_json["exposure"] >= 0.85
    assert plan.adjustments_json["shadows"] >= 50
    assert plan.adjustments_json["whites"] >= 8
    assert "dark photo planner exposure floor applied" in plan.reason_summary


def test_dark_photo_uses_local_adjustment_mask_plan() -> None:
    plan = create_correction_plan(_analysis(exposure="underexposed"))
    local_plan = plan.local_adjustments_json["local_adjustment_plan"]

    assert plan.local_adjustments_json["execution_intent"] == "request_lightroom_classic_masks_when_supported"
    assert local_plan["degraded_mode"] is False
    assert [item["supported_mask_type"] for item in local_plan["plans"]] == ["subject", "background"]
    assert local_plan["plans"][0]["bounded_adjustment_intents"]["exposure_delta"] == 0.7
    assert local_plan["plans"][0]["bounded_adjustment_intents"]["shadows_delta"] == 0.5


def test_high_noise_increases_noise_reduction() -> None:
    plan = create_correction_plan(_analysis(noise="high"))
    assert plan.adjustments_json["noise_reduction"] > 0


def test_all_neutral_issues_produce_minimal_adjustments() -> None:
    plan = create_correction_plan(_analysis())
    # Nothing wrong => temperature/exposure stay neutral.
    assert plan.adjustments_json["temperature_delta"] == 0
    assert plan.adjustments_json["exposure"] == 0


def test_adjustments_stay_within_safe_ranges() -> None:
    plan = create_correction_plan(
        _analysis(
            scene_type="underwater swimming",
            color_cast="strong_cool",
            exposure="severely_underexposed",
            contrast="very_low",
            sharpness="very_soft",
            noise="high",
        )
    )
    from tonevyra_agent.correction.schemas import ADJUSTMENT_RANGES

    for key, value in plan.adjustments_json.items():
        low, high = ADJUSTMENT_RANGES[key]
        assert low <= value <= high, f"{key}={value} out of range {low}..{high}"


def test_model_numeric_correction_intents_do_not_override_normal_planner_defaults() -> None:
    analysis = _analysis(scene_type="portrait", color_cast="cool")
    analysis.correction_intents = VisionCorrectionIntents(
        temperature_delta=1200,
        tint=12,
        vibrance=22,
        contrast=-6,
        saturation=-4,
        whites=5,
    )

    plan = create_correction_plan(analysis)

    assert plan.style_target == "test"
    assert plan.adjustments_json["temperature_delta"] == 950
    assert plan.adjustments_json["tint"] == 8
    assert plan.adjustments_json["vibrance"] == 14
    assert "model numeric correction intents applied" not in plan.reason_summary


def test_underwater_model_intents_get_quality_recovery_floor() -> None:
    analysis = _analysis(scene_type="underwater", color_cast="strong_cool")
    analysis.correction_intents = VisionCorrectionIntents(
        exposure=0,
        temperature_delta=2000,
        tint=15,
        vibrance=25,
        saturation=0,
        clarity=10,
        texture=10,
        dehaze=15,
    )

    plan = create_correction_plan(analysis)

    assert "temp" not in plan.adjustments_json
    assert plan.adjustments_json["temperature_delta"] == 3500
    assert plan.adjustments_json["tint"] == 35
    assert plan.adjustments_json["exposure"] == 1.35
    assert plan.adjustments_json["shadows"] == 75
    assert plan.adjustments_json["highlights"] == -45
    assert plan.adjustments_json["whites"] == 18
    assert plan.adjustments_json["saturation"] == -28
    assert plan.adjustments_json["blue_saturation"] == -82
    assert plan.adjustments_json["aqua_saturation"] == -75
    assert plan.adjustments_json["red_saturation"] == 55
    assert plan.adjustments_json["orange_luminance"] == 20
    assert plan.adjustments_json["sharpening"] == 35
    assert plan.adjustments_json["noise_reduction"] == 12
    assert "underwater planner-owned quality recovery floor applied" in plan.reason_summary
    assert "80-point underwater reference recipe validation" not in plan.reason_summary


def test_fire_scene_uses_warm_expert_reference_style() -> None:
    plan = create_correction_plan(
        _analysis(
            scene_type="outdoor campfire cooking",
            color_cast="none",
            contrast="none",
            exposure="none",
        )
    )

    assert plan.adjustments_json["temperature_delta"] > 0
    assert plan.adjustments_json["vibrance"] >= 22
    assert plan.adjustments_json["saturation"] >= 8
    assert plan.adjustments_json["orange_saturation"] >= 45
    assert plan.adjustments_json["orange_luminance"] >= 26
    assert plan.adjustments_json["blue_saturation"] <= -12
    assert plan.adjustments_json["texture"] >= 22
    assert plan.adjustments_json["clarity"] >= 18
    assert plan.adjustments_json["shadows"] >= 28
    assert plan.adjustments_json["blacks"] <= -14
    assert "warm fire reference style applied" in plan.reason_summary


def test_model_numeric_correction_intents_are_ignored_by_normal_planner() -> None:
    analysis = _analysis(scene_type="portrait", color_cast="cool")
    analysis.correction_intents = VisionCorrectionIntents(temperature_delta=9000, vibrance=120, dehaze=100)

    plan = create_correction_plan(analysis)

    assert plan.adjustments_json["temperature_delta"] == 950
    assert plan.adjustments_json["vibrance"] == 14
    assert plan.adjustments_json["dehaze"] == 0
    assert plan.clamped is False


def test_model_planner_comparison_log_records_model_values_and_planner_values() -> None:
    analysis = _analysis(scene_type="portrait", color_cast="cool")
    analysis.correction_intents = VisionCorrectionIntents(temperature_delta=9000, vibrance=120, dehaze=100)
    plan = create_correction_plan(analysis)

    log = build_model_planner_comparison_log(analysis=analysis, plan=plan)
    by_key = {item["key"]: item for item in log["differences"]}

    assert log["schema_version"] == "tonevyra.model_planner_comparison_log.v1"
    assert log["direct_model_application_allowed"] is False
    assert log["model_suggestions_used_by_planner"] is False
    assert log["lightroom_applied_source"] == "planner_validated_adjustments"
    assert log["model_suggested_adjustments"] == {
        "temperature_delta": 9000.0,
        "vibrance": 120.0,
        "dehaze": 100.0,
    }
    assert log["planner_validated_adjustments"]["temperature_delta"] == 950
    assert by_key["temperature_delta"]["status"] == "ignored_out_of_range_model_suggestion"
    assert by_key["vibrance"]["planner_validated_value"] == 14
    assert by_key["vibrance"]["status"] == "ignored_out_of_range_model_suggestion"
    assert by_key["dehaze"]["planner_validated_value"] == 0


def test_qwen_vision_coercion_preserves_numeric_correction_intents() -> None:
    payload = _coerce_vision_result(
        {
            "scene_type": "underwater",
            "main_subject": "diver",
            "usable": True,
            "issues": {
                "exposure": "none",
                "color_cast": "strong cool",
                "contrast": "high",
                "sharpness": "ok",
                "noise": "none",
            },
            "correction_intents": {
                "temp": "8200",
                "temperature_delta": "1400",
                "tint": 10,
                "vibrance": 24,
                "blue_saturation": -8,
                "unsupported": 999,
            },
            "confidence": 0.88,
            "risk_flags": [],
        }
    )

    assert payload["issues"]["color_cast"] == "strong_cool"
    assert payload["correction_intents"] == {
        "temp": 8200.0,
        "temperature_delta": 1400.0,
        "tint": 10.0,
        "vibrance": 24.0,
        "blue_saturation": -8.0,
    }


# ---- source-limited classification -----------------------------------------


def test_detect_failure_class_flags_underwater_red_loss() -> None:
    from tonevyra_agent.core.enums import QualityDecision
    from tonevyra_agent.quality.analyzer import _detect_failure_class

    metrics = {"underwater_cast": {"red_mean": 26.0, "blue_green_minus_red": 79.5}}
    assert _detect_failure_class(QualityDecision.FAILED, metrics) == "SOURCE_LIMITED_UNDERWATER_RED_CHANNEL_LOSS"


def test_detect_failure_class_none_when_recoverable() -> None:
    from tonevyra_agent.core.enums import QualityDecision
    from tonevyra_agent.quality.analyzer import _detect_failure_class

    metrics = {"underwater_cast": {"red_mean": 90.0, "blue_green_minus_red": 20.0}}
    assert _detect_failure_class(QualityDecision.FAILED, metrics) is None


def test_detect_failure_class_none_when_not_failed() -> None:
    from tonevyra_agent.core.enums import QualityDecision
    from tonevyra_agent.quality.analyzer import _detect_failure_class

    metrics = {"underwater_cast": {"red_mean": 26.0, "blue_green_minus_red": 79.5}}
    assert _detect_failure_class(QualityDecision.PASS, metrics) is None
