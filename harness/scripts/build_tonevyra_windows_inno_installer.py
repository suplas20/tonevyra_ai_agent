#!/usr/bin/env python3
"""Build a T-033 Windows installer with Inno Setup.

The legacy IExpress path is useful for small payloads, but the bundled local
model makes the T-033 all-in-one payload too large for that route to be
practical. This builder wraps the already staged TonevyraAI-app.zip and
installer scripts with Inno Setup without recompressing the zip.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = ROOT / "runtime" / "windows_installer"
DEFAULT_OUTPUT_DIR = Path(os.environ.get("TONEVYRA_WINDOWS_INSTALLER_OUTPUT_DIR", r"D:\Tonevyra_install"))
PAYLOAD_NAME = "TonevyraAI-app.zip"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--version")
    parser.add_argument("--stage-dir", type=Path)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=r"Final installer output directory (default: D:\Tonevyra_install).",
    )
    parser.add_argument("--iscc", type=Path, help="Path to ISCC.exe.")
    parser.add_argument(
        "--rebuild-stage",
        action="store_true",
        help="Rebuild runtime/windows_installer/TonevyraAI-<version> before compiling Inno.",
    )
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    version = args.version or _project_version(project_root)
    package_root = project_root / "runtime" / "windows_installer"
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    stage_dir = args.stage_dir or package_root / f"TonevyraAI-{version}"
    stage_dir = stage_dir if stage_dir.is_absolute() else project_root / stage_dir
    iscc = _resolve_iscc(args.iscc)

    if args.rebuild_stage:
        _run(
            [
                sys.executable,
                str(project_root / "harness" / "scripts" / "build_tonevyra_windows_installer.py"),
                "--skip-exe-build",
                "--skip-iexpress",
                "--output-dir",
                str(output_dir),
            ],
            project_root,
        )

    _require_stage(stage_dir, project_root=project_root)
    iss_path = package_root / f"TonevyraAI-Setup-{version}.inno.iss"
    setup_exe = output_dir / f"TonevyraAI-Setup-{version}.exe"
    _remove_previous_outputs(output_dir, version)
    _write_iss(iss_path, stage_dir=stage_dir, output_dir=output_dir, version=version)

    result = subprocess.run([str(iscc), str(iss_path)], cwd=project_root, check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)
    sidecars = _installer_sidecars(output_dir, version)
    if not setup_exe.is_file():
        raise SystemExit(f"Inno Setup finished without creating installer: {setup_exe}")

    manifest_path = _write_manifest(
        package_root=output_dir,
        stage_dir=stage_dir,
        setup_exe=setup_exe,
        sidecars=sidecars,
        iss_path=iss_path,
        version=version,
        iscc=iscc,
    )
    print(f"OK: inno_script={iss_path}")
    print(f"OK: installer={setup_exe}")
    for sidecar in sidecars:
        print(f"OK: installer_sidecar={sidecar}")
    print(f"OK: manifest={manifest_path}")
    return 0


def _project_version(project_root: Path) -> str:
    data = tomllib.loads((project_root / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def _resolve_iscc(explicit: Path | None) -> Path:
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit)
    found = shutil.which("iscc.exe") or shutil.which("ISCC.exe")
    if found:
        candidates.append(Path(found))
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        candidates.append(Path(local_appdata) / "Programs" / "Inno Setup 6" / "ISCC.exe")
    candidates.extend(
        [
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Inno Setup 6" / "ISCC.exe",
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Inno Setup 6" / "ISCC.exe",
        ]
    )
    for candidate in candidates:
        candidate = candidate.expanduser()
        if candidate.is_file():
            return candidate.resolve()
    raise SystemExit("ISCC.exe not found. Install Inno Setup 6 or pass --iscc <path>.")


def _run(command: list[str], cwd: Path) -> None:
    result = subprocess.run(command, cwd=cwd, check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def _require_stage(stage_dir: Path, *, project_root: Path) -> None:
    required = [
        stage_dir / PAYLOAD_NAME,
        stage_dir / "Install-TonevyraAI.ps1",
        stage_dir / "Uninstall-TonevyraAI.ps1",
        stage_dir / "README_INSTALL.txt",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise SystemExit("missing installer stage files: " + ", ".join(missing))
    _require_fresh_stage(stage_dir, project_root=project_root)
    _require_install_script_contract(stage_dir / "Install-TonevyraAI.ps1")


def _require_fresh_stage(stage_dir: Path, *, project_root: Path) -> None:
    install_script = stage_dir / "Install-TonevyraAI.ps1"
    stage_builder = project_root / "harness" / "scripts" / "build_tonevyra_windows_installer.py"
    if install_script.stat().st_mtime < stage_builder.stat().st_mtime:
        raise SystemExit(
            "installer stage is stale: Install-TonevyraAI.ps1 is older than "
            f"{stage_builder}. Run build_tonevyra_windows_inno_installer.py --rebuild-stage "
            "or rebuild the stage first."
        )


def _require_install_script_contract(install_script: Path) -> None:
    text = install_script.read_text(encoding="utf-8-sig")
    required_tokens = [
        "[string]$InstallerLogDir",
        "[string]$InstallerResultPath",
        "Write-TonevyraProgress",
        "Invoke-TonevyraTimedProcess",
        "PGCONNECT_TIMEOUT",
        "POSTGRES_INSTALLING",
        "POST_INSTALL_DOCTOR",
        "Existing TonevyraPostgreSQL service was found",
        "TonevyraAI-install-",
    ]
    missing = [token for token in required_tokens if token not in text]
    if missing:
        raise SystemExit(
            "installer stage script is missing required installation contract tokens: "
            + ", ".join(missing)
            + ". Rebuild the stage before compiling Inno."
        )


def _remove_previous_outputs(package_root: Path, version: str) -> None:
    for path in package_root.glob(f"TonevyraAI-Setup-{version}*.bin"):
        path.unlink()
    exe = package_root / f"TonevyraAI-Setup-{version}.exe"
    if exe.exists():
        exe.unlink()


def _write_iss(path: Path, *, stage_dir: Path, output_dir: Path, version: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = stage_dir / PAYLOAD_NAME
    install_script = stage_dir / "Install-TonevyraAI.ps1"
    uninstall_script = stage_dir / "Uninstall-TonevyraAI.ps1"
    readme = stage_dir / "README_INSTALL.txt"
    content = f'''#define MyAppName "Tonevyra AI"
#define MyAppVersion "{version}"

[Setup]
AppId={{{{D8CC633A-7FFB-4E54-9F46-B589B3A74422}}}}
AppName={{#MyAppName}}
AppVersion={{#MyAppVersion}}
AppPublisher=Tonevyra
DefaultDirName={{autopf}}\\Tonevyra AI Installer
DisableDirPage=yes
DisableProgramGroupPage=yes
OutputDir={_iss_value(output_dir)}
OutputBaseFilename=TonevyraAI-Setup-{version}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
Compression=none
SolidCompression=no
DiskSpanning=yes
DiskSliceSize=2000000000
WizardStyle=modern
Uninstallable=no
CreateUninstallRegKey=no
SetupLogging=yes

[Files]
Source: {_iss_value(payload)}; DestDir: "{{tmp}}\\TonevyraAI"; Flags: deleteafterinstall
Source: {_iss_value(install_script)}; DestDir: "{{tmp}}\\TonevyraAI"; Flags: deleteafterinstall
Source: {_iss_value(uninstall_script)}; DestDir: "{{tmp}}\\TonevyraAI"; Flags: deleteafterinstall
Source: {_iss_value(readme)}; DestDir: "{{tmp}}\\TonevyraAI"; Flags: isreadme deleteafterinstall

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  PowerShellPath: String;
  InstallScriptPath: String;
  ResultPath: String;
  BootstrapLogPath: String;
  SourceFallbackLogPath: String;
  DurableFallbackLogPath: String;
  FailureLogPath: String;
  Parameters: String;
  ErrorDetails: String;
  ErrorLines: TArrayOfString;
  LineIndex: Integer;
begin
  if CurStep <> ssPostInstall then
    exit;

  WizardForm.StatusLabel.Caption := 'Tonevyra AI installation is running. On older PCs this can take 20-40 minutes.';
  PowerShellPath := ExpandConstant('{{sys}}\\WindowsPowerShell\\v1.0\\powershell.exe');
  InstallScriptPath := ExpandConstant('{{tmp}}\\TonevyraAI\\Install-TonevyraAI.ps1');
  ResultPath := ExpandConstant('{{tmp}}\\TonevyraAI\\install-result.txt');
  BootstrapLogPath := ExpandConstant('{{tmp}}\\TonevyraAI\\install-bootstrap.log');
  DeleteFile(ResultPath);
  DeleteFile(BootstrapLogPath);
  Parameters := '-NoProfile -ExecutionPolicy Bypass -File "' + InstallScriptPath +
    '" -InstallerLogDir "' + ExpandConstant('{{src}}') +
    '" -InstallerResultPath "' + ResultPath + '"';

  ResultCode := -1;
  if (not Exec(PowerShellPath, Parameters, '', SW_SHOWNORMAL,
      ewWaitUntilTerminated, ResultCode)) or (ResultCode <> 0) then
  begin
    ErrorDetails := '';
    if FileExists(ResultPath) and LoadStringsFromFile(ResultPath, ErrorLines) then
      for LineIndex := 0 to GetArrayLength(ErrorLines) - 1 do
      begin
        if ErrorDetails <> '' then
          ErrorDetails := ErrorDetails + #13#10;
        ErrorDetails := ErrorDetails + ErrorLines[LineIndex];
      end;
    if (ErrorDetails = '') and FileExists(BootstrapLogPath) and
       LoadStringsFromFile(BootstrapLogPath, ErrorLines) then
      for LineIndex := 0 to GetArrayLength(ErrorLines) - 1 do
      begin
        if ErrorDetails <> '' then
          ErrorDetails := ErrorDetails + #13#10;
        ErrorDetails := ErrorDetails + ErrorLines[LineIndex];
      end;
    if ErrorDetails = '' then
      ErrorDetails := Format('Installer process exit code: %d', [ResultCode]);

    SourceFallbackLogPath := ExpandConstant('{{src}}\\TonevyraAI-install-bootstrap-error.txt');
    DurableFallbackLogPath := ExpandConstant(
      '{{commonappdata}}\\TonevyraAI\\install-receipts\\TonevyraAI-install-bootstrap-error.txt');
    if SaveStringToFile(SourceFallbackLogPath, ErrorDetails, False) then
      FailureLogPath := SourceFallbackLogPath
    else
    begin
      ForceDirectories(ExtractFileDir(DurableFallbackLogPath));
      SaveStringToFile(DurableFallbackLogPath, ErrorDetails, False);
      FailureLogPath := DurableFallbackLogPath;
    end;
    RaiseException(
      'Tonevyra AI 설치에 실패했습니다.' + #13#10 + #13#10 +
      ErrorDetails + #13#10 + #13#10 +
      '설치는 완료되지 않았습니다.' + #13#10 +
      '오류 로그: ' + FailureLogPath);
  end;
end;
'''
    path.write_text(content, encoding="utf-8")


def _iss_value(path: Path) -> str:
    return '"' + str(path.resolve()).replace('"', '""') + '"'


def _write_manifest(
    *,
    package_root: Path,
    stage_dir: Path,
    setup_exe: Path,
    sidecars: list[Path],
    iss_path: Path,
    version: str,
    iscc: Path,
) -> Path:
    payload = stage_dir / PAYLOAD_NAME
    manifest = {
        "schema_version": "tonevyra.windows_installer.v1",
        "product": "Tonevyra AI",
        "version": version,
        "python": sys.version,
        "stage_dir": str(stage_dir),
        "payload_zip": str(payload),
        "payload_sha256": _sha256(payload),
        "installer_backend": "inno_setup",
        "inno_script": str(iss_path),
        "inno_compiler": str(iscc),
        "installer_stage_validated": True,
        "powershell_install_window_visible": True,
        "installer_exe": str(setup_exe),
        "installer_sha256": _sha256(setup_exe),
        "installer_size_bytes": setup_exe.stat().st_size,
        "installer_sidecars": [
            {
                "path": str(path),
                "sha256": _sha256(path),
                "size_bytes": path.stat().st_size,
            }
            for path in sidecars
        ],
        "all_in_one_orchestrator": True,
        "postgres_unattended_install": True,
        "database_bootstrap_automation": True,
        "post_install_doctor_required": True,
        "code_signed": False,
        "blocked_reasons": ["BLOCKED_CODE_SIGNING_NOT_CONFIGURED"],
    }
    path = package_root / f"TonevyraAI-Setup-{version}.manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _installer_sidecars(package_root: Path, version: str) -> list[Path]:
    return sorted(package_root.glob(f"TonevyraAI-Setup-{version}*.bin"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
