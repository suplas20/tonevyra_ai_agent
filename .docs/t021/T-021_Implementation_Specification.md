# T-021 구현 명세 — Dual-Mode Agent Core & Closed-Loop Reprocessing

## 1. 목적

이 명세는 T-021 작업 지시서를 실제 코드 구조, 인터페이스, 스키마, 상태 전이, artifact, DB migration, harness 항목으로 변환한다. 구현자는 임의 구조보다 이 명세의 경계를 우선한다.

---

## 2. 권장 모듈 구조

```text
src/tonevyra_agent/
  agent/
    core.py
    job_manager.py
    state_manager.py
    retry_controller.py
    plan_policy.py
    audit.py
  providers/
    base.py
    registry.py
    module_analysis.py
    model_analysis.py
    module_quality.py
    model_quality.py
  schemas/
    analysis.py
    quality.py
    adjustment.py
    job.py
  correction/
    planner.py
    safety.py
  lightroom/
    apply_client.py
    export_client.py
    result_collector.py
  quality/
    evaluator.py
    source_limit.py
  storage/
    artifacts.py
  persistence/
    models.py
    repositories.py
```

기존 모듈이 이미 같은 책임을 수행하면 새 파일을 중복 생성하지 말고 기존 위치를 확장한다. 단, Provider, Planner, Plugin transport, Quality decision의 책임 경계는 유지한다.

---

## 3. 핵심 인터페이스

### 3.1 AnalysisProvider

```python
class AnalysisProvider(Protocol):
    provider_type: Literal["module", "model"]
    provider_version: str

    def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        ...
```

요구사항:

- 동기 또는 비동기 구현은 adapter 뒤에 숨긴다.
- `AnalysisResult`는 공통 schema를 사용한다.
- source file path를 remote URL로 변환하지 않는다.
- model provider는 Lightroom adjustment를 반환하지 않는다.

### 3.2 QualityProvider

```python
class QualityProvider(Protocol):
    provider_type: Literal["module", "model"]
    provider_version: str

    def evaluate(self, request: QualityRequest) -> QualityResult:
        ...
```

### 3.3 AdjustmentPlanner

```python
class AdjustmentPlanner(Protocol):
    def build_plan(
        self,
        analysis: AnalysisResult,
        context: AttemptContext,
    ) -> AdjustmentPlan:
        ...
```

### 3.4 RetryController

```python
class RetryController(Protocol):
    def decide(
        self,
        quality: QualityResult,
        context: AttemptContext,
        policy: PlanPolicy,
    ) -> RetryDecision:
        ...
```

---

## 4. 공통 데이터 모델

### 4.1 JobEnvelope

```json
{
  "schema_version": "t021.job.v1",
  "job_id": "job-uuid",
  "task_id": "task-uuid",
  "plan": "free",
  "analysis_provider": "module",
  "quality_provider": "module",
  "state": "CREATED",
  "attempt_no": 0,
  "max_quality_retries": 1,
  "created_at": "2026-06-22T00:00:00Z",
  "updated_at": "2026-06-22T00:00:00Z"
}
```

### 4.2 AnalysisResult

필수 필드:

```text
schema_version
job_id
attempt_id
provider_type
provider_version
scene
subjects
technical_findings
color_findings
quality_risks
confidence
created_at
```

금지 필드:

```text
lightroom_adjustments
develop_settings
preset_path
export_path
final_decision
```

### 4.3 AdjustmentPlan

```json
{
  "schema_version": "t021.adjustment_plan.v1",
  "job_id": "job-uuid",
  "attempt_id": "attempt-uuid",
  "planner_version": "planner-v1",
  "based_on_analysis_sha256": "...",
  "adjustments": {
    "exposure": 0.35,
    "contrast": 8,
    "highlights": -25,
    "shadows": 18,
    "temperature": 4,
    "tint": 1,
    "dehaze": 5,
    "vibrance": 8,
    "saturation": 0
  },
  "clamp_events": [],
  "reason_codes": ["UNDEREXPOSED", "SHADOW_DETAIL_LOW"],
  "created_at": "2026-06-22T00:00:05Z"
}
```

### 4.4 QualityResult

```json
{
  "schema_version": "t021.quality.v1",
  "job_id": "job-uuid",
  "attempt_id": "attempt-uuid",
  "provider_type": "module",
  "status": "RETRY_REQUIRED",
  "scores": {
    "exposure": 0.78,
    "highlight_retention": 0.95,
    "shadow_detail": 0.62,
    "white_balance": 0.84,
    "color_naturalness": 0.81,
    "sharpness": 0.86,
    "noise": 0.71,
    "overall": 0.77
  },
  "reason_codes": ["SHADOW_DETAIL_LOW", "NOISE_ELEVATED"],
  "retry_recommendation": {
    "recommended": true,
    "strategy": "recover_shadows_and_reduce_sharpening",
    "expected_gain": 0.08
  },
  "source_limit_evidence": [],
  "created_at": "2026-06-22T00:00:20Z"
}
```

