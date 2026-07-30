from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tonevyra_agent.packaging.common.dependency_manifest import load_dependency_manifest, manifest_checks, parse_dependency_manifest
from tonevyra_agent.packaging.common.errors import T033ErrorCode, T033ValidationError
from tonevyra_agent.packaging.common.evidence import (
    all_in_one_runtime_checks,
    load_all_in_one_install_evidence,
    load_database_bootstrap_evidence,
    parse_all_in_one_install_evidence,
)
from tonevyra_agent.packaging.common.integrity import scan_packaged_artifact
from tonevyra_agent.packaging.common.postgres_resolver import load_postgresql_resolution, parse_postgresql_resolution
from tonevyra_agent.packaging.common.redaction import redact_installer_text
from tonevyra_agent.packaging.common.runtime_evidence import build_runtime_evidence
from tonevyra_agent.packaging.common.db_bootstrap import _database_connection_is_localhost

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
        one_click_all_in_one_defined=True,
        postgres_unattended_install_defined=True,
        database_bootstrap_automatic_defined=True,
        schema_migration_and_verification_defined=True,
        post_install_doctor_required=True,
    )

    assert evidence["schema_version"] == "t033.runtime.evidence.v1"
    assert evidence["completed"] is True
    assert evidence["checks"]["postgres_not_bundled"] is True
    assert evidence["checks"]["one_click_all_in_one_defined"] is True


def test_all_in_one_and_database_bootstrap_evidence_accept_valid_fixtures() -> None:
    all_in_one = load_all_in_one_install_evidence(FIXTURES / "valid_all_in_one_install_evidence.json")
    database = load_database_bootstrap_evidence(FIXTURES / "valid_database_bootstrap_evidence.json")

    checks = all_in_one_runtime_checks(all_in_one, database)

    assert all_in_one.manual_prerequisite_steps == 0
    assert all_in_one.manual_database_steps == 0
    assert database.runtime_role_non_superuser is True
    assert "alembic_version" in database.required_objects
    assert all(checks.values())


def test_all_in_one_evidence_rejects_manual_database_steps() -> None:
    data = _fixture("invalid_manual_database_install_evidence.json")

    with pytest.raises(T033ValidationError) as exc:
        parse_all_in_one_install_evidence(data)

    assert exc.value.code == T033ErrorCode.PREFLIGHT
    assert exc.value.field == "manual_database_steps"


def test_database_localhost_detection_accepts_ipv4_mapped_loopback() -> None:
    url = "postgresql+psycopg://tonevyra_app:secret@127.0.0.1:55432/tonevyra_agent"

    assert _database_connection_is_localhost(url, "::ffff:127.0.0.1") is True
    assert _database_connection_is_localhost(url, "127.0.0.1") is True
    assert _database_connection_is_localhost(url, "::1") is True
    assert _database_connection_is_localhost(url, None) is True
    # A loopback URL host is a localhost connection even when the platform reports
    # a non-loopback inet_server_addr() (observed on Windows PostgreSQL).
    assert _database_connection_is_localhost(url, "192.168.0.10") is True
    # A non-loopback URL host is not a localhost connection.
    remote = "postgresql+psycopg://tonevyra_app:secret@db.example.com:5432/tonevyra_agent"
    assert _database_connection_is_localhost(remote, "127.0.0.1") is False


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
    assert evidence["checks"]["one_click_all_in_one_defined"] is True
    assert evidence["checks"]["database_bootstrap_automatic_defined"] is True


