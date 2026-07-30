"""Runtime evidence assembly for T-033 implementation checks."""

from __future__ import annotations

from typing import Any

from tonevyra_agent.packaging.common.dependency_manifest import DependencyManifest, manifest_checks


def build_runtime_evidence(
    manifest: DependencyManifest,
    *,
    evidence_source: str,
    repair_upgrade_uninstall_defined: bool,
    planner_rules_excluded: bool,
    one_click_all_in_one_defined: bool,
    postgres_unattended_install_defined: bool,
    database_bootstrap_automatic_defined: bool,
    schema_migration_and_verification_defined: bool,
    post_install_doctor_required: bool,
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    checks = manifest_checks(manifest)
    checks["repair_upgrade_uninstall_defined"] = repair_upgrade_uninstall_defined
    checks["planner_rules_excluded"] = planner_rules_excluded
    checks["one_click_all_in_one_defined"] = one_click_all_in_one_defined
    checks["postgres_unattended_install_defined"] = postgres_unattended_install_defined
    checks["database_bootstrap_automatic_defined"] = database_bootstrap_automatic_defined
    checks["schema_migration_and_verification_defined"] = schema_migration_and_verification_defined
    checks["post_install_doctor_required"] = post_install_doctor_required
    return {
        "schema_version": "t033.runtime.evidence.v1",
        "ticket": "T033",
        "evidence_source": evidence_source,
        "completed": all(checks.values()),
        "checks": checks,
        "limitations": limitations or [],
    }
