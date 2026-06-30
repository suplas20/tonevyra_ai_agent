"""Tests for the measurement-driven target-based Correction Planner.

Covers stage-level behavior (measurement, targets, simulation, constraints) and
the end-to-end engine, including a regression for the JWY00172 black-and-white
bug where the legacy planner crushed saturation regardless of the actual image.
"""

from __future__ import annotations

import numpy as np
import pytest

from tonevyra_agent.correction.schemas import ADJUSTMENT_RANGES, CorrectionPlan
from tonevyra_agent.correction.target_based import candidates as candidates_mod
from tonevyra_agent.correction.target_based import constraints as constraints_mod
from tonevyra_agent.correction.target_based import simulation as simulation_mod
from tonevyra_agent.correction.target_based import targets as targets_mod
from tonevyra_agent.correction.target_based.engine import plan_from_rgb
from tonevyra_agent.correction.target_based.measurement import measure_array
from tonevyra_agent.vision.schemas import (
    VisionAnalysisResult,
    VisionCorrectionIntents,
    VisionIssues,
)


def _underwater_image() -> np.ndarray:
    """Cyan/blue dominant, slightly dark, with a small blown-out window."""

    rgb = np.zeros((256, 384, 3), dtype=np.uint8)
    rgb[:, :, 0] = 60  # low red (water absorbs red)
    rgb[:, :, 1] = 120  # green
    rgb[:, :, 2] = 150  # blue -> cyan cast
    rgb[40:120, 150:260] = [235, 235, 225]  # bright window
    return rgb


def _gray_image() -> np.ndarray:
    base = np.full((128, 128, 3), 120, dtype=np.uint8)
    # tiny noise so it is not perfectly flat
    base[::4, ::4] = 122
    return base


def _dark_underwater_image() -> np.ndarray:
    rgb = _underwater_image().astype(np.float32)
    rgb[:, :, :3] *= 0.65
    rgb[40:120, 150:260] = [235, 235, 225]  # retain HDR-style blown window
    return np.clip(rgb, 0, 255).astype(np.uint8)


def _underwater_analysis() -> VisionAnalysisResult:
    return VisionAnalysisResult(
        model_backend="qwen",
        model_name="Qwen3-VL-4B-Instruct",
        scene_type="underwater",
        main_subject="diver",
        usable=True,
        confidence=0.85,
        issues=VisionIssues(
            exposure="slightly_underexposed",
            color_cast="strong_cool",
            contrast="high",
            sharpness="ok",
            noise="none",
        ),
        correction_intents=VisionCorrectionIntents(
            saturation=-4.0, aqua_saturation=-18.0, blue_saturation=-8.0, vibrance=20.0, exposure=0.25
        ),
    )


def test_measurement_reports_color_dominance() -> None:
    measurement = measure_array(_underwater_image())
    assert measurement.colored_pixel_ratio > 0.8
    assert measurement.mean_saturation > 0.3
    assert measurement.dominant_hue in {"blue", "aqua"}
    assert measurement.blue_green_minus_red > 0  # measurable cool cast


def test_target_floor_preserves_chroma_for_colorful_source() -> None:
    measurement = measure_array(_underwater_image())
    target = targets_mod.build_target_state(scene_type="underwater", measurement=measurement)
    # A colorful source must keep a meaningful chroma floor.
    assert target.saturation_floor >= 0.12
    assert target.target_saturation_low >= target.saturation_floor


def test_target_floor_does_not_fabricate_color_for_gray_source() -> None:
    measurement = measure_array(_gray_image())
    target = targets_mod.build_target_state(scene_type="general", measurement=measurement)
    assert target.saturation_floor <= 0.12


