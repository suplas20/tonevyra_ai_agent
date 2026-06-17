# Tonevyra AI Agent — Skills (Final v4.1 Update)

Claude Code / Codex 등 AI 코딩 에이전트용 운영 지침이다.  
`AGENTS.md`는 프로젝트 헌법, `skills/*/SKILL.md`는 영역별 절차이다. 충돌 시 `AGENTS.md`가 우선한다.

이번 업데이트는 기존 v4 내용을 갈아엎지 않고 다음 불일치를 정리한다.

```text
MW/mw_photo_agent 명칭 잔존 → Tonevyra/tonevyra_agent 기준으로 정리
하네스 개념 → 단순 mock 환경이 아니라 스킬 이행 검증/감시 장치로 명확화
모델 정책 → 기술 검증 default와 commercial release default 후보를 분리
Loop Engineering → 자동 에이전트 루프의 bounded/evidence 규칙으로 정리
Feedback Learning → learning_samples 기준으로 통일
```

## 사용 원칙

1. 모든 작업 전에 `AGENTS.md`를 읽는다.
2. 구현 영역의 `skills/*/SKILL.md`를 읽는다. 애매하면 읽는다.
3. 요청된 범위만 구현한다. 규칙과 충돌하는 요청은 구현하지 말고 멈춰서 보고한다.
4. 기능마다 테스트 또는 하네스 검증을 추가한다.
5. Mock Vision + Fake Lightroom이 통과한 뒤에만 실제 모델/Lightroom을 연결한다.
6. 모델/Lightroom/Artifact/DB 상태 전환은 항상 복구 가능해야 한다.
7. 자동 에이전트 루프는 `task_events`에 loop evidence를 남긴다.

## Skill 목록

| Skill | 담당 영역 | 읽는 시점 |
|---|---|---|
| `project-scope` | MVP 범위, 금지 항목 | 모든 작업 시작 시 |
| `python-mvp-structure` | 폴더 구조, 레이어, 의존성 방향, 리팩터 트리거 | 파일/모듈 생성·이동 |
| `postgresql-persistence` | 테이블, 요약 뷰, repository 규칙, task event evidence | DB 모델/마이그레이션/쿼리 |
| `artifact-storage` | atomic write, checksum, 프라이버시 모드 | 아티팩트 저장 코드 |
| `model-security` | 로컬 전용 모델, 워커 격리, 모델/하드웨어 정책 | 모델 로딩/실행 코드 |
| `local-model-security` | runtime offline, telemetry 차단, 모델 파일 경계 | 모델 backend 보안 구현 |
| `vision-analysis` | 1024px preview + EXIF → 검증된 구조화 분석 | vision/ 구현 |
| `correction-planning` | 분석 → 클램프된 보정값, sticky requires_review | correction/ 구현 |
| `correction-planner` | correction-planning의 legacy 요약 문서 | 기존 티켓 호환용 |
| `lightroom-bridge` | JSON 브리지, 절대경로, 폴링/타임아웃, delta 의미 | lightroom/, Lua plugin |
| `agent-worker-pipeline` | 상태머신 전체 + stage commit 순서 | worker.py, 상태 전환 |
| `recovery-error-handling` | 복구 규칙, 에러 코드, 재시도 | recovery.py, 에러 처리 |
| `recovery-loop` | recovery_loop evidence와 복구 artifact | recovery harness 구현 |
| `quality-gate` | 점수·가중치·오버라이드 판정 | quality/ 구현 |
| `testing-harness` | 스킬 이행 검증, mock/fake 우선, smoke/recovery/security/benchmark 하네스 | 기능 완료 판정 |
| `cli-operations` | CLI 명령, doctor 하드웨어 체크, feedback/benchmark 명령 | cli.py |
| `folder-watcher` | 파일 감지, 안정화, dedupe, ignored file 정책 | watcher.py |
| `feedback-learning` | 사용자 피드백, 수동 수정 delta, learning sample 준비 | feedback/learning 구현 |
| `loop-engineering` | bounded autonomous loop, event evidence, timeout/retry 종료 조건 | agent loop 구현/검증 |
| `model-benchmark-loop` | 모델 후보 benchmark, 승격 증거, rollback | backend 후보 검증 |

## 공통 가드레일

