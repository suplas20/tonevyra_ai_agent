# Tonevyra AI 구현 준비 문서

버전: v2.0-tonevyra  
대상: Claude Code, Codex, 개발자, 기획자  
목적: 완료된 설계를 실제 구현 가능한 티켓, DB 계약, 검증 기준으로 전환한다.

---

## 1. 핵심 결론

Tonevyra AI는 이제 구현 단계로 넘어간다. 더 많은 기능 설계보다, 확정된 규칙을 코드가 정확히 따르는 것이 우선이다.

구현 원칙:

```text
1. 실제 Qwen과 실제 Lightroom을 먼저 붙이지 않는다.
2. Mock Vision과 Fake Lightroom으로 전체 파이프라인을 먼저 통과시킨다.
3. 모든 자동 반복 작업은 Loop Engineering 기준으로 제한된 루프로 구현한다.
4. 모든 단계는 PostgreSQL 상태, Artifact 파일, Task Event로 추적 가능해야 한다.
5. 사용자 피드백과 수동 보정 delta는 MVP부터 저장 가능한 구조로 만든다.
6. 구현 이후 DB 스키마 변경은 Alembic migration으로만 관리한다.
```

---

## 2. 구현 기준 문서 우선순위

```text
1. AGENTS.md
2. CLAUDE.md
3. 이 구현 준비 문서
4. .docs/*.md 설계 문서
5. skills/*/SKILL.md
6. harness/CONTRACT.md
```

`AGENTS.md`와 충돌하면 이 문서가 아니라 `AGENTS.md`를 우선한다.

---

## 3. 현재 확정된 구현 기준

```text
제품명: Tonevyra AI
Python package: tonevyra_agent
프로젝트 루트 예시: tonevyra_agent/
CLI: tonevyra-agent
DB: tonevyra_agent
DB app user: tonevyra_app
DB env: TONEVYRA_DATABASE_URL
```

`.env` 기본값 예시:

```env
TONEVYRA_DATABASE_URL=postgresql+psycopg://tonevyra_app:<password>@localhost:5432/tonevyra_agent
TONEVYRA_RUNTIME_DIR=runtime
TONEVYRA_INPUT_DIR=runtime/input
TONEVYRA_OUTPUT_DIR=runtime/output
TONEVYRA_ARTIFACT_DIR=runtime/artifacts
TONEVYRA_PREVIEW_DIR=runtime/previews
TONEVYRA_BRIDGE_DIR=runtime/bridge
TONEVYRA_LOG_DIR=logs
TONEVYRA_VISION_BACKEND=mock
TONEVYRA_LIGHTROOM_BACKEND=fake
```

---

## 4. 구현 기본 전략

### 4.1 Skeleton First

파일 구조, 설정, 상태값, 에러 코드, CLI 진입점을 먼저 만든다.

### 4.2 DB Persistence First

이미 생성된 `tonevyra_agent.public` DB 객체에 맞춰 SQLAlchemy 모델과 repository를 먼저 만든다.

### 4.3 Harness First

실제 모델과 실제 Lightroom 대신 Mock Vision과 Fake Lightroom을 사용한다.

### 4.4 Loop Safe First

루프는 항상 종료 조건, 재시도 제한, 실패 조건, 사람 검토 조건, 증거 기록을 가져야 한다.

### 4.5 Real Integration Later

Smoke Harness가 통과한 뒤에만 실제 Lightroom Lua Plugin과 Qwen 로컬 모델을 연결한다.

---

## 5. MVP Python 구조

```text
tonevyra_agent/
  pyproject.toml
  README.md
  .env.example
  AGENTS.md
  CLAUDE.md
  skills/
  harness/
  tests/

  src/tonevyra_agent/
    __init__.py
    main.py
    cli.py

    core/
      config.py
      enums.py
      errors.py

    agent/
      runner.py
      watcher.py
      worker.py
      recovery.py
      loops.py

    db/
      database.py
      models.py
      repositories.py

    storage/
      artifacts.py

    images/
      metadata.py
      preview.py

    vision/
      analyzer.py
      model.py
      schemas.py

    correction/
      planner.py
      schemas.py

    lightroom/
      bridge.py
      schemas.py
      plugin/
        TonevyraAI.lrplugin/
          Info.lua
          Main.lua

    quality/
      analyzer.py
      scoring.py
      schemas.py

    learning/
      feedback.py
      dataset_builder.py
      calibration.py
      schemas.py

  runtime/
    input/
    output/
      pass/
      review_required/
      failed/
    artifacts/
    previews/
    bridge/
      requests/
      processing/
      responses/
      errors/
  logs/
  models/
```

