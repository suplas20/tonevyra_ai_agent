# T-026 — Quality Benchmark and Regression Evaluation System 작업 지시서

## 1. 문서 상태

```text
Ticket: T-026
Title: Quality Benchmark and Regression Evaluation System
Baseline: T-025 구현 및 하네스 통과본
Primary goal: 장르별 기준 데이터셋, 전문가 기준, 기술 지표, 사람 평가를 결합해 품질과 회귀를 재현 가능하게 측정한다.
```

## 2. 한 문장 목표

> Module/Model Provider와 각 제품 버전의 결과를 동일한 원본·설정·Lightroom 조건에서 비교하고, 기술 품질·지각 품질·운영 성능·전문가 블라인드 평가를 버전이 있는 benchmark로 관리한다.

## 3. 핵심 원칙

1. 내부 Quality Gate 점수와 외부 Benchmark 점수를 구분한다.
2. “전문가 100점 대비” 같은 주장은 실제 기준 데이터와 평가 방법이 있을 때만 사용한다.
3. benchmark dataset은 train/calibration/test로 분리한다.
4. test set을 profile calibration이나 모델 튜닝에 사용하지 않는다.
5. 원본, 전문가 보정본, 평가 조건, 버전을 추적한다.
6. 사람 평가는 가능한 한 blind/randomized 방식으로 수행한다.
7. 품질 향상과 처리 시간·메모리·재시도 비용을 함께 평가한다.
8. 회귀 threshold를 임의로 완화해 실패를 통과시키지 않는다.

## 4. 포함 범위

```text
BenchmarkDataset manifest
license/consent metadata
scene/genre stratification
expert reference linkage
module/model A-B run
technical image metrics
perceptual metrics
human blind review import
first-pass approval rate
final approval rate
retry count
latency / memory / throughput
set consistency metrics
style adherence metrics
regression thresholds
release gate report
```

## 5. 제외 범위

```text
모델 훈련 파이프라인
결제·과금
공개 leaderboard 서비스
저작권 미확인 이미지 수집
전문가 평가 자동 대체
```

## 6. Dataset 계약

```text
dataset_id
version
split
case_id
source_artifact
reference_artifact(s)
license_or_consent
scene_class
subject_class
lighting_class
difficulty
required_metrics
```

데이터셋 변경 시 새 version을 생성한다. 기존 benchmark 결과를 새 데이터셋 결과와 동일한 것으로 비교하지 않는다.

## 7. 평가 축

### 기술 품질
```text
clipping
exposure distribution
white balance/color cast
noise/detail
sharpness/halo
artifact integrity
```

### 의미·미학 품질
```text
subject emphasis
skin naturalness
mood preservation
local adjustment appropriateness
set consistency
style adherence
```

### 운영 품질
```text
first-pass approval
final approval
quality retries
technical failures
latency
peak memory/GPU memory
throughput
fallback rate
```

## 8. 사람 평가

사람 평가 record에는 다음을 저장한다.

```text
review_session_id
reviewer_scope
blind_pair_id
randomized_order
criteria_scores
preference
confidence
notes
```

평가자와 reference 생성자가 동일한 경우 이를 표시한다. 모델 출력 설명을 먼저 보여줘 평가를 유도하지 않는다.

## 9. 회귀 정책

release block 예시:

```text
critical technical metric regression
final approval rate below threshold
skin naturalness regression above tolerance
technical failure rate increase
latency or memory budget violation
set consistency regression
```

장르별 threshold와 전체 threshold를 모두 관리한다. 평균이 좋아도 특정 핵심 장르가 심각하게 퇴보하면 실패할 수 있다.

## 10. artifact

```text
dataset_manifest.json
benchmark_run_manifest.json
case_results.jsonl
aggregate_metrics.json
human_review_results.json
provider_comparison.json
regression_decision.json
```

## 11. 구현 단계

### Phase A — 데이터셋과 runner
- manifest와 split 검증
- 동일 조건 실행 및 case artifact 연결

### Phase B — metrics
- 기술·의미·운영 지표 수집
- 장르별 aggregate

### Phase C — 사람 평가
- blind pair 생성, 결과 import, 합의도 기록

### Phase D — release gate
- baseline 비교와 threshold 적용
- machine-readable pass/fail

## 12. 하네스 필수 검증

1. dataset manifest와 license/consent 필드가 유효하다.
2. train/calibration/test leakage를 탐지한다.
3. 동일 case 비교에서 source·settings·export 조건이 일치한다.
4. provider/version 식별자가 누락되지 않는다.
5. 전문가 점수와 내부 점수를 혼합하지 않는다.
6. 장르별 및 전체 threshold를 적용한다.
7. threshold 완화는 승인된 버전 변경 없이는 불가능하다.
8. human review order가 randomized/blind evidence를 가진다.
9. T-019~T-025 회귀 계약을 유지한다.

## 13. 완료 기준

- 버전이 있는 benchmark dataset과 runner가 존재한다.
- Module/Model 및 버전 간 공정한 A-B 비교가 가능하다.
- 기술·의미·운영 지표가 함께 산출된다.
- 사람 blind review 결과를 연결할 수 있다.
- release regression gate가 자동 pass/fail을 생성한다.
- 품질 점수 주장이 데이터와 실행 evidence로 추적된다.

## 14. 다음 티켓과의 경계

T-027은 제품 플랜 라우팅, 사용량, 자원 및 비용 정책을 실제 런타임에 적용한다. T-026은 측정과 release gate에만 집중한다.
