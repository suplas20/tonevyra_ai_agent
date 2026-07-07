#!/usr/bin/env python3
"""Build a per-user Windows installer package for Tonevyra AI."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "runtime"
DIST_ROOT = RUNTIME / "windows_dist"
DIST_APP = DIST_ROOT / "TonevyraAI"
PACKAGE_ROOT = RUNTIME / "windows_installer"
PAYLOAD_NAME = "TonevyraAI-app.zip"
MODEL_BUNDLE_RELATIVE_DIR = Path("models") / "qwen3-vl-4b-instruct"
MODEL_MANIFEST_RELATIVE_PATH = MODEL_BUNDLE_RELATIVE_DIR / "model_manifest.json"
MODEL_METADATA_ONLY_FILENAMES = {".gitkeep", "model_manifest.json"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument(
        "--model-bundle-source",
        type=Path,
        default=os.environ.get("TONEVYRA_WINDOWS_MODEL_BUNDLE_SOURCE"),
        help=(
            "Directory containing the local model files to bundle. Defaults to "
            "models/qwen3-vl-4b-instruct, or the model_root from that manifest."
        ),
    )
    parser.add_argument("--skip-exe-build", action="store_true", help="Reuse runtime/windows_dist/TonevyraAI.")
    parser.add_argument("--skip-iexpress", action="store_true", help="Create payload only; do not compile setup exe.")
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    version = _project_version(project_root)
    PACKAGE_ROOT.mkdir(parents=True, exist_ok=True)

    if not args.skip_exe_build:
        _run([sys.executable, str(project_root / "harness" / "scripts" / "generate_t030_tray_icons.py")], project_root)
        _run([sys.executable, str(project_root / "harness" / "scripts" / "build_tonevyra_windows_exe.py")], project_root)

    _require_dist(project_root)
    stage_dir, model_bundle = _stage_payload(project_root, version, args.model_bundle_source)
    setup_exe = PACKAGE_ROOT / f"TonevyraAI-Setup-{version}.exe"
    sed_path = _write_iexpress_sed(stage_dir, setup_exe, version)

    i_express_status = "SKIPPED"
    if not args.skip_iexpress:
        i_express_status = _compile_iexpress(sed_path, setup_exe)

    manifest = _write_manifest(version, stage_dir, setup_exe if setup_exe.is_file() else None, i_express_status, model_bundle)
    print(f"OK: package stage={stage_dir}")
    print(f"OK: manifest={manifest}")
    if setup_exe.is_file():
        print(f"OK: installer={setup_exe}")
    else:
        print("WARN: installer exe was not created; payload and SED are available.")
    return 0 if i_express_status in {"BUILT", "SKIPPED"} else 2


def _project_version(project_root: Path) -> str:
    data = tomllib.loads((project_root / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def _run(command: list[str], cwd: Path) -> None:
    result = subprocess.run(command, cwd=cwd, check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def _require_dist(project_root: Path) -> None:
    exe = project_root / "runtime" / "windows_dist" / "TonevyraAI" / "TonevyraAI.exe"
    if not exe.is_file():
        raise SystemExit(f"missing PyInstaller output: {exe}")


def _stage_payload(project_root: Path, version: str, model_bundle_source: Path | None = None) -> tuple[Path, dict[str, Any]]:
    stage_dir = PACKAGE_ROOT / f"TonevyraAI-{version}"
    if stage_dir.exists():
        shutil.rmtree(stage_dir)
    stage_dir.mkdir(parents=True)

    app_stage = stage_dir / "payload" / "TonevyraAI"
    shutil.copytree(DIST_APP, app_stage)
    _copy_if_exists(project_root / "resources", app_stage / "resources")
    _copy_if_exists(project_root / ".env.example", app_stage / ".env.example")
    _copy_if_exists(project_root / "README.md", app_stage / "README.md")
    _copy_if_exists(project_root / "harness" / "fixtures" / "vision", app_stage / "harness" / "fixtures" / "vision")
    _copy_if_exists(
        project_root / "src" / "tonevyra_agent" / "lightroom" / "plugin" / "TonevyraAI.lrplugin",
        app_stage / "lightroom" / "TonevyraAI.lrplugin",
    )
    model_bundle = _copy_model_bundle(project_root, app_stage, model_bundle_source)

    payload_zip = stage_dir / PAYLOAD_NAME
    _zip_dir(app_stage, payload_zip, arc_root="TonevyraAI")
    shutil.rmtree(stage_dir / "payload")

    (stage_dir / "Install-TonevyraAI.ps1").write_text(_install_script(version), encoding="utf-8")
    (stage_dir / "Uninstall-TonevyraAI.ps1").write_text(_uninstall_script(), encoding="utf-8")
    (stage_dir / "README_INSTALL.txt").write_text(_readme(version), encoding="utf-8")
    return stage_dir, model_bundle


def _copy_model_bundle(project_root: Path, app_stage: Path, model_bundle_source: Path | None = None) -> dict[str, Any]:
    source = _resolve_model_bundle_source(project_root, model_bundle_source)
    payload_files = _model_payload_files(source)
    if not payload_files:
        raise SystemExit(
            "model bundle source contains no model payload files. "
            "Place local model weights/config files under models/qwen3-vl-4b-instruct "
            "or pass --model-bundle-source <local-model-dir>."
        )

    destination = app_stage / MODEL_BUNDLE_RELATIVE_DIR
    shutil.copytree(source, destination, dirs_exist_ok=True)
    manifest_payload = _bundled_model_manifest(project_root, source)
    _validate_bundled_model_manifest_files(destination, manifest_payload)
    (destination / "model_manifest.json").write_text(
        json.dumps(manifest_payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    copied_files = _model_payload_files(destination)
    return {
        "bundled": True,
        "source": str(source),
        "payload_dir": MODEL_BUNDLE_RELATIVE_DIR.as_posix(),
        "manifest_path": MODEL_MANIFEST_RELATIVE_PATH.as_posix(),
        "file_count": len(copied_files),
        "size_bytes": sum(path.stat().st_size for path in copied_files),
    }


def _resolve_model_bundle_source(project_root: Path, model_bundle_source: Path | None) -> Path:
    if model_bundle_source is not None:
        source = model_bundle_source if model_bundle_source.is_absolute() else project_root / model_bundle_source
        source = source.resolve()
        if not source.is_dir():
            raise SystemExit(f"model bundle source is not a directory: {source}")
        return source

    local_source = (project_root / MODEL_BUNDLE_RELATIVE_DIR).resolve()
    if local_source.is_dir() and _model_payload_files(local_source):
        return local_source

    manifest_path = project_root / MODEL_MANIFEST_RELATIVE_PATH
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"model manifest is invalid JSON: {manifest_path}") from exc
        manifest_root = Path(str(manifest.get("model_root", "")))
        external_source = manifest_root if manifest_root.is_absolute() else project_root / manifest_root
        external_source = external_source.resolve()
        if external_source.is_dir() and _model_payload_files(external_source):
            return external_source

    raise SystemExit(
        "missing model bundle files. Windows installer builds must include the local model. "
        "Place the model under models/qwen3-vl-4b-instruct or pass "
        "--model-bundle-source <local-model-dir>."
    )


def _model_payload_files(source: Path) -> list[Path]:
    if not source.is_dir():
        return []
    return sorted(
        path
        for path in source.rglob("*")
        if path.is_file() and path.name not in MODEL_METADATA_ONLY_FILENAMES
    )


def _bundled_model_manifest(project_root: Path, source: Path) -> dict[str, Any]:
    template_path = project_root / MODEL_MANIFEST_RELATIVE_PATH
    if template_path.is_file():
        payload = json.loads(template_path.read_text(encoding="utf-8"))
    else:
        payload = {
            "schema_version": "t022.local_model_manifest.v1",
            "model_id": source.name,
            "model_revision": "local-bundled",
            "model_checksum": "sha256:UNVERIFIED_BUNDLED_MODEL",
            "runtime_backend": "transformers_qwen3vl",
            "remote_api_enabled": False,
            "runtime_download_enabled": False,
            "external_image_url_enabled": False,
            "network_required": False,
            "device": "cuda",
            "dtype": "bfloat16",
            "quantization": "none",
            "checksum_mode": "directory",
        }
    payload["model_root"] = MODEL_BUNDLE_RELATIVE_DIR.as_posix()
    payload["allowed_model_root"] = "models"
    payload["remote_api_enabled"] = False
    payload["runtime_download_enabled"] = False
    payload["external_image_url_enabled"] = False
    payload["network_required"] = False
    return payload


def _validate_bundled_model_manifest_files(destination: Path, manifest_payload: dict[str, Any]) -> None:
    if manifest_payload.get("checksum_mode") != "index_file":
        return
    target_name = str(manifest_payload.get("checksum_target_file") or "model.safetensors.index.json")
    target = destination / target_name
    if not target.is_file():
        raise SystemExit(f"bundled model checksum target is missing: {target}")


def _copy_if_exists(source: Path, destination: Path) -> None:
    if source.is_dir():
        shutil.copytree(source, destination, dirs_exist_ok=True)
        return
    if source.is_file():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def _zip_dir(source_dir: Path, zip_path: Path, *, arc_root: str) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(source_dir.rglob("*")):
            if path.is_file():
                archive.write(path, Path(arc_root) / path.relative_to(source_dir))


def _write_iexpress_sed(stage_dir: Path, setup_exe: Path, version: str) -> Path:
    sed = _iexpress_sed(
        stage_dir=stage_dir,
        setup_exe=setup_exe,
        version=version,
        files=[
            PAYLOAD_NAME,
            "Install-TonevyraAI.ps1",
            "Uninstall-TonevyraAI.ps1",
            "README_INSTALL.txt",
        ],
    )
    sed_path = PACKAGE_ROOT / f"TonevyraAI-Setup-{version}.sed"
    sed_path.write_text(sed, encoding="utf-8")
    return sed_path


def _compile_iexpress(sed_path: Path, setup_exe: Path) -> str:
    iexpress = shutil.which("iexpress.exe")
    if iexpress is None:
        system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        candidate = system_root / "System32" / "iexpress.exe"
        iexpress = str(candidate) if candidate.is_file() else None
    if iexpress is None:
        return "IEXPRESS_NOT_FOUND"
    result = subprocess.run([iexpress, "/N", "/Q", str(sed_path)], cwd=PACKAGE_ROOT, check=False)
    if result.returncode == 0 and setup_exe.is_file():
        return "BUILT"
    return f"IEXPRESS_FAILED_{result.returncode}"


def _write_manifest(
    version: str,
    stage_dir: Path,
    setup_exe: Path | None,
    i_express_status: str,
    model_bundle: dict[str, Any],
) -> Path:
    payload = stage_dir / PAYLOAD_NAME
    manifest: dict[str, Any] = {
        "schema_version": "tonevyra.windows_installer.v1",
        "product": "Tonevyra AI",
        "version": version,
        "python": sys.version,
        "stage_dir": str(stage_dir),
        "payload_zip": str(payload),
        "payload_sha256": _sha256(payload),
        "model_bundle": model_bundle,
        "iexpress_status": i_express_status,
        "code_signed": False,
        "blocked_reasons": ["BLOCKED_CODE_SIGNING_NOT_CONFIGURED"],
    }
    if setup_exe is not None:
        manifest["installer_exe"] = str(setup_exe)
        manifest["installer_sha256"] = _sha256(setup_exe)
    path = PACKAGE_ROOT / f"TonevyraAI-Setup-{version}.manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _install_script(version: str, required_python: str = "3.11") -> str:
    return r"""$ErrorActionPreference = "Stop"
