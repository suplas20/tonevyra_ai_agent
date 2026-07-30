"""T-033 all-in-one installer and database bootstrap evidence validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tonevyra_agent.packaging.common.errors import T033ErrorCode, T033ValidationError

ALL_IN_ONE_SCHEMA_VERSION = "t033.all_in_one.install.v1"
DATABASE_BOOTSTRAP_SCHEMA_VERSION = "t033.database.bootstrap.v1"
TICKET = "T033"
VALID_PLATFORMS = {"windows", "macos"}
REQUIRED_DATABASE_OBJECTS = {
    "image_tasks",
    "task_artifacts",
    "task_events",
    "stage_results",
    "quality_results",
    "feedback_records",
    "learning_samples",
    "v_task_summary",
    "alembic_version",
}


@dataclass(frozen=True)
class AllInOneInstallEvidence:
    schema_version: str
    ticket: str
    platform: str
    single_install_session: bool
    manual_prerequisite_steps: int
    manual_database_steps: int
    os_elevation_only: bool
    postgres_unattended_install: bool
    database_bootstrap_automatic: bool
    startup_registration_automatic: bool
    post_install_doctor_passed: bool
    completed: bool


@dataclass(frozen=True)
class DatabaseBootstrapEvidence:
    schema_version: str
    ticket: str
    postgres_service_ready: bool
    role_exists: bool
    database_exists: bool
    runtime_role_non_superuser: bool
    localhost_only: bool
    alembic_head_matches: bool
    required_objects: list[str]
    read_write_smoke_rolled_back: bool
    credential_store_verified: bool
    completed: bool


def load_all_in_one_install_evidence(path: Path) -> AllInOneInstallEvidence:
    return parse_all_in_one_install_evidence(json.loads(path.read_text(encoding="utf-8")))


def load_database_bootstrap_evidence(path: Path) -> DatabaseBootstrapEvidence:
    return parse_database_bootstrap_evidence(json.loads(path.read_text(encoding="utf-8")))


def parse_all_in_one_install_evidence(data: dict[str, Any]) -> AllInOneInstallEvidence:
    required = {
        "schema_version",
        "ticket",
        "platform",
        "single_install_session",
        "manual_prerequisite_steps",
        "manual_database_steps",
        "os_elevation_only",
        "postgres_unattended_install",
        "database_bootstrap_automatic",
        "startup_registration_automatic",
        "post_install_doctor_passed",
        "completed",
    }
    _require_present(data, required, "all_in_one")
    if data["schema_version"] != ALL_IN_ONE_SCHEMA_VERSION or data["ticket"] != TICKET:
        raise T033ValidationError(T033ErrorCode.PREFLIGHT, "all-in-one evidence identity mismatch", "schema_version")
    if data["platform"] not in VALID_PLATFORMS:
        raise T033ValidationError(T033ErrorCode.PREFLIGHT, "unsupported all-in-one platform", "platform")
    expected = {
        "single_install_session": True,
        "manual_prerequisite_steps": 0,
        "manual_database_steps": 0,
        "os_elevation_only": True,
        "postgres_unattended_install": True,
        "database_bootstrap_automatic": True,
        "startup_registration_automatic": True,
        "post_install_doctor_passed": True,
        "completed": True,
    }
    for key, value in expected.items():
        if data[key] != value:
            raise T033ValidationError(T033ErrorCode.PREFLIGHT, "all-in-one completion gate failed", key)
    return AllInOneInstallEvidence(**{key: data[key] for key in required})


def parse_database_bootstrap_evidence(data: dict[str, Any]) -> DatabaseBootstrapEvidence:
    required = {
        "schema_version",
        "ticket",
        "postgres_service_ready",
        "role_exists",
        "database_exists",
        "runtime_role_non_superuser",
        "localhost_only",
        "alembic_head_matches",
        "required_objects",
        "read_write_smoke_rolled_back",
        "credential_store_verified",
        "completed",
    }
    _require_present(data, required, "database")
    if data["schema_version"] != DATABASE_BOOTSTRAP_SCHEMA_VERSION or data["ticket"] != TICKET:
        raise T033ValidationError(T033ErrorCode.DB_SCHEMA, "database bootstrap evidence identity mismatch", "schema_version")
    expected_true = {
        "postgres_service_ready": T033ErrorCode.DB_READY,
        "role_exists": T033ErrorCode.DB_ROLE,
        "database_exists": T033ErrorCode.DB_CREATE,
        "runtime_role_non_superuser": T033ErrorCode.DB_ROLE,
        "localhost_only": T033ErrorCode.DB_READY,
        "alembic_head_matches": T033ErrorCode.DB_MIGRATION,
        "read_write_smoke_rolled_back": T033ErrorCode.DB_SMOKE,
        "credential_store_verified": T033ErrorCode.DB_CREDENTIAL,
        "completed": T033ErrorCode.DB_BOOTSTRAP,
    }
    for key, code in expected_true.items():
        if data[key] is not True:
            raise T033ValidationError(code, "database bootstrap completion gate failed", key)
    objects = data["required_objects"]
    if not isinstance(objects, list) or any(not isinstance(item, str) for item in objects):
        raise T033ValidationError(T033ErrorCode.DB_SCHEMA, "required_objects must be a string list", "required_objects")
    missing = REQUIRED_DATABASE_OBJECTS - set(objects)
    if missing:
        raise T033ValidationError(T033ErrorCode.DB_SCHEMA, "database bootstrap is missing required objects: " + ", ".join(sorted(missing)), "required_objects")
    return DatabaseBootstrapEvidence(**{key: data[key] for key in required})


def all_in_one_runtime_checks(
    all_in_one: AllInOneInstallEvidence,
    database: DatabaseBootstrapEvidence,
) -> dict[str, bool]:
    return {
        "one_click_all_in_one_defined": all_in_one.single_install_session
        and all_in_one.manual_prerequisite_steps == 0
        and all_in_one.manual_database_steps == 0,
        "postgres_unattended_install_defined": all_in_one.postgres_unattended_install,
        "database_bootstrap_automatic_defined": all_in_one.database_bootstrap_automatic and database.completed,
        "schema_migration_and_verification_defined": database.alembic_head_matches
        and REQUIRED_DATABASE_OBJECTS.issubset(set(database.required_objects)),
        "post_install_doctor_required": all_in_one.post_install_doctor_passed,
    }


def _require_present(data: dict[str, Any], required: set[str], field: str) -> None:
    missing = sorted(required - set(data))
    if missing:
        raise T033ValidationError(T033ErrorCode.PREFLIGHT, "evidence is missing required field(s): " + ", ".join(missing), field)
