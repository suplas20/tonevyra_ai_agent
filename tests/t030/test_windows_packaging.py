from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.scripts.build_tonevyra_windows_installer import (
    MODEL_MANIFEST_RELATIVE_PATH,
    _copy_model_bundle,
    _iexpress_sed,
    _install_script,
    _resolve_model_bundle_source,
    _uninstall_script,
)
from harness.scripts.build_tonevyra_windows_native_installer import PLUGIN_SRC


def test_install_script_uses_per_user_install_location() -> None:
    script = _install_script("0.1.0")

    assert "$env:LOCALAPPDATA" in script
    assert "$env:APPDATA" in script
    assert "HKCU:" in script
    assert "TonevyraAI.exe" in script
    assert "Windows\\CurrentVersion\\Run" not in script


def test_native_inno_installer_creates_desktop_shortcut() -> None:
    script = Path("installer/windows/TonevyraAI.iss").read_text(encoding="utf-8")

    assert 'Name: "{autodesktop}\\Tonevyra AI"' in script
    assert 'Filename: "{app}\\TonevyraAI.exe"' in script
    assert 'Parameters: "tray"' in script


def test_native_installer_packages_complete_lightroom_adapter() -> None:
    assert PLUGIN_SRC == Path("lightroom/TonevyraAI.lrplugin").resolve()
    assert (PLUGIN_SRC / "Bridge.lua").is_file()
    assert (PLUGIN_SRC / "BridgeConfig.lua").is_file()
    assert (PLUGIN_SRC / "Worker.lua").is_file()

    bridge = (PLUGIN_SRC / "Bridge.lua").read_text(encoding="utf-8")
    worker = (PLUGIN_SRC / "Worker.lua").read_text(encoding="utf-8")
    assert 'Bridge.root = BridgeConfig.root' in bridge
    assert "lightroom_apply_requests" in bridge
    assert "lightroom_export_requests" in bridge
    assert "local function applyRequest" in worker
    assert "local function exportRequest" in worker


def test_frozen_app_includes_local_qwen_runtime() -> None:
    script = Path("harness/scripts/build_tonevyra_windows_exe.py").read_text(encoding="utf-8")

    assert '"transformers.models.qwen3_vl"' in script
    assert '"--exclude-module",\n        "torch",' not in script
    assert '"--exclude-module",\n        "torchvision",' not in script
    assert '"--exclude-module",\n        "transformers",' not in script


def test_provisioning_selects_real_model_and_lightroom_backends() -> None:
    script = Path("installer/windows/Invoke-TonevyraProvision.ps1").read_text(encoding="utf-8")

    assert 'TONEVYRA_VISION_BACKEND=qwen3vl' in script
    assert 'TONEVYRA_LIGHTROOM_BACKEND=lightroom' in script
    assert '[Environment]::GetFolderPath([Environment+SpecialFolder]::MyDocuments)' in script
    assert 'Join-Path $documentsDir "TonevyraAI\\input"' in script
    assert '"TONEVYRA_INPUT_DIR=$inputDir"' in script
    assert "New-Object System.Text.UTF8Encoding($false)" in script
    assert 'TONEVYRA_PLANNER_API_BASE_URL=http://127.0.0.1:8000' in script
    assert 'function Read-DatabaseUrl' in script
    assert 'Write-EnvFile $existingUrl' in script
    assert 'installer-requeue-legacy-model-tasks' in script
    assert 'legacy_model_task_repair.json' in script
    assert 'BridgeConfig.lua' in script
    assert r'runtime\bridge' in script
    assert 'RESTART_REQUIRED' in script


def test_install_script_orchestrates_all_in_one_prerequisites() -> None:
    script = _install_script("0.1.0")

    assert "Assert-TonevyraPrerequisites" not in script
    assert '$RequiredPython = "3.11.9"' in script
    assert "Assert-TonevyraBundledRuntime" in script
    assert "Get-TonevyraPostgreSQLResolution" in script
    assert "Install-TonevyraPostgreSQLUnattended" in script
    assert "Initialize-TonevyraDatabase" in script
    assert '@("installer-db", "bootstrap-schema")' in script
    assert '@("installer-db", "verify", "--credential-store-verified"' in script
    assert '@("doctor")' in script
    assert '"post-install doctor"' in script
    assert "Test-TonevyraLightroomClassic" in script
    assert "Missing prerequisites" not in script
    assert "python.org/downloads/windows/" not in script
    assert "postgresql.org/download/windows/" not in script


def test_install_script_requires_bundled_model_manifest() -> None:
    script = _install_script("0.1.0")

    assert "models\\qwen3-vl-4b-instruct\\model_manifest.json" in script
    assert "Payload does not contain the bundled model manifest." in script


