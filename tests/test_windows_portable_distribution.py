from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PORTABLE = ROOT / "portable" / "windows"


def test_portable_environment_uses_separate_loopback_planner_and_local_model() -> None:
    text = (PORTABLE / "Tonevyra.local.env.example").read_text(encoding="utf-8")

    assert "TONEVYRA_PLANNER_API_MODE=local_server" in text
    assert "TONEVYRA_PLANNER_API_BASE_URL=http://127.0.0.1:8000" in text
    assert "TONEVYRA_PLANNER_SERVER_HOST=127.0.0.1" in text
    assert "TONEVYRA_QWEN3_MODEL_PATH=models/qwen3-vl-4b-instruct" in text
    assert "TONEVYRA_MODEL_OFFLINE=true" in text
    assert "CHANGE_ME_PLANNER_API_KEY" in text
    assert "secret-key" not in text


def test_portable_helpers_cover_initialize_check_and_separate_startup() -> None:
    scripts = PORTABLE / "scripts"

    required = {
        "Common.ps1",
        "Initialize-Tonevyra.ps1",
        "Check-Prerequisites.ps1",
        "Start-PlannerServer.ps1",
        "Stop-PlannerServer.ps1",
        "Start-Agent.ps1",
    }
    assert required == {path.name for path in scripts.glob("*.ps1")}

    planner_start = (scripts / "Start-PlannerServer.ps1").read_text(encoding="utf-8")
    agent_start = (scripts / "Start-Agent.ps1").read_text(encoding="utf-8")
    planner_stop = (scripts / "Stop-PlannerServer.ps1").read_text(encoding="utf-8")
    prerequisite_check = (scripts / "Check-Prerequisites.ps1").read_text(encoding="utf-8")

    assert "PlannerServer\\TonevyraPlannerServer.exe" in planner_start
    assert "Test-PlannerReady" in agent_start
    assert 'ArgumentList @("tray")' in agent_start
    assert 'Get-Process -Name "TonevyraPlannerServer"' in planner_stop
    assert "CHANGE_ME_DATABASE_PASSWORD" in prerequisite_check
    assert "CHANGE_ME_PLANNER_API_KEY" in prerequisite_check


def test_portable_builder_bundles_python_runtimes_model_and_plugin() -> None:
    builder = (ROOT / "harness" / "scripts" / "build_tonevyra_windows_portable.py").read_text(
        encoding="utf-8"
    )

    assert 'destination / "Agent"' in builder
    assert 'destination / "PlannerServer"' in builder
    assert 'destination / "lightroom"' in builder
    assert "shutil.copytree(" in builder
    assert '"python_runtime_bundled": True' in builder
    assert '"system_python_required": False' in builder
    assert '"planner_server_separate_process": True' in builder
    assert '"authenticode_signed": False' in builder
