#!/usr/bin/env python3
"""Generate implementation policy evidence for the T-033 installer layer.

This script exercises the local T-033 validation modules. It does not install
software, sign artifacts, notarize packages, or prove live platform completion.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _add_src_to_path(root: Path) -> None:
    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _scenario_ids(path: Path) -> set[str]:
    payload = _load_json(path)
    return {str(item.get("id")) for item in payload.get("scenarios", []) if isinstance(item, dict)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[2])
    ap.add_argument("--output", type=Path, default=Path("runtime/evidence/t033/implementation_runtime_evidence.json"))
    ap.add_argument("--dependency-manifest", type=Path, default=Path("harness/fixtures/t033_installer/valid_dependency_manifest.json"))
    args = ap.parse_args()
    root = args.project_root.resolve()
    _add_src_to_path(root)

    from tonevyra_agent.packaging.common.dependency_manifest import load_dependency_manifest
    from tonevyra_agent.packaging.common.evidence import (
        all_in_one_runtime_checks,
        load_all_in_one_install_evidence,
        load_database_bootstrap_evidence,
    )
    from tonevyra_agent.packaging.common.postgres_resolver import load_postgresql_resolution
    from tonevyra_agent.packaging.common.runtime_evidence import build_runtime_evidence

    manifest_path = args.dependency_manifest if args.dependency_manifest.is_absolute() else root / args.dependency_manifest
    manifest = load_dependency_manifest(manifest_path)
    allowed_hosts = {"postgresql.org", "enterprisedb.com", "get.enterprisedb.com"}
    fixtures = root / "harness/fixtures/t033_installer"
    windows_resolution = load_postgresql_resolution(fixtures / "valid_postgresql_resolution_windows.json", allowed_hosts=allowed_hosts)
    macos_resolution = load_postgresql_resolution(fixtures / "valid_postgresql_resolution_macos.json", allowed_hosts=allowed_hosts)
    all_in_one = load_all_in_one_install_evidence(fixtures / "valid_all_in_one_install_evidence.json")
    database = load_database_bootstrap_evidence(fixtures / "valid_database_bootstrap_evidence.json")
    all_in_one_checks = all_in_one_runtime_checks(all_in_one, database)
    scenarios = _scenario_ids(fixtures / "install_scenarios.json")
    lifecycle_scenarios = {
        "windows_existing_user_postgres",
        "offline_postgres",
        "hash_mismatch",
        "uninstall_default",
    }
    planner_rule_paths = [
        root / "src/tonevyra_agent/planner_rules",
        root / "src/tonevyra_agent/planner_service/rules",
    ]

    evidence = build_runtime_evidence(
        manifest,
        evidence_source="implementation",
        repair_upgrade_uninstall_defined=lifecycle_scenarios.issubset(scenarios),
        planner_rules_excluded=not any(path.exists() for path in planner_rule_paths),
        one_click_all_in_one_defined=all_in_one_checks["one_click_all_in_one_defined"],
        postgres_unattended_install_defined=all_in_one_checks["postgres_unattended_install_defined"],
        database_bootstrap_automatic_defined=all_in_one_checks["database_bootstrap_automatic_defined"],
        schema_migration_and_verification_defined=all_in_one_checks["schema_migration_and_verification_defined"],
        post_install_doctor_required=all_in_one_checks["post_install_doctor_required"],
        limitations=[
            "Policy implementation evidence only; no software was installed.",
            "No Windows Authenticode signature was verified.",
            "No macOS signing, notarization, stapling or Gatekeeper test was performed.",
        ],
    )
    evidence["checks"]["postgres_windows_resolution_valid"] = windows_resolution.platform == "windows-x64"
    evidence["checks"]["postgres_macos_resolution_valid"] = macos_resolution.platform == "macos-arm64"
    evidence["completed"] = all(evidence["checks"].values())

    output = args.output if args.output.is_absolute() else root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
