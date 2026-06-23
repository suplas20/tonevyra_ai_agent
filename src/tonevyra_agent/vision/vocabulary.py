"""Canonical vision-issue vocabulary and natural-language normalization.

Real vision models describe image problems in free natural language
(e.g. "cool", "bluish", "slightly dark", "blurry"). The Correction Planner,
however, needs a small, stable, testable set of canonical tokens to map onto
bounded Lightroom Classic adjustments.

This module is the single source of truth that bridges the two:

    model free text  --normalize_issues()-->  canonical token  --planner-->  Lightroom value

Keeping the mapping here lets both the vision normalization layer and the planner
agree on the same vocabulary, and lets tests assert the model-word -> value path.
"""

from __future__ import annotations

from typing import Iterable

# ---- Canonical tokens -------------------------------------------------------

# exposure
EXP_NONE = "none"
EXP_SLIGHTLY_UNDER = "slightly_underexposed"
EXP_UNDER = "underexposed"
EXP_SEVERELY_UNDER = "severely_underexposed"
EXP_OVER = "overexposed"
EXP_SEVERELY_OVER = "severely_overexposed"

# color_cast
CAST_NONE = "none"
CAST_COOL = "cool"
CAST_STRONG_COOL = "strong_cool"
CAST_WARM = "warm"
CAST_STRONG_WARM = "strong_warm"
CAST_GREEN = "green"
CAST_MAGENTA = "magenta"

# contrast
CON_NONE = "none"
CON_LOW = "low"
CON_VERY_LOW = "very_low"
CON_HIGH = "high"

# sharpness
SHARP_OK = "ok"
SHARP_SOFT = "soft"
SHARP_VERY_SOFT = "very_soft"

# noise
NOISE_NONE = "none"
NOISE_LOW = "low"
NOISE_MODERATE = "moderate"
NOISE_HIGH = "high"

# haze / turbidity
HAZE_NONE = "none"
HAZE_MEDIUM = "medium"
HAZE_HEAVY = "heavy"
HAZE_EXTREME = "extreme"


def _match(text: str, *needles: str) -> bool:
    return any(needle in text for needle in needles)


def normalize_exposure(raw: str | None) -> str:
    t = (raw or "").strip().lower()
    if not t or _match(t, "none", "good", "balanced", "well", "correct", "proper", "normal", "ok", "fine", "accurate"):
        return EXP_NONE
    severe = _match(t, "severe", "very", "extreme", "heavily", "badly", "blown", "crushed")
    if _match(t, "over", "bright", "hot", "washed", "high"):
        return EXP_SEVERELY_OVER if severe else EXP_OVER
    if _match(t, "under", "dark", "dim", "low", "shadow", "murky"):
        if severe:
            return EXP_SEVERELY_UNDER
        if _match(t, "slight", "mild", "a bit", "somewhat", "minor"):
            return EXP_SLIGHTLY_UNDER
        return EXP_UNDER
    return EXP_NONE


def normalize_color_cast(raw: str | None) -> str:
    t = (raw or "").strip().lower()
    if not t or _match(t, "none", "neutral", "balanced", "accurate", "natural", "correct", "ok", "no cast"):
        return CAST_NONE
    strong = _match(t, "strong", "heavy", "severe", "very", "extreme", "deep", "intense", "significant")
    # green / magenta are tint-axis casts; check before warm/cool catch-alls
    if _match(t, "magenta", "pink", "purple", "violet"):
        return CAST_MAGENTA
    if _match(t, "green", "greenish"):
        # blue-green underwater casts read as cool, not pure green
        if _match(t, "blue", "cyan", "teal", "aqua"):
            return CAST_STRONG_COOL if strong else CAST_COOL
        return CAST_GREEN
    if _match(t, "cool", "cold", "blue", "bluish", "cyan", "teal", "aqua"):
        return CAST_STRONG_COOL if strong else CAST_COOL
    if _match(t, "warm", "orange", "yellow", "amber", "golden"):
        return CAST_STRONG_WARM if strong else CAST_WARM
    return CAST_NONE