- React UI/대시보드, 블로그·인스타·홈페이지 기능은 MVP에서 만들지 않는다.
- 메인 DB는 PostgreSQL 고정. SQLite 대체 금지.
- 이미지 바이너리·무거운 payload는 DB 저장 금지 → Artifact Storage.
- 디버그 trace는 파일 로그에만. 복구는 DB + artifact + checksum으로 한다.
- 모델은 분석만 한다. 직접 편집·Correction Planner 우회·Lightroom 직접 제어 금지.
- 어떤 사용자 데이터도 외부로 전송하지 않는다.
- MVP 모델 입력: 1024px sRGB JPEG preview + EXIF/basic metadata.
- Deferred: 2048px preview, subject/multi-crop, multi-view, Lightroom neutral preview, 상위 모델 기본값화.
- 아티팩트 영속화와 crash recovery는 어떤 단계에서도 생략 불가.
- Worker 동시성 = 1.
- 하네스 통과 전 완료 처리 금지.

## 모델 정책

모델 정책은 두 층으로 분리한다.

```text
1. 기술 검증 default: 로컬/private MVP에서 안정적으로 돌아가는 후보
2. commercial release default: 라이선스 검토와 benchmark까지 통과한 후보
```

| 구분 | 모델 | 비고 |
|---|---|---|
| development / CI | MockVisionBackend | 항상 먼저 통과해야 함 |
| technical stable candidate | Qwen2.5-VL-3B-Instruct 4bit | Windows/Mac mini 24GB + Lightroom 동시 구동 안정성 검증 후보. commercial default는 별도 license review 필요 |
| commercial default candidate | Qwen3-VL-4B-Instruct 4bit/GGUF | benchmark + license review 통과 후에만 default 승격 가능, opt-in |
| quality mode only | Qwen2.5-VL-7B / Qwen3-VL-8B 이상 | 고사양 전용, MVP 기본값 금지 |

모델 파일 크기를 런타임 메모리 추정치로 사용하지 않는다. 실제 메모리 사용량은 벤치마크로 측정해야 한다.

## 하드웨어 정책

| 구분 | 기준 | 의미 |
|---|---|---|
| Minimum development | Windows RAM 16GB / VRAM 8GB | Mock 또는 constrained 3B 테스트 가능. Lightroom 동시 “여유 구동” 보장 아님 |
| Stable MVP | Windows RAM 32GB / VRAM 8GB+ 또는 Mac mini 24GB unified memory | 3B/4B급 4bit backend + Lightroom 동시 구동 목표 |
| Candidate validation | Qwen3-VL 4B 4bit/GGUF | Lightroom 실행 상태에서 benchmark 통과 필요 |
| Quality profile | 7B/8B+ | 고사양 전용. Mac mini 24GB 기본값 금지 |

`tonevyra-agent doctor` 또는 `python -m tonevyra_agent.cli doctor`가 RAM/VRAM/unified memory와 활성 backend 적합성을 검증한다.

## Stage commit 원칙

파일시스템 write는 DB transaction 안에 들어가지 않는다. 정확한 순서는 다음이다.

```text
artifact temp write → flush/fsync → atomic rename → checksum/size 계산
→ DB transaction 시작 → task_artifacts 등록 → stage summary 저장
→ image_tasks 상태 전환 → task_event 저장 → commit
```

## Lightroom bridge 원칙

Lightroom request payload의 `source_path`, `export_path`는 normalized absolute path여야 한다. DB나 artifact index는 relative path를 저장할 수 있지만, Lua plugin으로 전달되는 경로는 작업 디렉토리에 의존하면 안 된다.

## Loop Engineering and Harness

Loop Engineering은 “가상 환경 만들기”가 아니라, 자동 에이전트가 반복 행동을 할 때 다음을 강제하는 제어 방식이다.

```text
명시적 loop_name
loop_iteration
retry / timeout / exit condition
DB + artifact 근거
task_events evidence
```

하네스는 이 규칙이 실제 구현에 반영되었는지 검사한다. 즉, 하네스는 에이전트가 스킬과 계약을 우회하지 못하도록 만드는 검증 장치다.

## Acceptance 기준

기능 완료는 다음이 모두 참일 때만 인정한다.

```text
관련 skill 문서 기준 충족
단위 테스트 또는 harness 통과
Mock Vision + Fake Lightroom에서 재현 가능
PostgreSQL 상태와 artifact checksum 일관
task_events에 필요한 loop evidence 존재
security harness 통과
scope 밖 기능 없음
```
