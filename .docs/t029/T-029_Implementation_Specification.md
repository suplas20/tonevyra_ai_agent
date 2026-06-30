# T-029 구현 명세 — Lightroom Mask Executor와 Radial Template Fallback

## 0. 2026-06-29 Scope Update — Native Mask Only

방사형 그레이디언트 / `radial_template` fallback은 T-029 구현 범위에서 제외한다.

이 명세의 기존 radial template library, seed preset, template generator, manifest checksum, radial fit policy, template selection algorithm, radial preset application 경로는 superseded로 취급한다. 구현은 native Lightroom mask execution only로 제한한다.

허용 전략:

```text
native_ai
skip_local
review_required
```

`native_ai`는 native target-detection evidence에서 `target_detected=true`일 때만 실행 가능하다. `target_detected=false`이면 mask apply request를 만들지 않고 `skip_local` 또는 `review_required` evidence를 남긴다.

## 1. 목적

이 문서는 T-029 작업 지시서를 코드 모듈, 데이터 모델, bridge 계약, template manifest, 선택 알고리즘, Plugin 실행 순서, artifact, 하네스로 변환한다. 기존 프로젝트 구조에 같은 책임을 가진 모듈이 있으면 새 파일을 중복 생성하지 말고 기존 모듈을 확장한다.

## 2. 권장 모듈 구조

```text
src/tonevyra_agent/
  masking/
    models.py
    capability.py
    strategy_planner.py
    radial_selector.py
    safety.py
    quality.py
  lightroom/
    mask_request_builder.py
    schemas.py

lightroom/TonevyraAI.lrplugin/
  MaskWorker.lua
  MaskExecutor.lua
  MaskCapabilities.lua
  MaskTemplateRegistry.lua
  DevelopSnapshot.lua
  Resources/radial_masks/
    manifest.json
    v1/*.xmp

tools/
  generate_radial_mask_templates.py
  validate_radial_mask_templates.py
```

Plugin 경로가 `src/tonevyra_agent/lightroom/plugin/TonevyraAI.lrplugin/`에 이미 존재하면 그 경로를 유지한다.

## 3. 핵심 Python 인터페이스

```python
class MaskStrategyPlanner(Protocol):
    def build_mask_plan(
        self,
        semantic_analysis: SemanticAnalysis,
        capability: MaskCapabilitySnapshot,
        template_manifest: RadialTemplateManifest,
        attempt: AttemptContext,
    ) -> MaskExecutionPlan:
        ...
```

```python
class RadialTemplateSelector(Protocol):
    def select(
        self,
        target: NormalizedGeometry,
        templates: Sequence[RadialTemplate],
        policy: RadialFitPolicy,
    ) -> RadialSelectionResult:
        ...
```

```python
class MaskRequestBuilder(Protocol):
    def build_request(
        self,
        plan: MaskExecutionPlan,
        source_path: Path,
        capability: MaskCapabilitySnapshot,
    ) -> MaskApplyRequest:
        ...
```

Provider가 이 인터페이스를 호출하거나 직접 request를 생성해서는 안 된다.

## 4. 데이터 모델

### 4.1 NormalizedGeometry

```json
{
  "coordinate_space": "oriented_normalized_image",
  "center_x": 0.27,
  "center_y": 0.155,
  "width": 0.15,
  "height": 0.12,
  "rotation_deg": 0.0
}
```

Validation:

```text
0 <= center_x <= 1
0 <= center_y <= 1
0 < width <= 1
0 < height <= 1
-180 <= rotation_deg <= 180
```

### 4.2 RadialTemplate

```json
{
  "template_id": "radial.r01.c01.small.vertical.f80",
  "library_version": "t029.radial.v1",
  "relative_path": "v1/radial_r01_c01_small_vertical_f80.xmp",
  "sha256": "64-hex",
  "geometry": {
    "coordinate_space": "oriented_normalized_image",
    "center_x": 0.25,
    "center_y": 0.166667,
    "width": 0.16,
    "height": 0.22,
    "rotation_deg": 0.0
  },
  "feather": 0.8,
  "size_class": "small",
  "aspect_class": "vertical",
  "supported_lightroom_min": "<PHASE0_VERIFIED_VERSION>"
}
```

### 4.3 RadialFitPolicy