---

## 5. 상태 전이 표

| From | To | 조건 |
|---|---|---|
| CREATED | ANALYZING | job과 source artifact 유효 |
| ANALYZING | ADJUSTMENT_READY | analysis schema와 Planner 검증 성공 |
| ANALYZING | TECHNICAL_FAILED | provider 실행 또는 schema 오류 |
| ADJUSTMENT_READY | LIGHTROOM_PROCESSING | apply request atomic write 성공 |
| LIGHTROOM_PROCESSING | EXPORTED | T-019 applied + T-020 exported + 실제 파일 검증 |
| LIGHTROOM_PROCESSING | TECHNICAL_FAILED | apply/export/timeout/file 실패 |
| EXPORTED | EVALUATING | export artifact 등록 성공 |
| EVALUATING | APPROVED | 품질 threshold 통과 |
| EVALUATING | RETRY_REQUIRED | 개선 가능 + retry budget 남음 |
| EVALUATING | SOURCE_LIMITED | 원본 한계 증거 충족 |
| EVALUATING | FINAL_FAILED | budget 소진 또는 개선 가능성 부족 |
| RETRY_REQUIRED | ADJUSTMENT_READY | 새 analysis context 또는 retry plan 생성 |

모든 전이는 `task_events`와 `state_transition.json`에 기록한다.

---

## 6. Attempt 모델

```text
job_id: 전체 사진 작업 식별자
attempt_id: 각 보정 시도 식별자
attempt_no: 0부터 시작하는 시도 번호
parent_attempt_id: 재시도일 때 이전 attempt
```

한 attempt는 하나의 analysis, plan, apply, export, quality 결과 세트를 가진다. 재시도 시 기존 artifact를 수정하지 않고 새 attempt 디렉터리를 만든다.

권장 경로:

```text
runtime/artifacts/<job_id>/attempts/000/
runtime/artifacts/<job_id>/attempts/001/
```

---

## 7. PlanPolicy

```python
@dataclass(frozen=True)
class PlanPolicy:
    name: str
    analysis_provider: str
    quality_provider: str
    max_quality_retries: int
    allow_model_loading: bool
    allow_set_consistency: bool
    output_profile: str
```

기본 정책:

| Plan | Analysis | Quality | Retry | Model loading |
|---|---|---:|---:|---|
| free | module | module | 1 | no |
| lite | module | module | 2 | no |
| standard | model | model | 2 | yes |
| pro | model | model | 3 | yes |
| t021_mvp | module | module | 2 | no |

정책은 사용자 사진의 품질을 의도적으로 낮추는 slider cap을 포함하면 안 된다.

---

## 8. Module Provider 구현

### Analysis

- histogram bin statistics
- luminance percentiles
- clipping ratios
- channel imbalance
- estimated color temperature/tint tendency
- local contrast estimate
- noise estimate
- edge-based sharpness/blur
- basic face/skin heuristics
- EXIF risk signals

### Quality

- source와 output 비교
- 절대 품질 + 개선도 동시 평가
- threshold와 reason code 생성
- deterministic output
- 동일 input checksum + provider version + config hash에서 동일 결과

모든 threshold는 versioned config artifact에 기록한다.

---

## 9. Model Provider 구현

Model Provider adapter는 다음을 강제한다.

1. local-only model path
2. offline environment
3. common JSON schema
4. forbidden field rejection
5. confidence threshold
6. timeout
7. no remote fallback
8. no direct Planner bypass
9. raw response artifact와 normalized result 분리
10. prompt/model/config version 기록

Model Provider 실패 시 Module Provider로 자동 강등하지 않는다. 플랜 정책이 명시적으로 허용하고 감사 이벤트가 남는 경우에만 controlled fallback을 사용할 수 있으며, T-021 MVP 기본값은 fallback 금지다.

---

## 10. QualityEvaluator 결정 규칙

개념적 순서:

```text
1. export technical evidence 검증
2. quality schema 검증
3. source-limit evidence 검증
4. hard failure rules
5. overall and category thresholds
6. source-to-output improvement
7. retry budget
8. loop-progress guard
9. terminal decision
```

우선순위:

```text
TECHNICAL_FAILED
→ SOURCE_LIMITED
→ APPROVED
→ RETRY_REQUIRED
→ FINAL_FAILED
```

기술 실패는 사진 품질 점수로 덮어쓰지 않는다.

---

## 11. Loop-progress guard

무한 반복 방지를 위해 다음을 기록한다.

```text
previous_overall_score
current_overall_score
score_delta
plan_delta_hash
repeated_reason_codes
attempt_no
remaining_retry_budget
```

기본 중단 조건 예:

```text
score_delta < 0.02 for two consecutive attempts
same plan_delta_hash repeated
same dominant reason without strategy change
retry budget exhausted
```

정확한 threshold는 config로 관리하고 fixture/harness로 검증한다.

---

## 12. 오류 분류

기술 오류 예:

