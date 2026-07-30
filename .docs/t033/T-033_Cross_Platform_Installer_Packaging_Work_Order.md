# T-033 — Windows/macOS 설치 패키징 및 필수 구성요소 부트스트랩 작업 지시서

## 1. 문서 상태

```text
Ticket: T-033
Baseline: T-032
Target: Windows x64 + macOS Apple Silicon arm64
Primary result: end-user installable Tonevyra AI packages
```

이 문서는 T-032 완료 상태를 기준으로 Tonevyra AI Agent를 일반 사용자가 개발 도구나 명령어 없이 설치·복구·제거할 수 있도록 패키징하는 작업을 정의한다.

T-033의 최우선 사용자 경험은 **설치 파일 실행 → 운영체제 관리자 승인 → 설치 버튼 1회 → 전체 자동 구성 → 실행**이다. Python, PostgreSQL, DB 계정, DB 스키마, 플러그인, 자동 시작 및 진단을 사용자에게 별도 작업으로 요구하지 않는다.

기존 문서, 스킬, 하네스, 계약, 상태 머신, Planner API 경계 및 보안 규칙을 삭제하거나 약화하지 않는다.

## 2. 확정된 제품 정책

### 2.1 배포 방식

```text
재배포가 명확히 허용되고 버전 고정이 필요한 구성요소
→ Tonevyra 설치 패키지에 내장

설치 파일을 패키지에 포함하지 않기로 결정한 구성요소
→ 설치 시 공식 배포처에서 다운로드 후 검증·설치

계정·구독·별도 사용자 동의가 필요한 구성요소
→ 설치 여부만 검사하고 공식 설치 경로 안내
```

### 2.2 구성요소별 확정 정책

| 구성요소 | T-033 처리 |
|---|---|
| Tonevyra Agent | 운영체제별 패키지에 내장 |
| Python | **Python 3.11.9 호환 런타임을 내장** |
| Python 패키지 및 네이티브 라이브러리 | 라이선스 검토 통과분을 버전 고정하여 내장 |
| PostgreSQL | **내장 금지. 최신 정식 안정화 버전을 설치 시 다운로드** |
| DB 스키마·마이그레이션 | 패키지에 내장 |
| Lightroom Classic | 설치 여부와 지원 버전만 검사; 자동 설치하지 않음 |
| Tonevyra Lightroom 플러그인 | 패키지에 내장하고 가능한 경우 자동 등록 |
| Adobe Creative Cloud | 내장·자동 설치하지 않음 |
| GPU 드라이버 | 내장·자동 설치하지 않음 |
| Planner 엔진 | T-032 정책대로 서버 전용; 로컬 패키지에 포함 금지 |

## 3. 핵심 원칙

1. Python 최신 버전을 탐색하거나 시스템 Python을 재사용하지 않는다.
2. Python 3.11.9 런타임은 Tonevyra 애플리케이션에 포함하고 절대경로로 실행한다.
3. 시스템 PATH, 파일 연결, 사용자의 기존 Python 설치를 변경하지 않는다.
4. PostgreSQL 설치 파일은 Tonevyra 배포물에 포함하지 않는다.
5. PostgreSQL은 공식 배포 경로에서 최신 GA(정식 안정화) 릴리스만 다운로드한다.
6. Alpha, Beta, RC, snapshot, nightly 빌드는 PostgreSQL 설치 후보에서 제외한다.
7. 다운로드 파일은 HTTPS, 공식 호스트, SHA-256, 전자서명/패키지 서명을 검증한 뒤 실행한다.
8. 사용자의 기존 PostgreSQL 데이터와 서비스를 임의로 변경하거나 제거하지 않는다.
9. Lightroom Classic이 없어도 Tonevyra 본체 설치는 완료할 수 있어야 한다.
10. 실제 Windows/macOS 설치 증거 없이 T-033 완료를 선언하지 않는다.

## 4. 설치 산출물

### Windows

```text
dist/windows/
├─ TonevyraAI-Setup-{version}-windows-x64.exe
├─ TonevyraAI-Setup-{version}-windows-x64.exe.sha256
├─ TonevyraAI-Setup-{version}-windows-x64.manifest.json
└─ third-party-notices/
```

필수 조건:

