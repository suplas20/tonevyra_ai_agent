# T-033 — 실제 설치 검증 체크리스트

## A. 공통 정적 게이트

- [ ] 기존 51개 스킬 보존
- [ ] T-033 신규 7개 스킬 존재
- [ ] Python 3.11.9 exact policy
- [ ] PostgreSQL installer not bundled
- [ ] stable-only PostgreSQL metadata policy
- [ ] third-party license inventory
- [ ] payload SHA-256 manifest
- [ ] Planner rules/local fallback absent from client package

## B. Windows 클린 설치

테스트 환경:

```text
clean supported Windows x64 VM
no Python
no PostgreSQL
no Lightroom
standard user account + UAC available
```

- [ ] installer Authenticode valid
- [ ] bundled Python reports 3.11.9
- [ ] no Python added to PATH
- [ ] PostgreSQL installer downloaded, not extracted from Tonevyra payload
- [ ] downloaded installer hash/signature/publisher valid
- [ ] PostgreSQL service running
- [ ] DB and role created
- [ ] migrations at head
- [ ] Agent starts once
- [ ] Lightroom integration shown as pending
- [ ] reboot/startup behavior valid

## C. Windows coexistence

- [ ] Python 3.12/3.13 remains untouched
- [ ] existing PostgreSQL service remains untouched
- [ ] port collision handled
- [ ] existing user DB remains intact
- [ ] repair does not reset DB
- [ ] uninstall preserves data by default

## D. macOS 클린 설치

테스트 환경:

```text
clean supported Apple Silicon Mac/VM where allowed
no user Python dependency
no PostgreSQL
no Lightroom
Gatekeeper enabled
```

- [ ] arm64 executable
- [ ] Developer ID Application valid
- [ ] Developer ID Installer valid
- [ ] notarization Accepted
- [ ] staple validation valid
- [ ] Gatekeeper assessment accepted
- [ ] bundled Python reports 3.11.9
- [ ] no system Python modification
- [ ] PostgreSQL downloaded from approved official source
- [ ] package hash/signature valid
- [ ] DB bootstrap/migrations valid
- [ ] menu bar/Worker lifecycle valid
- [ ] Lightroom integration pending

## E. Lightroom scenarios

- [ ] Lightroom absent: base install succeeds
- [ ] Lightroom supported: plugin installed and visible
- [ ] Lightroom unsupported: warning without destructive action
- [ ] Lightroom installed later: re-detection and plugin repair works

## F. Network and integrity failures

- [ ] offline PostgreSQL download failure is recoverable
- [ ] partial download deleted
- [ ] SHA mismatch blocks execution
- [ ] invalid publisher/signature blocks execution
- [ ] prerelease metadata rejected
- [ ] unsigned channel metadata rejected
- [ ] redirect to non-allowlisted host rejected

## G. Upgrade/repair/uninstall

- [ ] same-version repair
- [ ] app upgrade with DB backup/rollback evidence
- [ ] PostgreSQL major version not silently upgraded
- [ ] user settings preserved
- [ ] processing history preserved
- [ ] default uninstall preserves DB/results
- [ ] explicit data removal requires confirmation

## H. Strict evidence files

```text
evidence/T-033/
├─ release_manifest.json
├─ license_inventory.json
├─ windows_install_evidence.json
├─ windows_artifact_scan.json
├─ macos_install_evidence.json
├─ macos_signing_notarization_evidence.json
├─ postgresql_resolution_evidence.json
├─ upgrade_repair_uninstall_evidence.json
└─ regression_summary.json
```

Reference harness output is not accepted as strict live evidence.
