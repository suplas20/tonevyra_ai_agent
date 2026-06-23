# T-022 — Local Model Provider Integration and Premium Quality Pipeline 작업 지시서

## 1. 문서 상태

```text
Ticket: T-022
Title: Local Model Provider Integration and Premium Quality Pipeline
Project root: F:\tonevyra_ai_agent
Baseline: T-021 구현 및 T-021 하네스 통과본
Primary goal: T-021의 Provider 인터페이스에 실제 로컬 비전 모델을 연결하고, 모델 기반 분석·품질 평가·제한된 재보정 경로를 Standard/Pro 플랜에서 동작하게 한다.
Priority: 로컬 전용, 구조화 출력, 안전한 Planner 경계, 재현 가능한 검증
```

이 문서는 T-022 구현의 작업 지시서다. T-021에서 완성한 Common Agent Core, 상태 머신, Adjustment Planner, 품질 평가 및 bounded retry 구조를 변경하거나 우회하지 않는다.

---

## 2. 선행 조건

T-022는 다음 T-021 결과가 실제 코드에 존재하고 하네스를 통과한 상태에서 시작한다.

```text
Common Agent Core
AnalysisProvider / QualityProvider interfaces
ModuleAnalysisProvider / ModuleQualityProvider
normalized analysis schema
normalized quality schema
Adjustment Planner and parameter clamp
T-021 state machine
Retry Controller
plan policy
T-019 Lightroom Apply Adapter
T-020 Lightroom Final Export Adapter
```

위 구성요소가 mock 문서에만 존재하고 실제 실행 경로에 연결되지 않았다면 T-022를 완료 처리하지 않는다.

---

## 3. 한 문장 목표

> Hugging Face에서 사전 확보한 로컬 모델 파일을 직접 로드하는 ModelAnalysisProvider와 ModelQualityProvider를 구현하고, 모델 출력을 T-021 공통 스키마로 정규화한 뒤 정책 검증·Adjustment Planner·품질 상태 머신을 통해 Standard/Pro 플랜의 실제 보정 루프를 완성한다.

---

## 4. T-022가 해결할 문제

T-021은 모델 Provider를 교체할 수 있는 공통 구조와 closed-loop를 만들었다. T-022는 그 인터페이스에 실제 모델 실행 계층을 연결한다.

T-022 완료 후 목표 흐름은 다음과 같다.

```text
사진 입력
→ Plan Router
→ ModelAnalysisProvider
→ Local Vision Model Runtime
→ 구조화 분석 결과
→ schema / policy / confidence validation
→ Adjustment Planner
→ Lightroom Apply Adapter
→ Lightroom Final Export Adapter
→ ModelQualityProvider
→ source/export 비교 평가
→ APPROVED
   또는 RETRY_REQUIRED → 새 분석 근거와 재보정 전략 → 제한된 재처리
   또는 SOURCE_LIMITED
   또는 TECHNICAL_FAILED
   또는 FINAL_FAILED
```

모델은 사진을 해석하고 품질 문제와 재보정 방향을 제안한다. 모델이 Lightroom 값을 직접 실행하거나 최종 상태를 단독 확정해서는 안 된다.

---

## 5. 절대 보존 규칙

1. T-021 완료본을 기준선으로 사용한다.
2. 기존 27개 스킬과 기존 하네스 파일을 삭제·병합·이름 변경하지 않는다.
3. T-019 Apply Adapter와 T-020 Final Export Adapter 계약을 유지한다.
4. T-021 Provider 인터페이스, 공통 스키마, 상태 머신, Retry Controller를 우회하지 않는다.
5. 모델 없는 Free/Lite 경로가 기존과 동일하게 동작해야 한다.
6. Free/Lite 작업에서는 모델 파일을 로드하거나 GPU 메모리를 점유하지 않는다.
7. 모델은 `lightroom_adjustments`, `develop_settings`, `preset_path`를 직접 출력하거나 실행하지 않는다.
8. 원격 모델 API, 런타임 다운로드, 외부 이미지 URL 전송을 금지한다.
9. 모델 오류를 사진 품질 실패로 위장하지 않는다.
10. Provider fallback은 정책에 명시된 경우에만 수행하고 모든 사실을 로그에 남긴다.
11. 기존 하네스 회귀 테스트를 삭제하거나 약화하지 않는다.
12. T-022 완료 선언에는 mock fixture뿐 아니라 실제 로컬 모델 실행 증거가 필요하다.

