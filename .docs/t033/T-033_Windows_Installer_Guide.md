# T-033 — Windows 설치 프로그램 가이드

## 1. 지원 범위

```text
OS: Windows 10/11 64-bit
Architecture: x64
Application model: per-user tray/background Agent
Database prerequisite: machine-level PostgreSQL service when required
```

## 2. 설치 순서

```text
verify bootstrapper Authenticode
→ detect OS/architecture
→ verify bundled application/Python payload hashes
→ detect Lightroom Classic
→ detect Tonevyra PostgreSQL instance
→ resolve/download latest stable PostgreSQL if absent
→ verify downloaded Authenticode/hash/publisher
→ elevate and install PostgreSQL
→ initialize/migrate DB
→ install application per-user
→ install Lightroom plugin if possible
→ register startup
→ launch doctor
```

## 3. 권한 경계

관리자 권한은 PostgreSQL 설치, ProgramData 쓰기, 방화벽/서비스 구성처럼 실제로 필요한 단계에서만 요청한다. Agent 실행 자체는 일반 사용자 권한으로 동작한다.

## 4. 설치 경로

```text
Application: %LOCALAPPDATA%\Programs\TonevyraAI\
Per-user config: %LOCALAPPDATA%\TonevyraAI\
Shared logs/receipts when required: %PROGRAMDATA%\TonevyraAI\
```

DB 실제 경로는 선택한 PostgreSQL 설치 프로그램의 검증된 경로와 Tonevyra install receipt에 기록한다. 경로를 추측하지 않는다.

## 5. Python

Tonevyra 실행 파일은 자체 번들 Python 3.11.9를 사용한다. 레지스트리의 Python, `py.exe`, `python.exe`, `PATH`는 설치 결정에 사용하지 않는다.

## 6. PostgreSQL 다운로드

```text
TLS required
approved final host required
stable release only
64-bit Windows artifact only
SHA-256 exact match
Authenticode signature valid
publisher exact/allowlisted
no execution on validation failure
```

## 7. 설치 결과 검사

```text
application executable signature
bundled Python 3.11.9
Agent single instance
PostgreSQL service running
DB connection and migration head
Planner API configuration present without secret leakage
Lightroom integration status
startup registration
uninstaller registration
```

## 8. 복구/제거

복구는 Tonevyra 파일과 설정만 복구한다. 기존 PostgreSQL을 무조건 재설치하지 않는다. 제거는 기본적으로 데이터베이스와 사용자 결과물을 보존한다.
