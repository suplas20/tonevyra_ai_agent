"""Redaction helpers for installer evidence and logs."""

from __future__ import annotations

import re

SECRET_PATTERNS = [
    re.compile(r"(?i)(authorization:\s*bearer\s+)([A-Za-z0-9._~+/=-]+)"),
    re.compile(r"(?i)(password|passwd|pwd|token|api[_-]?key|authorization)\s*[:=]\s*([^\s,;]+)"),
]
WINDOWS_HOME_PATTERN = re.compile(r"(?i)\b[A-Z]:\\Users\\[^\\\s]+")
POSIX_HOME_PATTERN = re.compile(r"(?<!\w)/(Users|home)/[^/\s]+")


def redact_installer_text(text: str) -> str:
    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(lambda match: match.group(1) + "[REDACTED]", redacted)
    redacted = WINDOWS_HOME_PATTERN.sub("[REDACTED_HOME]", redacted)
    redacted = POSIX_HOME_PATTERN.sub("[REDACTED_HOME]", redacted)
    return redacted