def test_uninstall_script_requires_app_to_be_closed() -> None:
    script = _uninstall_script()

    assert "Get-Process -Name \"TonevyraAI\"" in script
    assert "throw" in script
    assert "HKCU:" in script


def test_iexpress_sed_launches_only_installer_script() -> None:
    sed = _iexpress_sed(
        stage_dir=Path(r"C:\tonevyra-stage"),
        setup_exe=Path(r"C:\tonevyra-stage\TonevyraAI-Setup-0.1.0.exe"),
        version="0.1.0",
        files=["TonevyraAI-app.zip", "Install-TonevyraAI.ps1"],
    )

    assert "AppLaunched=powershell.exe -NoProfile -ExecutionPolicy Bypass -File Install-TonevyraAI.ps1" in sed
    assert "TonevyraAI-app.zip" in sed
    assert "0.0.0.0" not in sed


def test_model_bundle_source_cannot_be_metadata_only(tmp_path: Path) -> None:
    model_dir = tmp_path / "models" / "qwen3-vl-4b-instruct"
    model_dir.mkdir(parents=True)
    (model_dir / "model_manifest.json").write_text("{}", encoding="utf-8")
    app_stage = tmp_path / "app"
    app_stage.mkdir()

    with pytest.raises(SystemExit, match="no model payload files"):
        _copy_model_bundle(tmp_path, app_stage, model_dir)


def test_model_bundle_is_copied_and_manifest_is_rebased(tmp_path: Path) -> None:
    model_dir = tmp_path / "external-model"
    model_dir.mkdir()
    (model_dir / "config.json").write_text("{}", encoding="utf-8")
    (model_dir / "model.safetensors.index.json").write_text("{}", encoding="utf-8")
    manifest_path = tmp_path / MODEL_MANIFEST_RELATIVE_PATH
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "t022.local_model_manifest.v1",
                "model_id": "Qwen3-VL-4B-Instruct",
                "model_revision": "local-test",
                "model_root": str(model_dir),
                "model_checksum": "sha256:test",
                "runtime_backend": "transformers_qwen3vl",
                "remote_api_enabled": False,
                "runtime_download_enabled": False,
                "external_image_url_enabled": False,
                "allowed_model_root": str(model_dir.parent),
                "network_required": False,
                "device": "cuda",
                "dtype": "bfloat16",
                "quantization": "none",
                "checksum_mode": "index_file",
                "checksum_target_file": "model.safetensors.index.json",
            }
        ),
        encoding="utf-8",
    )
    app_stage = tmp_path / "app"
    app_stage.mkdir()

    summary = _copy_model_bundle(tmp_path, app_stage)
    bundled_manifest = json.loads((app_stage / MODEL_MANIFEST_RELATIVE_PATH).read_text(encoding="utf-8"))

    assert summary["bundled"] is True
    assert summary["file_count"] == 2
    assert (app_stage / "models" / "qwen3-vl-4b-instruct" / "config.json").is_file()
    assert bundled_manifest["model_root"] == "models/qwen3-vl-4b-instruct"
    assert bundled_manifest["allowed_model_root"] == "models"
    assert bundled_manifest["remote_api_enabled"] is False
    assert bundled_manifest["runtime_download_enabled"] is False


def test_model_bundle_source_can_be_inferred_from_manifest(tmp_path: Path) -> None:
    model_dir = tmp_path / "external-model"
    model_dir.mkdir()
    (model_dir / "config.json").write_text("{}", encoding="utf-8")
    manifest_path = tmp_path / MODEL_MANIFEST_RELATIVE_PATH
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(json.dumps({"model_root": str(model_dir)}), encoding="utf-8")

    assert _resolve_model_bundle_source(tmp_path, None) == model_dir.resolve()


def test_model_bundle_requires_checksum_target_when_manifest_uses_index_file(tmp_path: Path) -> None:
    model_dir = tmp_path / "external-model"
    model_dir.mkdir()
    (model_dir / "config.json").write_text("{}", encoding="utf-8")
    manifest_path = tmp_path / MODEL_MANIFEST_RELATIVE_PATH
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "t022.local_model_manifest.v1",
                "model_id": "Qwen3-VL-4B-Instruct",
                "model_revision": "local-test",
                "model_root": str(model_dir),
                "model_checksum": "sha256:test",
                "runtime_backend": "transformers_qwen3vl",
                "remote_api_enabled": False,
                "runtime_download_enabled": False,
                "external_image_url_enabled": False,
                "allowed_model_root": str(model_dir.parent),
                "network_required": False,
                "checksum_mode": "index_file",
                "checksum_target_file": "model.safetensors.index.json",
            }
        ),
        encoding="utf-8",
    )
    app_stage = tmp_path / "app"
    app_stage.mkdir()

    with pytest.raises(SystemExit, match="checksum target is missing"):
        _copy_model_bundle(tmp_path, app_stage)
