# CONTRACT — T-033 Cross-platform Installer Packaging

## Required product behavior

```text
Windows x64 installer
macOS arm64 PKG/DMG
bundled Python 3.11.9
PostgreSQL installer absent from package
latest stable PostgreSQL downloaded from approved official source
Lightroom external/user-managed
repair, upgrade, uninstall
release signing and macOS notarization
```

## Required static invariants

- T-032 baseline files remain.
- At least 58 cumulative skills exist.
- T-033 inventory snapshot contains exactly 58 skills.
- Required T-033 documents, skills, schemas, fixtures and scripts exist.
- Python distribution is `bundled`, version policy is exact `3.11.9`.
- PostgreSQL distribution is `download`, `bundled=false`, `channel=latest-stable`.
- PostgreSQL prerelease is forbidden.
- Lightroom is external and not required for base installation.
- Artifact scan must prove that no PostgreSQL installer is bundled.

## Strict completion evidence

```text
implementation runtime evidence
real Windows installation evidence
real macOS signed/notarized installation evidence
final package artifact scan
T-019 through T-032 regression summary
```

Reference harness evidence cannot satisfy strict completion.