def test_t033_windows_distribution_script_creates_dist_layout(tmp_path: Path) -> None:
    root = tmp_path / "project"
    source_dir = root / "runtime" / "windows_installer"
    source_dir.mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "tonevyra-agent"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    source_installer = source_dir / "TonevyraAI-Setup-0.1.0.exe"
    source_installer.write_bytes(b"installer")
    source_manifest = source_dir / "TonevyraAI-Setup-0.1.0.manifest.json"
    source_manifest.write_text(
        json.dumps(
            {
                "schema_version": "tonevyra.windows_installer.v1",
                "version": "0.1.0",
                "python": "3.11.9 test",
                "code_signed": False,
            }
        ),
        encoding="utf-8",
    )
    output_dir = root / "dist" / "windows"
    artifact_scan = root / "runtime" / "evidence" / "t033" / "windows_artifact_scan.json"
    script = Path("harness/scripts/build_t033_windows_distribution.py").resolve()

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--project-root",
            str(root),
            "--output-dir",
            str(output_dir),
            "--artifact-scan-output",
            str(artifact_scan),
        ],
        cwd=Path("."),
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    installer = output_dir / "TonevyraAI-Setup-0.1.0-windows-x64.exe"
    manifest = output_dir / "TonevyraAI-Setup-0.1.0-windows-x64.manifest.json"
    assert installer.is_file()
    assert (output_dir / "TonevyraAI-Setup-0.1.0-windows-x64.exe.sha256").is_file()
    assert (output_dir / "third-party-notices" / "README.txt").is_file()
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["release_ready"] is False
    assert "WINDOWS_AUTHENTICODE_SIGNATURE_MISSING" in payload["release_blockers"]
    assert "SOURCE_INSTALLER_NOT_ALL_IN_ONE" in payload["release_blockers"]
    assert "ALL_IN_ONE_INSTALL_EVIDENCE_MISSING" in payload["release_blockers"]
    assert "DATABASE_BOOTSTRAP_EVIDENCE_MISSING" in payload["release_blockers"]
    assert payload["postgresql"]["installer_bundled"] is False
    scan = json.loads(artifact_scan.read_text(encoding="utf-8"))
    assert scan["schema_version"] == "t033.artifact_scan.v1"


