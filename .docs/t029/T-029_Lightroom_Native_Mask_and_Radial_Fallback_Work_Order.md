# T-029 — Lightroom Native Mask Execution and Deterministic Radial Fallback 작업 지시서

## 0. 2026-06-29 Scope Update — Radial Fallback Excluded

방사형 그레이디언트 / `radial_template` fallback은 T-029 범위에서 제외한다.

이 문서의 기존 radial fallback, radial preset, seed preset, template manifest, fit score, radial geometry retention 관련 지시는 모두 superseded로 취급한다. T-029의 현재 범위는 native Lightroom mask execution only이다.

허용 전략:

```text
native_ai
skip_local
review_required
```

금지 전략/필드:

```text
radial_template
template_ref
template_path
preset_path
generated_radial_xmp
mouse_coordinates
```

Subject, People, Object, Sky, Background 등 native mask가 의도한 target을 실제로 검출하지 못하면 자동 마스크를 만들지 않는다. Planner는 `skip_local` 또는 `review_required`를 선택하고, 명시적 evidence를 남긴다. Silent global fallback도 금지한다.

## 1. 문서 상태

```text
Ticket: T-029
Title: Lightroom Native Mask Execution and Deterministic Radial Fallback
Baseline: T-028 구현 및 전체 회귀 하네스 통과본
Depends on: T-019 Apply Adapter, T-020 Export Adapter, T-021 closed loop, T-023 semantic/local planning, T-028 idempotency/recovery
Primary goal: 현재 Lightroom Classic 플러그인이 T-023 로컬 보정 계획을 실제 마스크로 실행하게 하고, 피사체/사람/개체 AI가 작은 배경 대상을 인식하지 못할 때 버전이 고정된 방사형 마스크 템플릿으로 자동 대체한다.
```

## 2. 한 문장 목표

> 모델은 복원이 필요한 위치와 색상 문제를 분석하고, Planner는 안전한 마스크 전략과 템플릿을 결정하며, Lightroom Plugin은 검증된 요청만 비파괴적으로 실행하고 결과 증거를 반환한다.

## 3. 해결할 실제 문제

현재 테스트 사진에서는 전면 다이버는 피사체로 인식되지만 좌측 상단의 작은 배경 인물은 다음 기능으로 선택되지 않는다.

```text
Select Subject: 실패
Select People: 실패
Select Object: 실패
```

배경 인물의 붉은 의상은 수중 색 손실로 탁한 갈색 또는 청색 편향으로 남는다. 전역 보정으로 적색을 올리면 벽, 물, 피부, 창 주변까지 오염된다. 브러시 또는 Object Rectangle을 사람이 직접 그리는 방식은 무인 자동 처리 요구를 충족하지 못한다.

T-029의 필수 해결 경로:

```text
semantic target geometry
→ native AI mask reliability check
→ native mask unavailable/unreliable
→ deterministic radial template selection
→ bounded local color recovery
→ spill/quality verification
```

## 4. 책임 분리

### 4.1 Analysis Provider / Qwen3-VL

허용:

```text
target region semantics
normalized bounding box or ellipse proposal
confidence
detection risk
color-loss diagnosis
recommended correction intent
```

금지:

```text
plugin_command
preset_path
template file path
Lightroom mask payload
final Develop parameter values
mouse coordinates or UI automation commands
```

### 4.2 Mask Strategy Planner

Planner만 다음을 결정한다.

```text
mask strategy
radial template ID
fit score and rejection reason
bounded local adjustments
optional local Point Color intent
fallback or review decision
```

### 4.3 Lightroom Plugin

Plugin은 다음만 수행한다.

```text
request/schema/capability/template checksum validation
photo find/import
pre-apply Develop snapshot
approved template application
bounded local adjustment application
result/evidence write
failure rollback
same-request idempotent replay
```

Plugin은 의미 판단, 피사체 선정, 품질 점수 계산, 템플릿 검색 정책 결정을 하지 않는다.

## 5. Phase 0 — 필수 기술 타당성 게이트

방사형 템플릿 구현을 시작하기 전에 현재 지원 Lightroom Classic 버전과 실제 Plugin API 경로에서 다음을 증명한다.

