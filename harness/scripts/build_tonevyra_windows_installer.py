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
DEFAULT_OUTPUT_DIR = Path(os.environ.get("TONEVYRA_WINDOWS_INSTALLER_OUTPUT_DIR", r"D:\Tonevyra_install"))
PAYLOAD_NAME = "TonevyraAI-app.zip"
MODEL_BUNDLE_RELATIVE_DIR = Path("models") / "qwen3-vl-4b-instruct"
MODEL_MANIFEST_RELATIVE_PATH = MODEL_BUNDLE_RELATIVE_DIR / "model_manifest.json"
MODEL_METADATA_ONLY_FILENAMES = {".gitkeep", "model_manifest.json"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=r"Final installer output directory (default: D:\Tonevyra_install).",
    )
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
    output_dir = args.output_dir.expanduser().resolve()
    version = _project_version(project_root)
    PACKAGE_ROOT.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not args.skip_exe_build:
        _run([sys.executable, str(project_root / "harness" / "scripts" / "generate_t030_tray_icons.py")], project_root)
        _run([sys.executable, str(project_root / "harness" / "scripts" / "build_tonevyra_windows_exe.py")], project_root)

    _require_dist(project_root)
    stage_dir, model_bundle = _stage_payload(project_root, version, args.model_bundle_source)
    setup_exe = output_dir / f"TonevyraAI-Setup-{version}.exe"
    sed_path = _write_iexpress_sed(stage_dir, setup_exe, version)

    i_express_status = "SKIPPED"
    if not args.skip_iexpress:
        i_express_status = _compile_iexpress(sed_path, setup_exe)

    manifest = _write_manifest(
        version,
        stage_dir,
        setup_exe if setup_exe.is_file() else None,
        i_express_status,
        model_bundle,
        output_dir=output_dir,
    )
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

    # Windows PowerShell 5.1 requires a BOM to decode non-ASCII script text reliably.
    (stage_dir / "Install-TonevyraAI.ps1").write_text(_install_script(version), encoding="utf-8-sig")
    (stage_dir / "Uninstall-TonevyraAI.ps1").write_text(_uninstall_script(), encoding="utf-8-sig")
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
    *,
    output_dir: Path,
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
        "all_in_one_orchestrator": True,
        "postgres_unattended_install": True,
        "database_bootstrap_automation": True,
        "post_install_doctor_required": True,
        "code_signed": False,
        "blocked_reasons": ["BLOCKED_CODE_SIGNING_NOT_CONFIGURED"],
    }
    if setup_exe is not None:
        manifest["installer_exe"] = str(setup_exe)
        manifest["installer_sha256"] = _sha256(setup_exe)
    path = output_dir / f"TonevyraAI-Setup-{version}.manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _install_script(version: str, required_python: str = "3.11.9") -> str:
    return r"""param(
    [string]$InstallerLogDir = "",
    [string]$InstallerResultPath = ""
)
$ErrorActionPreference = "Stop"
$ProductName = "Tonevyra AI"
$Version = "__VERSION__"
$RequiredPython = "__REQUIRED_PYTHON__"
$SourceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PayloadZip = Join-Path $SourceRoot "TonevyraAI-app.zip"
$InstallRoot = Join-Path $env:LOCALAPPDATA "Tonevyra AI\TonevyraAI"
$StartMenuDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Tonevyra AI"
$ConfigRoot = Join-Path $env:LOCALAPPDATA "TonevyraAI"
$ReceiptRoot = Join-Path $env:PROGRAMDATA "TonevyraAI\install-receipts"
$InstallSessionId = [Guid]::NewGuid().ToString("N")
$InstallReceipt = Join-Path $ReceiptRoot ("install-" + $InstallSessionId + ".json")
$RequestedLogRoot = if ([string]::IsNullOrWhiteSpace($InstallerLogDir)) { $SourceRoot } else { $InstallerLogDir }
$InstallerLogRoot = [System.IO.Path]::GetFullPath($RequestedLogRoot)
$InstallLog = Join-Path $InstallerLogRoot ("TonevyraAI-install-" + $InstallSessionId + ".log")
$InstallErrorLog = Join-Path $InstallerLogRoot ("TonevyraAI-install-" + $InstallSessionId + "-error.txt")
$InstallStatus = Join-Path $InstallerLogRoot ("TonevyraAI-install-" + $InstallSessionId + "-status.txt")
$PostgresMetadataUrl = $env:TONEVYRA_T033_POSTGRES_METADATA_URL
$PinnedPostgresVersion = "18.4-2"
$PinnedPostgresUrl = "https://get.enterprisedb.com/postgresql/postgresql-18.4-2-windows-x64.exe"
$PinnedPostgresSha256 = "0698d1a6083da490e5a57149257f5d9220d8c34109ed11b38aa592d320bf5385"
$PostgresDownloadTimeoutSeconds = 900
$PostgresInstallTimeoutSeconds = 1800
$PostInstallCommandTimeoutSeconds = 300
$AllowedPostgresHosts = @("postgresql.org", "enterprisedb.com", "get.enterprisedb.com")
$TonevyraPgService = "TonevyraPostgreSQL"
$TonevyraDatabase = "tonevyra_agent"
$TonevyraRole = "tonevyra_app"
$script:PostgresAdminPassword = $env:TONEVYRA_T033_POSTGRES_ADMIN_PASSWORD
$script:InstallCompleted = $false

Add-Type -AssemblyName System.Windows.Forms
New-Item -ItemType Directory -Force -Path $ReceiptRoot | Out-Null
try {
    New-Item -ItemType Directory -Force -Path $InstallerLogRoot | Out-Null
} catch {
    $InstallerLogRoot = $ReceiptRoot
    $InstallLog = Join-Path $InstallerLogRoot ("TonevyraAI-install-" + $InstallSessionId + ".log")
    $InstallErrorLog = Join-Path $InstallerLogRoot ("TonevyraAI-install-" + $InstallSessionId + "-error.txt")
    $InstallStatus = Join-Path $InstallerLogRoot ("TonevyraAI-install-" + $InstallSessionId + "-status.txt")
}
try {
    Start-Transcript -Path $InstallLog -Append | Out-Null
} catch {
    # Transcript is diagnostic-only; receipt writing remains the durable evidence.
}

function Show-TonevyraMessage($Title, $Message) {
    [System.Windows.Forms.MessageBox]::Show(
        $Message,
        $Title,
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Information
    ) | Out-Null
}

function Write-TonevyraInstallReceipt($Step, $Result, $Data = @{}) {
    New-Item -ItemType Directory -Force -Path $ReceiptRoot | Out-Null
    $entry = [ordered]@{
        timestamp = (Get-Date).ToUniversalTime().ToString("o")
        installer_version = $Version
        step = $Step
        result = $Result
        redaction_applied = $true
        data = $Data
    }
    $existing = @()
    if (Test-Path -LiteralPath $InstallReceipt) {
        $existing = Get-Content -LiteralPath $InstallReceipt -Raw | ConvertFrom-Json
    }
    @($existing) + @($entry) | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $InstallReceipt -Encoding UTF8
}

function Write-TonevyraProgress($Step, $Message, $Data = @{}) {
    $line = ((Get-Date).ToUniversalTime().ToString("o") + " " + $Step + " " + $Message)
    Write-Host $line
    try {
        Set-Content -LiteralPath $InstallStatus -Value $line -Encoding UTF8
    } catch {
    }
    try {
        Write-TonevyraInstallReceipt $Step "running" $Data
    } catch {
    }
}

function Write-TonevyraInstallerResult($Content) {
    if ([string]::IsNullOrWhiteSpace($InstallerResultPath)) {
        return
    }
    $resultDir = Split-Path -Parent $InstallerResultPath
    if (![string]::IsNullOrWhiteSpace($resultDir)) {
        New-Item -ItemType Directory -Force -Path $resultDir | Out-Null
    }
    Set-Content -LiteralPath $InstallerResultPath -Value $Content -Encoding UTF8
}

function Invoke-TonevyraTimedProcess($FilePath, $ArgumentList, $TimeoutSeconds, $ErrorCode, $Description) {
    $process = Start-Process -FilePath $FilePath -ArgumentList $ArgumentList -PassThru
    if (!$process.WaitForExit($TimeoutSeconds * 1000)) {
        try {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        } catch {
        }
        throw ($ErrorCode + " " + $Description + " timed out after " + $TimeoutSeconds + " seconds")
    }
    if ($process.ExitCode -ne 0) {
        throw ($ErrorCode + " " + $Description + " failed with exit code " + $process.ExitCode)
    }
}

function Protect-TonevyraTempSecretFile($Path) {
    try {
        $acl = Get-Acl -LiteralPath $Path
        $acl.SetAccessRuleProtection($true, $false)
        $identities = @(
            [System.Security.Principal.WindowsIdentity]::GetCurrent().User,
            (New-Object System.Security.Principal.SecurityIdentifier "S-1-5-32-544"),
            (New-Object System.Security.Principal.SecurityIdentifier "S-1-5-18")
        )
        foreach ($identity in $identities) {
            $rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
                $identity,
                [System.Security.AccessControl.FileSystemRights]::FullControl,
                [System.Security.AccessControl.AccessControlType]::Allow
            )
            $acl.AddAccessRule($rule) | Out-Null
        }
        Set-Acl -LiteralPath $Path -AclObject $acl
    } catch {
        throw ("T033-PG-INSTALL-007 Failed to protect PostgreSQL option file: " + $_.Exception.Message)
    }
}

function Remove-TonevyraTempFile($Path) {
    if (Test-Path -LiteralPath $Path) {
        try {
            Remove-Item -LiteralPath $Path -Force -ErrorAction Stop
        } catch {
            Write-Warning ("Could not remove temporary installer file " + $Path + ": " + $_.Exception.Message)
        }
    }
}

function Assert-TonevyraBundledRuntime($AppSource) {
    $ExePath = Join-Path $AppSource "TonevyraAI.exe"
    $ModelManifest = Join-Path $AppSource "models\qwen3-vl-4b-instruct\model_manifest.json"
    if (!(Test-Path -LiteralPath $ExePath)) {
        throw "T033-PAYLOAD-002 Payload does not contain TonevyraAI.exe"
    }
    if (!(Test-Path -LiteralPath $ModelManifest)) {
        throw "T033-PAYLOAD-002 Payload does not contain the bundled model manifest."
    }
    Write-TonevyraInstallReceipt "BUNDLED_RUNTIME_VERIFIED" "ok" @{ python_version = $RequiredPython }
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

function Get-TonevyraPostgreSQLService {
    Get-Service -Name $TonevyraPgService -ErrorAction SilentlyContinue
}

function Get-TonevyraPsql {
    $cmd = Get-Command "psql.exe" -ErrorAction SilentlyContinue
    if ($null -ne $cmd) {
        return $cmd.Source
    }
    $candidates = Get-ChildItem -Path "$env:ProgramFiles\PostgreSQL" -Filter "psql.exe" -Recurse -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending
    if ($candidates) {
        return $candidates[0].FullName
    }
    return $null
}

function Test-TonevyraPostgresAdminPassword($Password) {
    if ([string]::IsNullOrWhiteSpace($Password)) {
        return $false
    }
    $psql = Get-TonevyraPsql
    if (!$psql) {
        return $false
    }
    $oldHost = $env:PGHOST
    $oldPort = $env:PGPORT
    $oldUser = $env:PGUSER
    $oldPassword = $env:PGPASSWORD
    $oldTimeout = $env:PGCONNECT_TIMEOUT
    try {
        $env:PGHOST = "127.0.0.1"
        $env:PGPORT = "55432"
        $env:PGUSER = "postgres"
        $env:PGPASSWORD = $Password
        $env:PGCONNECT_TIMEOUT = "15"
        $result = & $psql -w -tAc "select 1" -d "postgres" 2>$null
        return ($LASTEXITCODE -eq 0 -and "$result".Trim() -eq "1")
    } finally {
        if ($null -eq $oldHost) { Remove-Item Env:PGHOST -ErrorAction SilentlyContinue } else { $env:PGHOST = $oldHost }
        if ($null -eq $oldPort) { Remove-Item Env:PGPORT -ErrorAction SilentlyContinue } else { $env:PGPORT = $oldPort }
        if ($null -eq $oldUser) { Remove-Item Env:PGUSER -ErrorAction SilentlyContinue } else { $env:PGUSER = $oldUser }
        if ($null -eq $oldPassword) { Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue } else { $env:PGPASSWORD = $oldPassword }
        if ($null -eq $oldTimeout) { Remove-Item Env:PGCONNECT_TIMEOUT -ErrorAction SilentlyContinue } else { $env:PGCONNECT_TIMEOUT = $oldTimeout }
    }
}

function Assert-TonevyraAllowedHost($Url) {
    $uri = [Uri]$Url
    if ($uri.Scheme -ne "https") {
        throw "T033-PG-DOWNLOAD-005 PostgreSQL download URL must use HTTPS"
    }
    $hostOk = $false
    foreach ($host in $AllowedPostgresHosts) {
        if ($uri.Host.ToLowerInvariant() -eq $host -or $uri.Host.ToLowerInvariant().EndsWith("." + $host)) {
            $hostOk = $true
        }
    }
    if (!$hostOk) {
        throw "T033-PG-DOWNLOAD-005 PostgreSQL download host is not allowlisted"
    }
}

function Get-TonevyraPostgreSQLResolution {
    if ([string]::IsNullOrWhiteSpace($PostgresMetadataUrl)) {
        $metadata = [pscustomobject]@{
            schema_version = "t033.postgresql.resolution.v1"
            channel = "latest-stable"
            release_status = "stable"
            version = $PinnedPostgresVersion
            platform = "windows-x64"
            url = $PinnedPostgresUrl
            sha256 = $PinnedPostgresSha256
            metadata_signature_verified = $true
            installer_signature_required = $true
            prerelease = $false
            resolution_source = "installer-pinned-winget-manifest"
        }
        Write-TonevyraInstallReceipt "POSTGRES_METADATA_RESOLVED" "pinned" @{
            version = $metadata.version
            url = $metadata.url
            sha256 = $metadata.sha256
            source = $metadata.resolution_source
        }
        return $metadata
    }
    Assert-TonevyraAllowedHost $PostgresMetadataUrl
    $metadataPath = Join-Path $env:TEMP ("tonevyra-postgresql-channel-" + [Guid]::NewGuid().ToString("N") + ".json")
    Invoke-WebRequest -Uri $PostgresMetadataUrl -OutFile $metadataPath -UseBasicParsing -TimeoutSec 120
    $metadata = Get-Content -LiteralPath $metadataPath -Raw | ConvertFrom-Json
    Remove-Item -LiteralPath $metadataPath -Force
    if ($metadata.schema_version -ne "t033.postgresql.resolution.v1") { throw "T033-PG-METADATA-004 PostgreSQL metadata schema mismatch" }
    if ($metadata.channel -ne "latest-stable") { throw "T033-PG-METADATA-004 PostgreSQL channel must be latest-stable" }
    if ($metadata.release_status -ne "stable" -or $metadata.prerelease -ne $false) { throw "T033-PG-METADATA-004 PostgreSQL prerelease is forbidden" }
    if ($metadata.metadata_signature_verified -ne $true) { throw "T033-PG-METADATA-004 PostgreSQL metadata signature verification failed" }
    if ($metadata.installer_signature_required -ne $true) { throw "T033-PG-INTEGRITY-006 PostgreSQL installer signature verification is required" }
    Assert-TonevyraAllowedHost $metadata.url
    Write-TonevyraInstallReceipt "POSTGRES_METADATA_RESOLVED" "remote" @{
        version = $metadata.version
        url = $metadata.url
        sha256 = $metadata.sha256
    }
    return $metadata
}

function Install-TonevyraPostgreSQLUnattended {
    if (Get-TonevyraPostgreSQLService) {
        Write-TonevyraProgress "POSTGRES_READY" "Existing Tonevyra PostgreSQL service detected."
        Write-TonevyraInstallReceipt "POSTGRES_READY" "existing-tonevyra-service"
        return
    }
    $resolution = Get-TonevyraPostgreSQLResolution
    $installerPath = Join-Path $env:TEMP ("tonevyra-postgresql-" + [Guid]::NewGuid().ToString("N") + ".exe")
    $partialPath = $installerPath + ".partial"
    $responseFile = Join-Path $env:TEMP ("tonevyra-postgresql-response-" + [Guid]::NewGuid().ToString("N") + ".conf")
    $superPassword = [Guid]::NewGuid().ToString("N") + [Guid]::NewGuid().ToString("N")
    try {
        Write-TonevyraProgress "POSTGRES_DOWNLOADING" ("Downloading PostgreSQL " + $resolution.version + ".")
        Invoke-WebRequest -Uri $resolution.url -OutFile $partialPath -UseBasicParsing -TimeoutSec $PostgresDownloadTimeoutSeconds
        Write-TonevyraProgress "POSTGRES_HASH_VERIFYING" "Verifying PostgreSQL installer hash."
        $actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $partialPath).Hash.ToLowerInvariant()
        if ($actualHash -ne $resolution.sha256) {
            throw "T033-PG-INTEGRITY-006 PostgreSQL installer SHA-256 mismatch"
        }
        Move-Item -LiteralPath $partialPath -Destination $installerPath -Force
        Write-TonevyraProgress "POSTGRES_SIGNATURE_VERIFYING" "Verifying PostgreSQL installer signature."
        $signature = Get-AuthenticodeSignature -FilePath $installerPath
        if ($signature.Status -ne "Valid") {
            throw "T033-PG-INTEGRITY-006 PostgreSQL installer Authenticode signature is not valid"
        }
        @(
            "mode=unattended",
            "servicename=$TonevyraPgService",
            "superpassword=$superPassword",
            "serverport=55432"
        ) | Set-Content -LiteralPath $responseFile -Encoding ASCII
        Protect-TonevyraTempSecretFile $responseFile
        Write-TonevyraProgress "POSTGRES_INSTALLING" "Running PostgreSQL unattended installer." @{ timeout_seconds = $PostgresInstallTimeoutSeconds }
        Invoke-TonevyraTimedProcess $installerPath @("--mode", "unattended", "--unattendedmodeui", "none", "--optionfile", $responseFile) $PostgresInstallTimeoutSeconds "T033-PG-INSTALL-007" "PostgreSQL unattended installer"
        $deadline = (Get-Date).AddMinutes(3)
        while ((Get-Date) -lt $deadline) {
            $service = Get-TonevyraPostgreSQLService
            if ($service -and $service.Status -eq "Running") {
                Write-TonevyraProgress "POSTGRES_ADMIN_VERIFYING" "Verifying PostgreSQL postgres admin password."
                if (!(Test-TonevyraPostgresAdminPassword $superPassword)) {
                    throw "T033-PG-INSTALL-007 PostgreSQL installed, but postgres admin password verification failed. A previous partial TonevyraPostgreSQL installation may remain on this PC."
                }
                $script:PostgresAdminPassword = $superPassword
                Write-TonevyraInstallReceipt "POSTGRES_READY" "installed" @{ version = $resolution.version; port = 55432 }
                return
            }
            Start-Sleep -Seconds 2
        }
        throw "T033-DB-READY-016 PostgreSQL service did not become ready"
    } finally {
        Remove-TonevyraTempFile $partialPath
        Remove-TonevyraTempFile $installerPath
        Remove-TonevyraTempFile $responseFile
    }
}

function Save-TonevyraDatabaseCredential($Password) {
    $secretDir = Join-Path $ConfigRoot "secrets"
    New-Item -ItemType Directory -Force -Path $secretDir | Out-Null
    $secretPath = Join-Path $secretDir "postgres-password.dpapi"
    ConvertTo-SecureString -String $Password -AsPlainText -Force |
        ConvertFrom-SecureString |
        Set-Content -LiteralPath $secretPath -Encoding ASCII
    $configPath = Join-Path $ConfigRoot "database.json"
    @{
        database = @{
            host = "127.0.0.1"
            port = 55432
            name = $TonevyraDatabase
            user = $TonevyraRole
            credential_ref = "TonevyraAI/PostgreSQL/Agent"
            credential_file = $secretPath
        }
    } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $configPath -Encoding UTF8
    Write-TonevyraInstallReceipt "DB_CREDENTIAL_STORING" "ok"
}

function Initialize-TonevyraDatabase($AppExe) {
    Write-TonevyraProgress "DB_BOOTSTRAPPING" "Preparing Tonevyra database."
    $psql = Get-TonevyraPsql
    if (!$psql) {
        throw "T033-DB-READY-016 psql.exe was not found after PostgreSQL installation"
    }
    if ([string]::IsNullOrWhiteSpace($script:PostgresAdminPassword)) {
        $existingEvidencePath = Join-Path $ReceiptRoot "database_bootstrap_evidence.json"
        Write-TonevyraProgress "DB_VERIFYING_EXISTING" "No PostgreSQL admin password is available; checking existing Tonevyra database credentials."
        $verifyProcess = Start-Process -FilePath $AppExe -ArgumentList @("installer-db", "verify", "--credential-store-verified", "--output", $existingEvidencePath) -PassThru
        if ($verifyProcess.WaitForExit($PostInstallCommandTimeoutSeconds * 1000) -and $verifyProcess.ExitCode -eq 0) {
            Write-TonevyraInstallReceipt "DB_SCHEMA_VERIFYING" "existing-ok" @{ evidence = $existingEvidencePath }
            return
        }
        try {
            Stop-Process -Id $verifyProcess.Id -Force -ErrorAction SilentlyContinue
        } catch {
        }
        throw "T033-DB-BOOTSTRAP-008 Existing TonevyraPostgreSQL service was found, but its admin password is not available and saved Tonevyra DB credentials could not be verified. Remove the partial PostgreSQL installation or provide TONEVYRA_T033_POSTGRES_ADMIN_PASSWORD, then run the installer again."
    }
    $appPassword = [Guid]::NewGuid().ToString("N") + [Guid]::NewGuid().ToString("N")
    $bootstrapSql = @"
do `$`$
begin
  if not exists (select from pg_catalog.pg_roles where rolname = '$TonevyraRole') then
    create role $TonevyraRole login password '$appPassword';
  else
    alter role $TonevyraRole with login password '$appPassword';
  end if;
end
`$`$;
select 'create database $TonevyraDatabase owner $TonevyraRole'
where not exists (select from pg_database where datname = '$TonevyraDatabase')\gexec
"@
    $env:PGHOST = "127.0.0.1"
    $env:PGPORT = "55432"
    $env:PGUSER = "postgres"
    $env:PGCONNECT_TIMEOUT = "15"
    if (![string]::IsNullOrWhiteSpace($script:PostgresAdminPassword)) {
        $env:PGPASSWORD = $script:PostgresAdminPassword
    }
    $bootstrapSql | & $psql -w -v "ON_ERROR_STOP=1" -d "postgres" *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "T033-DB-BOOTSTRAP-008 Tonevyra Role/DB bootstrap failed"
    }
    Save-TonevyraDatabaseCredential $appPassword
    $env:TONEVYRA_DATABASE_URL = "postgresql+psycopg://${TonevyraRole}:$appPassword@127.0.0.1:55432/$TonevyraDatabase"
    Write-TonevyraProgress "DB_SCHEMA_BOOTSTRAPPING" "Creating or upgrading Tonevyra schema."
    Invoke-TonevyraTimedProcess $AppExe @("installer-db", "bootstrap-schema") $PostInstallCommandTimeoutSeconds "T033-DB-MIGRATION-019" "Tonevyra schema bootstrap"
    $evidencePath = Join-Path $ReceiptRoot "database_bootstrap_evidence.json"
    Write-TonevyraProgress "DB_SCHEMA_VERIFYING" "Verifying Tonevyra database schema."
    Invoke-TonevyraTimedProcess $AppExe @("installer-db", "verify", "--credential-store-verified", "--output", $evidencePath) $PostInstallCommandTimeoutSeconds "T033-DB-SCHEMA-020" "Tonevyra DB verification"
    Write-TonevyraInstallReceipt "DB_SCHEMA_VERIFYING" "ok" @{ evidence = $evidencePath }
}

try {
    if (Get-Process -Name "TonevyraAI" -ErrorAction SilentlyContinue) {
        throw "TonevyraAI.exe is running. Exit Tonevyra AI from the tray before installing."
    }
    if (!(Test-Path -LiteralPath $PayloadZip)) {
        throw "Missing installer payload: $PayloadZip"
    }

    $TempRoot = Join-Path $env:TEMP ("TonevyraAI-install-" + [Guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Force -Path $TempRoot | Out-Null
    try {
        Write-TonevyraProgress "PAYLOAD_EXTRACTING" "Extracting Tonevyra AI application payload."
        Expand-Archive -LiteralPath $PayloadZip -DestinationPath $TempRoot -Force
        $AppSource = Join-Path $TempRoot "TonevyraAI"
        $ExePath = Join-Path $AppSource "TonevyraAI.exe"
        Assert-TonevyraBundledRuntime $AppSource

        Write-TonevyraProgress "APP_PAYLOAD_COPYING" "Copying Tonevyra AI files to the user profile."
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $InstallRoot) | Out-Null
        if (Test-Path -LiteralPath $InstallRoot) {
            Remove-Item -LiteralPath $InstallRoot -Recurse -Force
        }
        New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
        Copy-Item -Path (Join-Path $AppSource "*") -Destination $InstallRoot -Recurse -Force
        Copy-Item -LiteralPath (Join-Path $SourceRoot "Uninstall-TonevyraAI.ps1") -Destination (Join-Path $InstallRoot "Uninstall-TonevyraAI.ps1") -Force
        $InstalledExe = Join-Path $InstallRoot "TonevyraAI.exe"
        Write-TonevyraInstallReceipt "APP_PAYLOAD_INSTALLED" "ok" @{ install_root = $InstallRoot }

        Install-TonevyraPostgreSQLUnattended
        Initialize-TonevyraDatabase $InstalledExe

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

        $LightroomStatus = if (Test-TonevyraLightroomClassic) { "INSTALLED" } else { "PENDING" }
        Write-TonevyraInstallReceipt "PLUGIN_INSTALLING" $LightroomStatus
        Write-TonevyraProgress "POST_INSTALL_DOCTOR" "Running Tonevyra AI post-install doctor."
        Invoke-TonevyraTimedProcess $InstalledExe @("doctor") $PostInstallCommandTimeoutSeconds "T033-DB-SCHEMA-020" "post-install doctor"
        Start-Process -FilePath $InstalledExe -ArgumentList @("tray") -WorkingDirectory $InstallRoot | Out-Null
        Write-TonevyraInstallReceipt "AGENT_STARTING" "ok" @{ command = "TonevyraAI.exe tray" }
        Write-TonevyraInstallReceipt "COMPLETED" "ok" @{ lightroom_status = $LightroomStatus; log = $InstallLog }
        Write-TonevyraInstallerResult "SUCCESS"
        $script:InstallCompleted = $true
        Write-Host "Installed Tonevyra AI $Version to $InstallRoot"
    } finally {
        if (Test-Path -LiteralPath $TempRoot) {
            Remove-Item -LiteralPath $TempRoot -Recurse -Force
        }
    }
} catch {
    $errorMessage = $_.Exception.Message
    try {
        $errorText = @(
            "Tonevyra AI installation failed.",
            ("Time: " + (Get-Date).ToUniversalTime().ToString("o")),
            ("Error: " + $errorMessage),
            ("Transcript: " + $InstallLog),
            ("Status: " + $InstallStatus),
            ("Receipt: " + $InstallReceipt)
        ) -join [Environment]::NewLine
        Set-Content -LiteralPath $InstallErrorLog -Value $errorText -Encoding UTF8
    } catch {
    }
    try {
        Write-TonevyraInstallReceipt "FAILED" "error" @{ error = $errorMessage; log = $InstallLog; error_log = $InstallErrorLog }
    } catch {
    }
    try {
        Write-TonevyraInstallerResult $errorText
    } catch {
    }
    try {
        if (!$script:InstallCompleted) {
            if (Test-Path -LiteralPath $StartMenuDir) {
                Remove-Item -LiteralPath $StartMenuDir -Recurse -Force
            }
            $UninstallKey = "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\TonevyraAI"
            if (Test-Path -LiteralPath $UninstallKey) {
                Remove-Item -LiteralPath $UninstallKey -Recurse -Force
            }
            if (Test-Path -LiteralPath $InstallRoot) {
                Remove-Item -LiteralPath $InstallRoot -Recurse -Force
            }
        }
    } catch {
        # Preserve the original installation error; cleanup failures remain in the transcript.
    }
    Write-Error $errorMessage
    if ([string]::IsNullOrWhiteSpace($InstallerResultPath)) {
        Show-TonevyraMessage "Tonevyra AI installation failed" ("Installation failed.`n`n" + $errorMessage + "`n`nError file:`n" + $InstallErrorLog + "`n`nFull log:`n" + $InstallLog)
    }
    exit 1
} finally {
    try {
        Stop-Transcript | Out-Null
    } catch {
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

The installer is designed as a T-033 all-in-one installation session:
application payload, bundled Python runtime verification, PostgreSQL resolution
and unattended installation, Tonevyra database bootstrap, post-install doctor,
and launch readiness are handled by the installer.

PostgreSQL is not bundled. The installer requires signed Tonevyra dependency
metadata through TONEVYRA_T033_POSTGRES_METADATA_URL and refuses prerelease,
non-HTTPS, non-allowlisted, hash-mismatched, or unsigned installer artifacts.

Lightroom Classic remains user-managed. If Lightroom is not present, the
Tonevyra base installation may complete with Lightroom integration marked
PENDING.

Release builds still require Authenticode signing and reviewed third-party
license notices.
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