def test_simulation_is_directionally_correct() -> None:
    rgb = _underwater_image()
    base = measure_array(rgb)

    brighter = simulation_mod.predict_measurement(rgb, {"exposure": 1.0})
    assert brighter.mean_luma > base.mean_luma

    warmer = simulation_mod.predict_measurement(rgb, {"temperature_delta": 3000.0})
    assert warmer.blue_green_minus_red < base.blue_green_minus_red  # warmed up

    more_sat = simulation_mod.predict_measurement(rgb, {"saturation": 25.0})
    assert more_sat.mean_saturation > base.mean_saturation


def test_candidates_are_within_safety_ranges_after_clamp() -> None:
    measurement = measure_array(_underwater_image())
    target = targets_mod.build_target_state(scene_type="underwater", measurement=measurement)
    raw = candidates_mod.generate_candidates(
        measurement=measurement, target=target, is_underwater=True, model_intents={}
    )
    assert {c["name"] for c in raw} == {"conservative", "balanced", "aggressive", "model_anchored"}
    for candidate in raw:
        clamped, _ = constraints_mod.clamp_adjustments(candidate["adjustments"])
        for key, value in clamped.items():
            low, high = ADJUSTMENT_RANGES[key]
            assert low <= value <= high


def test_monochrome_guard_rejects_desaturating_candidate() -> None:
    rgb = _underwater_image()
    measurement = measure_array(rgb)
    target = targets_mod.build_target_state(scene_type="underwater", measurement=measurement)
    # Legacy-style crush: global -28 + blue/aqua/green near -100.
    crush = {
        "saturation": -28.0,
        "blue_saturation": -82.0,
        "aqua_saturation": -75.0,
        "green_saturation": -35.0,
    }
    predicted = simulation_mod.predict_measurement(rgb, crush)
    result = constraints_mod.evaluate(predicted=predicted, measurement=measurement, target=target)
    assert result["rejected"] is True
    assert "monochrome" in result["penalties"]


def test_engine_produces_valid_plan() -> None:
    plan, log = plan_from_rgb(analysis=_underwater_analysis(), rgb=_underwater_image())
    assert isinstance(plan, CorrectionPlan)
    assert plan.planner_version == "target-planner-v1"
    assert plan.source["planner_mode"] == "target_based"
    assert log.predicted_not_actual is True
    assert log.ground_truth_source == "closed_loop_quality_gate"
    assert log.selected_candidate in {"conservative", "balanced", "aggressive", "model_anchored"}


def test_jwy00172_regression_no_black_and_white() -> None:
    """The exact failure mode: underwater + strong_cool must NOT collapse to mono."""

    rgb = _underwater_image()
    plan, log = plan_from_rgb(analysis=_underwater_analysis(), rgb=rgb)
    adj = plan.adjustments_json

    # The legacy floor forced saturation=-28 and blue=-82; the new planner must not.
    assert adj["saturation"] > -28.0
    assert adj["blue_saturation"] > -82.0
    assert adj["aqua_saturation"] > -75.0

    # Predicted result keeps real color above the monochrome floor.
    floor = log.target_state["saturation_floor"]
    assert log.predicted_after["mean_saturation"] >= floor


def test_warm_recovery_direction_for_underwater() -> None:
    plan, _ = plan_from_rgb(analysis=_underwater_analysis(), rgb=_underwater_image())
    adj = plan.adjustments_json
    # Cool cast should be warmed (positive temperature delta) and red recovered.
    assert adj["temperature_delta"] > 0.0
    assert adj["red_saturation"] >= 0.0


def test_underwater_dark_frame_uses_midtone_aware_exposure_floor() -> None:
    plan, log = plan_from_rgb(analysis=_underwater_analysis(), rgb=_dark_underwater_image())

    assert 1.45 <= plan.adjustments_json["exposure"] <= 1.6
    assert log.secondary_correction["measured_deficit_floors"]["exposure"] > 0


def test_underwater_bright_frame_does_not_force_dark_exposure_floor() -> None:
    plan, log = plan_from_rgb(analysis=_underwater_analysis(), rgb=_underwater_image())

    assert plan.adjustments_json["exposure"] < 1.0
    assert "exposure" not in log.secondary_correction["measured_deficit_floors"]
