# T-028 — Production Reliability and Agent Operations 작업 지시서

## 1. 문서 상태

```text
Ticket: T-028
Title: Production Reliability and Agent Operations
Baseline: T-027 구현 및 하네스 통과본
Primary goal: Agent·모델·Lightroom·Plugin·파일 시스템 장애가 발생해도 작업을 추적하고 안전하게 재개하며 중복 실행을 방지하는 운영 안정성을 완성한다.
```

## 2. 한 문장 목표

> 모든 주요 단계에 durable checkpoint와 idempotency 경계를 두고, crash·timeout·stale lock·중복 명령·부분 완료를 복구하며, 운영자가 상태와 원인을 판단할 수 있는 로그·메트릭·알림을 제공한다.

## 3. 핵심 원칙

1. 성공 응답보다 실제 artifact와 DB evidence를 신뢰한다.
2. 재시작 후 마지막 안전 checkpoint에서 재개한다.
3. apply/export/usage commit은 idempotency key로 중복 실행을 방지한다.
4. lock과 lease에는 owner, acquired_at, expires_at, heartbeat가 필요하다.
5. 무한 재시도와 무한 대기를 금지한다.
6. 자동 복구 가능한 오류와 운영자 조치가 필요한 오류를 구분한다.
7. 원본과 완료 artifact는 복구 과정에서 덮어쓰지 않는다.
8. 운영 관측성 때문에 이미지나 개인정보를 외부로 전송하지 않는다.
9. 단일 worker 기준 안정화를 먼저 완료하고 분산화를 가정하지 않는다.

## 4. 포함 범위

```text
durable checkpoint
job lease / heartbeat / stale lock recovery
idempotent command dispatch
outbox-like pending command persistence
crash restart recovery
Lightroom unavailable handling
model worker unavailable handling
file/DB partial commit reconciliation
timeout and circuit-break policy
dead-letter/manual intervention classification
structured logs
metrics and health checks
incident events
operator CLI for inspect/retry/cancel/resume
soak/endurance test
backup/restore verification for metadata
```

## 5. 제외 범위

```text
Kubernetes 또는 분산 오케스트레이션
다중 리전 복제
클라우드 전용 모니터링 종속
자동 영구 삭제
무제한 worker pool
```

## 6. Checkpoint 계약

```text
checkpoint_id
job_id
attempt_id
stage
state
input_checksums
output_checksums
pending_command
idempotency_key
lease_owner
created_at
committed_at
```

checkpoint는 실제 완료 evidence가 검증된 후 commit한다. 상태만 먼저 전진시키지 않는다.

## 7. Idempotency 경계

필수 경계:

```text
analysis request
adjustment plan creation
Lightroom apply request
Lightroom export request
artifact registration
quality decision
usage ledger commit
```

동일 key 재요청은 기존 성공 결과를 반환하거나 안전하게 현재 상태를 알려야 하며, 동일 작업을 다시 실행해서는 안 된다.

## 8. 장애 분류

```text
TRANSIENT: bounded retry 가능
RECOVERABLE_RESTART: checkpoint 재개
MANUAL_INTERVENTION: 운영자 확인 필요
TERMINAL: 정책상 종료
```

예:

```text
model timeout → transient
Lightroom process restart → recoverable restart
checksum mismatch → manual intervention 또는 technical failed
source missing → terminal/manual policy
```

## 9. 관측성

필수 구조화 필드:

```text
correlation_id
job_id
attempt_id
batch_id optional
stage
component
provider
plan
error_code
duration_ms
retry_count
artifact/checkpoint reference
```

메트릭은 최소 다음을 포함한다.

```text
queue depth
active job
stage latency
technical failure rate
quality retry rate
model memory/latency
Lightroom availability
stale lease count
recovery success rate
```

## 10. 운영 CLI

초기 CLI 범위:

```text
inspect job
inspect checkpoint
resume job
retry technical failure
cancel job
release stale lease
reconcile artifacts
show health
```

위험한 명령은 dry-run과 확인 옵션을 제공하고 audit event를 남긴다.

## 11. 장시간 검증

```text
반복 batch 실행
의도적 model/Lightroom 종료
프로세스 재시작
디스크 공간 부족 시뮬레이션
DB 연결 끊김
중복 이벤트 주입
stale lock
부분 파일 생성
```

복구 후 중복 apply/export/usage commit이 없어야 한다.

## 12. 구현 단계

### Phase A — Checkpoint/lease/idempotency
- stage별 durable checkpoint
- lease heartbeat와 stale recovery
- command idempotency

### Phase B — Reconciliation/recovery
- DB/artifact 부분 commit 탐지
- restart resume와 operator intervention

### Phase C — Observability/CLI
- structured logs, metrics, health
- inspect/resume/cancel/reconcile CLI

### Phase D — Soak/release readiness
- fault injection
- 장시간 실행과 복구율 검증
- 운영 runbook은 실제 운영 절차에 필요한 범위에서만 작성

## 13. 하네스 필수 검증

1. crash 후 마지막 안전 checkpoint에서 재개한다.
2. 동일 idempotency key의 apply/export가 중복 실행되지 않는다.
3. stale lease를 안전하게 회수한다.
4. 부분 파일·DB commit을 reconciliation한다.
5. timeout/retry가 bounded하다.
6. manual intervention과 terminal 실패가 구분된다.
7. usage ledger 중복 commit을 방지한다.
8. 구조화 로그와 핵심 메트릭이 존재한다.
9. operator CLI가 audit event를 남긴다.
10. fault injection 후 artifact 무결성을 유지한다.
11. T-019~T-027 회귀 계약을 유지한다.

## 14. 완료 기준

- 주요 단계가 durable checkpoint와 idempotency key를 가진다.
- Agent/Lightroom/model 프로세스 재시작 후 작업이 안전하게 재개된다.
- 중복 보정·익스포트·사용량 commit이 발생하지 않는다.
- stale lock과 partial commit이 자동 또는 운영자 절차로 해결된다.
- 로그·메트릭·health·CLI로 장애 원인을 추적할 수 있다.
- 장시간 fault-injection 하네스를 통과한다.
- 출시 후보가 T-026 benchmark와 전체 회귀 gate를 함께 통과한다.

## 15. 티켓 종료 경계

T-028 완료는 현재 정의된 에이전트 제품화 티켓 T-021~T-028의 기능·품질·운영 기준이 연결되었음을 의미한다. 결제, 조직 관리, 분산 인프라, 엔터프라이즈 보안은 후속 별도 티켓으로 분리한다.
