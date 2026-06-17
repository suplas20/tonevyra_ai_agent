from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from harness.fake_lightroom.fake_lightroom_worker import process_request
from tonevyra_agent.core.config import Settings
from tonevyra_agent.lightroom.bridge import LightroomBridge
from tonevyra_agent.lightroom.schemas import (
    LIGHTROOM_COMMAND_PING,
    LIGHTROOM_RESPONSE_SUCCESS,
    LightroomRequestPayload,
    LightroomResponsePayload,
)


PLUGIN_DIR = PROJECT_ROOT / "src" / "tonevyra_agent" / "lightroom" / "plugin" / "TonevyraAI.lrplugin"
INFO_LUA = PLUGIN_DIR / "Info.lua"
MAIN_LUA = PLUGIN_DIR / "Main.lua"
RUNTIME_DIR = PROJECT_ROOT / "runtime" / "harness" / "lightroom_t016"


def _settings() -> Settings:
    return Settings(
        runtime_dir=RUNTIME_DIR,
        input_dir=RUNTIME_DIR / "input",
        output_dir=RUNTIME_DIR / "output",
        artifact_dir=RUNTIME_DIR / "artifacts",
        preview_dir=RUNTIME_DIR / "previews",
        bridge_dir=RUNTIME_DIR / "bridge",
        log_dir=RUNTIME_DIR / "logs",
        models_dir=PROJECT_ROOT / "models",
        lightroom_backend="lightroom",
    )


def _fail(message: str) -> int:
    print(f"FAIL {message}")
    return 1


def _reset_runtime(settings: Settings) -> None:
    runtime_dir = settings.project_path(settings.runtime_dir)
    if runtime_dir.exists():
        shutil.rmtree(runtime_dir)
    for path in settings.required_runtime_dirs():
        path.mkdir(parents=True, exist_ok=True)


def _verify_plugin_files() -> str | None:
    if not INFO_LUA.exists():
        return "TonevyraAI.lrplugin/Info.lua is missing"
    if not MAIN_LUA.exists():
        return "TonevyraAI.lrplugin/Main.lua is missing"

    info = INFO_LUA.read_text(encoding="utf-8")
    main = MAIN_LUA.read_text(encoding="utf-8")
    required_info_tokens = [
        'LrToolkitIdentifier = "com.tonevyra.ai.agent"',
        'LrPluginName = "Tonevyra AI"',
        'LrInitPlugin = "Main.lua"',
    ]
    for token in required_info_tokens:
        if token not in info:
            return f"Info.lua missing required token: {token}"

    required_main_tokens = [
        'requestDir()',
        'processingDir()',
        'responseDir()',
        'request.command == "PING"',
        'request.command == "APPLY_ADJUSTMENTS_AND_EXPORT"',
        "findOrImportPhoto",
        "applyDevelopSettings",
        "exportPhoto",
        "writeSuccess",
        "writeFailure",
    ]
    for token in required_main_tokens:
        if token not in main:
            return f"Main.lua missing required token: {token}"

    banned_tokens = [
        "psycopg",
        "postgres",
        "quality_score",
        "QualityResult",
        "VisionModel",
        "Qwen",
        "requests.",
        "http" + "://",
        "https" + "://",
    ]
    lowered_main = main.lower()
    for token in banned_tokens:
        if token.lower() in lowered_main:
            return f"Main.lua contains prohibited boundary token: {token}"
    return None


def _verify_ping_round_trip(settings: Settings) -> str | None:
    bridge = LightroomBridge(settings=settings)
    request = bridge.write_ping_request(request_id="tonevyra-t016-ping")
    if not request.request_path.exists():
        return "PING request was not written"

    request_payload = LightroomRequestPayload.model_validate(json.loads(request.request_path.read_text(encoding="utf-8")))
    if request_payload.command != LIGHTROOM_COMMAND_PING:
        return f"expected PING request, got {request_payload.command}"
    if request_payload.source_path is not None or request_payload.export_path is not None:
        return "PING request should not require source_path or export_path"

    response_path = process_request(request.request_path, bridge_dir=settings.project_path(settings.bridge_dir))
    response_payload = LightroomResponsePayload.model_validate(json.loads(response_path.read_text(encoding="utf-8")))
    if response_payload.command != LIGHTROOM_COMMAND_PING:
        return f"expected PING response command, got {response_payload.command}"
    if response_payload.status != LIGHTROOM_RESPONSE_SUCCESS:
        return f"expected PING success, got {response_payload.status}"

    bridge_response = bridge.read_ping_response(request_id=request_payload.request_id, response_path=response_path)
    if bridge_response.response_payload is None or bridge_response.response_payload.status != LIGHTROOM_RESPONSE_SUCCESS:
        return "Python bridge did not read PING response as success"
    return None


def main() -> int:
    settings = _settings()
    _reset_runtime(settings)

    plugin_error = _verify_plugin_files()
    if plugin_error:
        return _fail(plugin_error)
    print("OK TonevyraAI.lrplugin files contain required Lightroom bridge PoC entry points")

    ping_error = _verify_ping_round_trip(settings)
    if ping_error:
        return _fail(ping_error)
    print("OK PING request/response protocol is valid through Python bridge")

    shutil.rmtree(settings.project_path(settings.runtime_dir), ignore_errors=True)
    print("Lightroom plugin PoC verification complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
