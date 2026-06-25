#!/usr/bin/env python3
from __future__ import annotations

ALLOWED_RANGES = {
    "exposure": (-5.0, 5.0),
    "contrast": (-100, 100),
    "highlights": (-100, 100),
    "shadows": (-100, 100),
    "whites": (-100, 100),
    "blacks": (-100, 100),
    "temp": (1500, 50000),
    "temperature_delta": (-3500, 3500),
    "tint": (-150, 150),
    "vibrance": (-100, 100),
    "saturation": (-100, 100),
    "texture": (-100, 100),
    "clarity": (-100, 100),
    "dehaze": (-100, 100),
    "sharpening": (0, 150),
    "noise_reduction": (0, 100),
}

def clamp_settings(settings):
    applied = {}
    skipped = {}
    for key, value in settings.items():
        if key not in ALLOWED_RANGES:
            skipped[key] = {"reason": "unsupported_key", "value": value}
            continue
        lo, hi = ALLOWED_RANGES[key]
        try:
            num = float(value)
        except Exception:
            skipped[key] = {"reason": "non_numeric", "value": value}
            continue
        applied[key] = max(lo, min(hi, num))
    return applied, skipped

def main():
    sample = {
        "exposure": 10,
        "contrast": -120,
        "vibrance": 10,
        "temperature_delta": 9000,
        "unsupported_magic": 99,
        "clarity": "bad",
    }
    applied, skipped = clamp_settings(sample)
    assert applied["exposure"] == 5.0
    assert applied["contrast"] == -100
    assert applied["vibrance"] == 10
    assert applied["temperature_delta"] == 3500
    assert "unsupported_magic" in skipped
    assert "clarity" in skipped
    print("OK Lightroom worker mapping clamp/skipped behavior is valid")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