```text
ANALYSIS_PROVIDER_FAILED
ANALYSIS_SCHEMA_INVALID
PLANNER_FAILED
LIGHTROOM_APPLY_FAILED
LIGHTROOM_EXPORT_FAILED
EXPORT_FILE_MISSING
QUALITY_PROVIDER_FAILED
ARTIFACT_WRITE_FAILED
DB_WRITE_FAILED
STATE_TRANSITION_INVALID
```

품질 이유 예:

```text
UNDEREXPOSED
HIGHLIGHT_CLIPPED
SHADOW_CRUSHED
WHITE_BALANCE_OFF
COLOR_CAST
OVERSATURATED
NOISE_ELEVATED
BLUR_DETECTED
OVERSHARPENED
SKIN_TONE_UNNATURAL
SUBJECT_NOT_PRIORITIZED
MOOD_LOST
```

원본 한계 예:

```text
SOURCE_FOCUS_FAILURE
SOURCE_MOTION_BLUR
SOURCE_IRRECOVERABLE_CLIPPING
SOURCE_RESOLUTION_TOO_LOW
SOURCE_DATA_INSUFFICIENT
```

신규 값은 enum, DB, migration, documentation, fixture, recovery를 동기화한다.

---

## 13. Artifact manifest

`attempt_manifest.json` 예:

```json
{
  "schema_version": "t021.attempt_manifest.v1",
  "job_id": "job-uuid",
  "attempt_id": "attempt-uuid",
  "attempt_no": 1,
  "parent_attempt_id": "attempt-uuid-0",
  "analysis_provider": "module",
  "quality_provider": "module",
  "artifacts": [
    {"type": "analysis_result", "path": "analysis_result.json", "sha256": "..."},
    {"type": "adjustment_plan", "path": "adjustment_plan.json", "sha256": "..."},
    {"type": "quality_evaluation", "path": "quality_evaluation.json", "sha256": "..."}
  ]
}
```

---

## 14. DB migration 계획

1. 현재 enum/constraint와 실제 DB 상태를 조사한다.
2. T-021 상태를 직접 추가할지 compatibility payload 단계로 둘지 결정한다.
3. additive Alembic migration을 작성한다.
4. downgrade 또는 rollback 절차를 문서화한다.
5. 기존 T-020 row를 손실 없이 읽을 수 있어야 한다.
6. 기존 `PASS`, `REVIEW_REQUIRED`, `FAILED` 데이터를 자동 재분류하지 않는다.
7. 새 row부터 T-021 failure class를 기록한다.

---

## 15. CLI 요구

기존 CLI-first 원칙을 유지한다. 최소 진단 출력:

```text
job_id
plan
analysis_provider
quality_provider
state
attempt_no / max retries
last quality status
failure_class
artifact root
```

권장 명령은 기존 CLI 구조에 맞춰 확장하며 임의로 새 command family를 만들지 않는다.

---

## 16. Harness 요구

정적 계약:

```powershell
python .\harness\scripts\verify_t021_dual_mode_closed_loop.py --project-root F:\tonevyra_ai_agent
```

구현 증거가 준비된 뒤 strict 검증:

```powershell
python .\harness\scripts\verify_t021_dual_mode_closed_loop.py --project-root F:\tonevyra_ai_agent --job-evidence <job-manifest.json> --strict
```

T-021 harness 전에 T-019와 T-020 harness를 실행한다.

---

## 17. 수용 테스트 시나리오

### Scenario A — Module Provider first-pass approval

```text
module analysis
→ safe plan
→ apply/export success
→ quality APPROVED
→ no retry
```

### Scenario B — Module Provider quality retry

```text
attempt 0 RETRY_REQUIRED
→ new plan delta
→ attempt 1 APPROVED
```

### Scenario C — Retry exhausted

```text
attempt 0 RETRY_REQUIRED
→ attempt 1 insufficient gain
→ FINAL_FAILED
```

### Scenario D — Source limited

```text
export technically succeeds
→ severe source blur evidence
→ SOURCE_LIMITED
→ no retry
```

### Scenario E — Technical export failure

```text
Lightroom export failed
→ TECHNICAL_FAILED
→ no quality evaluation
```

### Scenario F — Model output bypass attempt

```text
model output includes lightroom_adjustments
→ schema rejected
→ ANALYSIS_SCHEMA_INVALID
```

### Scenario G — Plan provider policy

```text
free loads no model
standard selects model provider
provider result schema remains identical
```

---

## 18. Definition of Done

- 모든 인터페이스가 타입과 schema로 명확하다.
- Module Provider 기반 end-to-end 폐쇄 루프가 통과한다.
- Model Provider는 interface/mock contract까지 통과한다.
- Plugin은 기술 실행 계층으로 유지된다.
- 재시도는 bounded, versioned, auditable하다.
- 기존 T-019/T-020 회귀 테스트가 통과한다.
- T-021 static harness와 runtime evidence harness가 통과한다.
- 기존 스킬 25개와 신규 스킬 2개가 모두 존재한다.
