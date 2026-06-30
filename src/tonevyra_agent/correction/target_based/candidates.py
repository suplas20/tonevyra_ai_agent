"""Stage 5 - generate multiple bounded correction candidates.

Candidates are derived from the gap between measured state and target state, then
scaled by strategy intensity. A model-anchored candidate lets the model's own
numeric suggestion compete fairly during scoring. Values here are intentionally
loose; stage 6 (constraints) clamps everything to the safety ranges.
"""

from __future__ import annotations

import math
from typing import Any

from tonevyra_agent.core.config import get_settings
from tonevyra_agent.correction.schemas import ADJUSTMENT_RANGES
from tonevyra_agent.correction.target_based.schemas import ImageMeasurement, TargetState


_STRATEGY_INTENSITY: dict[str, float] = {
    "conservative": 0.6,
    "balanced": 1.0,
    "aggressive": 1.4,
}


def generate_candidates(
    *,
    measurement: ImageMeasurement,
    target: TargetState,
    is_underwater: bool,
    model_intents: dict[str, float],
) -> list[dict[str, Any]]:
    base = _base_correction(measurement=measurement, target=target, is_underwater=is_underwater)
    candidates: list[dict[str, Any]] = []
    for strategy, intensity in _STRATEGY_INTENSITY.items():
        candidates.append(
            {
                "name": strategy,
                "strategy": strategy,
                "adjustments": _scale(base, intensity),
            }
        )
    candidates.append(
        {
            "name": "model_anchored",
            "strategy": "model_anchored",
            "adjustments": _model_anchored(base=base, model_intents=model_intents),
        }
    )
    return candidates


def _base_correction(
    *,
    measurement: ImageMeasurement,
    target: TargetState,
    is_underwater: bool,
) -> dict[str, float]:
    adj = {key: 0.0 for key in ADJUSTMENT_RANGES if key != "temp"}

    # Exposure toward target mid luma (log2 of brightness ratio).
    mean_luma = max(measurement.mean_luma, 1.0)
    ratio = target.target_luma_mid / mean_luma
    adj["exposure"] = _bounded(math.log2(ratio), -1.6, 1.6)

    # Shadow lift when deep shadows are crushed relative to target.
    shadow_gap = target.target_luma_low - measurement.luma_p05
    if shadow_gap > 0:
        adj["shadows"] = _bounded(shadow_gap * 0.9, 0.0, 80.0)
        adj["blacks"] = _bounded(-shadow_gap * 0.10, -20.0, 0.0)

    # Highlight recovery when bright areas clip or sit near white.
    highlight_pressure = measurement.clipped_highlight_ratio * 600.0
    if measurement.luma_p95 > 245.0:
        highlight_pressure += (measurement.luma_p95 - 245.0) * 4.0
    if highlight_pressure > 0:
        adj["highlights"] = _bounded(-highlight_pressure, -80.0, 0.0)
        adj["whites"] = _bounded(-highlight_pressure * 0.15, -25.0, 0.0)

    # Contrast toward a healthy spread.
    if measurement.contrast_std < 45.0:
        adj["contrast"] = _bounded((45.0 - measurement.contrast_std) * 0.6, 0.0, 35.0)
    elif measurement.contrast_std > 75.0:
        adj["contrast"] = _bounded(-(measurement.contrast_std - 75.0) * 0.5, -25.0, 0.0)

    # White balance from the measured blue-green vs red cast. Warm only enough to
    # neutralize the cast - over-warming pushes the whole frame yellow and kills
    # the natural water color, so the gain is moderate.
    cast = measurement.blue_green_minus_red
    if cast > 4.0:
        # Underwater images are meant to read COOL, not warm. Only nudge white
        # balance enough to clear murk; do NOT warm toward neutral (that kills the
        # natural underwater blue/teal and looks wrong).
        adj["temperature_delta"] = _bounded(cast * 18.0, 0.0, 800.0)
        adj["tint"] = _bounded(cast * 0.15, 0.0, 10.0)
    elif cast < -8.0:  # warm cast -> cool down
        adj["temperature_delta"] = _bounded(cast * 25.0, -3000.0, 0.0)

    # Color life. A cool cast makes the preview read as "oversaturated" in blue,
    # but the cure is white balance + per-hue control, NOT global desaturation
    # (which leaves a flat, lifeless result). Only pull global saturation down for
    # a genuine, non-cast oversaturation; otherwise keep it and lean on vibrance.
    sat = measurement.mean_saturation
    dominant_is_cool = measurement.dominant_hue in ("blue", "aqua")
    if sat < target.target_saturation_low:
        deficit = target.target_saturation_low - sat
        adj["vibrance"] = _bounded(deficit * 120.0, 0.0, 45.0)
        adj["saturation"] = _bounded(deficit * 40.0, 0.0, 20.0)
    elif sat > target.target_saturation_high and not dominant_is_cool:
        excess = sat - target.target_saturation_high
        adj["saturation"] = _bounded(-excess * 50.0, -18.0, 0.0)
    # Vibrance lifts muted mid-saturation tones for a lively (not garish) result.
    adj["vibrance"] = _bounded(max(adj["vibrance"], 22.0), 0.0, 42.0)

    if is_underwater:
        _apply_underwater_color_recovery(adj=adj, measurement=measurement)

    return adj


