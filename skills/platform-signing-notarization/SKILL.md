# Platform Signing and Notarization Skill

## Purpose

Use this skill for Windows Authenticode release signing and macOS Developer ID signing, notarization, stapling and Gatekeeper verification.

## Windows

- Sign final installer and critical installed executables.
- Verify signature status and expected publisher after signing.
- Timestamp release signatures.

## macOS

- Sign nested code from inside out.
- Use Developer ID Application for executable code.
- Use Developer ID Installer for PKG.
- Submit with `notarytool`, require Accepted, then staple.
- Verify with codesign, pkgutil, stapler and Gatekeeper.

## Security

Certificates, private keys, passwords and notary credentials never enter source control, package payloads or public logs.