```text
1. 사람이 미리 만든 방사형 마스크 프리셋 1개를 Plugin이 자동 적용할 수 있다.
2. 프리셋 적용 후 방사형 위치·크기·페더가 대상 사진에 유지된다.
3. Plugin이 적용 성공/실패를 JSON 결과로 반환한다.
4. 같은 request를 재실행해 동일 마스크가 중복 생성되지 않는다.
5. 실패 시 기존 사용자 마스크와 Develop 상태가 손상되지 않는다.
```

허용되는 구현 경로는 Lightroom이 공식적으로 노출하는 Plugin/Develop/Preset 적용 경로뿐이다.

다음 우회는 금지한다.

```text
AutoHotkey, pyautogui, 마우스 드래그 자동화
화면 해상도 기반 클릭
Lightroom catalog DB 직접 수정
임의 sidecar XMP 덮어쓰기
검증되지 않은 내부 API 호출
```

Phase 0이 실패하면 T-029 완료를 선언하지 않는다. `BLOCKED_RADIAL_PRESET_APPLICATION` 증거와 재현 절차를 남기고 중단한다.

## 6. 마스크 전략 정책

초기 전략 enum:

```text
native_ai
radial_template
skip_local
review_required
```

결정 순서:

```text
1. target confidence와 geometry 유효성 확인
2. capability snapshot 확인
3. native AI가 해당 대상에 대해 신뢰 가능하다는 실제 evidence가 있으면 native_ai
4. native AI가 실패하거나 대상이 탐지되지 않았고 radial fit가 기준 이상이면 radial_template
5. 위치 분리가 불충분하거나 spill risk가 높으면 skip_local 또는 review_required
```

AI 마스크가 단순히 API상 존재한다는 이유만으로 `native_ai`를 선택하지 않는다. 현재 사진처럼 실제 감지 결과가 실패한 경우 반드시 radial fallback 후보로 넘어간다.

## 7. 정규화 geometry 계약

모든 geometry는 원본 방향 보정이 반영된 표시 이미지 기준 `0.0..1.0` 좌표를 사용한다.

```json
{
  "coordinate_space": "oriented_normalized_image",
  "center_x": 0.270,
  "center_y": 0.155,
  "width": 0.150,
  "height": 0.120,
  "rotation_deg": 0.0
}
```

규칙:

1. 좌상단은 `(0, 0)`, 우하단은 `(1, 1)`이다.
2. EXIF orientation 적용 전 픽셀 좌표를 전달하지 않는다.
3. 값이 범위를 벗어나면 request를 거부한다.
4. width/height가 0이거나 최대 허용 크기를 넘으면 자동 적용하지 않는다.
5. Planner는 원본 target geometry와 선택된 template geometry를 모두 evidence로 저장한다.

## 8. Radial Template Library

MVP는 임의의 동적 마스크 XMP를 생성하지 않는다. 검증된 seed preset을 기반으로 생성·검수된 버전형 템플릿 라이브러리를 사용한다.

필수 구조 예시:

```text
lightroom/TonevyraAI.lrplugin/
  Resources/
    radial_masks/
      manifest.json
      v1/
        radial_r00_c00_s_small_a_vertical_f80.xmp
        ...
```

각 템플릿 필수 metadata:

```text
template_id
library_version
relative_path
sha256
center_x / center_y
width / height
rotation_deg
feather
aspect_class
size_class
supported_lightroom_min
supported_lightroom_max optional
seed_signature
```

MVP 기준 라이브러리는 build-time generator로 생성한다. 사람이 수백 개 파일을 직접 편집하지 않는다.

권장 초기 격자:

```text
positions: 5 columns × 7 rows
sizes: small / medium / large
aspects: round / horizontal / vertical
feather: fixed high-feather baseline (예: 0.80)
```

총 315개 후보는 빌드 산출물이며, 실제 지원 버전에서 샘플링 검증을 거쳐 manifest checksum을 고정한다. 격자와 클래스 수는 Phase 0 결과에 따라 조정할 수 있지만, 변경 시 library version과 하네스를 함께 올린다.

## 9. Template 선택 정책

Planner는 target geometry와 template geometry를 비교한다.

필수 fit evidence:

```text
center_distance
coverage_ratio
overflow_ratio
aspect_error
size_error
fit_score
```

