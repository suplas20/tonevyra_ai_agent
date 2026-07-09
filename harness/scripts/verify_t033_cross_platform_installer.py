#!/usr/bin/env python3
"""Static/reference/strict evidence verifier for T-033."""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path
from typing import Any

TICKET = "T033"
EXPECTED_SKILLS = 58
REQUIRED_SKILLS = {
    "cross-platform-installer-packaging",
    "dependency-detection-compatibility",
    "bundled-runtime-distribution",
    "postgresql-bootstrap-installation",
    "installer-download-integrity",
    "platform-signing-notarization",
    "installer-upgrade-repair-uninstall",
}
REQUIRED_FILES = [
    ".docs/t033/T-033_Cross_Platform_Installer_Packaging_Work_Order.md",
    ".docs/t033/T-033_Implementation_Specification.md",
    ".docs/t033/T-033_Dependency_Distribution_and_License_Policy.md",
    ".docs/t033/T-033_Windows_Installer_Guide.md",
    ".docs/t033/T-033_macOS_Installer_Guide.md",
    ".docs/t033/T-033_Live_Test_Checklist.md",
    ".docs/t033/T-033_Codex_Prompt.md",
    "harness/CONTRACT_T033_CROSS_PLATFORM_INSTALLER.md",
    "harness/HARNESS_ENV_T033_INSTALLER.example",
    "harness/T033_INSTALLER_UPDATE_MANIFEST.json",
    "harness/schemas/t033_dependency_manifest.schema.json",
    "harness/schemas/t033_runtime_evidence.schema.json",
    "harness/schemas/t033_windows_live_evidence.schema.json",
    "harness/schemas/t033_macos_live_evidence.schema.json",
    "harness/schemas/t033_artifact_scan.schema.json",
    "harness/schemas/t033_postgresql_resolution.schema.json",
    "harness/fixtures/t033_installer/valid_dependency_manifest.json",
    "harness/fixtures/t033_installer/valid_postgresql_resolution_windows.json",
    "harness/fixtures/t033_installer/valid_postgresql_resolution_macos.json",
    "harness/fixtures/t033_installer/invalid_python_latest_manifest.json",
    "harness/fixtures/t033_installer/invalid_bundled_postgresql_manifest.json",
    "harness/fixtures/t033_installer/invalid_postgresql_prerelease.json",
    "harness/fixtures/t033_installer/install_scenarios.json",
    "harness/scripts/run_t033_installer_reference.py",
    "harness/scripts/run_t033_windows_installer_probe.ps1",
    "harness/scripts/run_t033_macos_installer_probe.sh",
    "skills/T033_SKILL_INVENTORY.json",
]


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_dependency_manifest(data: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    py = data.get("python", {})
    pg = data.get("postgresql", {})
    lr = data.get("lightroom_classic", {})
    if data.get("schema_version") != "t033.dependency_manifest.v1" or data.get("ticket") != "T-033": failures.append("dependency manifest schema/ticket mismatch")
    if py.get("distribution") != "bundled": failures.append("python must be bundled")
    if py.get("required_version") != "3.11.9" or py.get("version_policy") != "exact": failures.append("python must be exact 3.11.9")
    if py.get("system_path_mutation") is not False: failures.append("system Python/PATH mutation forbidden")
    if pg.get("distribution") != "download" or pg.get("bundled") is not False: failures.append("PostgreSQL installer must not be bundled")
    if pg.get("channel") != "latest-stable" or pg.get("prerelease_allowed") is not False: failures.append("PostgreSQL must be latest stable with prerelease forbidden")
    if pg.get("metadata_signature_required") is not True or pg.get("installer_signature_required") is not True: failures.append("PostgreSQL metadata and installer signatures required")
    if lr.get("distribution") != "external-user-managed" or lr.get("automatic_install") is not False: failures.append("Lightroom must be external/user-managed")
    return failures


def validate_resolution(data: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if data.get("schema_version") != "t033.postgresql.resolution.v1": failures.append("PostgreSQL resolution schema mismatch")
    if data.get("channel") != "latest-stable" or data.get("release_status") != "stable" or data.get("prerelease") is not False: failures.append("PostgreSQL resolution is not stable GA")
    if data.get("metadata_signature_verified") is not True or data.get("installer_signature_required") is not True: failures.append("PostgreSQL signature requirements missing")
    if not re.fullmatch(r"[0-9]+\.[0-9]+(?:\.[0-9]+)?", str(data.get("version", ""))): failures.append("PostgreSQL version is not stable numeric semantic version")
    if not str(data.get("url", "")).startswith("https://"): failures.append("PostgreSQL URL must use HTTPS")
    if not re.fullmatch(r"[0-9a-f]{64}", str(data.get("sha256", ""))): failures.append("PostgreSQL SHA-256 invalid")
    return failures


def validate_static(root: Path) -> list[str]:
    failures: list[str] = []
    for rel in REQUIRED_FILES:
        if not (root / rel).is_file(): failures.append("missing:" + rel)
    skill_dirs = sorted(p.parent.name for p in (root / "skills").glob("*/SKILL.md"))
    if len(skill_dirs) < EXPECTED_SKILLS: failures.append(f"skill_count={len(skill_dirs)} expected_at_least={EXPECTED_SKILLS}")
    for skill in REQUIRED_SKILLS:
        if skill not in skill_dirs: failures.append("missing_skill:" + skill)
    inventory_path = root / "skills/T033_SKILL_INVENTORY.json"
    if inventory_path.is_file():
        inv = load(inventory_path)
        if inv.get("baseline_skill_count") != 51 or inv.get("added_skill_count") != 7 or inv.get("expected_total_skill_count") != 58: failures.append("T033 inventory counts mismatch")
        snapshot = set(inv.get("all_skills", []))
        if len(snapshot) != 58 or not snapshot.issubset(set(skill_dirs)): failures.append("T033 inventory snapshot mismatch")
    fixture = root / "harness/fixtures/t033_installer/valid_dependency_manifest.json"
    if fixture.is_file(): failures += validate_dependency_manifest(load(fixture))
    for name in ("valid_postgresql_resolution_windows.json", "valid_postgresql_resolution_macos.json"):
        path = root / "harness/fixtures/t033_installer" / name
        if path.is_file(): failures += validate_resolution(load(path))
    for name in ("invalid_python_latest_manifest.json", "invalid_bundled_postgresql_manifest.json"):
        path = root / "harness/fixtures/t033_installer" / name
        if path.is_file() and not validate_dependency_manifest(load(path)): failures.append(name + " unexpectedly valid")
    prerelease = root / "harness/fixtures/t033_installer/invalid_postgresql_prerelease.json"
    if prerelease.is_file() and not validate_resolution(load(prerelease)): failures.append("prerelease fixture unexpectedly valid")
    agents = (root / "AGENTS.md").read_text(encoding="utf-8")
    for needle in ("T-033 Cross-platform Installer Packaging Policy", "PostgreSQL installer must not be bundled", "58"):
        if needle not in agents: failures.append("AGENTS missing T033 rule:" + needle)
    claude = (root / "CLAUDE.md").read_text(encoding="utf-8")
    if "Required reading for T-033" not in claude: failures.append("CLAUDE missing T033 reading section")
    return failures


def validate_runtime(path: Path, strict: bool) -> list[str]:
    d = load(path); failures: list[str] = []
    if d.get("schema_version") != "t033.runtime.evidence.v1" or d.get("ticket") != TICKET: failures.append("runtime schema/ticket mismatch")
    if d.get("completed") is not True: failures.append("runtime not completed")
    checks = d.get("checks", {})
    required = ["python_exact_3119_bundled","system_python_unused","postgres_not_bundled","postgres_latest_stable_policy","postgres_prerelease_rejected","download_integrity_required","lightroom_external","repair_upgrade_uninstall_defined","planner_rules_excluded"]
    for key in required:
        if checks.get(key) is not True: failures.append("runtime check failed:" + key)
    if strict and d.get("evidence_source") != "implementation": failures.append("strict runtime evidence must be implementation")
    return failures


def validate_windows(path: Path) -> list[str]:
    d = load(path); failures: list[str] = []
    if d.get("schema_version") != "t033.windows.live.v1" or d.get("ticket") != TICKET or d.get("platform") != "windows" or d.get("architecture") != "x64": failures.append("Windows evidence identity mismatch")
    for key in ["installer_signature_valid","python_3119_bundled","postgres_installer_downloaded","postgres_installer_not_bundled","postgres_service_ok","database_ok","agent_ok","uninstall_data_preserved"]:
        if d.get(key) is not True: failures.append("Windows evidence field must be true:" + key)
    return failures


def validate_macos(path: Path) -> list[str]:
    d = load(path); failures: list[str] = []
    if d.get("schema_version") != "t033.macos.live.v1" or d.get("ticket") != TICKET or d.get("platform") != "macos" or d.get("architecture") != "arm64": failures.append("macOS evidence identity mismatch")
    for key in ["developer_id_application_valid","developer_id_installer_valid","notarization_accepted","staple_valid","gatekeeper_accepted","python_3119_bundled","postgres_installer_downloaded","postgres_installer_not_bundled","database_ok","agent_ok","uninstall_data_preserved"]:
        if d.get(key) is not True: failures.append("macOS evidence field must be true:" + key)
    return failures


def validate_artifact_scan(path: Path) -> list[str]:
    d = load(path); failures: list[str] = []
    if d.get("schema_version") != "t033.artifact_scan.v1" or d.get("ticket") != TICKET: failures.append("artifact scan identity mismatch")
    if not re.fullmatch(r"[0-9a-f]{64}", str(d.get("artifact_sha256", ""))): failures.append("artifact SHA-256 missing")
    expected = {"postgres_installer_bundled":False,"planner_rules_bundled":False,"system_python_dependency":False,"python_version":"3.11.9","license_inventory_complete":True}
    for key, value in expected.items():
        if d.get(key) != value: failures.append(f"artifact scan {key} mismatch")
    return failures


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[2])
    ap.add_argument("--runtime-evidence", type=Path)
    ap.add_argument("--windows-evidence", type=Path)
    ap.add_argument("--macos-evidence", type=Path)
    ap.add_argument("--artifact-scan", type=Path)
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args(); root = a.project_root.resolve()
    failures = validate_static(root)
    if a.runtime_evidence: failures += validate_runtime(a.runtime_evidence.resolve(), a.strict)
    elif a.strict: failures.append("strict requires --runtime-evidence")
    if a.windows_evidence: failures += validate_windows(a.windows_evidence.resolve())
    elif a.strict: failures.append("strict requires --windows-evidence")
    if a.macos_evidence: failures += validate_macos(a.macos_evidence.resolve())
    elif a.strict: failures.append("strict requires --macos-evidence")
    if a.artifact_scan: failures += validate_artifact_scan(a.artifact_scan.resolve())
    elif a.strict: failures.append("strict requires --artifact-scan")
    if failures:
        print("FAIL: T033"); [print("- " + f) for f in failures]; return 1
    print("PASS: T033 static contract, skills, schemas, and fixtures")
    if a.runtime_evidence: print("PASS: T033 runtime evidence")
    if a.windows_evidence: print("PASS: T033 Windows live evidence")
    if a.macos_evidence: print("PASS: T033 macOS live evidence")
    if a.artifact_scan: print("PASS: T033 final artifact scan")
    if a.strict: print("PASS: T033 strict completion gate")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
