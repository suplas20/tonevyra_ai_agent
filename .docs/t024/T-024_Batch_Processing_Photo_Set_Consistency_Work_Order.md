# T-024 — Batch Processing and Photo Set Consistency 작업 지시서

## 1. 문서 상태

```text
Ticket: T-024
Title: Batch Processing and Photo Set Consistency
Baseline: T-023 구현 및 하네스 통과본
Primary goal: 여러 사진을 안전하게 batch로 처리하고, 같은 촬영 세트 안에서 밝기·화이트밸런스·색상·피부 표현의 일관성을 유지한다.
```

## 2. 한 문장 목표

> 개별 사진의 job/attempt 격리를 유지한 채 batch와 photo set을 구성하고, 대표 사진과 세트 기준을 사용해 사진별 최적화와 전체 일관성 사이의 균형을 검증 가능한 방식으로 관리한다.

## 3. 선행 조건

```text
단일 사진 closed-loop 정상 동작
실제 Lightroom apply/export 증거
T-023 semantic/local adjustment 경로
immutable attempt artifact
recoverable state manager
```

단일 사진 작업이 안정적이지 않으면 batch 병렬화나 대량 처리를 시작하지 않는다.

## 4. 핵심 원칙

1. `batch_id`, `set_id`, `job_id`, `attempt_id`를 구분한다.
2. 각 사진은 독립 job과 독립 품질 결정을 가진다.
3. 한 사진의 실패가 전체 batch를 무조건 실패시키지 않는다.
4. 세트 기준은 개별 사진의 노출·장면 차이를 무시하고 강제로 동일값을 적용하는 기능이 아니다.
5. 기본 MVP batch chunk는 10장으로 시작한다.
6. 기존 단일 worker/concurrency 정책을 우회하지 않는다.
7. batch 재시도와 사진 quality retry를 구분한다.
8. 완료된 사진 artifact를 batch 재실행으로 덮어쓰지 않는다.

## 5. 포함 범위

```text
BatchJob / BatchItem
PhotoSet grouping
representative image selection
set baseline extraction
per-image deviation analysis
white balance / exposure / color consistency
portrait skin consistency
semantic scene subgrouping
chunked sequential execution
partial failure handling
batch progress and resume
set-level quality summary
outlier detection
```

## 6. 제외 범위

```text
다중 사용자 SaaS 큐
분산 worker pool
결제·과금
사용자 개인 스타일
모델 파인튜닝
클라우드 스토리지
```

## 7. 식별자와 상태

```text
batch_id: 사용자 제출 단위
set_id: 유사 촬영 조건/장면 그룹
job_id: 사진 한 장의 영구 작업 ID
attempt_id: 해당 사진의 보정 시도 ID
```

batch 상태 예시:

```text
CREATED → GROUPING → PROCESSING → EVALUATING → COMPLETED
                                      ├─ PARTIAL_FAILED
                                      └─ FAILED
```

개별 사진은 T-021 상태 머신을 그대로 사용한다. 새 batch 상태가 개별 job 상태를 덮어쓰면 안 된다.

## 8. 그룹화 정책

그룹화 근거:

```text
capture time proximity
camera/lens metadata
scene embedding or scene class
lighting similarity
subject/portrait continuity
user-provided grouping
```

자동 그룹화 결과는 `grouping_confidence`와 근거를 저장한다. confidence가 낮으면 단일 세트로 강제 병합하지 않는다.

## 9. 대표 사진과 세트 기준

대표 사진은 다음 조건으로 선정한다.

```text
technical quality
source limitation absence
subject relevance
lighting representativeness
median-like exposure/color characteristics
```

대표 사진 한 장의 절대값을 모든 사진에 복사하지 않는다. 세트 기준은 목표 범위와 상대적 delta로 사용한다.

## 10. 일관성 평가

최소 평가 항목:

```text
exposure continuity
white-balance continuity
color cast continuity
contrast continuity
skin-tone continuity
local subject emphasis continuity
style intent continuity
```

일관성 점수와 개별 품질 점수를 분리한다. 세트와 다르다는 이유만으로 좋은 개별 사진을 훼손하지 않는다.

## 11. 부분 실패와 재시도

```text
individual TECHNICAL_FAILED
→ 해당 item만 복구 또는 실패 처리
→ 다른 item 계속 처리 가능

individual RETRY_REQUIRED
→ 해당 job의 quality retry budget만 사용

batch infrastructure failure
→ batch checkpoint에서 재개
```

동일 사진을 중복 실행하지 않도록 idempotency key를 사용한다.

## 12. artifact

```text
batch_manifest.json
set_grouping.json
representative_selection.json
set_baseline.json
item_progress.json
set_consistency_evaluation.json
batch_summary.json
```

각 사진의 기존 attempt artifact는 그대로 유지한다.

## 13. 구현 단계

### Phase A — Batch/Set 모델
- 식별자와 상태 정의
- chunk size 10 순차 실행
- item별 격리와 progress persistence

### Phase B — 그룹화와 기준
- 자동/수동 그룹화
- 대표 사진 선정
- 세트 baseline과 outlier 탐지

### Phase C — 일관성 Planner
- 사진별 계획에 set delta 적용
- 안전 범위와 개별 품질 우선 규칙

### Phase D — 복구와 평가
- 부분 실패, resume, 중복 방지
- set-level 품질 보고

## 14. 하네스 필수 검증

1. 식별자 계층과 job/attempt 격리를 검증한다.
2. 기본 chunk size 10과 bounded processing을 검증한다.
3. 대표 사진 선정이 결정론적이다.
4. 한 item 실패 후 나머지 item이 계속 처리된다.
5. quality retry가 다른 사진의 budget을 소비하지 않는다.
6. resume 시 완료 item이 재실행되지 않는다.
7. 세트 일관성 적용이 안전 범위를 넘지 않는다.
8. outlier를 무리하게 세트 기준에 맞추지 않는다.
9. T-019~T-023 회귀 계약을 유지한다.

## 15. 완료 기준

- 10장 batch가 item 격리 상태로 처리된다.
- photo set grouping과 대표 사진 근거가 저장된다.
- 일관성 평가와 개별 품질 평가가 분리된다.
- 부분 실패 및 재시작 후 정확히 재개된다.
- 중복 apply/export가 발생하지 않는다.
- 실제 사진 세트에서 밝기·색상·피부 일관성 개선 증거가 확인된다.

## 16. 다음 티켓과의 경계

T-025는 사용자별 스타일과 피드백 개인화를 다룬다. T-024는 사용자 취향이 아닌 같은 촬영 세트 내부의 객관적 일관성에 집중한다.