def normalize_contrast(raw: str | None) -> str:
    t = (raw or "").strip().lower()
    if not t or _match(t, "none", "good", "balanced", "ok", "normal", "fine"):
        return CON_NONE
    if _match(t, "high", "harsh", "punchy", "excessive", "too much"):
        return CON_HIGH
    if _match(t, "very low", "very flat", "extremely flat", "no contrast", "severely"):
        return CON_VERY_LOW
    if _match(t, "low", "flat", "dull", "washed"):
        return CON_LOW
    return CON_NONE


def normalize_sharpness(raw: str | None) -> str:
    t = (raw or "").strip().lower()
    if not t or _match(t, "ok", "good", "sharp", "crisp", "fine", "acceptable", "clear"):
        if _match(t, "soft", "blur"):
            pass  # fall through to soft handling below
        else:
            return SHARP_OK
    if _match(t, "very soft", "blurry", "blur", "out of focus", "severely", "heavily soft"):
        return SHARP_VERY_SOFT
    if _match(t, "soft", "slightly soft", "mild"):
        return SHARP_SOFT
    return SHARP_OK


def normalize_noise(raw: str | None) -> str:
    t = (raw or "").strip().lower()
    if not t or _match(t, "none", "clean", "no noise", "negligible"):
        return NOISE_NONE
    if _match(t, "high", "heavy", "severe", "strong", "very"):
        return NOISE_HIGH
    if _match(t, "moderate", "medium", "noticeable", "some"):
        return NOISE_MODERATE
    if _match(t, "low", "slight", "mild", "minor", "faint"):
        return NOISE_LOW
    return NOISE_NONE


def normalize_haze(raw: str | None) -> str:
    t = (raw or "").strip().lower()
    if not t or _match(t, "none", "clear", "no haze"):
        return HAZE_NONE
    if _match(t, "extreme", "very heavy", "severe"):
        return HAZE_EXTREME
    if _match(t, "heavy", "strong", "thick"):
        return HAZE_HEAVY
    if _match(t, "medium", "moderate", "some", "mild", "light", "slight"):
        return HAZE_MEDIUM
    return HAZE_NONE


_FIELD_NORMALIZERS = {
    "exposure": normalize_exposure,
    "color_cast": normalize_color_cast,
    "contrast": normalize_contrast,
    "sharpness": normalize_sharpness,
    "noise": normalize_noise,
    "haze": normalize_haze,
    "haze_turbidity": normalize_haze,
}


def normalize_issues(issues: dict[str, object]) -> dict[str, object]:
    """Return a copy of ``issues`` with known fields mapped to canonical tokens."""

    result = dict(issues)
    for field, normalizer in _FIELD_NORMALIZERS.items():
        if field in result and result[field] is not None:
            result[field] = normalizer(str(result[field]))
    return result


def canonical_tokens() -> dict[str, tuple[str, ...]]:
    """Expose the full canonical vocabulary (useful for prompts and tests)."""

    return {
        "exposure": (EXP_NONE, EXP_SLIGHTLY_UNDER, EXP_UNDER, EXP_SEVERELY_UNDER, EXP_OVER, EXP_SEVERELY_OVER),
        "color_cast": (CAST_NONE, CAST_COOL, CAST_STRONG_COOL, CAST_WARM, CAST_STRONG_WARM, CAST_GREEN, CAST_MAGENTA),
        "contrast": (CON_NONE, CON_LOW, CON_VERY_LOW, CON_HIGH),
        "sharpness": (SHARP_OK, SHARP_SOFT, SHARP_VERY_SOFT),
        "noise": (NOISE_NONE, NOISE_LOW, NOISE_MODERATE, NOISE_HIGH),
        "haze": (HAZE_NONE, HAZE_MEDIUM, HAZE_HEAVY, HAZE_EXTREME),
    }