def _apply_underwater_color_recovery(*, adj: dict[str, float], measurement: ImageMeasurement) -> None:
    """Measurement-driven, bounded underwater recovery.

    Unlike the legacy floor, blue/aqua are reduced only in proportion to how much
    they actually dominate the frame, and warm channels are recovered. This keeps
    the image from collapsing to monochrome.
    """

    blue_cov = measurement.hue_stats.get("blue")
    aqua_cov = measurement.hue_stats.get("aqua")
    green_cov = measurement.hue_stats.get("green")
    blue_coverage = blue_cov.coverage if blue_cov else 0.0
    aqua_coverage = aqua_cov.coverage if aqua_cov else 0.0
    green_coverage = green_cov.coverage if green_cov else 0.0

    # Keep the blue subject/water alive (only a light trim), but clean the murky
    # GREEN/yellow cast that makes pool water look turbid. Dehaze + clarity clear
    # the murk. Warm channels are recovered only modestly to avoid a yellow look.
    adj["blue_saturation"] = _bounded(-blue_coverage * 26.0, -20.0, 0.0)
    adj["aqua_saturation"] = _bounded(-aqua_coverage * 32.0, -22.0, 0.0)
    adj["green_saturation"] = _bounded(-(8.0 + green_coverage * 45.0), -26.0, 0.0)
    # Light red recovery only - heavy red/orange boosts make the frame warm, which
    # is wrong for an underwater look. Keep warm channels modest.
    adj["red_saturation"] = _bounded(10.0 + blue_coverage * 10.0, 0.0, 22.0)
    adj["red_luminance"] = _bounded(12.0, 0.0, 20.0)
    adj["orange_saturation"] = _bounded(4.0 + blue_coverage * 4.0, 0.0, 12.0)
    adj["dehaze"] = max(adj.get("dehaze", 0.0), 18.0)
    adj["clarity"] = max(adj.get("clarity", 0.0), 16.0)
    adj["red_luminance"] = _bounded(15.0, 0.0, 35.0)
    # Light detail recovery typical of turbid water.
    adj["dehaze"] = max(adj.get("dehaze", 0.0), 12.0)
    adj["clarity"] = max(adj.get("clarity", 0.0), 10.0)


def _scale(base: dict[str, float], intensity: float) -> dict[str, float]:
    return {key: round(value * intensity, 3) for key, value in base.items()}


def _model_anchored(*, base: dict[str, float], model_intents: dict[str, float]) -> dict[str, float]:
    """Blend the model's numeric suggestion (50%) with the measured base (50%)."""

    blended = dict(base)
    for key, value in model_intents.items():
        if key not in ADJUSTMENT_RANGES or key == "temp" or value is None:
            continue
        blended[key] = round(0.5 * float(value) + 0.5 * base.get(key, 0.0), 3)
    return blended


