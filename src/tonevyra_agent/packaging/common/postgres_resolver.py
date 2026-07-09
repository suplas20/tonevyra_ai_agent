"""PostgreSQL stable resolution validation for T-033."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tonevyra_agent.packaging.common.errors import T033ErrorCode, T033ValidationError
from tonevyra_agent.packaging.common.integrity import require_allowed_host

SCHEMA_VERSION = "t033.postgresql.resolution.v1"
CHANNEL = "latest-stable"
VALID_PLATFORMS = {"windows-x64", "macos-arm64"}
PRERELEASE_PATTERN = re.compile(r"(alpha|beta|rc|snapshot|nightly|preview)", re.IGNORECASE)
VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+(?:\.[0-9]+)?$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

_ROOT_KEYS = {
    "schema_version",
    "channel",
    "release_status",
    "version",
    "platform",
    "url",
    "sha256",
    "metadata_signature_verified",
    "installer_signature_required",
    "prerelease",
}


@dataclass(frozen=True)
class PostgreSQLResolution:
    schema_version: str
    channel: str
    release_status: str
    version: str
    platform: str
    url: str
    sha256: str
    metadata_signature_verified: bool
    installer_signature_required: bool
    prerelease: bool
    resolved_host: str


def load_postgresql_resolution(path: Path, *, allowed_hosts: set[str]) -> PostgreSQLResolution:
    return parse_postgresql_resolution(json.loads(path.read_text(encoding="utf-8")), allowed_hosts=allowed_hosts)


def parse_postgresql_resolution(data: dict[str, Any], *, allowed_hosts: set[str]) -> PostgreSQLResolution:
    _require_keys(data)
    if data["schema_version"] != SCHEMA_VERSION:
        raise T033ValidationError(T033ErrorCode.PG_METADATA, "PostgreSQL resolution schema mismatch", "schema_version")
    if data["channel"] != CHANNEL:
        raise T033ValidationError(T033ErrorCode.PG_METADATA, "PostgreSQL channel must be latest-stable", "channel")
    if data["release_status"] != "stable" or data["prerelease"] is not False:
        raise T033ValidationError(T033ErrorCode.PG_METADATA, "PostgreSQL prerelease artifacts are forbidden", "release_status")
    version = str(data["version"])
    if not VERSION_PATTERN.fullmatch(version) or PRERELEASE_PATTERN.search(version):
        raise T033ValidationError(T033ErrorCode.PG_METADATA, "PostgreSQL version must be stable numeric semantic version", "version")
    platform = str(data["platform"])
    if platform not in VALID_PLATFORMS:
        raise T033ValidationError(T033ErrorCode.PG_METADATA, "unsupported PostgreSQL platform", "platform")
    url = str(data["url"])
    if PRERELEASE_PATTERN.search(url):
        raise T033ValidationError(T033ErrorCode.PG_METADATA, "PostgreSQL prerelease URL is forbidden", "url")
    host = require_allowed_host(url, allowed_hosts)
    sha256 = str(data["sha256"])
    if not SHA256_PATTERN.fullmatch(sha256):
        raise T033ValidationError(T033ErrorCode.PG_INTEGRITY, "PostgreSQL SHA-256 is invalid", "sha256")
    if data["metadata_signature_verified"] is not True:
        raise T033ValidationError(T033ErrorCode.PG_METADATA, "signed metadata verification is required", "metadata_signature_verified")
    if data["installer_signature_required"] is not True:
        raise T033ValidationError(T033ErrorCode.PG_INTEGRITY, "installer signature verification is required", "installer_signature_required")
    return PostgreSQLResolution(
        schema_version=data["schema_version"],
        channel=data["channel"],
        release_status=data["release_status"],
        version=version,
        platform=platform,
        url=url,
        sha256=sha256,
        metadata_signature_verified=data["metadata_signature_verified"],
        installer_signature_required=data["installer_signature_required"],
        prerelease=data["prerelease"],
        resolved_host=host,
    )


def _require_keys(data: dict[str, Any]) -> None:
    present = set(data)
    missing = sorted(_ROOT_KEYS - present)
    extra = sorted(present - _ROOT_KEYS)
    if missing:
        raise T033ValidationError(T033ErrorCode.PG_METADATA, "resolution is missing required field(s): " + ", ".join(missing), "resolution")
    if extra:
        raise T033ValidationError(T033ErrorCode.PG_METADATA, "resolution contains unknown field(s): " + ", ".join(extra), "resolution")