---

## 6. 현재 DB 스키마 구현 범위

이미 생성된 MVP DB 객체가 기준이다.

| 객체 | 역할 |
|---|---|
| `image_tasks` | 사진 1장 처리 상태의 source of truth |
| `task_artifacts` | 단계별 산출물 파일 경로, checksum, size, type, version |
| `task_events` | 상태 전환, 루프 이벤트, 복구 이벤트, 실패 이벤트 |
| `stage_results` | 단계별 요약, 소요시간, 성공/실패 여부 |
| `quality_results` | 품질 점수와 PASS/REVIEW_REQUIRED/FAILED 판정 |
| `feedback_records` | 사용자 피드백, AI 설정, 최종 설정, manual edit delta |
| `learning_samples` | planner calibration/style profile/future fine-tune 후보 |
| `v_task_summary` | 작업 현황 조회용 view |

다음 객체들은 현재 MVP DB에는 만들지 않는다. 필요해지면 Alembic migration으로 추가한다.

```text
jobs
images
vision_analyses
correction_plans
lightroom_requests
manual_edit_records
style_profiles
training_samples
```

현재는 해당 상세 데이터가 `stage_results`, `task_artifacts`, `feedback_records`, `learning_samples`로 처리된다.

---

## 7. Artifact와 JSON 계약

필수 artifact:

```text
exif.json
preview.jpg
vision_prompt.txt
vision_raw_response.json
vision_structured.json
correction_plan.json
lightroom_request.json
lightroom_response.json
quality_detail.json
retry_history.json
loop_trace.json
user_feedback.json
manual_edit_delta.json
```

Artifact 저장 순서:

```text
1. temp file write
2. flush/fsync
3. atomic rename
4. sha256/size 계산
5. task_artifacts 등록
6. stage_results/task_events/image_tasks 업데이트
7. commit
```

---

## 8. Loop Engineering 구현 규칙

모든 자동 루프는 다음 필드를 설계 문서나 코드 상수로 명시한다.

```text
loop_name
entry_condition
allowed_actions
state_transitions
retry_limit
timeout
exit_condition
failure_condition
human_review_condition
persisted_evidence
harness_verification
```

현재 DB에는 loop 전용 컬럼이 없으므로 MVP에서는 `task_events.payload_json`에 아래 값을 기록한다.

```json
{
  "loop_name": "processing_loop",
  "loop_iteration": 1,
  "from_status": "ANALYZING",
  "to_status": "ANALYSIS_DONE",
  "reason": "vision_structured artifact saved"
}
```

대시보드/분석 쿼리가 필요해지면 Alembic migration으로 `task_events` 전용 컬럼을 승격한다.

---

## 9. Feedback Learning 구현 규칙

MVP에서 모델을 직접 학습시키지 않는다. 대신 다음 데이터를 로컬에 저장한다.

```text
AI 적용 보정값
AI 적용 직후 Develop Settings hash
사용자가 Lightroom에서 수정한 현재 Develop Settings
AI 값과 사용자 값의 delta
사용자 평가: 그대로 사용 / 수동 수정 / 다시 보정 / 실패
학습 사용 승인 여부
```

저장 위치:

```text
feedback_records
learning_samples
task_artifacts: AI_SETTINGS, FINAL_SETTINGS, MANUAL_EDIT_DELTA, FEEDBACK_RECORD
```

학습 순서:

```text
1. 피드백 데이터 저장
2. Correction Planner calibration
3. 사용자 스타일 프로파일
4. 오프라인 opt-in 모델 fine-tuning
```

---

