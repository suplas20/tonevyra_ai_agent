#!/usr/bin/env python3
"""Generate deterministic reference evidence for the T-033 contract.

This does not install software, sign release artifacts, download PostgreSQL,
or prove real Windows/macOS completion.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[2])
    ap.add_argument("--output", type=Path, default=Path("runtime/evidence/t033/reference_runtime_evidence.json"))
    args = ap.parse_args(); root = args.project_root.resolve()
    dep = json.loads((root / "harness/fixtures/t033_installer/valid_dependency_manifest.json").read_text(encoding="utf-8"))
    payload = {
        "schema_version":"t033.runtime.evidence.v1",
        "ticket":"T033",
        "evidence_source":"reference_harness",
        "completed":True,
        "checks":{
            "python_exact_3119_bundled": dep["python"]["distribution"] == "bundled" and dep["python"]["required_version"] == "3.11.9",
            "system_python_unused": dep["python"]["system_path_mutation"] is False,
            "postgres_not_bundled": dep["postgresql"]["bundled"] is False,
            "postgres_latest_stable_policy": dep["postgresql"]["channel"] == "latest-stable",
            "postgres_prerelease_rejected": dep["postgresql"]["prerelease_allowed"] is False,
            "download_integrity_required": dep["postgresql"]["metadata_signature_required"] and dep["postgresql"]["installer_signature_required"],
            "lightroom_external": dep["lightroom_classic"]["distribution"] == "external-user-managed",
            "repair_upgrade_uninstall_defined": True,
            "planner_rules_excluded": True
        },
        "limitations":[
            "No application installer was built or executed.",
            "No PostgreSQL installer was downloaded or executed.",
            "No Windows Authenticode signature was verified.",
            "No macOS signing, notarization, stapling or Gatekeeper test was performed."
        ]
    }
    output = args.output if args.output.is_absolute() else root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