def test_windows_installer_persists_failure_logs_next_to_setup_source() -> None:
    installer_builder = Path("harness/scripts/build_tonevyra_windows_installer.py").read_text(encoding="utf-8")
    inno_builder = Path("harness/scripts/build_tonevyra_windows_inno_installer.py").read_text(encoding="utf-8")
    native_provision = Path("installer/windows/Invoke-TonevyraProvision.ps1").read_text(encoding="utf-8")
    native_builder = Path("harness/scripts/build_tonevyra_windows_native_installer.py").read_text(encoding="utf-8")
    native_iss = Path("installer/windows/TonevyraAI.iss").read_text(encoding="utf-8")

    for builder in (installer_builder, inno_builder, native_builder):
        assert r"D:\Tonevyra_install" in builder
        assert "TONEVYRA_WINDOWS_INSTALLER_OUTPUT_DIR" in builder
        assert '"--output-dir"' in builder
    assert '#define OutputDir "D:\\Tonevyra_install"' in native_iss

    assert "[string]$InstallerLogDir" in installer_builder
    assert "TonevyraAI-install-" in installer_builder
    assert "$InstallStatus" in installer_builder
    assert "Write-TonevyraProgress" in installer_builder
    assert "Invoke-TonevyraTimedProcess" in installer_builder
    assert "Test-TonevyraPostgresAdminPassword" in installer_builder
    assert "POSTGRES_ADMIN_VERIFYING" in installer_builder
    assert "postgres admin password verification failed" in installer_builder
    assert "Protect-TonevyraTempSecretFile" in installer_builder
    assert "Remove-TonevyraTempFile" in installer_builder
    assert "WindowsIdentity]::GetCurrent().User" in installer_builder
    assert 'SecurityIdentifier "S-1-5-32-544"' in installer_builder
    assert 'SecurityIdentifier "S-1-5-18"' in installer_builder
    assert "Could not remove temporary installer file" in installer_builder
    assert "Protect-TempSecretFile" in native_provision
    assert "Test-PostgresAdminPassword" in native_provision
    assert "POSTGRES_ADMIN_VERIFYING" in native_provision
    assert "postgres admin password verification failed" in native_provision
    assert "Remove-TempFile" in native_provision
    assert "WindowsIdentity]::GetCurrent().User" in native_provision
    assert 'SecurityIdentifier "S-1-5-32-544"' in native_provision
    assert 'SecurityIdentifier "S-1-5-18"' in native_provision
    assert "PostgresInstallTimeoutSeconds" in installer_builder
    assert "-TimeoutSec $PostgresDownloadTimeoutSeconds" in installer_builder
    assert "& $psql -w" in installer_builder
    assert "PGCONNECT_TIMEOUT" in installer_builder
    assert "Existing TonevyraPostgreSQL service was found" in installer_builder
    assert '"PAYLOAD_EXTRACTING" "Extracting Tonevyra AI application payload."' in installer_builder
    assert '"POSTGRES_INSTALLING" "Running PostgreSQL unattended installer."' in installer_builder
    assert '"POST_INSTALL_DOCTOR" "Running Tonevyra AI post-install doctor."' in installer_builder
    assert "-error.txt" in installer_builder
    assert "Set-Content -LiteralPath $InstallErrorLog" in installer_builder
    assert 'error_log = $InstallErrorLog' in installer_builder
    assert "[string]$InstallerResultPath" in installer_builder
    assert '$PinnedPostgresVersion = "18.4-2"' in installer_builder
    assert "postgresql-18.4-2-windows-x64.exe" in installer_builder
    assert "0698d1a6083da490e5a57149257f5d9220d8c34109ed11b38aa592d320bf5385" in installer_builder
    assert 'resolution_source = "installer-pinned-winget-manifest"' in installer_builder
    assert '"POSTGRES_METADATA_RESOLVED" "pinned"' in installer_builder
    assert "Write-TonevyraInstallerResult $errorText" in installer_builder
    assert 'Write-TonevyraInstallerResult "SUCCESS"' in installer_builder
    assert 'Copy-Item -Path (Join-Path $AppSource "*")' in installer_builder
    assert "$script:InstallCompleted = $true" in installer_builder
    assert 'Write-TonevyraInstallReceipt "APP_PAYLOAD_INSTALLED" "ok"' in installer_builder
    assert installer_builder.index('"APP_PAYLOAD_INSTALLED"') < installer_builder.index(
        "        Install-TonevyraPostgreSQLUnattended"
    )
    assert 'Start-Process -FilePath $InstalledExe -ArgumentList @("tray")' in installer_builder
    assert 'Write-TonevyraInstallReceipt "AGENT_STARTING" "ok"' in installer_builder
    assert "procedure CurStepChanged(CurStep: TSetupStep);" in inno_builder
    assert "--rebuild-stage" in inno_builder
    assert "_require_fresh_stage" in inno_builder
    assert "_require_install_script_contract" in inno_builder
    assert "installer stage is stale" in inno_builder
    assert "installer_stage_validated" in inno_builder
    assert "powershell_install_window_visible" in inno_builder
    assert "installation is running. On older PCs this can take 20-40 minutes" in inno_builder
    assert "SW_SHOWNORMAL" in inno_builder
    assert "SW_HIDE" not in inno_builder
    assert "CmdPath := ExpandConstant" not in inno_builder
    assert "ResultCode <> 0" in inno_builder
    assert "LoadStringsFromFile(ResultPath, ErrorLines)" in inno_builder
    assert "install-bootstrap.log" in inno_builder
    assert "LoadStringsFromFile(BootstrapLogPath, ErrorLines)" in inno_builder
    assert "TonevyraAI-install-bootstrap-error.txt" in inno_builder
    assert "SaveStringToFile(SourceFallbackLogPath, ErrorDetails, False)" in inno_builder
    assert r"{{commonappdata}}\\TonevyraAI\\install-receipts" in inno_builder
    assert "RaiseException(" in inno_builder
    assert "-InstallerResultPath" in inno_builder
    assert "[Run]" not in inno_builder