---

## 6. 범위

### 6.1 포함 범위

```text
LocalVisionModelRuntime
ModelAnalysisProvider
ModelQualityProvider
ModelOutputNormalizer
ModelSchemaValidator
ModelConfidenceGate
PlanRouter integration
ProviderFallbackController
model artifact verification
model runtime telemetry
source/export paired quality evaluation
retry recommendation normalization
module/model comparison harness
Standard/Pro plan activation gate
```

### 6.2 제외 범위

```text
새로운 Lightroom 플러그인 기능 개발
사용자별 취향 학습
사진 세트 전체 일관성 최적화
클라우드 모델 API 연결
모델 파인튜닝 파이프라인
SaaS 결제·과금 구현
대규모 분산 GPU 스케줄러
```

위 항목은 별도 티켓으로 분리한다.

---

## 7. 목표 아키텍처

```text
Common Agent Core
├─ Plan Router
├─ Analysis Orchestrator
│  ├─ ModuleAnalysisProvider
│  └─ ModelAnalysisProvider
│     └─ LocalVisionModelRuntime
├─ ModelOutputNormalizer
├─ Schema / Policy / Confidence Gate
├─ Adjustment Planner
├─ Lightroom Apply / Export Adapters
├─ Quality Orchestrator
│  ├─ ModuleQualityProvider
│  └─ ModelQualityProvider
│     └─ LocalVisionModelRuntime
├─ Retry Controller
├─ ProviderFallbackController
├─ State Manager
└─ Audit / Metrics Logger
```

ModelAnalysisProvider와 ModelQualityProvider는 동일한 Runtime을 공유할 수 있지만, 요청 프롬프트·출력 스키마·평가 책임은 분리한다.

---

## 8. 로컬 모델 실행 정책

### 8.1 모델 확보 방식

모델은 배포 또는 설치 단계에서 미리 확보한다.

```text
approved model repository
→ 별도 다운로드 절차
→ checksum 검증
→ 로컬 model directory 배치
→ runtime 시작 시 manifest 검증
→ 로컬 파일만 로드
```

운영 중 자동 다운로드를 허용하지 않는다.

### 8.2 네트워크 정책

```text
remote inference API: forbidden
runtime model download: forbidden
external image upload: forbidden
URL-based image input: forbidden
telemetry upload: forbidden by default
```

모델 실행 프로세스는 네트워크가 차단된 상태에서도 정상 동작해야 한다.

### 8.3 모델 식별과 무결성

각 실행은 다음 정보를 기록한다.

```text
model_id
model_revision
model_file_path
model_checksum
runtime_backend
runtime_version
device
dtype
quantization
config_hash
```

허용 목록과 checksum이 일치하지 않으면 모델을 로드하지 않고 `TECHNICAL_FAILED`로 처리한다.

### 8.4 Backend

현재 프로젝트의 로컬 Qwen 계열 Backend 또는 동일 계약을 따르는 로컬 비전 Backend를 사용한다. T-022가 특정 모델 파일명에 종속되게 구현하지 말고 Runtime adapter로 분리한다.

---

## 9. Plan Router 규칙

기본 라우팅은 T-021 정책을 유지한다.

```text
free     → ModuleAnalysisProvider / ModuleQualityProvider
lite     → ModuleAnalysisProvider / ModuleQualityProvider
standard → ModelAnalysisProvider / ModelQualityProvider
pro      → ModelAnalysisProvider / ModelQualityProvider
```

필수 조건:

1. Free/Lite 작업은 Model Runtime 초기화를 호출하지 않는다.
2. Standard/Pro 작업은 등록된 모델과 활성화된 정책이 모두 유효할 때만 시작한다.
3. 모델 비활성화 상태에서 Standard/Pro 작업을 Module Provider로 조용히 전환하지 않는다.
4. fallback이 허용된 정책에서는 `requested_provider`, `executed_provider`, `fallback_reason`, `degraded_mode`를 기록한다.
5. fallback이 금지된 정책에서는 모델 실패를 `TECHNICAL_FAILED`로 종료한다.