$ProductName = "Tonevyra AI"
$Version = "__VERSION__"
$RequiredPython = "__REQUIRED_PYTHON__"
$SourceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PayloadZip = Join-Path $SourceRoot "TonevyraAI-app.zip"
$InstallRoot = Join-Path $env:LOCALAPPDATA "Tonevyra AI\TonevyraAI"
$StartMenuDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Tonevyra AI"

Add-Type -AssemblyName System.Windows.Forms

function Show-TonevyraMessage($Title, $Message) {
    [System.Windows.Forms.MessageBox]::Show(
        $Message,
        $Title,
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Information
    ) | Out-Null
}

function Test-TonevyraPython {
    $commands = @(
        @("py", "-$RequiredPython", "-c", "import sys; raise SystemExit(0 if sys.version_info[:2] == tuple(map(int, '$RequiredPython'.split('.'))) else 1)"),
        @("python", "-c", "import sys; raise SystemExit(0 if sys.version_info[:2] == tuple(map(int, '$RequiredPython'.split('.'))) else 1)")
    )
    foreach ($command in $commands) {
        $exe = Get-Command $command[0] -ErrorAction SilentlyContinue
        if ($null -eq $exe) {
            continue
        }
        $exeName = $command[0]
        $arguments = $command[1..($command.Length - 1)]
        & $exeName @arguments *> $null
        if ($LASTEXITCODE -eq 0) {
            return $true
        }
    }
    return $false
}

