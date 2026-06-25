"""Local Lightroom recipe calibration for planner validation.

Recipe calibration is local-only evidence. It does not fine-tune the vision
model at runtime; it gives the model a reference target and lets the Planner
validate advisory model numbers against a known good Lightroom recipe.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tonevyra_agent.core.config import Settings, get_settings


COLOR_MIXER_COLORS = ("red", "orange", "yellow", "green", "aqua", "blue", "purple", "magenta")

RECIPE_TOLERANCES: dict[str, float] = {
    "temp": 400.0,
    "tint": 4.0,
    "exposure": 0.08,
    "contrast": 8.0,
    "highlights": 10.0,
    "shadows": 8.0,
    "whites": 8.0,
    "blacks": 8.0,
    "texture": 6.0,
    "clarity": 6.0,
    "dehaze": 6.0,
    "vibrance": 8.0,
    "saturation": 6.0,
    "sharpening": 8.0,
    "noise_reduction": 8.0,
}


@dataclass(frozen=True)
class RecipeCalibrationResult:
    recipe_name: str
    reference_score: float
    target_adjustments: dict[str, float]
    corrected_keys: tuple[str, ...]
    within_tolerance: bool

    def summary(self) -> dict[str, Any]:
        return {
            "recipe_name": self.recipe_name,
            "reference_score": self.reference_score,
            "corrected_keys": list(self.corrected_keys),
            "within_tolerance": self.within_tolerance,
        }


def load_underwater_action_recipe(settings: Settings | None = None) -> tuple[str, dict[str, Any]] | None:
    config = settings or get_settings()
    recipe_dir = config.project_path(config.calibration_recipe_dir)
    if not recipe_dir.exists():
        return None

    candidates = sorted(recipe_dir.glob("*_lightroom_recipe.json"))
    for path in candidates:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        intent = str(payload.get("intent", "")).lower()
        source_file = str((payload.get("source") or {}).get("file", "")).lower()
        if "underwater" in intent or "jwy00030" in source_file:
            return path.name, payload
    return None


def build_recipe_model_guidance(settings: Settings | None = None) -> str:
    loaded = load_underwater_action_recipe(settings)
    if loaded is None:
        return ""
    recipe_name, recipe = loaded
    targets = recipe_to_planner_adjustments(recipe)
    keys = [
        "temp",
        "tint",
        "exposure",
        "contrast",
        "highlights",
        "shadows",
        "whites",
        "blacks",
        "texture",
        "clarity",
        "dehaze",
        "vibrance",
        "saturation",
        "sharpening",
        "noise_reduction",
        "aqua_saturation",
        "blue_saturation",
        "orange_luminance",
    ]
    compact = {key: targets[key] for key in keys if key in targets}
    return (
        f"Local calibration recipe active: {recipe_name}. For underwater action scenes near this reference, "
        f"target these planner values for an approximately 80-point edit: {compact}. "
        "Use temp as absolute Kelvin when confident; otherwise emit temperature_delta and the Planner will validate."
    )


def apply_underwater_recipe_calibration(
    analysis: Any,
    adjustments: dict[str, float],
    *,
    settings: Settings | None = None,
) -> RecipeCalibrationResult | None:
    if "underwater" not in analysis.scene_type.lower():
        return None

    loaded = load_underwater_action_recipe(settings)
    if loaded is None:
        return None

    recipe_name, recipe = loaded
    targets = recipe_to_planner_adjustments(recipe)
    corrected: list[str] = []

    if "temp" in targets:
        # Absolute recipe temperature is stronger evidence than a model-proposed
        # relative delta for this calibrated reference scene.
        adjustments.pop("temperature_delta", None)

    for key, target in targets.items():
        current = float(adjustments.get(key, 0.0))
        tolerance = _tolerance_for(key)
        if key not in adjustments or abs(current - target) > tolerance:
            adjustments[key] = target
            corrected.append(key)

    return RecipeCalibrationResult(
        recipe_name=recipe_name,
        reference_score=float(recipe.get("reference_score", 80.0)),
        target_adjustments=targets,
        corrected_keys=tuple(sorted(corrected)),
        within_tolerance=not corrected,
    )


def recipe_to_planner_adjustments(recipe: dict[str, Any]) -> dict[str, float]:
    global_settings = recipe.get("global") or {}
    detail = recipe.get("detail") or {}
    mixer = recipe.get("color_mixer") or {}

    result: dict[str, float] = {}
    _copy_number(result, "temp", global_settings, "temperature_kelvin")
    for key in (
        "tint",
        "exposure",
        "contrast",
        "highlights",
        "shadows",
        "whites",
        "blacks",
        "texture",
        "clarity",
        "dehaze",
        "vibrance",
        "saturation",
    ):
        _copy_number(result, key, global_settings, key)

    _copy_number(result, "sharpening", detail, "sharpening")
    _copy_number(result, "noise_reduction", detail, "luminance_noise_reduction")

    for color in COLOR_MIXER_COLORS:
        values = mixer.get(color) or {}
        _copy_number(result, f"{color}_hue", values, "hue")
        _copy_number(result, f"{color}_saturation", values, "saturation")
        _copy_number(result, f"{color}_luminance", values, "luminance")

    return result


def _copy_number(target: dict[str, float], target_key: str, source: dict[str, Any], source_key: str) -> None:
    value = source.get(source_key)
    if isinstance(value, (int, float)):
        target[target_key] = float(value)


def _tolerance_for(key: str) -> float:
    if key in RECIPE_TOLERANCES:
        return RECIPE_TOLERANCES[key]
    if key.endswith("_hue"):
        return 8.0
    if key.endswith("_saturation") or key.endswith("_luminance"):
        return 8.0
    return 10.0
