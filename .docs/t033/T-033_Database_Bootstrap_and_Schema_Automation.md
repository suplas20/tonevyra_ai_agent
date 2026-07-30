# T-033 — PostgreSQL DB Bootstrap 및 스키마 자동 설치

## 1. 목적

PostgreSQL 설치가 완료된 후 Tonevyra 설치 프로그램이 사용자 입력 없이 전용 데이터베이스, Role, 권한, 스키마, 뷰, 인덱스 및 마이그레이션 버전을 자동 구성한다.

## 2. 소유권과 식별자

```text
PostgreSQL service identity: Tonevyra가 생성·소유한 명시적 식별자
Database: tonevyra_agent
Application role: tonevyra_app
Host: 127.0.0.1
Listen scope: localhost only
Schema: public
Migration owner: installer bootstrap context
Runtime owner: tonevyra_app least privilege
```

기존 사용자의 PostgreSQL 서비스·클러스터·DB를 추측하거나 수정하지 않는다.

## 3. 자동 Bootstrap 순서

```text
PostgreSQL service ready 확인
→ 관리자 bootstrap 연결
→ advisory/install lock 획득
→ tonevyra_app Role 존재 확인·필요 시 생성
→ tonevyra_agent DB 존재 확인·필요 시 생성
→ owner/privilege 검증
→ 애플리케이션 연결 테스트
→ 현재 Alembic revision 조회
→ Alembic upgrade head
→ 필수 DB object 검증
→ 읽기/쓰기 smoke transaction 후 ROLLBACK
→ Credential Store/Keychain 저장
→ install receipt에 revision 기록
→ lock 해제
```

## 4. 필수 DB 객체

```text
Tables:
- image_tasks
- task_artifacts
- task_events
- stage_results
- quality_results
- feedback_records
- learning_samples
- alembic_version

Views:
- v_task_summary
```

실제 모델과 제약조건은 `.docs/04_PostgreSQL_Database_Schema_Agent.md` 및 Alembic migration을 source of truth로 사용한다.

## 5. Alembic 정책

```text
최초 설치: base → head
기존 설치: current revision → head
동일 revision: no-op
하위 앱 버전 설치: 자동 downgrade 금지
기존 DB reset/drop: 정상 설치·복구에서 금지
```

설치 프로그램 안에 별도의 임시 `schema.sql`을 복제하여 Alembic과 이중 관리하지 않는다. 필요한 bootstrap SQL은 Role/DB 생성처럼 데이터베이스 외부 컨텍스트에서만 사용한다.

## 6. 트랜잭션과 백업

```text
신규 빈 DB:
- migration 실패 시 Agent 시작 금지
- 실패 DB는 진단을 위해 보존
- 사용자가 명시적으로 초기화 재시도를 선택한 경우에만 제거 가능

기존 DB:
- Agent/Worker 정상 중지
- 백업 또는 검증된 restore point 생성
- migration 실행
- post-migration verify
- 실패 시 자동 시작 금지 및 rollback/restore 경로 제공
```

PostgreSQL 메이저 업그레이드는 일반 Tonevyra 앱 업데이트와 동시에 자동 실행하지 않는다.

## 7. 비밀번호와 자격 증명

설치 프로그램이 강한 임의 비밀번호를 생성한다. 사용자는 DB 비밀번호를 입력하지 않는다.

```text
Windows: DPAPI 또는 Windows Credential Manager
macOS: Keychain
```

설정 파일에는 자격 증명 참조만 저장한다.

```json
{
  "database": {
    "host": "127.0.0.1",
    "port": 55432,
    "name": "tonevyra_agent",
    "user": "tonevyra_app",
    "credential_ref": "TonevyraAI/PostgreSQL/Agent"
  }
}
```

비밀번호, 관리자 접속 URL, response file 내용은 로그·evidence·프로세스 목록에 노출하지 않는다.

## 8. 검증 계약

DB bootstrap 성공 증거는 다음 조건을 만족해야 한다.

```text
postgres_service_ready = true
role_exists = true
database_exists = true
runtime_role_is_not_superuser = true
localhost_only = true
alembic_head_matches_application = true
required_tables_verified = true
required_view_verified = true
read_write_smoke_rolled_back = true
credential_store_verified = true
```

## 9. 구현 명령 경계

권장 명령:

```text
tonevyra-db-bootstrap initialize
tonevyra-db-bootstrap upgrade
tonevyra-db-bootstrap verify
tonevyra-db-bootstrap repair
```

설치 프로그램은 명령 실행과 종료 코드만 조정하고 DB 도메인 로직은 공통 bootstrap 모듈에 둔다.

## 10. 오류 코드

```text
T033-DB-READY-016
T033-DB-ROLE-017
T033-DB-CREATE-018
T033-DB-MIGRATION-019
T033-DB-SCHEMA-020
T033-DB-SMOKE-021
T033-DB-CREDENTIAL-022
T033-DB-BACKUP-023
T033-DB-RESTORE-024
```