```json
{
  "policy_version": "t029.radial_fit.v1",
  "minimum_coverage_ratio": 0.9,
  "maximum_overflow_ratio": 2.5,
  "maximum_center_distance": 0.16,
  "maximum_aspect_log_error": 0.7,
  "minimum_fit_score": 0.65
}
```

초기 수치는 fixture 기준값이며 실제 사진 세트 검증으로 조정한다. 변경 시 policy version을 올린다.

### 4.4 MaskExecutionPlan

```json
{
  "schema_version": "t029.mask_plan.v1",
  "plan_id": "mask-plan-001",
  "job_id": "job-001",
  "attempt_id": "attempt-001",
  "planner_version": "mask-planner-t029-v1",
  "capability_snapshot_id": "cap-001",
  "operations": [
    {
      "operation_id": "rear-person-red",
      "target_region_id": "secondary-person-01-red-garment",
      "strategy": "radial_template",
      "native_assessment": {
        "attempted_types": ["subject", "people", "object"],
        "target_detected": false,
        "reason_code": "NATIVE_TARGET_NOT_DETECTED"
      },
      "predicted_geometry": {},
      "template_ref": {
        "library_version": "t029.radial.v1",
        "template_id": "radial.r01.c01.small.vertical.f80",
        "sha256": "64-hex"
      },
      "fit_evidence": {},
      "mask_name": "Tonevyra::T029::job-001::attempt-001::rear-person-red",
      "local_adjustments": {},
      "point_color": null,
      "safety": {}
    }
  ]
}
```

## 5. Template 선택 알고리즘

### 5.1 계산 항목

Target ellipse와 candidate ellipse의 axis-aligned approximation을 사용해 MVP fit를 계산한다.

```text
center_distance = Euclidean distance of normalized centers
intersection_area = intersection of target/template bounding rectangles
coverage_ratio = intersection_area / target_area
overflow_ratio = max(0, template_area - intersection_area) / target_area
aspect_log_error = abs(log(template_aspect / target_aspect))
size_log_error = abs(log(template_area / target_area))
```

### 5.2 예시 score

```text
fit_score =
  0.35 * clamp(coverage_ratio, 0, 1)
+ 0.25 * (1 - normalized_center_error)
+ 0.20 * (1 - normalized_aspect_error)
+ 0.20 * (1 - normalized_overflow_error)
```

실제 계수는 policy에 저장한다. 구현 코드에 숨기지 않는다.

### 5.3 deterministic tie-break

```text
1. accepted candidate only
2. highest fit_score
3. highest coverage_ratio
4. lowest overflow_ratio
5. lowest center_distance
6. lexicographically smallest template_id
```

## 6. Adjustment clamp

초기 clamp 예시:

```text
Exposure2012: -1.0 .. +1.0
Shadows2012: -40 .. +40
Temperature: -20 .. +20
Tint: -20 .. +20
Saturation: -35 .. +35
Vibrance: -30 .. +30
Texture: -20 .. +20
Clarity2012: -20 .. +20
Dehaze: -15 .. +15
```

피부 또는 사람 영역은 더 좁은 색상/texture 제한을 적용한다. 모든 clamp event를 plan artifact에 남긴다.

## 7. Bridge 경로

기존 T-019 Apply Adapter 경로를 우선 재사용한다. 별도 디렉터리를 추가해야 한다면 다음을 사용한다.

```text
runtime/bridge/lightroom_mask_requests/<request_id>.json
runtime/bridge/lightroom_mask_results/<request_id>.json
```

기존 worker가 하나의 command dispatcher를 사용한다면 동일 request/result 디렉터리에서 `command=APPLY_LIGHTROOM_MASK_PLAN`으로 분기한다. 두 경로를 동시에 만들지 않는다.

## 8. Plugin 실행 순서

```text
1. atomic claim request
2. schema_version/command 검증
3. idempotency result 조회
4. source_path photo find/import
5. capability snapshot 생성
6. request capability_snapshot_id 호환 확인
7. pre-apply Develop snapshot 저장
8. 각 operation 순차 실행
9. template ID → local manifest resolve
10. template file checksum 검증
11. approved Lightroom preset/develop path로 적용
12. local adjustments 적용
13. 가능한 범위에서 mask evidence 수집
14. post-apply snapshot 저장
15. atomic result write
```

중간 실패:

