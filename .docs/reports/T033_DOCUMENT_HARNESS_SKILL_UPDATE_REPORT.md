# T-033 문서·하네스·스킬 업데이트 보고서

## 기준

```text
Baseline: T-032
Baseline skills: 51
Added T-033 skills: 7
T-033 cumulative total: 58
```

기존 51개 스킬과 기존 파일을 삭제·병합·이름 변경하지 않았다. 이번 개정은 신규 스킬 수를 늘리지 않고 기존 T-033 설치 스킬과 계약을 올인원 설치 기준으로 강화했다.

## 확정 배포 및 설치 정책

```text
사용자 경험: 설치 파일 실행 → OS 관리자 승인 → 설치 1회 클릭 → 전체 자동 구성 → 실행
Python 3.11.9: installer/application payload에 내장
PostgreSQL installer: 내장하지 않음
PostgreSQL: 설치 시 latest approved stable GA 다운로드 + 서명/해시 검증 + 무인 설치
DB: Role/Database 생성, Alembic migration, 스키마/권한/RW 검증 자동 수행
DB credential: Windows DPAPI/Credential Manager, macOS Keychain
Lightroom Classic: 외부 사용자 관리, 설치 여부만 검사
Lightroom plugin: 가능하면 자동 설치, 미설치 시 PENDING
Windows: signed installer
macOS: signed + notarized + stapled package
```

## 올인원 설치 하드 게이트

```text
manual_prerequisite_steps = 0
manual_database_steps = 0
postgres_unattended_install = true
database_bootstrap_automatic = true
alembic_head_verified = true
required_schema_objects_verified = true
agent_startup_registered = true
post_install_doctor_passed = true
```

## 추가 문서

```text
.docs/t033/T-033_All_In_One_Installer_Orchestration.md
.docs/t033/T-033_Database_Bootstrap_and_Schema_Automation.md
```

기존 T-033 작업지시서, 구현 명세, Windows/macOS 가이드, 체크리스트 및 Codex 프롬프트도 동일 정책으로 갱신했다.

## 갱신 스킬

```text
cross-platform-installer-packaging
postgresql-bootstrap-installation
installer-upgrade-repair-uninstall
project-scope
```

## 하네스 추가

```text
harness/schemas/t033_all_in_one_install_evidence.schema.json
harness/schemas/t033_database_bootstrap_evidence.schema.json
harness/fixtures/t033_installer/valid_all_in_one_install_evidence.json
harness/fixtures/t033_installer/valid_database_bootstrap_evidence.json
harness/fixtures/t033_installer/invalid_manual_database_install_evidence.json
harness/scripts/verify_t033_all_in_one_install.py
```

## 완료 주의

현재 산출물은 T-033 구현을 위한 문서·하네스·스킬 계약이다. 실제 설치 프로그램, PostgreSQL 무인 설치, 자동 DB bootstrap, Windows 서명, macOS 공증 및 실장비 증거가 생성되기 전에는 T-033 strict 완료가 아니다.

## 파일 보존 결과

```text
원본 파일 수: 465
최종 파일 수: 473
신규 파일 수: 8
삭제 파일 수: 0
최종 스킬 수: 58
```
