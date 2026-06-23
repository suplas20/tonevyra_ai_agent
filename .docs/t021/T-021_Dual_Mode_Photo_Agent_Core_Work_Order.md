# T-021 — Dual-Mode Photo Agent Core and Closed-Loop Quality Reprocessing 작업 지시서

## 1. 문서 상태

```text
Ticket: T-021
Title: Dual-Mode Photo Agent Core and Closed-Loop Quality Reprocessing
Project root: F:\tonevyra_ai_agent
Baseline: T-020 완료본
Primary goal: 공통 Agent Core에서 Module/Model Provider를 교체하고, Lightroom 익스포트 결과를 평가하여 제한된 재보정 루프를 완성한다.
Priority: 제품화 우선, ModuleAnalysisProvider MVP 우선
```

이 문서는 T-021 구현의 최우선 작업 지시서다. `AGENTS.md`가 프로젝트 최상위 규칙이며, 본 문서는 T-021의 범위와 완료 조건을 구체화한다. 기존 T-018, T-019, T-020 문서·스킬·하네스·테스트는 삭제하거나 대체하지 않는다.

---

## 2. 배경

T-019와 T-020에서 다음 실행 경로가 정립됐다.

```text
Agent correction plan
→ Lightroom Apply Adapter
→ Develop settings applied
→ Lightroom Final Export Adapter
→ corrected output file
→ export result JSON
```

현재 남은 핵심 문제는 익스포트된 사진의 품질이 기준에 미달할 때 단일 `failed` 처리로 종료되고, 에이전트가 실패 원인을 분석하여 새로운 보정값으로 재처리하지 못한다는 점이다.

T-021은 플러그인을 판단 계층으로 확장하지 않는다. Lightroom Plugin은 계속 실행 어댑터이며, 사진 분석·품질 판단·재보정 전략·최종 승인과 실패 분류는 Agent가 담당한다.

---

## 3. 한 문장 목표

> 하나의 Common Agent Core에서 분석 Provider를 교체할 수 있게 하고, 익스포트 결과를 평가해 `APPROVED`, `RETRY_REQUIRED`, `SOURCE_LIMITED`, `TECHNICAL_FAILED`, `FINAL_FAILED`로 분류하며, 허용된 횟수 안에서 자동 재보정한다.

---

## 4. 절대 보존 규칙

1. T-020 완료본이 기준선이다.
2. 기존 파일, 문서, 스킬, 하네스, 테스트를 삭제하지 않는다.
3. 기존 스킬 25개를 모두 유지한다.
4. 유사하다는 이유로 기존 스킬을 병합하거나 이름을 변경하지 않는다.
5. T-019 Apply Adapter와 T-020 Final Export Adapter 계약을 회귀 게이트로 유지한다.
6. 기존 플러그인 역할을 확대하지 않는다.
7. 기존 `PASS / REVIEW_REQUIRED / FAILED` 상태를 즉시 제거하지 않는다. T-021 상태와의 호환 매핑 및 DB migration을 제공한다.
8. 기존 산출물을 새 문서로 덮어쓴 뒤 이전 파일을 제거하지 않는다.
9. 신규 규칙은 증분 추가하고 변경 이력을 남긴다.

---

## 5. 제품 구조

```text
Common Agent Core
├─ Job Manager
├─ State Manager
├─ Analysis Orchestrator
├─ Adjustment Planner
├─ Lightroom Command Generator
├─ Plugin Interface
├─ Export Result Collector
├─ Quality Evaluator
├─ Retry Controller
├─ Plan Policy
├─ Audit Logger
└─ Providers
   ├─ ModuleAnalysisProvider
   ├─ ModelAnalysisProvider
   ├─ ModuleQualityProvider
   └─ ModelQualityProvider
```

두 플랜은 별도 코드베이스나 별도 저장소가 아니다. Provider만 교체하고 동일한 코어, 상태 머신, Lightroom 명령 포맷, 로그 구조, 익스포트 설정 골격을 사용한다.

---

## 6. 구현 순서

### Phase A — 공통 코어와 Module Provider MVP

1. Job/State Manager
2. 공통 분석 결과 스키마
3. `AnalysisProvider`와 `QualityProvider` 인터페이스
4. `ModuleAnalysisProvider`
5. `ModuleQualityProvider`
6. Adjustment Planner 연결
7. Lightroom apply/export 결과 수집
8. T-021 상태 머신
9. Retry Controller
10. 감사 로그와 artifact
11. 정적·mock·fake harness

### Phase B — Model Provider 연결

