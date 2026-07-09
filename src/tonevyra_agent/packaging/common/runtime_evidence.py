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
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    checks = manifest_checks(manifest)
    checks["repair_upgrade_uninstall_defined"] = repair_upgrade_uninstall_defined
    checks["planner_rules_excluded"] = planner_rules_excluded
    return {
        "schema_version": "t033.runtime.evidence.v1",
        "ticket": "T033",
        "evidence_source": evidence_source,
        "completed": all(checks.values()),
        "checks": checks,
        "limitations": limitations or [],
    }

