"""T-033 installer-specific errors.

These stable error codes belong to installation evidence and logs. They are
kept out of the image processing task status/error enum on purpose.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class T033ErrorCode(StrEnum):
    PREFLIGHT = "T033-PREFLIGHT-001"
    PAYLOAD = "T033-PAYLOAD-002"
    PYTHON = "T033-PYTHON-003"
    PG_METADATA = "T033-PG-METADATA-004"
    PG_DOWNLOAD = "T033-PG-DOWNLOAD-005"
    PG_INTEGRITY = "T033-PG-INTEGRITY-006"
    PG_INSTALL = "T033-PG-INSTALL-007"
    DB_BOOTSTRAP = "T033-DB-BOOTSTRAP-008"
    LIGHTROOM = "T033-LIGHTROOM-009"
    PLUGIN = "T033-PLUGIN-010"
    SIGNING = "T033-SIGNING-011"
    NOTARIZATION = "T033-NOTARIZATION-012"
    UPGRADE = "T033-UPGRADE-013"
    REPAIR = "T033-REPAIR-014"
    UNINSTALL = "T033-UNINSTALL-015"


@dataclass
class T033ValidationError(Exception):
    code: T033ErrorCode
    message: str
    field: str | None = None

    def __str__(self) -> str:
        field = f" field={self.field}" if self.field else ""
        return f"{self.code.value}:{field} {self.message}"

