# T-033 — 구현 명세

## 1. 구현 범위

T-033은 애플리케이션 기능을 변경하는 티켓이 아니라, T-032까지의 기능을 운영체제별 설치 가능한 제품으로 전달하는 배포·설치·복구 계층을 구현한다.

```text
Application payload
One-click installer orchestrator
Installer bootstrapper
Dependency detector
Bundled runtime verifier
PostgreSQL stable resolver/downloader
Database bootstrap/migration
Lightroom detector/plugin installer
Startup registration
Repair/upgrade/uninstall
Signing/notarization/release evidence
```

## 2. 권장 모듈 경계

```text
packaging/
├─ common/
│  ├─ installer_orchestrator.py
│  ├─ installer_adapters.py
│  ├─ dependency_manifest.py
│  ├─ dependency_detector.py
│  ├─ integrity.py
│  ├─ license_inventory.py
│  ├─ postgres_resolver.py
│  ├─ postgres_bootstrap.py
│  ├─ database_migrator.py
│  ├─ database_verifier.py
│  ├─ credential_store.py
│  ├─ post_install_doctor.py
│  ├─ install_state.py
│  └─ redaction.py
├─ windows/
│  ├─ bootstrapper/
│  ├─ installer/
│  ├─ signing/
│  └─ probes/
├─ macos/
│  ├─ app_bundle/
│  ├─ pkg/
│  ├─ signing/
│  ├─ notarization/
│  └─ probes/
└─ manifests/
   ├─ bundled-components.lock.json
   ├─ postgresql-channel.schema.json
   ├─ third-party-manifest.json
   └─ release-manifest.json
```

애플리케이션의 사업 로직은 installer 모듈을 import하지 않는다. installer는 Agent 내부 서비스 로직을 소유하지 않는다.

## 3. 설치 상태 모델

```text
NOT_STARTED
PREFLIGHT
PAYLOAD_VERIFIED
APP_INSTALLING
APP_PAYLOAD_INSTALLED
BUNDLED_RUNTIME_VERIFIED
POSTGRES_REQUIRED
POSTGRES_RESOLVING
POSTGRES_DOWNLOADING
POSTGRES_VERIFIED
POSTGRES_INSTALLING
POSTGRES_READY
DB_ROLE_CREATING
DB_DATABASE_CREATING
DB_MIGRATING
DB_SCHEMA_VERIFYING
DB_CREDENTIAL_STORING
PLUGIN_INSTALLING
STARTUP_REGISTERING
POST_INSTALL_CHECK
COMMITTING
COMPLETED
FAILED_RECOVERABLE
FAILED_TERMINAL
ROLLING_BACK
ROLLED_BACK
```

이 상태는 설치 로그/증거 전용이며 `image_tasks.status`에 추가하지 않는다.

## 4. Dependency manifest

필수 필드:

```json
{
  "schema_version": "t033.dependency_manifest.v1",
  "python": {
    "distribution": "bundled",
    "required_version": "3.11.9",
    "version_policy": "exact",
    "system_path_mutation": false
  },
  "postgresql": {
    "distribution": "download",
    "channel": "latest-stable",
    "prerelease_allowed": false,
    "bundled": false,
    "metadata_signature_required": true,
    "installer_signature_required": true
  },
  "lightroom_classic": {
    "distribution": "external-user-managed",
    "required_for_base_install": false
  }
}
```

Manifest parsing is fail-closed. Unknown distribution modes, missing hashes, invalid signatures, unsupported architecture, and prerelease flags must stop execution.

## 5. Bundled Python runtime

### Build gate

```text
python --version == 3.11.9
locked dependency install
license inventory generated
payload hash manifest generated
network disabled during packaging verification
clean-machine import smoke test
```

### Runtime gate

The installed application must expose a diagnostic command that returns:

```json
{
  "runtime_source": "bundled",
  "python_version": "3.11.9",
  "python_executable": "<application-local-path>",
  "system_python_used": false,
  "dependency_imports_ok": true,
  "payload_integrity_ok": true
}
```

Do not log full user home paths in public evidence; normalize or redact them.

## 6. PostgreSQL stable resolver

### Input

```text
OS: windows | macos
architecture: x64 | arm64
channel: latest-stable
Tonevyra supported DB contract version
signed metadata endpoint
```

### Resolution rules

```text
GA/stable only
numeric semantic version ordering
no beta/rc/snapshot/nightly strings
platform artifact must exist
URL final host must be allowlisted
SHA-256 required
publisher or package signature identity required
new major compatibility gate required
```

### Output

