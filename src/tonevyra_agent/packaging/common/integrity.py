"""Integrity helpers shared by T-033 installer code."""

from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import urlparse

from tonevyra_agent.packaging.common.errors import T033ErrorCode, T033ValidationError

POSTGRES_INSTALLER_SUFFIXES = {
    ".exe",
    ".msi",
    ".pkg",
    ".dmg",
    ".zip",
    ".tar",
    ".gz",
}
POSTGRES_NAME_TOKENS = ("postgres", "postgresql", "enterprisedb")
PLANNER_RULE_TOKENS = ("planner_rules", "planner-rules", "correction-planner-service")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_sha256_file(path: Path, expected_sha256: str) -> str:
    actual = sha256_file(path)
    if actual != expected_sha256:
        raise T033ValidationError(T033ErrorCode.PG_INTEGRITY, "SHA-256 mismatch", str(path))
    return actual


def normalized_host(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise T033ValidationError(T033ErrorCode.PG_DOWNLOAD, "HTTPS is required", "url")
    host = (parsed.hostname or "").lower()
    if not host:
        raise T033ValidationError(T033ErrorCode.PG_DOWNLOAD, "URL host is missing", "url")
    return host


def require_allowed_host(url: str, allowed_hosts: set[str]) -> str:
    host = normalized_host(url)
    allowed = {item.lower() for item in allowed_hosts}
    if not any(host == item or host.endswith("." + item) for item in allowed):
        raise T033ValidationError(T033ErrorCode.PG_DOWNLOAD, "URL host is not allowlisted", "url")
    return host


def scan_packaged_artifact(root: Path, *, python_version: str, license_inventory_complete: bool) -> dict[str, object]:
    """Scan a built payload/staging tree for T-033 forbidden bundled content."""

    if not root.exists():
        raise T033ValidationError(T033ErrorCode.PAYLOAD, "artifact root does not exist", str(root))
    digest = hashlib.sha256()
    postgres_bundled = False
    planner_rules_bundled = False
    system_python_dependency = False

    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        rel = path.relative_to(root).as_posix().lower()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_file(path).encode("ascii"))
        if any(token in rel for token in POSTGRES_NAME_TOKENS) and path.suffix.lower() in POSTGRES_INSTALLER_SUFFIXES:
            postgres_bundled = True
        if any(token in rel for token in PLANNER_RULE_TOKENS):
            planner_rules_bundled = True
        if rel in {"requires-system-python.txt", "system-python.txt"} or "python-from-path" in rel:
            system_python_dependency = True

    return {
        "schema_version": "t033.artifact_scan.v1",
        "ticket": "T033",
        "artifact_sha256": digest.hexdigest(),
        "postgres_installer_bundled": postgres_bundled,
        "planner_rules_bundled": planner_rules_bundled,
        "system_python_dependency": system_python_dependency,
        "python_version": python_version,
        "license_inventory_complete": license_inventory_complete,
    }