def apply_measured_deficit_floors(
    *,
    adjustments: dict[str, float],
    measurement: ImageMeasurement,
    target: TargetState,
    is_underwater: bool,
) -> tuple[dict[str, float], dict[str, float]]:
    """Guarantee minimum correction strength for severe measured deficits.

    The predictive simulation cannot perfectly match Lightroom's RAW render, so a
    very dark or strongly cast image can be under-corrected if we trust the
    simulation alone. These floors are measurement-gated and apply ONLY to
    exposure / white balance / tone - never to saturation, so they cannot
    re-introduce the black-and-white regression. The monochrome guard still owns
    chroma safety.
    """

    floored = dict(adjustments)
    applied: dict[str, float] = {}

    # Underexposed but recoverable captures (e.g. a dark pool shot) need real
    # brightening, not a timid lift. Lightroom's RAW exposure response is weaker
    # than the sRGB-preview simulation implies, so the floors push hard.
    #
    # HDR scenes (dark body + a blown window/light) need different handling: a
    # global exposure push would blow the window further, so we lean on shadows
    # (which lift only dark pixels) for the body and pull highlights/whites DOWN
    # to recover the window instead of raising whites to brighten it.
    luma = measurement.mean_luma
    window_blown = measurement.clipped_highlight_ratio > 0.015 or measurement.luma_p95 >= 244.0
    if target.target_luma_mid - luma > 8.0:
        exp_floor = _dark_frame_exposure_floor(
            measurement=measurement,
            target=target,
            is_underwater=is_underwater,
            window_blown=window_blown,
        )
        sh_floor = _dark_frame_shadow_floor(measurement=measurement, target=target)
        _raise(floored, applied, "exposure", exp_floor)
        _raise(floored, applied, "shadows", sh_floor)
        if window_blown:
            # Keep the body bright via exposure/shadows, but clamp the blown
            # window hard: max highlight recovery plus strongly negative whites
            # pull the brightest pixels (window) down without darkening the body
            # midtones. This handles the dark-room + bright-window HDR case.
            _lower(floored, applied, "highlights", -80.0)
            _lower(floored, applied, "whites", -45.0)
        else:
            _lower(floored, applied, "highlights", -45.0 if luma < 60.0 else -30.0)
            _raise(floored, applied, "whites", 18.0)

    # White-balance floor: a real, visible correction toward a cool-neutral
    # underwater white balance. Strong enough to break an extreme blue cast, but
    # kept well below a warm/yellow result (nominal as-shot ~6500K + delta).
    cast = measurement.blue_green_minus_red
    if is_underwater:
        # Underwater RED is physically absorbed and cannot be recovered by HSL red
        # saturation (almost no red pixels to saturate). The real lever is TINT
        # toward magenta - magenta adds red WITHOUT the yellow that temperature
        # adds. The planner does NOT use fixed numbers: it warms proportionally to
        # the measured blue cast (kept cool) and DERIVES the magenta tint
        # PROPORTIONAL to that warming. The calibration coefficients live in
        # Settings (the planner's owned, tunable memory), not as literals here.
        cfg = get_settings()
        temp_delta = _bounded(
            cast * cfg.underwater_temp_per_cast,
            cfg.underwater_temp_delta_min,
            cfg.underwater_temp_delta_max,
        )
        tint_value = _bounded(temp_delta * cfg.underwater_tint_per_temp_delta, 0.0, cfg.underwater_tint_max)
        _raise(floored, applied, "temperature_delta", temp_delta)
        _raise(floored, applied, "tint", tint_value)
    elif cast > 12.0:
        # Non-underwater cool cast: mild neutralization only.
        _raise(floored, applied, "temperature_delta", 900.0)
        _raise(floored, applied, "tint", 8.0)

    if is_underwater:
        # Core underwater color correction applied POST candidate-selection so that
        # candidate blending (e.g. model_anchored) cannot dilute it toward zero (the
        # "only exposure changed" symptom). Tame the dominant, over-saturated blue,
        # recover the water-absorbed red, and add clarity/contrast for a real edit -
        # while white balance stays cool.
        blue_cov = measurement.hue_stats.get("blue")
        blue_coverage = blue_cov.coverage if blue_cov else 0.0
        _lower(floored, applied, "blue_saturation", -min(38.0, 14.0 + blue_coverage * 38.0))
        _lower(floored, applied, "aqua_saturation", -24.0)
        # Underwater absorbs the RED channel first, so recover red STRONGLY (chroma
        # + luminance). Keep orange/yellow modest so the recovery reads as red, not
        # a yellow/orange cast. Positive tint biases the warm recovery toward red
        # rather than green/yellow.
        cfg = get_settings()
        _raise(floored, applied, "red_saturation", cfg.underwater_red_saturation)
        _raise(floored, applied, "red_luminance", cfg.underwater_red_luminance)
        _raise(floored, applied, "orange_saturation", 10.0)
        # Cut yellow so the warm recovery reads as red, not a yellow cast.
        _lower(floored, applied, "yellow_saturation", -15.0)
        _raise(floored, applied, "vibrance", 24.0)
        _raise(floored, applied, "clarity", 24.0)
        _raise(floored, applied, "dehaze", 22.0)
        _raise(floored, applied, "contrast", 12.0)

    return floored, applied