1. `ModelAnalysisProvider` adapter
2. 모델 출력 schema validation
3. 정책 검증과 안전 범위 clamp
4. `ModelQualityProvider`
5. Provider 비교 harness
6. 비용·지연·메모리 계측
7. 명시적 human approval 후 플랜 활성화

Module Provider MVP가 통과하기 전에 실제 모델 Provider를 기본 경로로 연결하지 않는다.

---

## 7. Provider 계약

### 7.1 AnalysisProvider

입력:

```text
job_id
source artifact reference
preview artifact reference
EXIF/basic metadata
plan policy
previous attempt context (optional)
```

출력:

```text
schema_version
provider_type
provider_version
scene
subjects
technical_findings
color_findings
quality_risks
confidence
analysis_evidence
```

Provider는 Lightroom slider 값을 직접 확정하지 않는다. 특히 Model Provider 출력에 `lightroom_adjustments`, `develop_settings`, `preset_path`를 포함하여 Planner를 우회하면 안 된다.

### 7.2 QualityProvider

입력:

```text
source reference
export reference
analysis result
applied adjustment plan
previous quality result (optional)
plan policy
```

출력:

```text
status
scores
reason_codes
improvement_summary
retry_recommendation
source_limit_evidence
confidence
```

최종 상태 결정은 Quality Evaluator와 State Manager가 정책 검증 후 수행한다.

---

## 8. 분석 방식

### 8.1 ModuleAnalysisProvider

모델 없이 다음 분석을 수행한다.

```text
histogram
mean/median/center luminance
highlight clipping
shadow crushing
white balance estimate
color cast
saturation
contrast
noise
sharpness
blur
basic face detection
basic skin-tone range
simple scene classification
EXIF-derived risk
```

규칙은 재현 가능하고 버전이 고정되어야 한다. 같은 입력과 같은 설정에서는 같은 구조화 결과를 생성해야 한다.

### 8.2 ModelAnalysisProvider

모델은 다음 의미 기반 정보를 구조화한다.

```text
scene and genre
primary subject
subject/background priority
portrait and skin naturalness
mixed lighting
mood preservation
local adjustment intent
semantic defects
set consistency
```

모델은 분석자이며 최종 Lightroom 값 생성자가 아니다. 모델 출력은 schema validation, policy validation, confidence gate, Adjustment Planner, clamp를 순서대로 거친다.

---

## 9. Adjustment Planner 규칙

```text
Provider result
→ schema validation
→ provider policy validation
→ normalized analysis
→ Adjustment Planner
→ Lightroom parameter clamp
→ correction plan artifact
→ T-019 Apply Adapter
```

Planner는 다음을 보장한다.

1. Lightroom 지원 파라미터만 사용한다.
2. 모든 값은 정의된 안전 범위 안에 있다.
3. 재보정 시 이전 plan과의 delta가 기록된다.
4. 같은 실패 원인에 동일한 값을 반복 적용하지 않는다.
5. 모델 출력이 Planner를 우회하지 못한다.
6. 전역 보정과 향후 부분 보정 의도를 구분한다.
7. 적용 불가능한 의도는 명시적으로 defer 또는 reject한다.

---

## 10. 상태 머신

정상 흐름:

```text
CREATED
→ ANALYZING
→ ADJUSTMENT_READY
→ LIGHTROOM_PROCESSING
→ EXPORTED
→ EVALUATING
→ APPROVED
```

재보정 흐름:

```text
EVALUATING
→ RETRY_REQUIRED
→ ADJUSTMENT_READY
→ LIGHTROOM_PROCESSING
→ EXPORTED
→ EVALUATING
```

실패 흐름:

```text
ANY EXECUTION STAGE → TECHNICAL_FAILED
EVALUATING → SOURCE_LIMITED
EVALUATING → FINAL_FAILED
```

금지:

```text
APPROVED → RETRY_REQUIRED
SOURCE_LIMITED → ADJUSTMENT_READY
FINAL_FAILED → ADJUSTMENT_READY
TECHNICAL_FAILED → quality retry without technical recovery evidence
EVALUATING → EVALUATING without a new evaluation attempt record
```

---

## 11. T-020 상태 호환 매핑

T-021 migration 완료 전에는 기존 상태를 보존하며 다음과 같이 매핑한다.

