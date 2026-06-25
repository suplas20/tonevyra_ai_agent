from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = PROJECT_ROOT / "lightroom" / "TonevyraAI.lrplugin"


def _read(name: str) -> str:
    return (PLUGIN_DIR / name).read_text(encoding="utf-8")


def test_lightroom_plugin_starts_bridge_worker_on_init() -> None:
    info = _read("Info.lua")
    main = _read("Main.lua")
    worker = _read("Worker.lua")

    assert 'LrInitPlugin = "Main.lua"' in info
    assert 'Worker.startAsync("lightroom_init")' in main
    assert "postAsyncTaskWithContext" in worker
    assert "tonevyra_bridge_worker_start" in worker
    assert "start_requested" in worker


def test_bridge_status_menu_is_diagnostic_self_heal_not_primary_flow() -> None:
    info = _read("Info.lua")
    status = _read("Status.lua")

    assert "Tonevyra Bridge Status" in info
    assert 'Worker.startAsync("status_self_heal")' in status
    assert "Bridge worker:" in status
    assert "Start requested:" in status
