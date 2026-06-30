"""T-030 tray icon asset lookup and production gate."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tonevyra_agent.core.config import PROJECT_ROOT


ICON_DIR = PROJECT_ROOT / "resources" / "branding" / "windows"
SOURCE_DIR = PROJECT_ROOT / "resources" / "branding" / "source"


@dataclass(frozen=True)
class TrayIconStatus:
    production_ready: bool
    source_asset: Path | None
    icons: dict[str, Path]
    blocked_code: str | None = None


def tray_icon_status() -> TrayIconStatus:
    source_candidates = [
        SOURCE_DIR / "tonevyra_symbol.svg",
        SOURCE_DIR / "tonevyra_symbol.png",
    ]
    source = next((path for path in source_candidates if path.is_file()), None)
    icon_names = [
        "tonevyra_tray.ico",
        "tonevyra_tray_processing.ico",
        "tonevyra_tray_warning.ico",
        "tonevyra_tray_error.ico",
    ]
    icons = {name: ICON_DIR / name for name in icon_names if (ICON_DIR / name).is_file()}
    ready = source is not None and len(icons) == len(icon_names)
    return TrayIconStatus(
        production_ready=ready,
        source_asset=source,
        icons=icons,
        blocked_code=None if ready else "BLOCKED_TRAY_ICON_ASSET_MISSING",
    )
