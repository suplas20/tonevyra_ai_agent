"""Stage 6 - constraint validation and the monochrome guard.

Two responsibilities:
1. Clamp every adjustment to the project safety ranges (ADJUSTMENT_RANGES).
2. After simulation, penalize/reject predicted results that violate safety
   targets - most importantly the monochrome guard that blocks the
   black-and-white regression.
"""

from __future__ import annotations

from typing import Any

from tonevyra_agent.correction.schemas import ADJUSTMENT_RANGES
from tonevyra_agent.correction.target_based.schemas import ImageMeasurement, TargetState


def clamp_adjustments(adjustments: dict[str, float]) -> tuple[dict[str, float], bool]:
    """Clamp to ADJUSTMENT_RANGES. Mirrors the legacy planner's safety clamp."""

    clamped = False
    result: dict[str, float] = {}
    for key, value in adjustments.items():
        if key not in ADJUSTMENT_RANGES:
            continue
        minimum, maximum = ADJUSTMENT_RANGES[key]
        safe = max(minimum, min(maximum, float(value)))
        if safe != float(value):
            clamped = True
        result[key] = round(safe, 3)
    return result, clamped


def evaluate(
    *,
    predicted: ImageMeasurement,
    measurement: ImageMeasurement,
    target: TargetState,
    adjustments: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Return penalties/reject decision for a simulated candidate."""

    penalties: dict[str, float] = {}
    reasons: list[str] = []
    rejected = False

    # --- Input-magnitude monochrome guard (robust to simulation error). ---
    # Catches pathological desaturation directly from the adjustment values, so
    # it works even when the predictive simulation under-states chroma loss.
    if adjustments is not None and measurement.colored_pixel_ratio >= 0.05:
        dominant_key = f"{measurement.dominant_hue}_saturation"
        global_sat = float(adjustments.get("saturation", 0.0))
        dominant_sat = float(adjustments.get(dominant_key, 0.0))
        if global_sat <= -20.0 or dominant_sat <= -60.0:
            penalties["monochrome_input"] = 1000.0
            rejected = True
            reasons.append(
                f"monochrome guard (input): saturation={global_sat} "
                f"{dominant_key}={dominant_sat} crush a colorful source"
            )

    # --- Monochrome guard: never let a colorful source go (near) grayscale. ---
    if predicted.mean_saturation < target.saturation_floor:
        penalties["monochrome"] = 1000.0
        rejected = True
        reasons.append(
            f"monochrome guard: predicted saturation {predicted.mean_saturation} "
            f"< floor {round(target.saturation_floor, 4)}"
        )

    # Severe chroma loss relative to the source (even if above the absolute floor).
    if measurement.mean_saturation > 0.05:
        retained = predicted.mean_saturation / measurement.mean_saturation
        if retained < 0.45:
            penalties["chroma_loss"] = (0.45 - retained) * 200.0
            reasons.append(f"chroma retained {round(retained, 3)} below 0.45")

    # --- Clipping guards. ---
    if predicted.clipped_highlight_ratio > target.max_highlight_clip:
        over = predicted.clipped_highlight_ratio - target.max_highlight_clip
        penalties["highlight_clip"] = over * 1500.0
        reasons.append(f"highlight clipping {predicted.clipped_highlight_ratio} over limit")
    if predicted.clipped_shadow_ratio > target.max_shadow_clip:
        over = predicted.clipped_shadow_ratio - target.max_shadow_clip
        penalties["shadow_clip"] = over * 1500.0
        reasons.append(f"shadow clipping {predicted.clipped_shadow_ratio} over limit")

    return {"penalties": penalties, "rejected": rejected, "reasons": reasons}
