# Installer Download Integrity Skill

## Purpose

Use this skill whenever the bootstrapper downloads third-party installers or signed dependency-channel metadata.

## Mandatory Rules

- HTTPS is required.
- Initial and final redirect hosts must be allowlisted.
- Signed metadata is verified before trusting URL or hash.
- File size and SHA-256 are checked before execution.
- Authenticode, package signature or equivalent publisher identity is verified.
- Partial files use a temporary extension and restricted permissions.
- Validation failure prevents execution and removes/quarantines the payload.
- Logs contain no secrets or unredacted credentials.

## Forbidden

HTML scraping followed by immediate execution, hash-only trust from the same untrusted response, disabled TLS verification, or prerelease fallback.
