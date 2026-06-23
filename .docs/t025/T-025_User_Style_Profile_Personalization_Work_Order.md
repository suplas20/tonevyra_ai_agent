# T-025 — User Style Profile and Personalization 작업 지시서

## 1. 문서 상태

```text
Ticket: T-025
Title: User Style Profile and Personalization
Baseline: T-024 구현 및 하네스 통과본
Primary goal: 사용자 선호를 버전이 있는 로컬 Style Profile로 표현하고, 안전한 Planner 제약과 피드백 보정에 적용한다.
```

## 2. 한 문장 목표

> 사용자의 색감·대비·피부 표현·보정 강도 선호를 구조화하고 버전화하여, 모델이나 Plugin을 직접 제어하지 않고 Adjustment Planner의 목표와 제한으로 적용하며 사용자 피드백으로 점진적으로 보정한다.

## 3. 핵심 원칙

1. 개인화는 사용자 명시 설정 또는 동의된 피드백에서만 생성한다.
2. 모든 스타일 데이터는 로컬에 저장하며 사용자 간 공유하지 않는다.
3. Style Profile은 직접 실행 가능한 Lightroom 명령이 아니다.
4. 자동 모델 파인튜닝과 숨은 학습을 금지한다.
5. profile 변경은 새 version을 만들고 이전 version을 보존한다.
6. 사용자 opt-out과 profile reset을 지원한다.
7. 스타일 적용 전후의 기술적 품질 및 안전 기준은 동일하게 유지한다.
8. Free 플랜 품질을 의도적으로 낮추는 용도로 profile을 사용하지 않는다.

## 4. 포함 범위

```text
UserStyleProfile
style presets as structured intent
per-dimension preference strength
profile versioning
profile activation / rollback
style-to-planner mapping
manual edit delta capture
approval/rejection feedback
local calibration samples
confidence and minimum evidence gate
privacy boundary
profile application audit
```

## 5. 제외 범위

```text
온라인 계정·결제 시스템
클라우드 동기화
자동 모델 파인튜닝
사용자 간 스타일 마켓
생성형 LUT 제작
저작권이 불명확한 프리셋 복제
```

## 6. Style Profile 계약

필수 필드:

```text
profile_id
user_scope_id
version
status
created_at
source
preferences
constraints
confidence
minimum_evidence_count
```

초기 preference 차원:

```text
exposure_bias
contrast_strength
highlight_rolloff
shadow_openness
white_balance_bias
saturation_strength
vibrance_strength
skin_warmth
skin_smoothing_strength
texture_clarity_balance
sharpening_strength
noise_reduction_strength
mood_tags
```

값은 의미 기반 정규화 범위로 저장하고 Planner가 Lightroom 범위로 변환한다.

## 7. 적용 우선순위

```text
hard technical safety
→ source limitation
→ plan capability
→ set consistency constraints
→ active user style profile
→ per-photo semantic intent
```

사용자 취향은 클리핑 방지, 피부색 안전, 지원 기능, 품질 기준을 우회할 수 없다.

## 8. 피드백 학습

허용:

```text
사용자 승인/거절
사용자 Lightroom 수동 수정 delta
스타일 강도 변경
profile 직접 편집
```

금지:

```text
동의 없는 행동 수집
실시간 모델 fine-tuning
다른 사용자의 데이터 혼합
외부 서버 전송
한두 번의 피드백으로 과도한 profile 변경
```

최소 evidence와 confidence threshold를 통과한 경우에만 자동 calibration candidate를 만든다. 자동 활성화는 정책에 따라 명시적으로 제어한다.

## 9. 버전과 롤백

```text
DRAFT → ACTIVE → SUPERSEDED | DISABLED
```

활성 profile은 한 user scope당 하나다. 모든 적용은 `profile_id`, `version`, `mapping_version`을 기록한다.

## 10. artifact

```text
style_profile.json
style_application_plan.json
style_mapping_evidence.json
feedback_record.json
manual_edit_delta.json
calibration_candidate.json
```

## 11. 구현 단계

### Phase A — Profile 모델
- 스키마, 버전, 활성화/롤백
- 로컬 저장과 사용자 격리

### Phase B — Planner mapping
- 의미 preference를 bounded delta로 변환
- 안전·세트·사진 의도와 우선순위 적용

### Phase C — Feedback
- 승인/거절 및 수동 수정 delta 기록
- 최소 evidence 기반 calibration candidate

### Phase D — 검증
- profile 재현성, opt-out, rollback
- cross-user leakage 방지

## 12. 하네스 필수 검증

1. 유효한 profile과 version 전이가 통과한다.
2. 직접 Lightroom 명령이나 preset 실행 필드를 거부한다.
3. 사용자 격리와 cross-user leakage 방지를 검증한다.
4. 기술 안전보다 스타일이 우선하지 못한다.
5. opt-out 시 profile이 로드·적용되지 않는다.
6. 낮은 evidence에서 자동 calibration을 거부한다.
7. rollback 후 이전 결과가 재현 가능하다.
8. 자동 fine-tuning과 외부 전송 설정을 거부한다.
9. T-019~T-024 회귀 계약을 유지한다.

## 13. 완료 기준

- Style Profile을 생성·활성화·버전업·롤백할 수 있다.
- profile은 Planner를 통해서만 적용된다.
- 사용자 피드백과 수동 수정 delta가 로컬 evidence로 저장된다.
- opt-out/reset이 완전히 동작한다.
- 동일 profile/version/input에서 재현 가능한 계획을 생성한다.
- 품질 안전 기준을 유지하면서 사용자 선호 차이가 결과에 나타난다.

## 14. 다음 티켓과의 경계

T-026은 제품 품질과 회귀를 객관적으로 측정하는 benchmark 체계를 만든다. T-025는 사용자 취향 기능 자체에 집중한다.
