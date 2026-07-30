#!/usr/bin/env python3
"""Build the native Inno Setup Windows installer for Tonevyra AI.

Unlike the legacy zip-in-zip route, this builder lets Inno Setup install the
application, bundled model, Lightroom plugin and resources natively via
``[Files]`` and delegates DB/schema/doctor gates to the app CLI at install time.

Responsibilities of this script:
  * resolve machine-specific source paths (frozen app, local model root),
  * stage a relative-path ``model_manifest.json`` for the installed layout,
  * compile ``installer/windows/TonevyraAI.iss`` with ISCC (paths via /D),
  * write a hash manifest of the produced installer + disk slices.

It does NOT rebuild the frozen app; run ``build_tonevyra_windows_exe.py`` first
(or reuse the existing ``runtime/windows_dist/TonevyraAI`` output).
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
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
INSTALLER_SRC = ROOT / "installer" / "windows"
ISS_PATH = INSTALLER_SRC / "TonevyraAI.iss"
FROZEN_APP = ROOT / "runtime" / "windows_dist" / "TonevyraAI"
PLUGIN_SRC = ROOT / "lightroom" / "TonevyraAI.lrplugin"
RESOURCES_SRC = ROOT / "resources"
MODEL_MANIFEST = ROOT / "models" / "qwen3-vl-4b-instruct" / "model_manifest.json"
STAGE_DIR = ROOT / "runtime" / "windows_installer" / "native" / "stage"
DEFAULT_OUTPUT_DIR = Path(os.environ.get("TONEVYRA_WINDOWS_INSTALLER_OUTPUT_DIR", r"D:\Tonevyra_install"))
INSTALLED_MODEL_ROOT = "models/qwen3-vl-4b-instruct"
MODEL_METADATA_ONLY = {".gitkeep", "model_manifest.json"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-root", type=Path, default=ROOT)
    ap.add_argument("--model-source", type=Path, default=os.environ.get("TONEVYRA_WINDOWS_MODEL_BUNDLE_SOURCE"))
    ap.add_argument("--iscc", type=Path, help="Path to ISCC.exe")
    ap.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=r"Final installer output directory (default: D:\Tonevyra_install).",
    )
    ap.add_argument(
        "--sign",
        action="store_true",
        default=_env_flag("TONEVYRA_SIGN"),
        help="Authenticode-sign the app exe and installer via installer/windows/Sign-Tonevyra.ps1.",
    )
    args = ap.parse_args()

    project_root = args.project_root.resolve()
    version = _project_version(project_root)
    # Keep the installer file-set (exe + disk slices + manifest) grouped in its
    # own versioned folder so it is not mixed with other files at the output root.
    output_dir = (args.output_dir.expanduser().resolve() / f"TonevyraAI-Setup-{version}")
    iscc = _resolve_iscc(args.iscc)
    frozen_app = project_root / "runtime" / "windows_dist" / "TonevyraAI"
    _require_frozen_app(frozen_app)
    model_source = _resolve_model_source(project_root, args.model_source)
    _require_sources(project_root)

    # Sign the frozen app exe BEFORE ISCC packages it, so the installed
    # TonevyraAI.exe carries the signature.
    if args.sign:
        _sign_files([frozen_app / "TonevyraAI.exe"])

    output_dir.mkdir(parents=True, exist_ok=True)
    _stage_model_manifest(project_root, model_source)
    _clean_previous_outputs(output_dir, version)

    defines = {
        "MyAppVersion": version,
        "AppSource": str(frozen_app),
        "ModelSource": str(model_source),
        "PluginSource": str(PLUGIN_SRC),
        "ResourcesSource": str(RESOURCES_SRC),
        "InstallerSrc": str(INSTALLER_SRC),
        "StageDir": str(STAGE_DIR),
        "OutputDir": str(output_dir),
    }
    command = [str(iscc)] + [f"/D{name}={value}" for name, value in defines.items()] + [str(ISS_PATH)]
    print("ISCC:", " ".join(command))
    result = subprocess.run(command, cwd=project_root, check=False)
    if result.returncode != 0:
        raise SystemExit(f"ISCC failed with exit code {result.returncode}")

    setup_exe = output_dir / f"TonevyraAI-Setup-{version}.exe"
    slices = sorted(output_dir.glob(f"TonevyraAI-Setup-{version}-*.bin"))
    if not setup_exe.is_file():
        raise SystemExit(f"ISCC finished but installer is missing: {setup_exe}")

    # Sign the produced installer executable (the disk slices carry no code).
    if args.sign:
        _sign_files([setup_exe])

    manifest_path = _write_manifest(
        version, setup_exe, slices, model_source, iscc, output_dir=output_dir, signed=args.sign
    )
    print(f"OK: installer={setup_exe}")
    for path in slices:
        print(f"OK: slice={path}")
    print(f"OK: manifest={manifest_path}")
    return 0


def _project_version(project_root: Path) -> str:
    data = tomllib.loads((project_root / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def _require_frozen_app(frozen_app: Path) -> None:
    exe = frozen_app / "TonevyraAI.exe"
    if not exe.is_file():
        raise SystemExit(
            f"missing frozen app: {exe}. Run harness/scripts/build_tonevyra_windows_exe.py first."
        )


def _require_sources(project_root: Path) -> None:
    """Fail fast on missing [Files] sources before ISCC starts compressing."""
    required = {
        "iss": ISS_PATH,
        "plugin": PLUGIN_SRC / "Info.lua",
        "resources": RESOURCES_SRC,
        ".env.example": project_root / ".env.example",
        "README.md": project_root / "README.md",
        "vision fixtures": project_root / "harness" / "fixtures" / "vision",
        "provision script": INSTALLER_SRC / "Invoke-TonevyraProvision.ps1",
        "db removal script": INSTALLER_SRC / "Remove-TonevyraDatabase.ps1",
        "install readme": INSTALLER_SRC / "README_INSTALL.txt",
    }
    missing = [f"{label}: {path}" for label, path in required.items() if not path.exists()]
    if missing:
        raise SystemExit("missing installer sources:\n  " + "\n  ".join(missing))


def _resolve_iscc(explicit: Path | None) -> Path:
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit)
    found = shutil.which("ISCC.exe") or shutil.which("iscc.exe")
    if found:
        candidates.append(Path(found))
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(Path(local) / "Programs" / "Inno Setup 6" / "ISCC.exe")
    candidates += [
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Inno Setup 6" / "ISCC.exe",
    ]
    for candidate in candidates:
        candidate = candidate.expanduser()
        if candidate.is_file():
            return candidate.resolve()
    raise SystemExit("ISCC.exe not found. Install Inno Setup 6 or pass --iscc <path>.")


def _model_payload_files(source: Path) -> list[Path]:
    if not source.is_dir():
        return []
    return sorted(
        path
        for path in source.rglob("*")
        if path.is_file() and path.name not in MODEL_METADATA_ONLY and ".cache" not in path.parts
    )


def _resolve_model_source(project_root: Path, override: Path | None) -> Path:
    if override is not None:
        source = override if override.is_absolute() else project_root / override
        source = source.resolve()
        if not _model_payload_files(source):
            raise SystemExit(f"model source has no weight files: {source}")
        return source

    local = (project_root / INSTALLED_MODEL_ROOT).resolve()
    if _model_payload_files(local):
        return local

    if MODEL_MANIFEST.is_file():
        manifest = json.loads(MODEL_MANIFEST.read_text(encoding="utf-8"))
        model_root = Path(str(manifest.get("model_root", "")))
        source = model_root if model_root.is_absolute() else project_root / model_root
        source = source.resolve()
        if _model_payload_files(source):
            return source

    raise SystemExit(
        "missing local model weights. Place them under models/qwen3-vl-4b-instruct, set "
        "model_root in model_manifest.json, or pass --model-source <dir>."
    )


def _stage_model_manifest(project_root: Path, model_source: Path) -> None:
    if STAGE_DIR.exists():
        shutil.rmtree(STAGE_DIR)
    STAGE_DIR.mkdir(parents=True)

    if MODEL_MANIFEST.is_file():
        manifest = json.loads(MODEL_MANIFEST.read_text(encoding="utf-8"))
    else:
        manifest = {
            "schema_version": "t022.local_model_manifest.v1",
            "model_id": model_source.name,
            "model_revision": "local-bundled",
            "runtime_backend": "transformers_qwen3vl",
            "checksum_mode": "index_file",
            "checksum_target_file": "model.safetensors.index.json",
        }
    # Rewrite absolute/machine paths to the installed relative layout and pin
    # local-only/offline flags for the bundled runtime.
    manifest["model_root"] = INSTALLED_MODEL_ROOT
    manifest["allowed_model_root"] = "models"
    manifest["remote_api_enabled"] = False
    manifest["runtime_download_enabled"] = False
    manifest["external_image_url_enabled"] = False
    manifest["network_required"] = False

    if manifest.get("checksum_mode") == "index_file":
        target = str(manifest.get("checksum_target_file") or "model.safetensors.index.json")
        if not (model_source / target).is_file():
            raise SystemExit(f"model checksum target missing in source: {model_source / target}")

    (STAGE_DIR / "model_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _clean_previous_outputs(output_dir: Path, version: str) -> None:
    for path in output_dir.glob(f"TonevyraAI-Setup-{version}*.bin"):
        path.unlink()
    exe = output_dir / f"TonevyraAI-Setup-{version}.exe"
    if exe.exists():
        exe.unlink()


def _env_flag(name: str) -> bool:
    return str(os.environ.get(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def _powershell() -> str:
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    candidate = Path(system_root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    return str(candidate) if candidate.is_file() else "powershell.exe"


def _sign_files(files: list[Path]) -> None:
    sign_script = INSTALLER_SRC / "Sign-Tonevyra.ps1"
    if not sign_script.is_file():
        raise SystemExit(f"signing requested but helper missing: {sign_script}")
    args = [_powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(sign_script), "-Files"]
    args += [str(f) for f in files]
    print("SIGN:", " ".join(str(f) for f in files))
    result = subprocess.run(args, check=False)
    if result.returncode != 0:
        raise SystemExit(f"signing failed (exit {result.returncode}) for: {', '.join(str(f) for f in files)}")


def _signature_status(path: Path) -> str:
    ps = (
        f"(Get-AuthenticodeSignature -LiteralPath '{path}').Status"
    )
    try:
        out = subprocess.run(
            [_powershell(), "-NoProfile", "-Command", ps],
            check=False,
            capture_output=True,
            text=True,
        )
        return (out.stdout or "").strip() or "Unknown"
    except OSError:
        return "Unknown"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_manifest(
    version: str,
    setup_exe: Path,
    slices: list[Path],
    model_source: Path,
    iscc: Path,
    *,
    output_dir: Path,
    signed: bool = False,
) -> Path:
    real_cert = bool(os.environ.get("TONEVYRA_SIGN_PFX") or os.environ.get("TONEVYRA_SIGN_THUMBPRINT"))
    signing_type = ("certificate" if real_cert else "self-signed-test") if signed else "none"
    # A self-signed signature does not satisfy Smart App Control; only a
    # reputable OV/EV certificate does. Keep the release gate honest.
    blocked = [] if (signed and real_cert) else ["BLOCKED_CODE_SIGNING_NOT_CONFIGURED"]
    manifest: dict[str, Any] = {
        "schema_version": "tonevyra.windows_installer.native.v1",
        "product": "Tonevyra AI",
        "version": version,
        "installer_backend": "inno_setup_native_files",
        "inno_script": str(ISS_PATH),
        "inno_compiler": str(iscc),
        "python": sys.version,
        "model_source": str(model_source),
        "installer_exe": str(setup_exe),
        "installer_sha256": _sha256(setup_exe),
        "installer_size_bytes": setup_exe.stat().st_size,
        "disk_slices": [
            {"path": str(path), "sha256": _sha256(path), "size_bytes": path.stat().st_size}
            for path in slices
        ],
        "all_in_one_orchestrator": True,
        "native_file_installation": True,
        "postgres_unattended_install": True,
        "database_bootstrap_automation": True,
        "post_install_doctor_required": True,
        "native_uninstaller": True,
        "uninstall_preserves_database": True,
        "code_signed": bool(signed),
        "code_signing_type": signing_type,
        "installer_signature_status": _signature_status(setup_exe),
        "blocked_reasons": blocked,
    }
    path = output_dir / f"TonevyraAI-Setup-{version}.manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


if __name__ == "__main__":
    raise SystemExit(main())