## 10. 구현 티켓 목록

| 티켓 | 작업 | 완료 기준 |
|---|---|---|
| T-001 | Project Bootstrap + DB Persistence Foundation | doctor가 DB와 테이블 확인, smoke CRUD 통과 |
| T-002 | ArtifactStorage Foundation | atomic write/checksum/task_artifacts 등록 |
| T-003 | Folder Watcher + Stabilizer | supported image task 생성, ignored file 무시 |
| T-004 | Preview/metadata | EXIF/preview artifact 생성 |
| T-005 | Mock Vision | fixture 기반 structured analysis 저장 |
| T-006 | Correction Planner | correction_plan artifact 생성 |
| T-007 | Fake Lightroom Bridge | request/response/export fake 처리 |
| T-008 | Quality Gate | quality_detail + quality_results 저장 |
| T-009 | Worker Pipeline | 사진 1장 end-to-end 최종 상태 도달 |
| T-010 | Recovery Loop | seeded incomplete state 안전 재개 |
| T-011 | Loop Event Verification | task_events.payload_json loop evidence 검증 |
| T-012 | Feedback Storage | feedback_records/learning_samples 저장 검증 |
| T-013 | Real Lightroom Lua PoC | 실제 PING/request/export 성공 |
| T-014 | Qwen Local Backend | local-only 분석 성공 |
| T-015 | Model Benchmark Loop | Qwen3 4B 승격 여부 판단 데이터 |

---

## 11. T-001 구현 프롬프트

```text
Read AGENTS.md first.
Then read CLAUDE.md.
Then read .docs/implementation/Tonevyra_AI_Implementation_Readiness_Agent_v2.md.

Implement T-001 only: Project Bootstrap + DB Persistence Foundation.

Do not implement real Qwen.
Do not implement real Lightroom.
Do not implement React, FastAPI, Redis, Celery, MinIO, dashboard, or worker pool.

Use Python 3.11.
Use package name src/tonevyra_agent.
Use CLI command tonevyra-agent.
Use TONEVYRA_DATABASE_URL.

Connect to existing PostgreSQL:
- database: tonevyra_agent
- user: tonevyra_app
- schema: public

Implement:
- config loading
- enums/errors
- SQLAlchemy session
- ORM models matching existing tables
- repositories for all current MVP tables
- doctor command
- DB smoke CRUD script or command

Doctor must verify:
- Python version
- runtime folder existence
- PostgreSQL connection
- current_database() = tonevyra_agent
- current_user = tonevyra_app
- required tables exist

Report changed files, run commands, doctor result, assumptions.
```

---

## 12. MVP 완료 체크리스트

```text
[ ] input 폴더 사진 감지
[ ] 파일 안정화 확인
[ ] PostgreSQL image_tasks 생성
[ ] 1024px preview 생성
[ ] Mock Vision 구조화 분석
[ ] correction_plan 생성
[ ] Lightroom request 생성
[ ] Fake Lightroom export 생성
[ ] Quality Gate 판정
[ ] 최종 PASS / REVIEW_REQUIRED / FAILED 저장
[ ] 필수 artifact 저장
[ ] task_artifacts metadata 검증
[ ] Recovery Harness 통과
[ ] Security Harness 통과
[ ] Loop Event 검증 통과
[ ] Feedback 저장 구조 검증 통과
[ ] 실제 Lightroom PoC 통과
[ ] Qwen local-only backend 통과
```

---

## 13. 지금 하지 말아야 할 것

```text
React Dashboard 상세 구현
FastAPI-first 구조
SaaS 계정/권한
Redis/Celery/Worker Pool
MinIO/S3 전환
Qwen fine-tuning 자동화
블로그/인스타/홈페이지 자동화
상용 결제/라이선스 시스템
```

---

## 14. 최종 구현 목표

첫 번째 구현 목표는 다음 한 문장이다.

> 사진 1장을 Mock Vision과 Fake Lightroom으로 끝까지 처리해 최종 상태와 모든 증거 데이터를 남기는 것.

이 목표가 달성되면 실제 Lightroom과 실제 Qwen을 연결한다.