```text
rollback 가능한 경우 pre-apply snapshot 복구
rollback 결과 기록
부분 성공을 success로 승격하지 않음
request 파일을 조용히 삭제하지 않음
```

## 9. Lua 구성 책임

### MaskWorker.lua

```text
request claim
command dispatch
error boundary
result write
```

### MaskCapabilities.lua

```text
Lightroom/plugin version
preset/radial/point-color capability
manifest version/checksum
```

### MaskTemplateRegistry.lua

```text
manifest load
ID lookup
relative path normalization
path traversal 차단
checksum validation
version compatibility
```

### MaskExecutor.lua

```text
photo context 준비
prevalidated template apply
bounded local values apply
mask namespace/idempotency evidence
```

### DevelopSnapshot.lua

```text
before/after settings snapshot
artifact reference
rollback
```

## 10. Template generator

Generator는 검증된 seed preset 없이는 실행을 거부한다.

입력:

```text
seed XMP/preset
seed checksum
position grid
size/aspect classes
feather policy
library version
supported Lightroom version
```

출력:

```text
versioned template files
manifest.json
manifest.sha256
generation_report.json
```

Generator는 seed에서 허용된 geometry 필드만 변경한다. 알 수 없는 필드를 임의로 삭제하거나 재작성하지 않는다. 생성 후 Lightroom live sampling validation이 필요하다.

## 11. Artifact

Attempt별 필수 artifact:

```text
mask_capability_snapshot.json
mask_execution_plan.json
radial_selection_evidence.json
lightroom_mask_request.json
lightroom_mask_result.json
develop_settings_before_mask.json
develop_settings_after_mask.json
mask_quality_evaluation.json
radial_template_manifest_ref.json
```

Library build artifact:

```text
seed_preset_metadata.json
generation_report.json
manifest.json
manifest.sha256
live_template_sampling_report.json
```

## 12. 오류 코드

새 error code가 필요하면 enum/DB/migration/recovery/fixture를 함께 업데이트한다.

권장 코드:

```text
MASK_PLAN_SCHEMA_INVALID
MASK_CAPABILITY_UNSUPPORTED
RADIAL_TEMPLATE_UNKNOWN
RADIAL_TEMPLATE_CHECKSUM_MISMATCH
RADIAL_TEMPLATE_APPLY_FAILED
RADIAL_FIT_REJECTED
LOCAL_ADJUSTMENT_OUT_OF_BOUNDS
MASK_IDEMPOTENCY_CONFLICT
MASK_ROLLBACK_FAILED
MASK_EVIDENCE_MISSING
```

기존 generic error code로 충분하면 새 enum을 만들지 않는다.

## 13. 상태 전이

T-029 때문에 새 top-level 작업 상태를 만들지 않는다. T-021 attempt 안의 `LIGHTROOM_PROCESSING` stage evidence로 처리한다.

```text
ADJUSTMENT_READY
→ LIGHTROOM_PROCESSING
  ├─ global apply
  ├─ local mask apply
  └─ export
→ EXPORTED
```

마스크 실패가 quality 문제인지 technical failure인지 구분한다.

```text
request/schema/template/plugin failure → TECHNICAL_FAILED
mask는 적용됐지만 target quality 부족 → RETRY_REQUIRED 또는 FINAL_FAILED
fit policy가 안전하지 않아 skip → policy에 따라 REVIEW_REQUIRED/SOURCE_LIMITED가 아니라 명시적 local degraded evidence
```

## 14. 테스트 계층

### Static
- required files/skills/schemas
- JSON fixture validation
- forbidden field detection
- manifest path/checksum format

### Unit
- geometry validation
- fit calculations
- deterministic tie-break
- clamp
- native failure → radial strategy

### Fake runtime
- valid request/result
- unknown template
- checksum mismatch
- duplicate idempotency key
- rollback path

### Real Lightroom
- one seed preset application
- geometry persistence
- full manifest sample application
- supplied photo target alignment
- replay duplicate prevention
- user mask preservation

## 15. 완료 보고 형식

```text
Ticket ID: T-029
Implemented scope:
Changed files:
Phase 0 result:
Supported Lightroom version:
Template library version/checksum:
Commands run:
Static harness result:
Runtime harness result:
Real Lightroom live result:
Regression result T-019..T-028:
Background-person recovery result:
Known limitations:
Blocked items:
Out-of-scope items not implemented:
Waiting for user approval:
```
