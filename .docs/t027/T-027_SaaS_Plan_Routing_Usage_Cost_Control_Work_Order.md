# T-027 — SaaS Plan Routing, Usage and Cost Control 작업 지시서

## 1. 문서 상태

```text
Ticket: T-027
Title: SaaS Plan Routing, Usage and Cost Control
Baseline: T-026 구현 및 하네스 통과본
Primary goal: Free/Lite/Standard/Pro 정책을 실제 작업 라우팅·쿼터·자원·재시도·사용량 원장에 일관되게 적용한다.
```

## 2. 한 문장 목표

> 하나의 Agent Core에서 플랜별 Provider, batch 크기, 해상도, 재시도, 우선순위, 자원 예산을 정책으로 결정하고, 모든 사용량을 중복 없이 감사 가능한 ledger event로 기록한다.

## 3. 핵심 원칙

1. 플랜 정책은 코드 곳곳의 조건문이 아니라 버전이 있는 Policy 객체에서 결정한다.
2. Free/Lite 품질을 의도적으로 낮추지 않는다.
3. 플랜 차이는 Provider capability, 처리량, batch, retry depth, 출력 기능, 우선순위에서 만든다.
4. 쿼터 검사와 사용량 차감은 idempotent해야 한다.
5. 재시도 때문에 동일 작업을 중복 과금하지 않는다.
6. 기술 실패·사용자 취소·품질 재시도의 사용량 처리 규칙을 명시한다.
7. 정책 누락 또는 불일치는 fail-closed로 처리한다.
8. T-027은 결제 대행사 연동이나 실제 청구서 발행을 구현하지 않는다.

## 4. 포함 범위

```text
PlanPolicy registry
plan versioning
provider routing
quality retry limits
batch size / resolution limits
concurrency and priority policy
monthly usage quota
GPU/model resource budget
usage reservation / commit / release
idempotent usage ledger
fallback/degraded mode accounting
admin override audit
quota exceeded handling
cost telemetry and estimate
```

## 5. 제외 범위

```text
결제 카드 처리
세금·청구서
구독 UI
조직·SSO
대규모 멀티테넌트 스케줄러
동적 가격 최적화
```

## 6. Plan Policy 계약

```text
plan_id
version
status
analysis_provider
quality_provider
max_quality_retries
max_batch_size
max_input_megapixels
output_capabilities
priority_class
monthly_photo_quota
model_resource_budget
fallback_policy
```

정책 변경은 새 version을 만들고 작업 시작 시 snapshot을 저장한다. 실행 중 정책이 바뀌어도 해당 job의 snapshot은 유지한다.

## 7. 초기 플랜 원칙

```text
free     → module/module, bounded monthly quota, retry 1
lite     → module/module, larger quota/batch, retry 1~2
standard → model/model, full-resolution policy, retry 2
pro      → advanced model policy, set/style features, retry 3
```

실제 수치와 상용 가격은 별도 제품 결정으로 설정한다. 하네스는 구조와 경계값을 검증한다.

## 8. Usage Ledger

이벤트 상태:

```text
RESERVED → COMMITTED
         → RELEASED
```

필수 식별자:

```text
usage_event_id
idempotency_key
user_scope_id
job_id
batch_id optional
plan_id/version
units
resource_metrics
reason
```

동일 idempotency key의 중복 commit은 한 번만 반영한다.

## 9. 실패와 사용량 처리

정책 예시:

```text
사용자 제출 후 처리 시작 전 취소 → reservation release
Agent/Plugin technical failure → 정책에 따라 release 또는 비과금 기록
quality retry → 동일 photo unit, 추가 compute metric만 기록
완료 결과 → commit
fallback → requested/executed provider와 degraded mode 기록
```

과금 여부와 운영 비용 측정을 분리해 기록한다.

## 10. 보안과 격리

- user scope별 quota와 ledger를 분리한다.
- 클라이언트가 제출한 plan 값을 신뢰하지 않는다.
- 서버/로컬 정책 저장소의 활성 정책으로 검증한다.
- admin override는 이유, 주체, 만료, audit event가 필요하다.

## 11. 구현 단계

### Phase A — Policy registry
- versioned policy와 snapshot
- Plan Router 단일 진입점

### Phase B — Quota/ledger
- reserve/commit/release
- idempotency와 경계값

### Phase C — Runtime enforcement
- Provider, retry, batch, resolution, priority 적용
- fallback 및 resource telemetry

### Phase D — 감사와 검증
- override, quota exceeded, race/duplicate 테스트

## 12. 하네스 필수 검증

1. 플랜별 Provider와 retry 정책이 정확히 선택된다.
2. Free/Lite에서 모델 runtime이 초기화되지 않는다.
3. Standard/Pro의 model policy가 누락되면 조용히 module로 전환하지 않는다.
4. quota 경계값과 초과를 검증한다.
5. 중복 usage event가 한 번만 commit된다.
6. quality retry가 photo unit을 중복 차감하지 않는다.
7. 사용자 간 quota/ledger가 섞이지 않는다.
8. Free 품질을 낮추는 금지 필드를 탐지한다.
9. 정책 snapshot과 audit가 존재한다.
10. T-019~T-026 회귀 계약을 유지한다.

## 13. 완료 기준

- 모든 작업이 versioned Plan Policy snapshot을 가진다.
- Provider·retry·batch·resolution·priority가 정책으로 집행된다.
- quota reserve/commit/release가 idempotent하다.
- 중복 실행과 재시도로 사용량이 중복 반영되지 않는다.
- fallback과 운영 비용을 감사할 수 있다.
- 결제 연동 없이도 플랜 집행 계층이 독립적으로 검증된다.

## 14. 다음 티켓과의 경계

T-028은 장시간 운영, 장애 복구, idempotency, 관측성, 출시 안정화를 다룬다. T-027은 플랜 정책과 사용량 제어에 집중한다.