초기 기본값은 자동 fallback 비활성화다.

---

## 10. ModelAnalysisProvider 계약

### 10.1 입력

```text
job_id
attempt_id
source artifact reference
preview artifact reference
EXIF/basic metadata
plan policy
previous attempt summary (optional)
model runtime config reference
```

### 10.2 모델이 분석해야 하는 항목

```text
scene and genre
primary and secondary subjects
subject/background priority
portrait presence
skin-tone naturalness risk
mixed lighting
white-balance intent
mood and atmosphere
highlight/shadow risk
noise and sharpness risk
semantic local-adjustment intent
source limitation candidates
previous-attempt failure cause (retry only)
```

### 10.3 출력 경계

모델의 raw output은 Runtime envelope에 저장하고, Normalizer가 T-021 `analysis_result` 스키마로 변환한다.

금지 필드:

```text
lightroom_adjustments
develop_settings
preset_path
execute_command
plugin_command
final_status
```

모델은 보정 의도를 reason code와 구조화된 finding으로 제시한다. 실제 Lightroom 수치는 Adjustment Planner가 생성한다.

### 10.4 Confidence Gate

```text
confidence >= configured threshold
→ normalized analysis 사용

confidence < threshold
→ 정책에 따라 재추론, Module Provider fallback 또는 TECHNICAL_FAILED
```

낮은 confidence를 임의의 정상 분석 결과로 취급하지 않는다.

---

## 11. ModelQualityProvider 계약

### 11.1 입력

```text
job_id
attempt_id
source artifact reference
export artifact reference
normalized analysis result
applied adjustment plan
previous quality result (optional)
plan policy
model runtime config reference
```

### 11.2 평가 항목

```text
exposure suitability
highlight preservation
shadow detail
white balance
color cast
saturation
contrast
noise
sharpness
oversharpening / halo
skin-tone naturalness
subject emphasis
subject/background separation
mood preservation
source-to-export improvement
retry potential
source limitation evidence
```

### 11.3 출력

모델의 출력은 T-021 품질 스키마로 정규화한다.

```text
status candidate
scores
reason_codes
improvement_summary
retry_recommendation
source_limit_evidence
confidence
```

모델이 제안한 상태는 Quality Evaluator와 State Manager가 정책 검증 후 확정한다.

### 11.4 재보정 권고

`RETRY_REQUIRED`는 다음 정보를 포함해야 한다.

```text
failure reasons
expected improvement
semantic strategy
priority
risk constraints
avoid repeating previous ineffective strategy
```

재보정 권고에 Lightroom slider 값이나 플러그인 명령을 포함하지 않는다.

---

## 12. Provider 오류와 fallback

### 12.1 기술 오류 분류

```text
MODEL_NOT_FOUND
MODEL_CHECKSUM_MISMATCH
MODEL_LOAD_FAILED
MODEL_OOM
MODEL_TIMEOUT
MODEL_INFERENCE_FAILED
MODEL_OUTPUT_PARSE_FAILED
MODEL_SCHEMA_INVALID
MODEL_LOW_CONFIDENCE
```

위 오류는 기본적으로 `TECHNICAL_FAILED` 계열이며 사진 품질 실패가 아니다.

### 12.2 재시도

모델 Runtime 재시도와 사진 품질 재보정 횟수를 분리한다.

```text
model_runtime_retry_count
quality_retry_count
```

모델 timeout 재호출을 사진 재보정 1회로 계산하지 않는다. 반대로 Lightroom 재보정은 모델 Runtime 재시도로 계산하지 않는다.

### 12.3 제어된 fallback

fallback은 다음 조건을 모두 만족할 때만 허용한다.

```text
plan_policy.allow_module_fallback == true
failure_reason is in allowed fallback reasons
fallback event persisted
executed_provider recorded
result marked degraded_mode
```

fallback이 수행되어도 사용자 플랜과 실제 실행 Provider 차이를 숨기지 않는다.

---

## 13. 상태 머신 연동

