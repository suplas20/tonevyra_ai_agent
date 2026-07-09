"""Dependency manifest validation for T-033 installers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tonevyra_agent.packaging.common.errors import T033ErrorCode, T033ValidationError

SCHEMA_VERSION = "t033.dependency_manifest.v1"
TICKET = "T-033"
PYTHON_VERSION = "3.11.9"

_ROOT_KEYS = {"schema_version", "ticket", "python", "postgresql", "lightroom_classic"}
_PYTHON_KEYS = {"distribution", "required_version", "version_policy", "system_path_mutation"}
_POSTGRES_KEYS = {
    "distribution",
    "bundled",
    "channel",
    "prerelease_allowed",
    "metadata_signature_required",
    "installer_signature_required",
}
_LIGHTROOM_KEYS = {"distribution", "required_for_base_install", "automatic_install"}


@dataclass(frozen=True)
class PythonManifest:
    distribution: str
    required_version: str
    version_policy: str
    system_path_mutation: bool


@dataclass(frozen=True)
class PostgreSQLManifest:
    distribution: str
    bundled: bool
    channel: str
    prerelease_allowed: bool
    metadata_signature_required: bool
    installer_signature_required: bool


@dataclass(frozen=True)
class LightroomManifest:
    distribution: str
    required_for_base_install: bool
    automatic_install: bool


@dataclass(frozen=True)
class DependencyManifest:
    schema_version: str
    ticket: str
    python: PythonManifest
    postgresql: PostgreSQLManifest
    lightroom_classic: LightroomManifest


def load_dependency_manifest(path: Path) -> DependencyManifest:
    return parse_dependency_manifest(json.loads(path.read_text(encoding="utf-8")))


def parse_dependency_manifest(data: dict[str, Any]) -> DependencyManifest:
    _require_keys(data, _ROOT_KEYS, "manifest", T033ErrorCode.PREFLIGHT)
    if data["schema_version"] != SCHEMA_VERSION:
        raise T033ValidationError(T033ErrorCode.PREFLIGHT, "dependency manifest schema mismatch", "schema_version")
    if data["ticket"] != TICKET:
        raise T033ValidationError(T033ErrorCode.PREFLIGHT, "dependency manifest ticket mismatch", "ticket")

    py_data = _object(data, "python")
    pg_data = _object(data, "postgresql")
    lr_data = _object(data, "lightroom_classic")
    _require_keys(py_data, _PYTHON_KEYS, "python", T033ErrorCode.PYTHON)
    _require_keys(pg_data, _POSTGRES_KEYS, "postgresql", T033ErrorCode.PG_METADATA)
    _require_keys(lr_data, _LIGHTROOM_KEYS, "lightroom_classic", T033ErrorCode.LIGHTROOM)

    python = PythonManifest(**py_data)
    postgresql = PostgreSQLManifest(**pg_data)
    lightroom = LightroomManifest(**lr_data)
    _validate_python(python)
    _validate_postgresql(postgresql)
    _validate_lightroom(lightroom)
    return DependencyManifest(
        schema_version=data["schema_version"],
        ticket=data["ticket"],
        python=python,
        postgresql=postgresql,
        lightroom_classic=lightroom,
    )


def manifest_checks(manifest: DependencyManifest) -> dict[str, bool]:
    """Return canonical runtime-evidence booleans from a validated manifest."""

    return {
        "python_exact_3119_bundled": manifest.python.distribution == "bundled"
        and manifest.python.required_version == PYTHON_VERSION
        and manifest.python.version_policy == "exact",
        "system_python_unused": manifest.python.system_path_mutation is False,
        "postgres_not_bundled": manifest.postgresql.distribution == "download" and manifest.postgresql.bundled is False,
        "postgres_latest_stable_policy": manifest.postgresql.channel == "latest-stable",
        "postgres_prerelease_rejected": manifest.postgresql.prerelease_allowed is False,
        "download_integrity_required": manifest.postgresql.metadata_signature_required is True
        and manifest.postgresql.installer_signature_required is True,
        "lightroom_external": manifest.lightroom_classic.distribution == "external-user-managed"
        and manifest.lightroom_classic.required_for_base_install is False
        and manifest.lightroom_classic.automatic_install is False,
    }


def _validate_python(python: PythonManifest) -> None:
    if python.distribution != "bundled":
        raise T033ValidationError(T033ErrorCode.PYTHON, "Python runtime must be bundled", "python.distribution")
    if python.required_version != PYTHON_VERSION or python.version_policy != "exact":
        raise T033ValidationError(T033ErrorCode.PYTHON, "Python runtime must be exact 3.11.9", "python.required_version")
    if python.system_path_mutation is not False:
        raise T033ValidationError(T033ErrorCode.PYTHON, "system Python and PATH mutation are forbidden", "python.system_path_mutation")


def _validate_postgresql(postgresql: PostgreSQLManifest) -> None:
    if postgresql.distribution != "download" or postgresql.bundled is not False:
        raise T033ValidationError(T033ErrorCode.PG_METADATA, "PostgreSQL installer must not be bundled", "postgresql.distribution")
    if postgresql.channel != "latest-stable" or postgresql.prerelease_allowed is not False:
        raise T033ValidationError(T033ErrorCode.PG_METADATA, "PostgreSQL must resolve latest stable GA only", "postgresql.channel")
    if postgresql.metadata_signature_required is not True or postgresql.installer_signature_required is not True:
        raise T033ValidationError(T033ErrorCode.PG_INTEGRITY, "PostgreSQL metadata and installer signatures are required", "postgresql")


def _validate_lightroom(lightroom: LightroomManifest) -> None:
    if lightroom.distribution != "external-user-managed":
        raise T033ValidationError(T033ErrorCode.LIGHTROOM, "Lightroom Classic must remain user-managed", "lightroom_classic.distribution")
    if lightroom.required_for_base_install is not False or lightroom.automatic_install is not False:
        raise T033ValidationError(T033ErrorCode.LIGHTROOM, "Lightroom must not block base install or be installed automatically", "lightroom_classic")


def _object(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise T033ValidationError(T033ErrorCode.PREFLIGHT, "manifest field must be an object", key)
    return value


def _require_keys(data: dict[str, Any], keys: set[str], field: str, code: T033ErrorCode) -> None:
    present = set(data)
    missing = sorted(keys - present)
    extra = sorted(present - keys)
    if missing:
        raise T033ValidationError(code, "manifest is missing required field(s): " + ", ".join(missing), field)
    if extra:
        raise T033ValidationError(code, "manifest contains unknown field(s): " + ", ".join(extra), field)

