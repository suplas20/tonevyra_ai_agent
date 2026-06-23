"""Tests for model-vocabulary normalization and planner adjustment mapping.

These cover the integration gap found during real ARW testing: the model emits
free-text issue words (e.g. "cool"), which must normalize to canonical tokens and
then drive concrete Lightroom Classic adjustment values via the Correction Planner.
"""

from __future__ import annotations

import pytest

from tonevyra_agent.correction.planner import create_correction_plan
from tonevyra_agent.vision import vocabulary as vocab
from tonevyra_agent.vision.schemas import VisionAnalysisResult, VisionIssues


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
    assert plan.adjustments_json["exposure"] > 0
    assert plan.adjustments_json["shadows"] > 0


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
