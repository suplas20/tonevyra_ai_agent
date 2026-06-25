"""Scene-aware quality scoring: underwater scenes must not be penalized for
naturally retained color the way a neutral studio scene would be.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from tonevyra_agent.quality.scoring import score_export_image


def _write_underwater_export(tmp_path: Path) -> Path:
    """A bright, colorful, blue-dominant underwater-style export."""

    rgb = np.zeros((200, 300, 3), dtype=np.uint8)
    rgb[:, :, 0] = 70   # low red (water absorbs red)
    rgb[:, :, 1] = 120  # green
    rgb[:, :, 2] = 150  # blue
    rgb[60:140, 110:200] = [210, 205, 195]  # a brighter subject region
    path = tmp_path / "underwater_export.jpg"
    Image.fromarray(rgb, "RGB").save(path, quality=95)
    return path


def test_underwater_profile_scores_color_higher_than_neutral(tmp_path: Path) -> None:
    export = _write_underwater_export(tmp_path)
    neutral_scores, neutral_metrics, _ = score_export_image(export, scene_type=None)
    uw_scores, uw_metrics, _ = score_export_image(export, scene_type="underwater")

    # The blue-green underwater color must be penalized less under the underwater
    # profile across color balance, saturation, and cast.
    assert uw_scores.color_score > neutral_scores.color_score
    assert uw_scores.saturation_score > neutral_scores.saturation_score
    assert uw_scores.underwater_cast_score > neutral_scores.underwater_cast_score
    assert uw_scores.overall_score > neutral_scores.overall_score

    assert uw_metrics["scene_profile"]["is_underwater"] is True
    assert neutral_metrics["scene_profile"]["is_underwater"] is False


def test_non_underwater_scene_uses_neutral_profile(tmp_path: Path) -> None:
    export = _write_underwater_export(tmp_path)
    portrait_scores, metrics, _ = score_export_image(export, scene_type="portrait")
    neutral_scores, _, _ = score_export_image(export, scene_type=None)
    # A non-underwater scene must score identically to the default neutral profile.
    assert portrait_scores.overall_score == neutral_scores.overall_score
    assert metrics["scene_profile"]["is_underwater"] is False