function Test-TonevyraPostgreSQL {
    if (Get-Command "psql.exe" -ErrorAction SilentlyContinue) {
        return $true
    }
    $service = Get-Service -ErrorAction SilentlyContinue | Where-Object {
        $_.Name -like "postgresql*" -or $_.DisplayName -like "postgresql*"
    } | Select-Object -First 1
    return $null -ne $service
}

function Test-TonevyraLightroomClassic {
    $candidatePaths = @(
        "$env:ProgramFiles\Adobe\Adobe Lightroom Classic\Lightroom.exe",
        "${env:ProgramFiles(x86)}\Adobe\Adobe Lightroom Classic\Lightroom.exe"
    )
    foreach ($path in $candidatePaths) {
        if ($path -and (Test-Path -LiteralPath $path)) {
            return $true
        }
    }
    $registryRoots = @(
        "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*"
    )
    foreach ($root in $registryRoots) {
        $match = Get-ItemProperty -Path $root -ErrorAction SilentlyContinue | Where-Object {
            $_.DisplayName -like "*Lightroom Classic*"
        } | Select-Object -First 1
        if ($null -ne $match) {
            return $true
        }
    }
    return $false
}

function Assert-TonevyraPrerequisites {
    $missing = New-Object System.Collections.Generic.List[string]
    if (!(Test-TonevyraPython)) {
        $missing.Add("Python $RequiredPython")
    }
    if (!(Test-TonevyraPostgreSQL)) {
        $missing.Add("PostgreSQL")
    }
    if (!(Test-TonevyraLightroomClassic)) {
        $missing.Add("Adobe Lightroom Classic")
    }
    if ($missing.Count -eq 0) {
        return
    }

    $message = "Tonevyra AI cannot continue until these prerequisites are installed:`r`n`r`n"
    $message += ($missing | ForEach-Object { "- $_" }) -join "`r`n"
    $message += "`r`n`r`nInstall the missing items, then run this installer again."
    $message += "`r`n`r`nPython: https://www.python.org/downloads/windows/"
    $message += "`r`nPostgreSQL: https://www.postgresql.org/download/windows/"
    $message += "`r`nLightroom Classic: install through Adobe Creative Cloud."
    Show-TonevyraMessage "Tonevyra AI prerequisites required" $message
    throw "Missing prerequisites: $($missing -join ', ')"
}

