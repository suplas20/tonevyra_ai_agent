# Cross-platform Installer Packaging Skill

## Purpose

Use this skill when packaging Tonevyra AI for Windows x64 and macOS Apple Silicon arm64, including installation state, payload layout, prerequisite orchestration and release artifacts.

## Mandatory Rules

- Preserve T-030 Windows and T-031 macOS runtime boundaries.
- Keep installer logic outside Agent business logic.
- Bundle Python 3.11.9; do not depend on system Python.
- Do not bundle PostgreSQL installers.
- Keep Lightroom Classic external and user-managed.
- Produce repair, upgrade and uninstall behavior.
- Separate reference evidence from real platform completion.

## Deliverables

```text
signed Windows installer
signed/notarized/stapled macOS package
release manifest
payload hash inventory
third-party notices
live install evidence
```