기본 원칙:

```text
coverage_ratio가 낮아 대상이 잘리면 거부
center_distance가 크면 거부
overflow가 커서 주변 오염 위험이 높으면 거부
동점이면 더 작은 overflow, 더 높은 coverage, 더 작은 template 순서
동일 입력/manifest/planner version에서는 동일 template 선택
```

정확한 threshold는 설정값으로 버전 관리하며 하네스 fixture에 고정한다.

## 10. 로컬 색상 복원 정책

T-029는 마스크 내부의 보정값을 Planner가 제한된 범위에서 생성한다.

초기 허용 파라미터 예시:

```text
Exposure2012
Shadows2012
Temperature
Tint
Saturation
Vibrance
Texture
Clarity2012
Dehaze
```

적색 복원은 단순 Saturation만 크게 올리지 않는다.

```text
밝기/그림자 소폭 복구
→ Temperature/Tint의 제한된 복원
→ 지원될 경우 Local Point Color로 muted-red를 natural-red 방향 보정
→ saturation/luminance 미세 조정
```

Local Point Color 기능은 capability snapshot에서 지원이 확인된 경우에만 사용한다. 지원되지 않으면 다음 중 하나로 처리한다.

```text
작은 radial + 낮은 강도의 색상 복원
skip_local
review_required
```

지원되지 않는 기능을 성공으로 기록하거나 전체 사진에 대신 적용해서는 안 된다.

## 11. Request 계약

새 명령:

```text
APPLY_LIGHTROOM_MASK_PLAN
```

필수 최상위 필드:

```text
schema_version = t029.mask_apply.request.v1
request_id
task_id
job_id
attempt_id
source_path
command
idempotency_key
capability_snapshot_id
mask_plan
created_at
```

각 operation 필수 필드:

```text
operation_id
target_region_id
strategy
template_ref when radial_template
predicted_geometry
fit_evidence
mask_name
local_adjustments
point_color optional
safety
```

`mask_name`은 다음 namespace를 사용한다.

```text
Tonevyra::T029::<job_id>::<attempt_id>::<operation_id>
```

## 12. Result 계약

필수 최상위 필드:

```text
schema_version = t029.mask_apply.result.v1
request_id
task_id
job_id
attempt_id
status = applied | partial | skipped | failed
idempotency_key
capability_snapshot
operation_results
pre_apply_snapshot_ref
post_apply_snapshot_ref
rollback_performed
error_code
message
completed_at
```

operation result는 다음을 포함한다.

```text
operation_id
status
strategy
template_id optional
template_checksum_verified
mask_name
mask_created_or_reused
applied_adjustments
point_color_status
warnings
```

## 13. 비파괴·소유권 규칙

1. 기존 사용자 마스크를 삭제·이름 변경·덮어쓰지 않는다.
2. Plugin은 `Tonevyra::` namespace의 마스크만 소유한다.
3. 적용 전 Develop settings snapshot을 저장한다.
4. 중간 실패 시 snapshot 복구를 시도하고 결과를 기록한다.
5. 같은 `idempotency_key` 재실행은 새 마스크를 만들지 않는다.
6. 새 quality attempt는 이전 attempt와 구분된 plan/evidence를 갖는다.
7. 기존 원본 파일을 수정하거나 덮어쓰지 않는다.
8. template path는 request에서 직접 신뢰하지 않고 local manifest의 ID로만 resolve한다.

## 14. Capability Snapshot

Plugin 시작 또는 요청 처리 시 다음 capability를 기록한다.

```text
lightroom_version
plugin_version
mask_plan_command_supported
preset_application_supported
radial_template_supported
native_ai_mask_types
local_point_color_supported
mask_result_introspection_level
rollback_supported
template_library_version
template_manifest_sha256
```

Capability 부족은 명시적인 `unsupported`, `skipped`, 또는 `failed`로 반환한다.

## 15. Quality Gate 연결

T-029는 단순 `mask applied`만으로 완료되지 않는다. export 후 quality evidence에서 최소 다음을 확인한다.

```text
target_color_recovery_gain
background_color_spill
skin_or_neutral_shift
highlight_clipping_delta
mask_boundary_visibility
local_adjustment_naturalness
```

