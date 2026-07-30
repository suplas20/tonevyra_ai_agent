#!/usr/bin/env python3
"""Create the T-033 Windows distribution folder from a built installer.

This promotes a previously built Windows installer into the canonical
dist/windows layout. It does not sign the installer or claim strict completion.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tomllib
from pathlib import Path
from typing import Any


def _add_src_to_path(root: Path) -> None:
    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))


def _project_version(root: Path) -> str:
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _python_version_from_manifest(manifest: dict[str, Any]) -> str:
    version_text = str(manifest.get("python", ""))
    if version_text.startswith("3.11.9"):
        return "3.11.9"
    return version_text.split(" ", 1)[0] if version_text else "unknown"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[2])
    ap.add_argument("--version")
    ap.add_argument("--source-installer", type=Path)
    ap.add_argument("--source-manifest", type=Path)
    ap.add_argument("--output-dir", type=Path, default=Path("dist/windows"))
    ap.add_argument("--artifact-scan-output", type=Path, default=Path("runtime/evidence/t033/windows_artifact_scan.json"))
    ap.add_argument("--all-in-one-evidence", type=Path)
    ap.add_argument("--database-evidence", type=Path)
    ap.add_argument("--require-signed", action="store_true")
    args = ap.parse_args()

    root = args.project_root.resolve()
    _add_src_to_path(root)

    from tonevyra_agent.packaging.common.evidence import (
        load_all_in_one_install_evidence,
        load_database_bootstrap_evidence,
    )
    from tonevyra_agent.packaging.common.integrity import scan_packaged_artifact, sha256_file

    version = args.version or _project_version(root)
    source_installer = args.source_installer or Path(f"runtime/windows_installer/TonevyraAI-Setup-{version}.exe")
    source_manifest = args.source_manifest or Path(f"runtime/windows_installer/TonevyraAI-Setup-{version}.manifest.json")
    source_installer = source_installer if source_installer.is_absolute() else root / source_installer
    source_manifest = source_manifest if source_manifest.is_absolute() else root / source_manifest
    output_dir = args.output_dir if args.output_dir.is_absolute() else root / args.output_dir
    artifact_scan_output = args.artifact_scan_output if args.artifact_scan_output.is_absolute() else root / args.artifact_scan_output
    all_in_one_evidence = args.all_in_one_evidence if args.all_in_one_evidence is None or args.all_in_one_evidence.is_absolute() else root / args.all_in_one_evidence
    database_evidence = args.database_evidence if args.database_evidence is None or args.database_evidence.is_absolute() else root / args.database_evidence

    if not source_installer.is_file():
        raise SystemExit(f"missing source installer: {source_installer}")
    if not source_manifest.is_file():
        raise SystemExit(f"missing source installer manifest: {source_manifest}")

    source_data = _load_json(source_manifest)
    code_signed = bool(source_data.get("code_signed"))
    if args.require_signed and not code_signed:
        raise SystemExit("source installer is not signed; cannot create signed release distribution")

    output_dir.mkdir(parents=True, exist_ok=True)
    notices_dir = output_dir / "third-party-notices"
    notices_dir.mkdir(parents=True, exist_ok=True)

    installer_name = f"TonevyraAI-Setup-{version}-windows-x64.exe"
    manifest_name = f"TonevyraAI-Setup-{version}-windows-x64.manifest.json"
    installer_out = output_dir / installer_name
    manifest_out = output_dir / manifest_name
    sha_out = output_dir / f"{installer_name}.sha256"

    shutil.copy2(source_installer, installer_out)
    sidecar_outputs: list[dict[str, Any]] = []
    for source_sidecar in _source_sidecars(source_installer, source_data):
        suffix = source_sidecar.name.removeprefix(source_installer.stem)
        sidecar_out = output_dir / f"{installer_out.stem}{suffix}"
        shutil.copy2(source_sidecar, sidecar_out)
        sidecar_outputs.append(
            {
                "file_name": sidecar_out.name,
                "sha256": sha256_file(sidecar_out),
                "size_bytes": sidecar_out.stat().st_size,
            }
        )
    installer_sha256 = sha256_file(installer_out)
    sha_lines = [f"{installer_sha256}  {installer_name}"]
    sha_lines.extend(f"{item['sha256']}  {item['file_name']}" for item in sidecar_outputs)
    sha_out.write_text("\n".join(sha_lines) + "\n", encoding="ascii")

    (notices_dir / "README.txt").write_text(
        "Tonevyra AI third-party notices placeholder for the T-033 Windows distribution.\n"
        "Release builds must replace this placeholder with the reviewed license inventory.\n",
        encoding="utf-8",
    )

    python_version = _python_version_from_manifest(source_data)
    artifact_scan = scan_packaged_artifact(
        output_dir,
        python_version=python_version,
        license_inventory_complete=False,
    )
    artifact_scan_output.parent.mkdir(parents=True, exist_ok=True)
    _write_json(artifact_scan_output, artifact_scan)

    release_blockers: list[str] = []
    if not code_signed:
        release_blockers.append("WINDOWS_AUTHENTICODE_SIGNATURE_MISSING")
    if not artifact_scan["license_inventory_complete"]:
        release_blockers.append("THIRD_PARTY_LICENSE_INVENTORY_PLACEHOLDER")
    if artifact_scan["postgres_installer_bundled"]:
        release_blockers.append("POSTGRESQL_INSTALLER_BUNDLED")
    if artifact_scan["planner_rules_bundled"]:
        release_blockers.append("PLANNER_RULES_BUNDLED")
    if artifact_scan["system_python_dependency"]:
        release_blockers.append("SYSTEM_PYTHON_DEPENDENCY_DETECTED")
    if python_version != "3.11.9":
        release_blockers.append("PYTHON_3119_NOT_PROVEN")
    source_all_in_one = (
        source_data.get("all_in_one_orchestrator") is True
        and source_data.get("postgres_unattended_install") is True
        and source_data.get("database_bootstrap_automation") is True
        and source_data.get("post_install_doctor_required") is True
    )
    if not source_all_in_one:
        release_blockers.append("SOURCE_INSTALLER_NOT_ALL_IN_ONE")
    all_in_one_ok = False
    database_bootstrap_ok = False
    if all_in_one_evidence is not None and all_in_one_evidence.is_file():
        load_all_in_one_install_evidence(all_in_one_evidence)
        all_in_one_ok = True
    if database_evidence is not None and database_evidence.is_file():
        load_database_bootstrap_evidence(database_evidence)
        database_bootstrap_ok = True
    if not all_in_one_ok:
        release_blockers.append("ALL_IN_ONE_INSTALL_EVIDENCE_MISSING")
    if not database_bootstrap_ok:
        release_blockers.append("DATABASE_BOOTSTRAP_EVIDENCE_MISSING")

    manifest = {
        "schema_version": "t033.windows.release_manifest.v1",
        "ticket": "T033",
        "product": "Tonevyra AI",
        "version": version,
        "platform": "windows",
        "architecture": "x64",
        "release_ready": not release_blockers,
        "release_blockers": release_blockers,
        "installer": {
            "file_name": installer_name,
            "sha256": installer_sha256,
            "size_bytes": installer_out.stat().st_size,
            "sidecars": sidecar_outputs,
            "code_signed": code_signed,
            "source_manifest": str(source_manifest),
        },
        "python": {
            "distribution": "bundled",
            "version": python_version,
            "system_python_dependency": artifact_scan["system_python_dependency"],
        },
        "postgresql": {
            "installer_bundled": artifact_scan["postgres_installer_bundled"],
            "distribution": "download",
            "channel": "latest-stable",
        },
        "all_in_one_install": {
            "evidence_path": str(all_in_one_evidence) if all_in_one_evidence else None,
            "verified": all_in_one_ok,
            "source_installer_orchestrator": source_all_in_one,
        },
        "database_bootstrap": {
            "evidence_path": str(database_evidence) if database_evidence else None,
            "verified": database_bootstrap_ok,
        },
        "planner_rules_bundled": artifact_scan["planner_rules_bundled"],
        "third_party_notices": str(notices_dir),
        "artifact_scan": str(artifact_scan_output),
        "source_installer_manifest": source_data,
    }
    _write_json(manifest_out, manifest)

    print(f"OK: dist={output_dir}")
    print(f"OK: installer={installer_out}")
    print(f"OK: sha256={sha_out}")
    print(f"OK: manifest={manifest_out}")
    print(f"OK: artifact_scan={artifact_scan_output}")
    if release_blockers:
        print("WARN: distribution created with release blockers: " + ", ".join(release_blockers))
    return 0


def _source_sidecars(source_installer: Path, source_data: dict[str, Any]) -> list[Path]:
    manifest_sidecars = source_data.get("installer_sidecars")
    paths: list[Path] = []
    if isinstance(manifest_sidecars, list):
        for item in manifest_sidecars:
            if isinstance(item, dict) and item.get("path"):
                paths.append(Path(str(item["path"])))
    if not paths:
        paths = sorted(source_installer.parent.glob(f"{source_installer.stem}-*.bin"))
    return [path for path in paths if path.is_file()]


if __name__ == "__main__":
    raise SystemExit(main())
