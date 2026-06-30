# T-030 문서·하네스·스킬 업데이트 보고서

## 1. 업데이트 대상

```text
Ticket: T-030
Title: Windows Background Watcher and System Tray Agent
Baseline archive: tonevyra_ai_agent.zip
Baseline SHA-256: 99d4b438e41f43fe993a4b4bd9e0a89e0681c24e3ab6849e3a188f58c172f2fe
Update date: 2026-06-29
```

## 2. 적용 결과

기존 파일을 삭제하거나 이름을 바꾸지 않고 additive 방식으로 T-030 문서, 하네스, fixture, schema, 검증 스크립트, 스킬을 추가했다.

```text
Removed baseline files: 0
Added files: 34
Modified existing files: 22
Baseline preserved: YES
```

## 3. T-030 핵심 설계

```text
Windows per-user Tray Shell
→ single-instance guard
→ Background Worker supervision
→ continuous folder watcher
→ event coalescing
→ size/mtime/read-probe stability gate
→ PostgreSQL idempotent task registration
→ existing Tonevyra processing pipeline
```

제품 계약에 다음을 명시했다.

```text
- Windows Service 금지
- Tray UI의 비즈니스 로직 소유 금지
- SQLite operational queue/fallback 금지
- 복사 중 파일 처리 금지
- 입력/출력 재귀 처리 금지
- 원본 덮어쓰기·삭제·이동 금지
- main model/Lightroom concurrency=1 유지
- Worker heartbeat/restart bounded
- 종료 후 orphan process 금지
```

## 4. 추가 문서

```text
.docs/t030/T-030_Windows_Background_Watcher_and_Tray_Agent_Work_Order.md
.docs/t030/T-030_Implementation_Specification.md
.docs/t030/T-030_Codex_Prompt.md
.docs/t030/T-030_Windows_Live_Test_Checklist.md
.docs/t030/T-030_Tray_Icon_Asset_Guide.md
```

`AGENTS.md`, `CLAUDE.md`, PRD, 시스템 아키텍처, 상태 머신, watcher, CLI, recovery, QA, roadmap, implementation readiness/work order를 함께 갱신했다.

## 5. 스킬 업데이트

T-029 기준 43개 스킬을 모두 유지하고 2개를 추가했다.

```text
Added:
- windows-background-agent-lifecycle
- system-tray-operations

Updated:
- agent-worker-pipeline
- folder-watcher
- production-reliability-operations
- resumable-idempotent-jobs
- testing-harness

Required total: 45 SKILL.md files
Actual total: 45 SKILL.md files
```

권위 있는 inventory:

```text
skills/T030_SKILL_INVENTORY.json
```

## 6. 하네스 업데이트

```text
harness/CONTRACT_T030_WINDOWS_BACKGROUND_TRAY.md
harness/HARNESS_ENV_T030_WINDOWS_BACKGROUND_TRAY.example
harness/schemas/t030_agent_runtime_snapshot.schema.json
harness/schemas/t030_watch_event.schema.json
harness/schemas/t030_tray_command.schema.json
harness/schemas/t030_runtime_evidence.schema.json
harness/schemas/t030_windows_live_evidence.schema.json
harness/fixtures/t030_background_tray/
harness/scripts/verify_t030_windows_background_tray.py
harness/scripts/run_t030_background_tray_reference.py
harness/prompts/10_t030_windows_background_tray_prompt.md
```

Strict gate는 다음 둘을 모두 요구한다.

```text
1. evidence_source=implementation인 실제 구현 runtime evidence
2. 실제 Windows 사용자 세션에서 작성한 live evidence
```

Reference harness는 계약과 fixture를 검증하지만 실제 트레이 구현 완료 증거로 인정하지 않는다.

## 7. 검증 결과

실행한 검증:

```text
python harness/scripts/verify_t030_windows_background_tray.py --project-root .
python harness/scripts/run_t030_background_tray_reference.py --project-root . --output-dir /mnt/data/t030_reference_evidence
python harness/scripts/verify_t030_windows_background_tray.py --project-root . --runtime-evidence /mnt/data/t030_reference_evidence/t030_runtime_evidence.json
```

결과:

```text
Static contract and fixtures: PASS
Reference runtime evidence: PASS
Strict Windows implementation gate: NOT RUN
```

실제 Windows Tray/Worker 코드는 이 문서 패키지에 구현되지 않았으므로 strict gate를 통과했다고 주장하지 않는다.

## 8. 로고 자산 상태

업로드된 baseline archive에는 승인된 SVG, 투명 고해상도 PNG, ICO 로고 원본이 포함되어 있지 않다. 대화에 제공된 화면 캡처는 production icon source로 사용하지 않도록 문서화했다.

따라서 Codex 구현 시 실제 승인 로고 원본이 저장소에 추가되지 않으면 생산 완료 상태는 다음으로 차단된다.

```text
BLOCKED_TRAY_ICON_ASSET_MISSING
```

기능 개발용 임시 아이콘은 허용되지만 최종 완료 증거가 될 수 없다.

## 9. 주요 차단 코드

```text
BLOCKED_TRAY_ICON_ASSET_MISSING
BLOCKED_WINDOWS_SESSION_TEST_UNAVAILABLE
BLOCKED_SINGLE_INSTANCE_PRIMITIVE
BLOCKED_WORKER_RECOVERY_REGRESSION
BLOCKED_WATCH_PATH_PERMISSION
```

## 10. 보존 결과

Removed files:

```text
(none)
```

기존 T-029 및 이전 하네스·스킬·문서는 삭제하지 않았다.