def _raise(target_dict: dict[str, float], applied: dict[str, float], key: str, floor: float) -> None:
    if floor <= 0.0 and key not in ("temperature_delta", "tint"):
        return
    current = float(target_dict.get(key, 0.0))
    if floor > current:
        target_dict[key] = floor
        applied[key] = round(floor - current, 3)


def _dark_frame_exposure_floor(
    *,
    measurement: ImageMeasurement,
    target: TargetState,
    is_underwater: bool,
    window_blown: bool,
) -> float:
    """Estimate the minimum RAW exposure lift needed for a dark frame.

    Preview simulation tends to overestimate Lightroom RAW brightening. This
    floor therefore looks at both global luma and the median/midtone deficit.
    A dark underwater frame needs extra lift because color recovery stays muted
    until the subject midtones are bright enough.
    """

    mean_luma = max(float(measurement.mean_luma), 1.0)
    mean_gap = max(0.0, float(target.target_luma_mid) - mean_luma)
    median_gap = max(0.0, float(target.target_luma_low) - float(measurement.luma_p50))
    raw_ratio_lift = math.log2(float(target.target_luma_mid) / mean_luma)
    underwater_bonus = 0.15 if is_underwater else 0.0
    floor = raw_ratio_lift + (mean_gap / 110.0) + (median_gap / 85.0) + underwater_bonus

    # When a window/light is already clipped, allow enough global lift for the
    # subject but keep a bounded ceiling; highlights/whites recovery handles the
    # bright region separately.
    ceiling = 1.6 if window_blown else 1.85
    return round(_bounded(floor, 0.65, ceiling), 3)


def _dark_frame_shadow_floor(*, measurement: ImageMeasurement, target: TargetState) -> float:
    median_gap = max(0.0, float(target.target_luma_low) - float(measurement.luma_p50))
    shadow_gap = max(0.0, float(target.target_luma_low) - float(measurement.luma_p05))
    floor = 36.0 + median_gap * 0.35 + shadow_gap * 0.08
    return round(_bounded(floor, 45.0, 80.0), 3)


def _lower(target_dict: dict[str, float], applied: dict[str, float], key: str, ceiling: float) -> None:
    current = float(target_dict.get(key, 0.0))
    if ceiling < current:
        target_dict[key] = ceiling
        applied[key] = round(ceiling - current, 3)


def _bounded(value: float, low: float, high: float) -> float:
    return float(min(high, max(low, value)))
