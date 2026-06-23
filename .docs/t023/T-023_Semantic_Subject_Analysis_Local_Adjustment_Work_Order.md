# T-023 — Semantic Subject Analysis and Lightroom Local Adjustment Planning 작업 지시서

## 1. 문서 상태

```text
Ticket: T-023
Title: Semantic Subject Analysis and Lightroom Local Adjustment Planning
Baseline: T-022 구현 및 T-022 하네스 통과본
Primary goal: 사진 안의 주요 피사체와 의미 영역을 구조화해 분석하고, 지원되는 Lightroom 로컬 보정 기능으로 안전하게 변환하는 Planner 계층을 구현한다.
```

T-023은 T-022 모델 Provider가 생성한 의미 정보를 실제 부분 보정 전략으로 연결하는 작업이다. 모델 또는 분석 Provider가 Lightroom 마스크 명령을 직접 실행하게 만드는 작업이 아니다.

## 2. 선행 조건

다음 기능이 실제 실행 경로에 존재해야 한다.

```text
T-021 Common Agent Core와 closed-loop
T-022 ModelAnalysisProvider와 ModelQualityProvider
normalized analysis / quality schema
Adjustment Planner와 parameter clamp
Lightroom Apply Adapter
Lightroom Final Export Adapter
Provider 및 attempt 감사 로그
```

T-022가 fixture만 통과하고 실제 로컬 모델 실행 증거가 없다면 T-023 완료를 선언하지 않는다.

## 3. 한 문장 목표

> 주요 피사체·인물·피부·하늘·배경 등 의미 영역을 안정적으로 식별하고, 분석 결과를 버전이 있는 Semantic Region 스키마로 정규화한 뒤 Local Adjustment Planner가 지원 가능한 Lightroom 마스크와 제한된 보정 의도로 변환하도록 한다.

## 4. 해결할 문제

전역 보정만으로는 인물의 얼굴과 배경, 하늘과 지면, 주요 제품과 주변부를 서로 다르게 처리할 수 없다. 반대로 모델이 임의의 영역과 Lightroom 명령을 직접 생성하면 재현성, 안전성, 플러그인 호환성이 깨진다.

목표 흐름:

```text
source / preview
→ Semantic Subject Analyzer
→ versioned semantic regions
→ region confidence / overlap validation
→ Local Adjustment Planner
→ supported Lightroom mask plan
→ global + local conflict resolver
→ bounded apply request
→ export
→ global/local paired quality evaluation
```

## 5. 절대 보존 규칙

1. T-019~T-022 계약과 기존 스킬을 삭제·병합·이름 변경하지 않는다.
2. 모델은 마스크 생성·실행 명령이나 최종 Lightroom 수치를 직접 출력하지 않는다.
3. 모든 영역에는 안정적인 `region_id`, 유형, confidence, 근거가 있어야 한다.
4. 지원되지 않는 마스크 유형을 지원된 것처럼 기록하지 않는다.
5. 마스크 기능을 사용할 수 없으면 명시적인 global-only degraded mode로 전환한다.
6. 전역 보정과 로컬 보정의 충돌을 Planner가 해결한다.
7. 피부·얼굴 보정은 과도한 매끄러움, 색상 왜곡, 비현실적 밝기 상승을 제한한다.
8. 영역별 보정도 기존 quality retry budget 안에서만 재처리한다.
9. 이전 attempt의 영역·마스크·결과 artifact는 덮어쓰지 않는다.
10. Plugin은 전달받은 지원 명령을 실행할 뿐 의미 판단을 하지 않는다.

## 6. 포함 범위

```text
SemanticSubjectAnalyzer
semantic region normalization
primary/secondary subject ranking
portrait / face / skin intent
sky / background / product / foreground intent
region confidence gate
region overlap and hierarchy validation
LocalAdjustmentPlanner
supported mask capability registry
global/local adjustment conflict resolver
local adjustment safety bounds
local quality reason codes
mask availability fallback
per-region evidence artifacts
```

## 7. 제외 범위

```text
사진 세트 전체 일관성
사용자 스타일 개인화
새로운 모델 파인튜닝
Lightroom에 존재하지 않는 마스크 기능 개발
생성형 인페인팅·객체 삭제
SaaS 사용량 및 과금
분산 처리
```

