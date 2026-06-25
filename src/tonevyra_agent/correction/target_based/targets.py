"""Stage 3 - scene-specific target state generation.

Targets are measurement-adaptive. The saturation floor in particular is derived
from the image's own measured chroma so the planner never forces a colorful
photo toward monochrome (the root cause of the black-and-white regression).
"""

from __future__ import annotations

from tonevyra_agent.correction.target_based.schemas import ImageMeasurement, TargetState


# Per-scene base envelopes: (luma_low, luma_high, sat_low, sat_high, channel_spread, warm_bias)
_SCENE_PROFILES: dict[str, tuple[float, float, float, float, float, bool]] = {
    "underwater": (105.0, 140.0, 0.20, 0.42, 45.0, True),
    "portrait": (115.0, 145.0, 0.18, 0.36, 22.0, False),
    "people": (115.0, 145.0, 0.18, 0.36, 22.0, False),
    "landscape": (110.0, 142.0, 0.22, 0.44, 28.0, False),
    "night": (70.0, 120.0, 0.18, 0.40, 30.0, False),
    "general": (110.0, 140.0, 0.20, 0.40, 24.0, False),
}

# Below this colored-pixel ratio the source is essentially grayscale, so we must
# not demand color (avoids fighting an intentionally monochrome capture).
_GRAYSCALE_SOURCE_RATIO = 0.05


def build_target_state(
    *,
    scene_type: str,
    measurement: ImageMeasurement,
    main_subject: str | None = None,
) -> TargetState:
    profile_key = _resolve_profile_key(scene_type=scene_type, main_subject=main_subject)
    luma_low, luma_high, sat_low, sat_high, channel_spread, warm_bias = _SCENE_PROFILES[profile_key]

    saturation_floor = _saturation_floor(measurement, scene_sat_low=sat_low)
    target_sat_low = max(saturation_floor, sat_low)
    notes = [
        f"profile={profile_key}",
        f"measured_mean_saturation={measurement.mean_saturation}",
        f"colored_pixel_ratio={measurement.colored_pixel_ratio}",
        f"dominant_hue={measurement.dominant_hue}({measurement.dominant_hue_coverage})",
        f"saturation_floor={round(saturation_floor, 4)} (preserves measured chroma)",
    ]
    if warm_bias:
        notes.append("warm color recovery permitted (channel spread tolerance relaxed)")

    return TargetState(
        scene_type=scene_type,
        target_luma_low=luma_low,
        target_luma_high=luma_high,
        target_saturation_low=target_sat_low,
        target_saturation_high=sat_high,
        saturation_floor=saturation_floor,
        target_channel_spread=channel_spread,
        allow_warm_bias=warm_bias,
        max_shadow_clip=0.02,
        max_highlight_clip=0.02,
        notes=notes,
    )


def _resolve_profile_key(*, scene_type: str, main_subject: str | None) -> str:
    scene = (scene_type or "").lower()
    subject = (main_subject or "").lower()
    if "underwater" in scene:
        return "underwater"
    if any(token in scene or token in subject for token in ("portrait", "person", "people", "face")):
        return "portrait"
    if any(token in scene for token in ("landscape", "nature", "scenery")):
        return "landscape"
    if any(token in scene for token in ("night", "lowlight", "low_light", "dark")):
        return "night"
    return "general"


def _saturation_floor(measurement: ImageMeasurement, *, scene_sat_low: float) -> float:
    """Minimum acceptable predicted chroma. Derived from the measured image.

    A colorful image keeps at least ~55% of its current chroma (absolute floor
    0.12). A near-grayscale source gets a very low floor so we don't fabricate
    color.
    """

    if measurement.colored_pixel_ratio < _GRAYSCALE_SOURCE_RATIO:
        return 0.06
    chroma_based = 0.55 * measurement.mean_saturation
    return float(min(scene_sat_low, max(0.12, round(chroma_based, 4))))