T-021 상태 머신을 유지한다.

```text
CREATED
→ ANALYZING
→ ADJUSTMENT_READY
→ LIGHTROOM_PROCESSING
→ EXPORTED
→ EVALUATING
→ APPROVED
```

재보정:

```text
EVALUATING
→ RETRY_REQUIRED
→ ADJUSTMENT_READY
→ LIGHTROOM_PROCESSING
→ EXPORTED
→ EVALUATING
```

모델 기술 실패:

```text
ANALYZING or EVALUATING
→ TECHNICAL_FAILED
```

원본 한계:

```text
EVALUATING
→ SOURCE_LIMITED
```

재보정 예산 소진:

```text
EVALUATING
→ FINAL_FAILED
```

T-022는 새로운 병렬 상태 체계를 만들지 않는다.

---

## 14. 데이터와 artifact

DB에는 경로·체크섬·요약·상태를 저장하고 대형 이미지나 모델 payload를 BLOB으로 저장하지 않는다.

필수 artifact:

```text
model request envelope
raw model response
normalized analysis result
normalized quality result
schema validation result
confidence gate result
fallback decision
runtime metrics
source/export checksums
planner input/output checksum
attempt linkage
```

민감 정보나 원본 이미지의 base64 문자열을 로그에 기록하지 않는다.

---

## 15. 성능 및 자원 계측

각 모델 호출에 대해 다음을 수집한다.

```text
model_load_ms
inference_ms
normalization_ms
peak_vram_mb
peak_ram_mb
input_image_dimensions
token_or_output_length
retry_count
provider_fallback
```

최소 비교 항목:

```text
Module vs Model first-pass approval rate
Module vs Model final approval rate
average quality retries
average processing time
model inference time
peak memory
portrait quality result
mixed-light quality result
source-limited classification accuracy
```

T-022는 모델이 항상 우수하다고 가정하지 않는다. 동일 fixture와 동일 Lightroom 경로에서 비교 증거를 남긴다.

---

## 16. 보안 조건

1. 런타임 네트워크 요청이 없어야 한다.
2. model path는 allowlisted root 밖으로 벗어날 수 없다.
3. symlink를 통한 외부 경로 탈출을 거부한다.
4. checksum 불일치 모델을 로드하지 않는다.
5. raw output을 명령으로 실행하지 않는다.
6. prompt 또는 model output에 포함된 경로·명령·URL을 신뢰하지 않는다.
7. 이미지 metadata의 문자열을 시스템 명령에 직접 삽입하지 않는다.
8. 모델 오류 상세에 비밀 값이나 전체 환경변수를 출력하지 않는다.

---

## 17. 구현 단계

### Phase A — Runtime와 Analysis Provider

1. `LocalVisionModelRuntime` 인터페이스 구현
2. 로컬 모델 manifest와 checksum 검증
3. 모델 load/unload lifecycle 구현
4. `ModelAnalysisProvider` 구현
5. raw response envelope 저장
6. Normalizer와 T-021 analysis schema 연결
7. confidence gate 구현
8. Free/Lite non-loading 검증

### Phase B — Quality Provider

1. source/export pair 입력 구성
2. `ModelQualityProvider` 구현
3. T-021 quality schema 정규화
4. reason code와 retry recommendation 검증
5. source limitation evidence 검증
6. 이전 attempt 반복 방지 정보 연결

### Phase C — Routing, fallback, telemetry

1. Standard/Pro Plan Router 연결
2. Provider registry 연결
3. 명시적 fallback policy 구현
4. runtime retry와 quality retry 분리
5. model metrics 및 audit event 저장
6. degraded mode 표시

### Phase D — 통합 검증

1. fixture 기반 schema/정책 검증
2. invalid direct-adjustment 출력 차단
3. remote fallback 설정 차단
4. Free/Lite 모델 미로딩 검증
5. Standard/Pro 모델 라우팅 검증
6. timeout/OOM/parse failure 검증
7. 실제 로컬 모델 analysis 실행
8. 실제 export 품질 평가 실행
9. `RETRY_REQUIRED` 1회 이상 실제 closed-loop 검증
10. T-019/T-020/T-021 회귀 검증