```text
Windows 10/11 x64
per-user Agent installation
UAC elevation only for machine-level prerequisites/database service
Authenticode signing for release artifacts
repair/upgrade/uninstall support
```

### macOS

```text
dist/macos/
├─ TonevyraAI-{version}-macos-arm64.pkg
├─ TonevyraAI-{version}-macos-arm64.dmg
├─ TonevyraAI-{version}-macos-arm64.pkg.sha256
├─ TonevyraAI-{version}-macos-arm64.manifest.json
└─ third-party-notices/
```

필수 조건:

```text
Apple Silicon arm64
Developer ID Application signing
Developer ID Installer signing
notarytool notarization
stapling
Gatekeeper assessment
repair/upgrade/uninstall support
```

Intel Mac은 별도 검증 전까지 지원 대상으로 표시하지 않는다.

## 5. 설치 단계

정상 경로에서 사용자는 설치 버튼과 운영체제 관리자 승인 외에 별도 입력을 하지 않는다.

```text
installer launch
→ OS/architecture/version preflight
→ disk/network/permission preflight
→ package signature and payload integrity verification
→ Tonevyra application payload installation
→ bundled Python 3.11.9 runtime verification
→ existing PostgreSQL/Tonevyra DB detection
→ if needed, resolve latest approved PostgreSQL stable installer
→ official download + integrity/signature validation
→ PostgreSQL unattended installation
→ wait until PostgreSQL service is ready
→ automatically create/verify Tonevyra DB role and database
→ automatically run Alembic upgrade head
→ verify tables/view/indexes/privileges and DB read/write smoke transaction
→ store DB credentials in OS credential storage
→ installed Lightroom Classic detection
→ Tonevyra Lightroom plugin automatic install or PENDING
→ background startup registration
→ Agent/DB/Planner API post-install doctor
→ commit installation receipt/evidence
→ launch Tonevyra AI
```

사용자에게 PostgreSQL 설치 마법사, DB 비밀번호, DB 이름, 포트, SQL 실행 또는 Alembic 명령을 노출하지 않는다.

## 6. Python 정책

### 6.1 버전

```text
Required runtime: Python 3.11.9
Version policy: exact
System Python dependency: forbidden
Network download during normal install: forbidden
```

### 6.2 패키징

Windows와 macOS 모두 빌드 결과물에 Python 인터프리터와 Tonevyra 의존성을 포함한다. PyInstaller/Nuitka 또는 검증된 app-local runtime 방식 중 하나를 사용하되, 최종 결과는 다음을 만족해야 한다.

```text
- user does not install Python separately
- no PATH mutation
- no global pip install
- no dependency download at first launch
- runtime can be hash-verified
- runtime version reports exactly 3.11.9
- application executes with the bundled runtime only
```

개발환경의 임의 `site-packages`를 복사하지 않는다. 잠금 파일로 재현 가능한 빌드를 생성한다.

## 7. PostgreSQL 정책

### 7.1 다운로드 방식

PostgreSQL 설치 프로그램은 패키지에 넣지 않는다. 설치 시 다음 소스로부터 운영체제와 아키텍처에 맞는 정식 배포본을 다운로드한다.

```text
Primary discovery: PostgreSQL official download/release information
Binary installer provider: PostgreSQL official download page가 연결하는 공식 제공자
Allowed channel: GA/stable only
Forbidden: alpha, beta, rc, snapshot, nightly
```

### 7.2 최신 안정화 버전 해석

`latest stable`은 문자열이나 웹 페이지 첫 링크를 그대로 신뢰하는 방식으로 구현하지 않는다.

```text
1. signed Tonevyra dependency channel metadata fetch
2. metadata source provenance verification
3. stable/GA marker verification
4. semantic version ordering
5. OS/architecture installer availability verification
6. supported installation contract verification
7. download URL allowlist and signature/hash verification
```

Tonevyra 매니페스트는 최신 정식 안정화 버전과 공식 설치 파일의 URL·해시·게시자 정보를 제공한다. 매니페스트 자체의 서명 검증에 실패하면 설치하지 않는다.

새 메이저 버전이 공개되었으나 Tonevyra DB 호환성 게이트가 아직 통과되지 않았다면 임의로 설치하지 않고 명확한 오류를 표시한다. 이는 데이터 손상 방지를 위한 하드 게이트다.

### 7.3 기존 설치 보호