| T-021 의미 | 기존 호환 상태/단계 | 추가 증거 |
|---|---|---|
| `EXPORTED` | `EXPORT_DONE` | T-020 result와 실제 파일 검증 |
| `EVALUATING` | `QUALITY_CHECK` | `quality_attempt` event |
| `APPROVED` | `PASS` | `t021_decision=APPROVED` |
| `RETRY_REQUIRED` | 비종결 이벤트 | `retry_required` event와 next plan |
| `SOURCE_LIMITED` | `FAILED` | `failure_class=SOURCE_LIMITED` |
| `TECHNICAL_FAILED` | `FAILED` | `failure_class=TECHNICAL_FAILED` |
| `FINAL_FAILED` | `FAILED` | `failure_class=FINAL_FAILED` |

DB enum을 확장할 때는 코드 enum, DB constraint, Alembic migration, repository, recovery, CLI, fixture, harness를 한 번에 갱신한다.

---

## 12. 실패 분류

### TECHNICAL_FAILED

Lightroom, Plugin, bridge, file, path, schema, artifact, DB, timeout 등 실행 계층 오류다. 사진 품질 실패가 아니다.

### RETRY_REQUIRED

현재 품질은 기준 미달이지만 새로운 보정값으로 개선 가능하다. 이유 코드와 다음 시도 전략이 반드시 존재해야 한다.

### SOURCE_LIMITED

심한 초점 실패, 흔들림, 복구 불가능한 clipping, 원본 정보 부족 등 보정값 변경으로 해결할 수 없는 원본 한계다.

### FINAL_FAILED

재시도 한도 초과, 개선 폭 부족, 반복 실패, 정책상 중단 등으로 더 이상 자동 보정을 진행하지 않는다.

### APPROVED

기술 검증과 품질 기준을 모두 통과했다.

---

## 13. 품질 평가

공통 기술 지표:

```text
exposure
highlight retention
shadow detail
white balance
color cast
saturation
contrast
noise
sharpness
oversharpening
halo
source-to-output improvement
```

의미 기반 지표:

```text
subject emphasis
skin naturalness
subject/background separation
mood preservation
scene intent
set consistency
```

Module Quality Provider는 수치와 규칙 중심으로 평가한다. Model Quality Provider는 동일한 기술 지표를 유지하면서 의미·미학 평가를 추가한다. Provider별 점수 스케일은 공통 normalized score로 변환해야 한다.

---

## 14. 재시도 정책

생산 기본값:

```text
Free: max_quality_retries = 1
Lite: max_quality_retries = 2
Standard: max_quality_retries = 2
Pro: max_quality_retries = 3
```

개발용 `t021_mvp` 프로필은 Module Provider 폐쇄 루프를 검증하기 위해 최대 2회까지 허용할 수 있다.

모든 재시도는 다음 조건을 만족해야 한다.

1. 명시적인 `RETRY_REQUIRED` 평가가 있다.
2. 남은 retry budget이 있다.
3. 새로운 correction plan이 이전 plan과 의미 있게 다르다.
4. 동일 request id를 재사용하지 않는다.
5. 동일 `job_id` 아래 `attempt_no`를 증가시킨다.
6. 이전 apply/export/quality artifact를 보존한다.
7. timeout과 retry는 bounded다.
8. 개선 폭이 최소 기준 미만이면 `FINAL_FAILED`로 종료한다.
9. 기술 실패는 품질 retry budget을 소비하지 않는다. 기술 recovery budget을 별도로 사용한다.

---

## 15. SaaS 플랜 정책

플랜 정책은 Provider 선택, 최대 처리량, 출력 옵션, retry budget을 결정한다. 품질을 인위적으로 훼손하는 규칙은 금지한다.

```yaml
plan: free
analysis_provider: module
quality_provider: module
max_quality_retries: 1
```

```yaml
plan: standard
analysis_provider: model
quality_provider: model
max_quality_retries: 2
```

무료 플랜도 가능한 범위에서 가장 좋은 Module Provider 결과를 제공해야 한다. 유료 플랜의 차이는 모델 기반 의미 이해, 복합 장면 대응, 재평가 깊이, 처리량, 고급 기능에서 발생해야 한다.

---

## 16. Plugin 역할 고정

Plugin 책임:

```text
request consume
schema validation
catalog photo find/import
Develop settings apply
Lightroom export
result JSON write
technical error report
```

Plugin 금지:

```text
photo aesthetic judgment
quality score
APPROVED/RETRY_REQUIRED decision
source limitation decision
retry plan generation
model execution
SaaS plan decision
PostgreSQL direct access
full pipeline orchestration
```

플러그인 성공은 지시된 Lightroom 작업과 익스포트를 정확히 수행했는지로 판단한다. 사진이 보기 좋은지는 Agent가 판단한다.

---

## 17. Artifact와 감사 로그

시도별 최소 artifact:

