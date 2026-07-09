from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tonevyra_agent.packaging.common.dependency_manifest import load_dependency_manifest, manifest_checks, parse_dependency_manifest
from tonevyra_agent.packaging.common.errors import T033ErrorCode, T033ValidationError
from tonevyra_agent.packaging.common.integrity import scan_packaged_artifact
from tonevyra_agent.packaging.common.postgres_resolver import load_postgresql_resolution, parse_postgresql_resolution
from tonevyra_agent.packaging.common.redaction import redact_installer_text
from tonevyra_agent.packaging.common.runtime_evidence import build_runtime_evidence

FIXTURES = Path("harness/fixtures/t033_installer")
ALLOWED_POSTGRES_HOSTS = {"postgresql.org", "enterprisedb.com", "get.enterprisedb.com"}


def _fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_dependency_manifest_accepts_t033_distribution_boundary() -> None:
    manifest = load_dependency_manifest(FIXTURES / "valid_dependency_manifest.json")

    checks = manifest_checks(manifest)

    assert checks["python_exact_3119_bundled"] is True
    assert checks["system_python_unused"] is True
    assert checks["postgres_not_bundled"] is True
    assert checks["download_integrity_required"] is True
    assert checks["lightroom_external"] is True


def test_dependency_manifest_rejects_system_or_floating_python() -> None:
    data = _fixture("invalid_python_latest_manifest.json")
    data.pop("expected_validation")

    with pytest.raises(T033ValidationError) as exc:
        parse_dependency_manifest(data)

    assert exc.value.code == T033ErrorCode.PYTHON


def test_dependency_manifest_rejects_bundled_postgresql_installer() -> None:
    data = _fixture("invalid_bundled_postgresql_manifest.json")
    data.pop("expected_validation")

    with pytest.raises(T033ValidationError) as exc:
        parse_dependency_manifest(data)

    assert exc.value.code == T033ErrorCode.PG_METADATA


def test_postgresql_resolution_accepts_signed_stable_official_windows_fixture() -> None:
    resolution = load_postgresql_resolution(
        FIXTURES / "valid_postgresql_resolution_windows.json",
        allowed_hosts=ALLOWED_POSTGRES_HOSTS,
    )

    assert resolution.platform == "windows-x64"
    assert resolution.release_status == "stable"
    assert resolution.resolved_host == "get.enterprisedb.com"


def test_postgresql_resolution_rejects_prerelease_and_unsigned_metadata() -> None:
    data = _fixture("invalid_postgresql_prerelease.json")
    data.pop("expected_validation")

    with pytest.raises(T033ValidationError) as exc:
        parse_postgresql_resolution(data, allowed_hosts=ALLOWED_POSTGRES_HOSTS)

    assert exc.value.code == T033ErrorCode.PG_METADATA


def test_postgresql_resolution_rejects_non_allowlisted_host() -> None:
    data = _fixture("valid_postgresql_resolution_windows.json")
    data["url"] = "https://downloads.example.invalid/postgresql-99.4-windows-x64.exe"

    with pytest.raises(T033ValidationError) as exc:
        parse_postgresql_resolution(data, allowed_hosts=ALLOWED_POSTGRES_HOSTS)

    assert exc.value.code == T033ErrorCode.PG_DOWNLOAD


def test_runtime_evidence_is_derived_from_validated_manifest() -> None:
    manifest = load_dependency_manifest(FIXTURES / "valid_dependency_manifest.json")

    evidence = build_runtime_evidence(
        manifest,
        evidence_source="implementation",
        repair_upgrade_uninstall_defined=True,
        planner_rules_excluded=True,
    )

    assert evidence["schema_version"] == "t033.runtime.evidence.v1"
    assert evidence["completed"] is True
    assert evidence["checks"]["postgres_not_bundled"] is True


def test_artifact_scan_flags_forbidden_payload_content(tmp_path: Path) -> None:
    clean = tmp_path / "clean"
    clean.mkdir()
    (clean / "TonevyraAI.exe").write_text("app", encoding="utf-8")
    clean_scan = scan_packaged_artifact(clean, python_version="3.11.9", license_inventory_complete=True)

    dirty = tmp_path / "dirty"
    dirty.mkdir()
    (dirty / "postgresql-99.4-windows-x64.exe").write_text("forbidden", encoding="utf-8")
    (dirty / "planner_rules.json").write_text("forbidden", encoding="utf-8")
    (dirty / "requires-system-python.txt").write_text("forbidden", encoding="utf-8")
    dirty_scan = scan_packaged_artifact(dirty, python_version="3.11.9", license_inventory_complete=True)

    assert clean_scan["postgres_installer_bundled"] is False
    assert clean_scan["planner_rules_bundled"] is False
    assert clean_scan["system_python_dependency"] is False
    assert dirty_scan["postgres_installer_bundled"] is True
    assert dirty_scan["planner_rules_bundled"] is True
    assert dirty_scan["system_python_dependency"] is True


def test_installer_redaction_removes_secrets_and_home_paths() -> None:
    raw = (
        "password=secret Authorization: Bearer abc.def "
        "C:\\Users\\alice\\AppData\\Local\\TonevyraAI /Users/bob/Pictures/photo.CR3"
    )

    redacted = redact_installer_text(raw)

    assert "secret" not in redacted
    assert "abc.def" not in redacted
    assert "alice" not in redacted
    assert "bob" not in redacted


def test_t033_implementation_runtime_script_generates_policy_evidence(tmp_path: Path) -> None:
    output = tmp_path / "implementation_runtime_evidence.json"
    script = Path("harness/scripts/run_t033_implementation_runtime.py")

    result = subprocess.run(
        [sys.executable, str(script), "--project-root", ".", "--output", str(output)],
        cwd=Path("."),
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    evidence = json.loads(output.read_text(encoding="utf-8"))
    assert evidence["schema_version"] == "t033.runtime.evidence.v1"
    assert evidence["evidence_source"] == "implementation"
    assert evidence["completed"] is True
    assert evidence["checks"]["postgres_windows_resolution_valid"] is True
    assert evidence["checks"]["postgres_macos_resolution_valid"] is True