Assert-TonevyraPrerequisites

if (Get-Process -Name "TonevyraAI" -ErrorAction SilentlyContinue) {
    throw "TonevyraAI.exe is running. Exit Tonevyra AI from the tray before installing."
}
if (!(Test-Path -LiteralPath $PayloadZip)) {
    throw "Missing installer payload: $PayloadZip"
}

$TempRoot = Join-Path $env:TEMP ("TonevyraAI-install-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $TempRoot | Out-Null
try {
    Expand-Archive -LiteralPath $PayloadZip -DestinationPath $TempRoot -Force
    $AppSource = Join-Path $TempRoot "TonevyraAI"
    $ExePath = Join-Path $AppSource "TonevyraAI.exe"
    $ModelManifest = Join-Path $AppSource "models\qwen3-vl-4b-instruct\model_manifest.json"
    if (!(Test-Path -LiteralPath $ExePath)) {
        throw "Payload does not contain TonevyraAI.exe"
    }
    if (!(Test-Path -LiteralPath $ModelManifest)) {
        throw "Payload does not contain the bundled model manifest."
    }

    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $InstallRoot) | Out-Null
    if (Test-Path -LiteralPath $InstallRoot) {
        Remove-Item -LiteralPath $InstallRoot -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
    Copy-Item -LiteralPath (Join-Path $AppSource "*") -Destination $InstallRoot -Recurse -Force
    Copy-Item -LiteralPath (Join-Path $SourceRoot "Uninstall-TonevyraAI.ps1") -Destination (Join-Path $InstallRoot "Uninstall-TonevyraAI.ps1") -Force

    New-Item -ItemType Directory -Force -Path $StartMenuDir | Out-Null
    $Shell = New-Object -ComObject WScript.Shell
    $AppShortcut = $Shell.CreateShortcut((Join-Path $StartMenuDir "Tonevyra AI.lnk"))
    $AppShortcut.TargetPath = (Join-Path $InstallRoot "TonevyraAI.exe")
    $AppShortcut.Arguments = "tray"
    $AppShortcut.WorkingDirectory = $InstallRoot
    $AppShortcut.IconLocation = (Join-Path $InstallRoot "TonevyraAI.exe") + ",0"
    $AppShortcut.Save()

    $UninstallShortcut = $Shell.CreateShortcut((Join-Path $StartMenuDir "Uninstall Tonevyra AI.lnk"))
    $UninstallShortcut.TargetPath = "powershell.exe"
    $UninstallShortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"" + (Join-Path $InstallRoot "Uninstall-TonevyraAI.ps1") + "`""
    $UninstallShortcut.WorkingDirectory = $InstallRoot
    $UninstallShortcut.Save()

    $UninstallKey = "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\TonevyraAI"
    New-Item -Path $UninstallKey -Force | Out-Null
    New-ItemProperty -Path $UninstallKey -Name "DisplayName" -Value $ProductName -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $UninstallKey -Name "DisplayVersion" -Value $Version -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $UninstallKey -Name "Publisher" -Value "Tonevyra AI" -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $UninstallKey -Name "InstallLocation" -Value $InstallRoot -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $UninstallKey -Name "UninstallString" -Value ("powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"" + (Join-Path $InstallRoot "Uninstall-TonevyraAI.ps1") + "`"") -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $UninstallKey -Name "NoModify" -Value 1 -PropertyType DWord -Force | Out-Null
    New-ItemProperty -Path $UninstallKey -Name "NoRepair" -Value 1 -PropertyType DWord -Force | Out-Null

    Write-Host "Installed Tonevyra AI $Version to $InstallRoot"
} finally {
    if (Test-Path -LiteralPath $TempRoot) {
        Remove-Item -LiteralPath $TempRoot -Recurse -Force
    }
}
""".replace("__VERSION__", version).replace("__REQUIRED_PYTHON__", required_python)


def _uninstall_script() -> str:
    return """$ErrorActionPreference = "Stop"
$InstallRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$StartMenuDir = Join-Path $env:APPDATA "Microsoft\\Windows\\Start Menu\\Programs\\Tonevyra AI"

if (Get-Process -Name "TonevyraAI" -ErrorAction SilentlyContinue) {
    throw "TonevyraAI.exe is running. Exit Tonevyra AI from the tray before uninstalling."
}
if (Test-Path -LiteralPath $StartMenuDir) {
    Remove-Item -LiteralPath $StartMenuDir -Recurse -Force
}
Remove-Item -Path "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\TonevyraAI" -Recurse -Force -ErrorAction SilentlyContinue
if (Test-Path -LiteralPath $InstallRoot) {
    Remove-Item -LiteralPath $InstallRoot -Recurse -Force
}
Write-Host "Uninstalled Tonevyra AI"
"""


def _readme(version: str) -> str:
    return f"""Tonevyra AI Windows Installer
Version: {version}

This installer is a per-user package. It installs under:
%LOCALAPPDATA%\\Tonevyra AI\\TonevyraAI

This package includes the local model bundle under:
%LOCALAPPDATA%\\Tonevyra AI\\TonevyraAI\\models\\qwen3-vl-4b-instruct

Before copying files, the installer checks for Python 3.11, PostgreSQL, and
Adobe Lightroom Classic. Missing prerequisites block installation and are shown
to the user in a Windows message box.

It does not silently install PostgreSQL, Lightroom Classic, Python, or code
signing certificates. Install missing prerequisites first, then run the setup
again.

Configure TONEVYRA_DATABASE_URL and local runtime settings after installation.
"""


def _iexpress_sed(*, stage_dir: Path, setup_exe: Path, version: str, files: list[str]) -> str:
    file_strings = "\n".join(f'FILE{index}="{name}"' for index, name in enumerate(files))
    source_entries = "\n".join(f"%FILE{index}%=" for index, _name in enumerate(files))
    return f"""[Version]
Class=IEXPRESS
SEDVersion=3
[Options]
PackagePurpose=InstallApp
ShowInstallProgramWindow=0
HideExtractAnimation=1
UseLongFileName=1
InsideCompressed=0
CAB_FixedSize=0
CAB_ResvCodeSigning=0
RebootMode=N
InstallPrompt=%InstallPrompt%
DisplayLicense=%DisplayLicense%
FinishMessage=%FinishMessage%
TargetName=%TargetName%
FriendlyName=%FriendlyName%
AppLaunched=%AppLaunched%
PostInstallCmd=<None>
AdminQuietInstCmd=%AppLaunched%
UserQuietInstCmd=%AppLaunched%
SourceFiles=SourceFiles
[Strings]
InstallPrompt=
DisplayLicense=
FinishMessage=Tonevyra AI {version} installation completed.
TargetName={setup_exe}
FriendlyName=Tonevyra AI {version}
AppLaunched=powershell.exe -NoProfile -ExecutionPolicy Bypass -File Install-TonevyraAI.ps1
FILE_COUNT={len(files)}
{file_strings}
[SourceFiles]
SourceFiles0={stage_dir}
[SourceFiles0]
{source_entries}
"""


if __name__ == "__main__":
    raise SystemExit(main())