```text
attempt_manifest.json
analysis_result.json
normalized_analysis.json
adjustment_plan.json
lightroom_apply_request.json
lightroom_apply_result.json
lightroom_export_request.json
lightroom_export_result.json
quality_evaluation.json
state_transition.json
retry_decision.json (retry 시)
```

필수 식별자:

```text
job_id
task_id
attempt_id
attempt_no
analysis_provider
quality_provider
plan
request_id
parent_attempt_id
```

모든 artifact는 atomic write, checksum, size, version, DB registration 규칙을 유지한다.

---

## 18. DB 및 migration 요구

필요한 경우 다음 필드를 추가한다.

```text
analysis_provider
quality_provider
plan_tier
attempt_no
max_quality_retries
failure_class
terminal_reason
parent_attempt_id
```

신규 테이블이 필요하다면 최소화하고 기존 `image_tasks`, `stage_results`, `quality_results`, `task_events`, `task_artifacts`를 우선 확장한다. 상태와 실패 분류는 문자열을 임의로 저장하지 말고 코드 enum과 DB constraint를 동기화한다.

---

## 19. 보안 및 모델 정책

1. 사진, preview, prompt, model result, quality result는 로컬에 남는다.
2. Model Provider는 local-only model file을 사용한다.
3. remote API fallback은 금지한다.
4. runtime download와 external URL image loading을 금지한다.
5. Provider 선택이 실패해도 원격 Provider로 자동 전환하지 않는다.
6. Model Provider 미사용 플랜에서 모델을 로드하지 않는다.
7. audit log에 원본 이미지 binary나 전체 prompt를 DB blob으로 저장하지 않는다.

---

## 20. 구현 범위

### 포함

- Common Agent Core 인터페이스
- Provider registry와 plan policy
- Module Analysis/Quality Provider MVP
- Model Provider interface와 mock contract
- normalized schema
- state machine
- quality evaluator
- retry controller
- failure classification
- compatibility mapping
- artifacts and audit events
- fixtures and harness
- T-019/T-020 regression gates

### 제외

- 두 개의 독립 agent repository
- 실시간 클라우드 모델 API
- 자동 fine-tuning
- 무제한 재시도
- Plugin 품질 판단
- 무료 플랜 고의 품질 저하
- Lightroom UI click automation
- 다중 사용자 SaaS 계정/결제 구현
- 대규모 분산 queue
- 모델이 직접 Lightroom 값을 확정하는 구조

---

## 21. 테스트 요구

필수 테스트:

1. 기존 25개 스킬 보존
2. T-019/T-020 문서·계약·스크립트 보존
3. Module/Model Provider 공통 schema
4. Model output의 direct adjustment 차단
5. legal/illegal state transition
6. retry budget
7. retry 시 attempt 증가와 artifact 보존
8. technical failure와 quality failure 분리
9. source limitation 종료
10. improvement 부족 종료
11. plan별 Provider 선택
12. Module Provider 결정론
13. 동일 fixture에 대한 Provider 비교
14. Plugin 역할 경계
15. T-020 실제 export file 검증 회귀

---

## 22. 완료 조건

T-021은 다음을 모두 충족해야 완료다.

```text
[ ] Common Agent Core가 Provider 구현과 분리되어 있다.
[ ] ModuleAnalysisProvider와 ModuleQualityProvider 폐쇄 루프가 동작한다.
[ ] Model Provider는 구조화 결과만 반환하고 Planner를 우회하지 않는다.
[ ] T-020 export 성공 증거 후에만 EVALUATING으로 진입한다.
[ ] 품질 결과가 다섯 상태 중 하나로 명확히 분류된다.
[ ] RETRY_REQUIRED에서 새 plan으로 재처리된다.
[ ] plan별 retry budget을 초과하지 않는다.
[ ] 기술 실패와 품질 실패가 분리된다.
[ ] 원본 한계가 SOURCE_LIMITED로 기록된다.
[ ] 모든 attempt artifact와 event가 보존된다.
[ ] 기존 T-019/T-020 harness가 계속 통과한다.
[ ] T-021 harness가 통과한다.
[ ] 기존 25개 스킬과 신규 스킬이 모두 inventory에 존재한다.
```

---

## 23. 필수 참조

```text
.docs/t021/T-021_Dual_Mode_Photo_Agent_Core_Work_Order.md
.docs/t021/T-021_Implementation_Specification.md
skills/dual-mode-agent-core/SKILL.md
skills/closed-loop-quality-reprocessing/SKILL.md
harness/CONTRACT_T021_DUAL_MODE_CLOSED_LOOP.md
harness/scripts/verify_t021_dual_mode_closed_loop.py
```