## 8. Semantic Region 계약

필수 필드:

```text
schema_version
job_id
attempt_id
region_id
region_type
priority
bounding_geometry or mask_reference_intent
confidence
attributes
quality_risks
recommended_intents
source
```

초기 허용 영역 유형:

```text
primary_subject
secondary_subject
person
face
skin
hair
sky
background
foreground
product
object
```

`region_type` 확장은 스키마·Planner·하네스를 함께 변경해야 한다.

## 9. Local Adjustment Plan 계약

Planner만 다음을 생성할 수 있다.

```text
mask_plan_id
region_id
supported_mask_type
mask_parameters
bounded_adjustment_intents
conflict_resolution
fallback_behavior
planner_version
```

Provider 출력에서 금지되는 필드:

```text
plugin_command
execute_mask
lightroom_mask_payload
final_develop_settings
preset_path
force_state_transition
```

## 10. 마스크 지원 정책

지원 여부는 Capability Registry에서 결정한다.

```text
supported and confidence valid
→ local plan 생성

unsupported or confidence below threshold
→ 해당 영역 로컬 보정 생략 또는 global-only fallback
→ degraded_mode와 이유 기록
```

마스크를 생성하지 못했는데 성공으로 위장하거나, 전체 사진에 영역 보정을 적용해서는 안 된다.

## 11. 충돌 해결

다음 충돌을 탐지한다.

```text
global exposure vs face exposure
white balance vs skin color intent
clarity/texture vs skin naturalness
sky saturation vs overall saturation
subject sharpening vs noise reduction
중첩 영역의 상반된 보정 방향
```

우선순위와 clamp 규칙은 결정론적이어야 하며, 동일 입력·설정·버전에서 동일 계획을 생성해야 한다.

## 12. 상태와 artifact

T-021 상태 머신을 유지한다. 새로운 top-level 상태를 추가하지 않는다.

attempt별 필수 증거:

```text
semantic_analysis.json
semantic_regions.json
local_adjustment_plan.json
mask_capability_snapshot.json
conflict_resolution.json
apply/export evidence
quality_evaluation.json
```

## 13. 구현 단계

### Phase A — 의미 영역 분석
- 영역 스키마와 normalizer 구현
- 주요 피사체 순위 및 confidence gate 구현
- 중첩·계층 검증

### Phase B — Local Adjustment Planner
- Capability Registry 구현
- 지원 마스크로의 변환
- 전역/로컬 충돌 해결 및 safety bounds

### Phase C — Lightroom 연동
- 지원 가능한 로컬 명령 계약 연결
- global-only fallback과 기술 오류 구분

### Phase D — 품질 루프
- 영역별 품질 reason code
- 재보정 시 strategy fingerprint와 영역 변화 기록

## 14. 하네스 필수 검증

1. 유효한 인물·하늘·배경 영역이 스키마를 통과한다.
2. Provider의 직접 마스크 실행 필드를 거부한다.
3. 지원하지 않는 mask type을 거부한다.
4. 낮은 confidence 영역이 자동 실행되지 않는다.
5. 중첩 영역 충돌 해결 결과가 결정론적이다.
6. mask 기능이 없을 때 global-only fallback 증거가 남는다.
7. 얼굴·피부 안전 범위를 초과한 계획을 거부한다.
8. T-019~T-022 회귀 계약이 유지된다.
9. strict 모드에서 실제 apply/export와 영역별 품질 증거를 요구한다.

## 15. 완료 기준

- 의미 영역 결과가 버전 스키마로 저장된다.
- Local Adjustment Planner만 실행 가능한 로컬 계획을 생성한다.
- 지원되지 않는 기능은 명시적으로 fallback 또는 기술 실패 처리된다.
- 전역/로컬 충돌과 안전 범위가 검증된다.
- 재보정 시 새 attempt와 새 local plan이 생성된다.
- 실제 Lightroom 결과에서 로컬 보정 적용 증거와 품질 평가가 확인된다.

## 16. 다음 티켓과의 경계

T-024는 여러 사진을 batch/set으로 묶고 일관성을 관리한다. T-023은 단일 사진 내부의 의미 영역과 로컬 보정에만 책임을 둔다.