---

## 18. 구현 대상 예시

실제 프로젝트 구조에 맞게 경로는 조정할 수 있지만 책임은 분리한다.

```text
src/
  providers/
    model_analysis_provider.py
    model_quality_provider.py
  model_runtime/
    local_vision_runtime.py
    model_manifest.py
    output_normalizer.py
    confidence_gate.py
  policies/
    provider_fallback_policy.py
  telemetry/
    model_runtime_metrics.py
```

기존 Module Provider와 Common Agent Core 파일을 복제해 별도 Agent를 만들지 않는다.

---

## 19. 하네스 필수 검증

T-022 하네스는 최소한 다음을 자동 검증해야 한다.

```text
[ ] 기존 27개 스킬 존재
[ ] T-022 신규 스킬 존재
[ ] T-021 Provider 계약 보존
[ ] Free/Lite 모델 미로딩
[ ] Standard/Pro 모델 라우팅
[ ] 로컬 파일 경로만 허용
[ ] runtime_download=false
[ ] remote_api=false
[ ] checksum 불일치 거부
[ ] 모델 raw output과 normalized output 분리
[ ] direct Lightroom adjustment 필드 거부
[ ] ModelAnalysisProvider 출력 공통 schema 적합
[ ] ModelQualityProvider 출력 공통 schema 적합
[ ] runtime retry와 quality retry 분리
[ ] fallback 비활성 기본값
[ ] 명시적 fallback evidence 기록
[ ] source/export pair 평가
[ ] RETRY_REQUIRED에 구조화 전략 존재
[ ] SOURCE_LIMITED에 evidence 존재
[ ] TECHNICAL_FAILED에 가짜 품질 점수 없음
[ ] 실제 local model evidence strict mode 지원
[ ] T-019/T-020/T-021 회귀 통과
```

---

## 20. 완료 기준

T-022는 다음 조건을 모두 만족해야 완료다.

1. Standard/Pro 요청이 실제 `ModelAnalysisProvider`로 라우팅된다.
2. Free/Lite 요청에서는 모델 Runtime이 로드되지 않는다.
3. 모델은 로컬 파일에서만 로드되고 원격 API와 런타임 다운로드를 사용하지 않는다.
4. 모델 무결성 검증이 동작한다.
5. 분석 결과가 T-021 공통 분석 스키마로 정규화된다.
6. 모델이 Lightroom 값을 직접 생성하거나 실행하지 못한다.
7. `ModelQualityProvider`가 source와 export를 함께 평가한다.
8. 품질 결과가 T-021 공통 품질 스키마와 상태 머신을 따른다.
9. `RETRY_REQUIRED`가 제한된 closed-loop를 실제로 수행한다.
10. runtime retry와 quality retry가 분리 기록된다.
11. fallback은 명시적 정책과 evidence가 있을 때만 수행된다.
12. Module/Model 비교 결과와 실행 metrics가 생성된다.
13. 실제 로컬 모델 실행 evidence를 사용한 strict 하네스가 통과한다.
14. T-019, T-020, T-021 회귀 하네스가 모두 통과한다.

---

## 21. 완료 시 금지되는 상태

다음 중 하나라도 해당하면 T-022 완료가 아니다.

```text
모델 Provider가 fixture만 반환함
모델이 Lightroom slider 값을 직접 출력함
Standard 플랜인데 실제로 Module Provider가 조용히 실행됨
Free 플랜에서 모델이 로드됨
모델이 실행 중 인터넷에서 파일을 다운로드함
원격 API 실패 시 자동으로 외부 서비스로 전송함
ModelQualityProvider가 source 없이 export만 평가함
모델 timeout을 사진 품질 실패로 기록함
retry 횟수 구분 없이 하나의 count를 사용함
mock harness만 통과하고 실제 로컬 모델 evidence가 없음
기존 T-021 closed-loop가 깨짐
```

---

## 22. 다음 티켓과의 경계

T-022 이후의 권장 별도 작업은 사진 세트 단위 일관성 및 배치 보정이다. T-022에서는 단일 사진의 모델 분석·모델 품질 평가·재보정 경로를 안정화하는 데 집중한다.
