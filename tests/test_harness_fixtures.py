from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_vision_fixtures_are_valid_json() -> None:
    fixture_dir = ROOT / "harness" / "fixtures" / "vision_outputs"
    for path in fixture_dir.glob("*.json"):
        json.loads(path.read_text(encoding="utf-8"))


def test_lightroom_response_fixtures_are_valid_json() -> None:
    fixture_dir = ROOT / "harness" / "fixtures" / "lightroom_responses"
    for path in fixture_dir.glob("*.json"):
        json.loads(path.read_text(encoding="utf-8"))


def test_sample_image_exists() -> None:
    path = ROOT / "harness" / "fixtures" / "images" / "sample_underwater_01.jpg"
    assert path.exists()
    assert path.stat().st_size > 1000