```text
- existing user PostgreSQL must not be uninstalled
- existing clusters must not be reinitialized
- existing service credentials must not be guessed
- port 5432 must not be assumed free
- Tonevyra-owned cluster/service identity must be explicit
```

권장 식별자:

```text
Windows service: TonevyraPostgreSQL
DB name: tonevyra_agent
app role: tonevyra_app
preferred port: 55432, or a persisted validated alternative
listen scope: localhost only
```

macOS에서는 설치 프로그램이 제공하는 PostgreSQL 서비스와 Tonevyra DB를 명시적으로 연결하고, 시스템 전역 서비스 충돌을 검사한다.

## 8. Lightroom Classic 정책

Lightroom Classic과 Creative Cloud는 Tonevyra 패키지에 포함하지 않는다.

```text
installed + supported → plugin install/verification
installed + unsupported → warning and supported-version guidance
not installed → Tonevyra install continues; Lightroom integration = PENDING
```

Adobe 로그인, 구독, 라이선스 동의는 사용자와 Adobe 사이에서 수행되어야 한다.

## 9. 보안 및 비밀정보

```text
- no DB password in CLI arguments when avoidable
- no API key in installer logs
- no Planner key in package manifest
- Windows secrets use DPAPI/Credential Manager
- macOS secrets use Keychain
- temporary installers use restricted permissions
- downloaded installer deleted after successful install unless diagnostic retention is opted in
- installer logs redact usernames, photo paths, tokens, passwords, and authorization headers
```

## 10. 업그레이드·복구·제거

### 업그레이드

```text
verify existing installation
→ stop Agent cleanly
→ back up settings and DB metadata
→ replace application payload atomically
→ run schema migration
→ restart and doctor
→ rollback on failure
```

PostgreSQL 메이저 업그레이드는 일반 앱 업데이트와 결합하지 않는다. 별도 데이터 마이그레이션 계획과 롤백 증거가 필요하다.

### 복구

```text
verify bundled runtime hashes
verify executable/signature
verify PostgreSQL service/connectivity
verify schema version
verify Lightroom plugin
repair only damaged Tonevyra-owned components
```

### 제거

기본 제거는 애플리케이션과 자동 시작 항목만 제거하며 사용자 DB·설정·처리 결과를 보존한다. 데이터 삭제는 별도 명시적 확인을 받아야 한다.

## 11. 완료 조건

- Windows x64 signed installer artifact
- macOS arm64 signed/notarized/stapled PKG and DMG
- bundled Python reports exactly 3.11.9
- no system Python dependency or PATH mutation
- PostgreSQL installer absent from final package payload
- PostgreSQL latest stable resolver and signed metadata verification
- PostgreSQL official download, SHA-256 and publisher/signature checks
- clean Windows install evidence
- clean Apple Silicon macOS install evidence
- Lightroom absent/present/unsupported scenarios
- repair, upgrade and uninstall evidence
- data-preservation evidence
- T-019 through T-032 regression evidence
- all 51 prior skills preserved
- seven T-033 skills added; total 58

## 12. 명시적 금지

```text
bundling PostgreSQL installer
using arbitrary system Python
installing newest Python instead of 3.11.9
running pip against the public internet during install
blindly scraping and executing the first PostgreSQL download link
installing prerelease PostgreSQL
silently taking over an existing PostgreSQL cluster
storing DB passwords in logs or plain text
bundling Lightroom Classic or Creative Cloud
claiming macOS completion without notarization/Gatekeeper evidence
claiming completion from reference harness output only
```

## 11. 올인원 설치 완료 조건

```text
manual_prerequisite_steps = 0
manual_database_steps = 0
python_3119_bundled = true
postgres_unattended_install = true
database_bootstrap_automatic = true
alembic_head_verified = true
required_schema_objects_verified = true
credential_store_verified = true
agent_startup_registered = true
post_install_doctor_passed = true
```

Lightroom Classic 미설치는 base install 실패가 아니라 `PENDING`이지만, PostgreSQL·DB 스키마·Agent doctor 실패는 설치 성공으로 처리하지 않는다.

상세 오케스트레이션과 DB bootstrap은 다음 문서를 따른다.

```text
.docs/t033/T-033_All_In_One_Installer_Orchestration.md
.docs/t033/T-033_Database_Bootstrap_and_Schema_Automation.md
```
