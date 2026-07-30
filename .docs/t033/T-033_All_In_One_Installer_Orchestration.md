# T-033 — 올인원 설치 오케스트레이션

## 1. 제품 목표

Tonevyra AI의 설치 경험은 다음과 같아야 한다.

```text
사용자: 설치 파일 실행
→ 운영체제 관리자 승인
→ [설치] 1회 클릭
→ 자동 설치·구성·검증
→ Tonevyra AI 실행
```

사용자에게 Python 설치, PostgreSQL 버전 선택, DB 포트 선택, DB 계정·비밀번호 입력, SQL 실행, 스키마 생성, 플러그인 복사 또는 서비스 등록을 요구하지 않는다.

운영체제의 UAC/macOS 관리자 인증과 Adobe 계정·구독이 필요한 Lightroom Classic 설치는 Tonevyra가 우회할 수 없는 예외다.

## 2. 올인원 설치의 정의

다음 항목이 하나의 설치 세션에서 자동 완료되어야 한다.

```text
1. 운영체제·아키텍처·디스크·네트워크 검사
2. 설치 패키지 서명과 payload 무결성 검사
3. Tonevyra Agent 파일 설치
4. 내장 Python 3.11.9 런타임 설치·검증
5. 잠금된 Python 의존성 검증
6. PostgreSQL 필요 여부 판정
7. PostgreSQL 최신 승인 안정화 설치본 조회·다운로드·검증
8. PostgreSQL 무인 설치와 서비스 준비 대기
9. Tonevyra 전용 Role·Database 생성
10. Alembic 스키마 마이그레이션 자동 실행
11. 필수 테이블·뷰·인덱스·권한 검증
12. DB 읽기·쓰기 smoke transaction
13. DB 자격 증명 보안 저장
14. Lightroom Classic 감지
15. Lightroom 플러그인 자동 설치 또는 PENDING 기록
16. Agent 자동 시작 등록
17. Agent·DB·Planner API 최종 doctor
18. 설치 receipt/evidence 기록
19. Tonevyra AI 실행
```

## 3. 사용자 입력 정책

정상 설치에서 허용되는 사용자 상호작용은 다음으로 제한한다.

```text
필수:
- 설치 시작 클릭
- Windows UAC 또는 macOS 관리자 인증

선택:
- 설치 경로 변경(지원할 경우)
- 진단 로그 보기
- Lightroom 미설치 안내 열기
- 설치 완료 후 즉시 실행 여부
```

다음 입력은 금지한다.

```text
Python 버전 선택
PostgreSQL 버전 선택
DB 관리자 비밀번호 입력
DB 이름/Role 입력
포트 수동 입력
SQL 파일 선택
Alembic 명령 실행
서비스명 입력
PATH 설정
pip install 실행
```

포트 충돌이 있으면 설치 프로그램이 허용 범위에서 사용 가능한 로컬 포트를 자동 선택하고 install receipt에 기록한다.

## 4. 설치 오케스트레이터

공통 오케스트레이터는 각 단계를 순서대로 실행하고 모든 단계 결과를 영속화한다.

권장 인터페이스:

```text
preflight()
verify_payload()
install_application_payload()
verify_bundled_runtime()
resolve_postgresql()
download_and_verify_postgresql()
install_postgresql_unattended()
wait_postgresql_ready()
bootstrap_database()
install_lightroom_plugin()
register_agent_startup()
run_post_install_doctor()
commit_installation()
```

운영체제별 차이는 adapter에 둔다.

```text
InstallerOrchestrator
├─ WindowsInstallerAdapter
└─ MacOSInstallerAdapter
```

Agent의 사진 처리, Planner API, Lightroom 보정, 품질 판단 로직을 installer에 복제하지 않는다.

## 5. 설치 상태 머신

```text
NOT_STARTED
PREFLIGHT
PAYLOAD_VERIFIED
APP_PAYLOAD_INSTALLED
BUNDLED_RUNTIME_VERIFIED
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
POST_INSTALL_DOCTOR
COMMITTING
COMPLETED
FAILED_RECOVERABLE
FAILED_TERMINAL
ROLLING_BACK
ROLLED_BACK
```

각 상태는 installer 전용이며 `image_tasks.status`나 처리 stage에 추가하지 않는다.

## 6. 멱등성과 재실행

설치 프로그램은 중간 실패 후 다시 실행해도 기존 성공 단계를 파괴하지 않아야 한다.

```text
Python 정상 → 재설치하지 않음
PostgreSQL 설치 완료 → 설치본 재실행하지 않음
Tonevyra DB 존재 → DROP/재생성하지 않음
Alembic head 일치 → 마이그레이션 재적용하지 않음
플러그인 동일 버전 → 해시 확인 후 건너뜀
Agent startup 등록 정상 → 중복 등록하지 않음
```

설치 상태와 receipt는 비밀정보 없이 다음을 기록한다.

```text
install_session_id
installer_version
completed_steps
component_versions
PostgreSQL service identity
selected local port
DB name and role name
Alembic revision
payload hashes
Lightroom integration status
post-install doctor result
```

## 7. 실패 처리

### 복구 가능한 실패

```text
일시적 네트워크 오류
PostgreSQL 다운로드 중단
서비스 시작 지연
파일 잠금
Lightroom 미설치
```

사용자에게 `다시 시도` 또는 `자동 복구`를 제공하고 완료된 단계를 재사용한다.

### 터미널 실패

```text
패키지 서명 불일치
SHA-256 불일치
게시자 불일치
지원하지 않는 OS/아키텍처
DB 스키마 검증 불일치
비밀정보 저장 실패
```

검증 실패 파일은 실행하지 않는다. Agent는 DB doctor가 통과하기 전 시작하지 않는다.

## 8. 설치 완료 기준

다음이 모두 참이어야 `COMPLETED`로 처리한다.

```text
application_payload_ok = true
python_3119_bundled_ok = true
postgres_service_ready = true
database_connectivity_ok = true
database_role_ok = true
database_schema_at_head = true
database_required_objects_ok = true
database_rw_smoke_ok = true
credential_store_ok = true
lightroom_status in [INSTALLED, PENDING]
plugin_status in [INSTALLED, PENDING]
agent_startup_registered = true
agent_health_ok = true
planner_api_config_ok = true
```

Lightroom Classic이 없을 때는 `PENDING`을 허용하지만, DB나 Agent 실패를 설치 성공으로 처리해서는 안 된다.

## 9. 릴리스 증거

Windows와 macOS 실제 설치 증거에는 최소 다음이 포함되어야 한다.

```text
single_install_session = true
manual_prerequisite_steps = 0
manual_database_steps = 0
python_3119_bundled = true
postgres_downloaded_and_verified = true
postgres_unattended_install = true
database_bootstrap_automatic = true
alembic_head_verified = true
required_schema_objects_verified = true
agent_started = true
post_install_doctor_passed = true
```

정적 문서나 reference harness만으로 올인원 설치 완료를 주장하지 않는다.