현재 배경 인물 적색 복원 사례의 핵심 실패 reason code:

```text
TARGET_RED_NOT_RECOVERED
BACKGROUND_RED_SPILL
RADIAL_TARGET_MISALIGNED
LOCAL_COLOR_OVERCOOKED
MASK_EXECUTION_UNVERIFIED
```

## 16. 포함 범위

```text
T-029 request/result schema
Mask Strategy Planner radial fallback
versioned radial template manifest
build-time template generator and validator
Plugin-side mask request executor
pre/post snapshot and rollback
idempotent replay
capability probe
background-person red recovery fixture
static harness and live Lightroom checklist
post-export local quality evidence connection
```

## 17. 제외 범위

```text
브러시 stroke 좌표 자동 생성
Object Rectangle UI 자동 드래그
외부 segmentation bitmap을 Lightroom mask로 삽입
Lightroom catalog 직접 수정
임의 런타임 XMP 구조 생성
생성형 인페인팅
모델 fine-tuning
다중 Lightroom 동시 제어
```

## 18. 구현 단계

### Phase A — Schema와 capability
- request/result/capability schema 구현
- Planner와 Plugin 책임 경계 고정
- Phase 0 live preset PoC

### Phase B — Template library
- 검증된 seed preset 확보
- template generator와 manifest 작성
- checksum/version 검증
- deterministic selector 구현

### Phase C — Plugin executor
- `APPLY_LIGHTROOM_MASK_PLAN` bridge 처리
- 사진 찾기/선택과 Develop 진입
- template 적용, local values 적용
- result/snapshot/rollback/idempotency

### Phase D — Planner와 품질 연결
- native failure → radial fallback
- fit threshold와 spill risk
- post-export region quality evidence

### Phase E — 실제 사례 검증
- 제공된 수중 사진에서 배경 인물 위치 targeting
- 무인 적용
- 붉은 의상 복원
- 주변 파란 벽과 물의 적색 오염 제한

## 19. 하네스 필수 검증

1. valid request/result/manifest가 schema를 통과한다.
2. Provider 출력의 직접 plugin command와 template path를 거부한다.
3. out-of-range geometry를 거부한다.
4. unknown template ID 또는 checksum mismatch를 거부한다.
5. native detection 실패 사례가 radial_template로 결정된다.
6. 동일 입력에서 template 선택 결과가 결정론적이다.
7. adjustment clamp를 벗어난 요청을 거부한다.
8. 같은 idempotency key replay가 duplicate mask를 만들지 않는다.
9. 기존 사용자 마스크를 수정하는 요청을 거부한다.
10. strict 모드는 실제 Lightroom preset 적용과 mask evidence를 요구한다.
11. 제공된 배경 인물 사례에서 target alignment와 color spill evidence를 요구한다.
12. T-019~T-028 회귀 하네스가 모두 유지된다.

## 20. 완료 기준

- Phase 0 live preset PoC가 실제 Lightroom Classic에서 통과한다.
- Agent가 T-029 mask request를 생성하고 Plugin이 자동 소비한다.
- native 인식 실패 시 radial template가 결정론적으로 선택된다.
- Plugin이 템플릿 checksum과 capability를 검증한다.
- 대상 위치에 방사형 마스크가 무인 생성된다.
- 로컬 보정값이 clamp 내에서 적용된다.
- 동일 request replay에 중복 마스크가 없다.
- 실패 시 사용자 마스크와 기존 Develop 상태가 보존된다.
- 실제 export에서 배경 인물의 붉은색 복원과 주변 spill 제한 증거가 남는다.
- 모든 T-029 정적/런타임/실 Lightroom 하네스 및 T-019~T-028 회귀가 통과한다.

## 21. 중단 규칙

다음 상황에서는 임의 우회 구현을 하지 말고 차단 보고서를 남긴다.

```text
Plugin에서 검증된 radial preset 자동 적용 불가
적용 시 geometry가 유지되지 않음
사용자 마스크 보존 또는 rollback 증명 불가
Lightroom 버전별 preset 포맷 차이를 안전하게 처리할 수 없음
로컬 보정이 아닌 전역 오염으로만 구현 가능
```

T-029를 끝낸 뒤 후속 티켓을 자동으로 시작하지 않는다.
