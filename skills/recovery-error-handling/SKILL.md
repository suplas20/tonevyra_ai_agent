---
name: recovery-error-handling
description: Crash recovery rules, the structured error-code registry, and retry policy. Use this skill when implementing agent/recovery.py, designing or adding error codes, changing task state transitions, handling Lightroom/plugin failures, or writing recovery harness tests. Recovery is an acceptance requirement — always consult before changing startup or failure recording.
---

# Recovery & Error Handling

## Recovery source

로그로 복구하지 않는다. 복구 근거: PostgreSQL task 상태, task_artifacts 레코드,
아티팩트 파일 존재, checksum, Lightroom response 파일, export 파일 존재.

## Startup recovery flow

```text
1 single-agent lock 획득            5 checksum 검증 (가능한 곳)
2 PostgreSQL 연결                   6 bridge response + export 파일 확인
3 non-terminal task 조회            7 가장 안전한 유효 stage에서 재개
4 아티팩트 레코드/실파일 검증       8 corrupted/missing 아티팩트 마킹 (CORRUPTED/MISSING)
```

복구는 신규 작업 수락 전에 실행된다. 각 재개는 RECOVERY_RESUMED task_event를 남긴다.

## Recovery rules (마지막 영속 상태 기준)

```text
ANALYZING + vision_structured READY          → correction planning부터 재개
ANALYZING + vision 아티팩트 없음             → vision 분석 재실행
CORRECTION_PLANNED + plan READY              → Lightroom request부터 재개
LIGHTROOM_REQUESTED/PROCESSING + response 有 → response 처리
LIGHTROOM_REQUESTED/PROCESSING + response 無 → 남은 timeout으로 폴링 재개;
                                               processing/의 timeout 초과 stale 파일은
                                               재요청 또는 retry 정책 따라 실패
EXPORT_DONE + export 파일 존재               → quality check부터 재개
EXPORT_DONE + export 파일 없음               → EXPORT_FILE_MISSING → 재export 또는 FAILED
QUALITY_CHECK + quality_detail 존재          → 게이트 결과로 finalize
최종 PASS인데 export 파일 없음               → FAILED 처리 또는 재export 스케줄
```

## Error code registry (core/errors.py 단일 등록)

```text
FILE_NOT_STABLE  UNSUPPORTED_FILE_TYPE  PREVIEW_GENERATION_FAILED
MODEL_LOAD_FAILED  MODEL_INFERENCE_FAILED  MODEL_OUTPUT_INVALID  GPU_OOM
CORRECTION_PLAN_FAILED  LIGHTROOM_REQUEST_FAILED  LIGHTROOM_RESPONSE_TIMEOUT
LIGHTROOM_EXPORT_FAILED  EXPORT_FILE_MISSING  QUALITY_CHECK_FAILED
ARTIFACT_WRITE_FAILED  ARTIFACT_CORRUPTED  DB_WRITE_FAILED
SECURITY_NETWORK_ACCESS_BLOCKED
```

`GPU_OOM`: 추론 OOM은 runner를 죽이지 않는다 — 작은 backend로 강등 시도 후 실패 시 이 코드로 FAILED.

## Failed task must store

error_code, error_message, failed_stage, retry_count, updated_at.

## Retry policy

`max_retry_count = 2` (config). 무한 재시도 금지.
- transient (IO, timeout, 강등 후 OOM) → backoff 재시도.
- 검증 실패 (schema-invalid plan/JSON 등) → 재시도 없이 즉시 실패.

## Guardrails

- recovery는 idempotent: 두 번 실행해도 두 번째는 아무것도 바꾸지 않는다.
- 두 번째 agent 인스턴스는 lock(PID 파일 또는 DB lock 행)을 감지하고 기동을 거부한다.
- "fresh start"로 recovery를 건너뛰지 않는다. non-terminal task를 조용히 버리지 않는다.

## Acceptance criteria

하네스가 최소 ANALYZING, LIGHTROOM_REQUESTED, EXPORT_DONE, QUALITY_CHECK 중단을 커버;
corrupted 아티팩트와 missing export 감지; retry count가 루프를 제한;
로그 없이 복구 가능; 이중 기동 차단.

## T-032 API Recovery

Classify transport timeout/408/429/5xx as bounded transient failures. Treat auth, schema, privacy, digest, version, and idempotency conflict as non-blind-retry failures. Resume from the persisted Planner request and stable idempotency key; never regenerate a different payload under the same key.
