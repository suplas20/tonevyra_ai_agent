from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter

from tonevyra_agent.learning.feedback import compute_manual_edit_delta
from tonevyra_agent.learning.reference_pair import analyze_expert_reference_pair
from tonevyra_agent.learning.schemas import DevelopSettingsSnapshot


def test_expert_reference_pair_extracts_numeric_style_delta(tmp_path: Path) -> None:
    original = tmp_path / "original.jpg"
    corrected = tmp_path / "corrected.jpg"

    image = Image.new("RGB", (96, 64), (72, 82, 96))
    for x in range(24, 72):
        for y in range(18, 48):
            image.putpixel((x, y), (120, 62, 32))
    image.save(original, quality=92)

    edited = ImageEnhance.Brightness(image).enhance(1.18)
    edited = ImageEnhance.Contrast(edited).enhance(1.35)
    warm_overlay = Image.new("RGB", edited.size, (255, 128, 24))
    edited = Image.blend(edited, warm_overlay, 0.20)
    edited = ImageEnhance.Color(edited).enhance(1.85)
    edited = edited.filter(ImageFilter.SHARPEN)
    edited.save(corrected, quality=92)

    analysis = analyze_expert_reference_pair(original, corrected)

    assert analysis.confidence > 0.1
    assert analysis.suggested_lightroom_delta["exposure"] > 0
    assert analysis.suggested_lightroom_delta["temperature_delta"] > 0
    assert analysis.suggested_lightroom_delta["vibrance"] > 0
    assert analysis.suggested_lightroom_delta["saturation"] > 0
    assert (
        analysis.suggested_lightroom_delta["clarity"] > 0
        or analysis.suggested_lightroom_delta["sharpening"] > 0
    )
    assert "expert edit" in analysis.reason_summary


def test_reference_pair_delta_can_be_stored_as_manual_edit_numeric_delta(tmp_path: Path) -> None:
    original = tmp_path / "original.jpg"
    corrected = tmp_path / "corrected.jpg"
    Image.new("RGB", (48, 48), (90, 80, 70)).save(original, quality=92)
    Image.new("RGB", (48, 48), (145, 108, 78)).save(corrected, quality=92)

    analysis = analyze_expert_reference_pair(original, corrected)
    ai_settings = DevelopSettingsSnapshot(
        source="expert_pair_original",
        settings={key: 0.0 for key in analysis.suggested_lightroom_delta},
    )
    final_settings = DevelopSettingsSnapshot(
        source="expert_pair_corrected",
        settings=analysis.suggested_lightroom_delta,
    )

    delta = compute_manual_edit_delta(ai_settings, final_settings)

    assert delta.changed is True
    assert delta.numeric_delta["temperature_delta"] == analysis.suggested_lightroom_delta["temperature_delta"]
    assert delta.numeric_delta["exposure"] == analysis.suggested_lightroom_delta["exposure"]
