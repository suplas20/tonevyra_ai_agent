from __future__ import annotations

import json

from PIL import Image

from tonevyra_agent.windows.tray_icons import ICON_DIR, SOURCE_DIR, tray_icon_status


def test_t030_tray_icon_assets_are_production_ready() -> None:
    status = tray_icon_status()

    assert status.production_ready is True
    assert status.blocked_code is None
    assert status.source_asset == SOURCE_DIR / "tonevyra_symbol.svg"
    assert set(status.icons) == {
        "tonevyra_tray.ico",
        "tonevyra_tray_processing.ico",
        "tonevyra_tray_warning.ico",
        "tonevyra_tray_error.ico",
    }


def test_t030_tray_icon_manifest_and_sizes() -> None:
    manifest = json.loads((ICON_DIR / "tray_icon_manifest.json").read_text(encoding="utf-8"))

    assert manifest["schema_version"] == "t030.tray_icon_manifest.v1"
    assert manifest["approved_source"] is True
    assert manifest["sizes"] == [16, 20, 24, 32, 40, 48, 64, 128, 256]
    for item in manifest["icons"].values():
        with Image.open(item["path"]) as image:
            sizes = sorted(size[0] for size in image.ico.sizes())
        assert sizes == [16, 20, 24, 32, 40, 48, 64, 128, 256]
