# MW Photo Correction Agent — Skills (Final v4)

Claude Code / Codex 등 AI 코딩 에이전트용 운영 지침 최종본.
`AGENTS.md`는 프로젝트 헌법, `skills/*/SKILL.md`는 영역별 절차이다. 충돌 시 `AGENTS.md`가 우선한다.

v4 기준: Fable5 final v3를 베이스로 하되, Windows + Mac mini 24GB에서 Lightroom Classic과 함께 여유롭게 구동한다는 운영 기준을 반영했다. 따라서 16GB RAM은 “최소 개발 프로필”이고, 안정 운영 기본값은 Qwen2.5-VL 3B 4bit + Windows 32GB RAM/8GB VRAM 또는 Mac mini 24GB이다. Qwen3-VL 4B는 검증 후보이며, 7B/8B는 고사양 quality mode 전용이다.

## 사용 원칙

1. 모든 작업 전에 `AGENTS.md`를 읽는다.
2. 구현 영역의 `skills/*/SKILL.md`를 읽는다. 애매하면 읽는다.
3. 요청된 범위만 구현한다. 규칙과 충돌하는 요청은 구현하지 말고 멈춰서 보고한다.
4. 기능마다 테스트 또는 하네스 검증을 추가한다.
5. Mock Vision + Fake Lightroom이 통과한 뒤에만 실제 모델/Lightroom을 연결한다.
6. 모델/Lightroom/Artifact/DB 상태 전환은 항상 복구 가능해야 한다.

## Skill 목록

| Skill | 담당 영역 | 읽는 시점 |
|---|---|---|
| `project-scope` | MVP 범위, 금지 항목 | 모든 작업 시작 시 |
| `python-mvp-structure` | 폴더 구조, 레이어, 의존성 방향, 리팩터 트리거 | 파일/모듈 생성·이동 |
| `postgresql-persistence` | 테이블, 요약 테이블 4종, repository 규칙 | DB 모델/마이그레이션/쿼리 |
| `artifact-storage` | atomic write, checksum, 프라이버시 모드 | 아티팩트 저장 코드 |
| `model-security` | 로컬 전용 모델, 워커 격리, 모델/하드웨어 정책 | 모델 로딩/실행 코드 |
| `vision-analysis` | 1024px preview + EXIF → 검증된 구조화 분석 | vision/ 구현 |
| `correction-planning` | 분석 → 클램프된 보정값, requires_review | correction/ 구현 |
| `lightroom-bridge` | JSON 브리지, 절대경로, 폴링/타임아웃, delta 의미 | lightroom/, Lua plugin |
| `agent-worker-pipeline` | 상태머신 전체 + stage commit 순서 | worker.py, 상태 전환 |
| `recovery-error-handling` | 복구 규칙, 에러 코드, 재시도 | recovery.py, 에러 처리 |
| `quality-gate` | 점수·가중치·오버라이드 판정 | quality/ 구현 |
| `testing-harness` | mock/fake 우선, 스모크/복구/보안/벤치마크 하네스 | 기능 완료 판정 |
| `cli-operations` | CLI 명령, doctor 하드웨어 체크 | cli.py |
| `folder-watcher` | 파일 감지, 안정화, dedupe, ignored file 정책 | watcher.py |

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

## 모델 정책

| 구분 | 모델 | 비고 |
|---|---|---|
| **stable default** | **Qwen2.5-VL-3B-Instruct 4bit** | Windows/Mac mini 24GB + Lightroom 동시 구동 안정성 우선 |
| validation candidate | Qwen3-VL-4B 4bit | benchmark 통과 후에만 default 승격 가능, opt-in |
| quality mode only | Qwen2.5-VL-7B / Qwen3-VL-8B | 고사양 전용, MVP 기본값 금지 |
| development / CI | MockVisionBackend | 항상 먼저 통과해야 함 |

모델 파일 크기를 런타임 메모리 추정치로 사용하지 않는다. 실제 메모리 사용량은 벤치마크로 측정해야 한다.

## 하드웨어 정책

| 구분 | 기준 | 의미 |
|---|---|---|
| Minimum development | Windows RAM 16GB / VRAM 8GB | Mock 또는 constrained 3B 테스트 가능. Lightroom 동시 “여유 구동” 보장 아님 |
| Stable MVP | Windows RAM 32GB / VRAM 8GB+ 또는 Mac mini 24GB unified memory | Qwen2.5-VL 3B 4bit + Lightroom 동시 구동 목표 |
| Candidate validation | Qwen3-VL 4B 4bit | Lightroom 실행 상태에서 benchmark 통과 필요 |
| Quality profile | 7B/8B+ | 고사양 전용. Mac mini 24GB 기본값 금지 |

`mw-agent doctor`가 RAM/VRAM/unified memory와 활성 backend 적합성을 검증한다.

## Stage commit 원칙

파일시스템 write는 DB transaction 안에 들어가지 않는다. 정확한 순서는 다음이다.

```text
artifact temp write → flush/fsync → atomic rename → checksum/size 계산
→ DB transaction 시작 → task_artifacts 등록 → stage summary 저장
→ image_tasks 상태 전환 → task_event 저장 → commit
```

## Lightroom bridge 원칙

Lightroom request payload의 `source_path`, `export_path`는 normalized absolute path여야 한다. DB나 artifact index는 relative path를 저장할 수 있지만, Lua plugin으로 전달되는 경로는 작업 디렉토리에 의존하면 안 된다.


## Loop Engineering and Feedback Learning Additions

Additional required skills:

| Skill | 담당 영역 | 목적 |
|---|---|---|
| `loop-engineering` | 제품 에이전트의 자동 반복 루프 | Watch / Processing / Quality / Recovery / Feedback / Benchmark 루프의 시작, 종료, 재시도, 실패, 사람 검토 조건 정의 |
| `feedback-learning` | 사용자 피드백과 행동 기반 학습 준비 | Lightroom 수동 수정 감지, delta 저장, 사용자 평가, 학습 샘플 후보, Planner calibration, style profile 설계 |

These skills clarify that Loop Engineering is part of the product agent runtime, not a development prompt technique.
