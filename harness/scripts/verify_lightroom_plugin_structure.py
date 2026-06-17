#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_CANDIDATES = [
    PROJECT_ROOT / "lightroom" / "TonevyraAI.lrplugin",
    PROJECT_ROOT / "plugin_scaffold" / "TonevyraAI.lrplugin",
    PROJECT_ROOT / "src" / "tonevyra_agent" / "lightroom" / "plugin" / "TonevyraAI.lrplugin",
]

REQUIRED_INFO_TOKENS = ["LrToolkitIdentifier", "LrPluginName"]
IDENTITY_TOKENS = ["com.tonevyra.ai.agent", "Tonevyra AI"]
WORKER_TOKENS = ["LrInitPlugin", "Worker.lua", "lightroom_apply_requests", "lightroom_apply_results"]
REQUIRED_BRIDGE_TOKENS = [
    "APPLY_LIGHTROOM_SETTINGS",
    "source_path",
    "task_id",
    "develop_settings",
    "applied_settings",
    "skipped_settings",
]
BANNED_TOKENS = [
    "get" + "TargetPhoto",
    "selected" + "_photo_detected",
    "selected" + "_count",
    "RUN_" + "TONEVYRA_CORRECTION",
    "request_origin = \"lightroom_plugin\"",
    "request_origin='lightroom_plugin'",
    "psycopg",
    "postgres",
    "sqlite3",
    "QualityResult",
    "quality_score",
    "VisionModel",
    "Qwen",
    "transformers",
    "torch.",
    "requests.",
    "http" + "://",
    "https" + "://",
    "curl ",
    "os.remove(",
    "deleteOriginal",
    "overwriteOriginal",
]

def fail(message: str) -> int:
    print(f"FAIL {message}")
    return 1

def find_plugin_dir(explicit: str | None) -> Path | None:
    if explicit:
        path = Path(explicit).resolve()
        return path if path.exists() else None
    for candidate in PLUGIN_CANDIDATES:
        if candidate.exists():
            return candidate
    return None

def read_all_lua(plugin_dir: Path) -> str:
    parts = []
    for path in sorted(plugin_dir.glob("*.lua")):
        try:
            parts.append(f"\n-- FILE: {path.name}\n" + path.read_text(encoding="utf-8"))
        except UnicodeDecodeError:
            parts.append(f"\n-- FILE: {path.name}\n" + path.read_text(encoding="utf-8-sig"))
    return "\n".join(parts)

def main() -> int:
    parser = argparse.ArgumentParser(description="Validate folder-driven T-019 Lightroom plugin structure.")
    parser.add_argument("--plugin-dir", default=None)
    args = parser.parse_args()

    plugin_dir = find_plugin_dir(args.plugin_dir)
    if not plugin_dir:
        return fail("TonevyraAI.lrplugin directory not found")
    info = plugin_dir / "Info.lua"
    if not info.exists():
        return fail("Info.lua is required")
    lua = read_all_lua(plugin_dir)
    text = info.read_text(encoding="utf-8") + "\n" + lua

    for token in REQUIRED_INFO_TOKENS:
        if token not in text:
            return fail(f"Info.lua missing required token: {token}")
    if not any(token in text for token in IDENTITY_TOKENS):
        return fail("plugin must contain Tonevyra identity")
    if not any(token in text for token in WORKER_TOKENS):
        return fail("plugin must expose background worker/init bridge behavior")
    for token in REQUIRED_BRIDGE_TOKENS:
        if token not in text:
            return fail(f"plugin missing folder-driven bridge token: {token}")
    lower = text.lower()
    for token in BANNED_TOKENS:
        if token.lower() in lower:
            return fail(f"plugin contains banned selected-flow or unsafe token: {token}")
    print(f"OK folder-driven Lightroom plugin structure is valid: {plugin_dir}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