```json
{
  "version": "<resolved-version>",
  "release_status": "stable",
  "platform": "windows-x64",
  "url": "<official-installer-url>",
  "sha256": "<64-hex>",
  "publisher": "<expected-publisher>",
  "metadata_signature_verified": true
}
```

The resolver must never derive an executable URL from untrusted HTML without signed metadata and host validation.

## 7. PostgreSQL installation

### Detection

```text
Tonevyra-owned service/instance identity
server executable version
service state
port ownership
DB connectivity
schema version
app role privilege
required extension availability
```

A generic `psql` in PATH is insufficient evidence.

### Installation

```text
download to restricted temporary directory
→ verify size/hash/signature/publisher
→ request OS elevation
→ unattended install with redacted secrets
→ verify service binary path and version
→ create/verify Tonevyra database and app role
→ apply migrations transactionally
→ record install receipt
→ delete temporary installer
```

Avoid passwords in process arguments. If the third-party installer requires a command-line secret, generate an ephemeral response/config file with restricted permissions, delete it immediately, and prove redaction in logs.

## 8. Database bootstrap

DB bootstrap is part of the same installer session and must not require manual SQL or database tooling.

```text
wait for PostgreSQL readiness
acquire install/bootstrap lock
create role only if absent
create database only if absent
set least privilege
restrict network to localhost
connect with application role
apply Alembic migrations to head
validate required tables/view/indexes/constraints
persist schema revision in install receipt
run read/write smoke transaction and rollback
store app credential in DPAPI/Credential Manager or Keychain
release bootstrap lock
```

Required product objects:

```text
image_tasks
task_artifacts
task_events
stage_results
quality_results
feedback_records
learning_samples
v_task_summary
alembic_version
```

Never run destructive reset on an existing database during normal install or repair. The Agent must not start until DB bootstrap and schema verification pass.

## 9. Windows implementation

```text
- x64-only release gate
- per-user application files
- machine-level elevation only when needed
- startup via approved per-user mechanism
- Authenticode verification of installer and installed executable
- Programs and Features entry
- repair/upgrade/uninstall commands
- installer log under ProgramData with redaction
```

A release build must not use IExpress as the final production installer if it cannot provide the required signing, upgrade, repair, transaction and prerequisite behavior. WiX Burn, Inno Setup, NSIS or an equivalent reviewed bootstrapper may be used.

## 10. macOS implementation

```text
- arm64 application bundle
- hardened runtime where required
- nested binaries signed inside-out
- Developer ID Application signature
- Developer ID Installer signature for PKG
- notarytool submission
- staple ticket
- spctl and codesign verification
- LaunchAgent/Login Item lifecycle
- Keychain for secrets
```

The `.app`, helper executables, Python/native libraries, plugin payload and package scripts must all satisfy signing/notarization rules.

## 11. Lightroom integration

Detection must not launch or automate Adobe UI without user intent.

```text
registry/application bundle detection
→ executable/app version parse
→ support matrix evaluation
→ plugin destination permission check
→ plugin copy/registration
→ plugin checksum/version verification
```

If Lightroom is absent, store `LIGHTROOM_PENDING` in installer state only. Do not invent a new image task status.

## 12. Logging

Required fields:

```text
timestamp
install_session_id
installer_version
OS/build/architecture
step
component
result
stable error code
elapsed_ms
redaction_applied
```

Forbidden values:

```text
DB passwords
API keys/tokens
Authorization headers
full photo paths
raw user names/email
unredacted home directory when exporting evidence
```

## 13. Error codes

```text
T033-PREFLIGHT-001
T033-PAYLOAD-002
T033-PYTHON-003
T033-PG-METADATA-004
T033-PG-DOWNLOAD-005
T033-PG-INTEGRITY-006
T033-PG-INSTALL-007
T033-DB-BOOTSTRAP-008
T033-LIGHTROOM-009
T033-PLUGIN-010
T033-SIGNING-011
T033-NOTARIZATION-012
T033-UPGRADE-013
T033-REPAIR-014
T033-UNINSTALL-015
```

## 14. Evidence separation

```text
reference harness evidence
≠ implementation installer evidence
≠ real Windows live evidence
≠ real macOS signed/notarized evidence
```

Strict completion requires all categories and prior-ticket regression evidence.

## 15. One-click orchestration contract

The installer must expose a single high-level operation:

```text
install_all()
```

This operation coordinates platform adapters but does not expose prerequisite wizards to the user. Normal install evidence must prove:

```text
single_install_session
manual_prerequisite_steps == 0
manual_database_steps == 0
postgres_unattended_install
schema_migration_automatic
startup_registration_automatic
post_install_doctor_passed
```

Idempotent re-entry is required. A second invocation after partial failure resumes or repairs completed Tonevyra-owned components rather than reinstalling or resetting them.
