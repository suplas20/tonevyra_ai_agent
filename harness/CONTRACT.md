# Harness Contract

이 문서는 하네스가 프로젝트 코드에 기대하는 최소 계약입니다.  
하네스는 단순한 가짜 실행 환경이 아니라, **스킬·계약·보안·복구·루프 증거를 검사하는 acceptance gate**입니다.

## 0. Harness responsibility

하네스는 다음 질문에 답해야 합니다.

```text
구현이 스킬 문서의 필수 규칙을 실제 코드와 데이터로 증명하는가?
실제 Qwen/Lightroom 없이도 end-to-end 흐름이 재현 가능한가?
실패·재시작·품질 판정·피드백이 DB + artifact 근거로 추적 가능한가?
자동 루프가 무한 반복 없이 종료되고 task_events 증거를 남기는가?
```

Mock/Fake backend는 검증을 위한 통제 장치이며, 하네스의 정의 자체는 아닙니다.

## 1. Runtime 폴더 계약

프로젝트는 기본적으로 아래 구조를 사용합니다.

```text
runtime/
  input/
  output/
    pass/
    review_required/
    failed/
    temp/
  artifacts/
  previews/
  bridge/
    requests/
    processing/
    responses/
    errors/
```

## 2. Backend 모드 계약

하네스 실행 시 프로젝트는 아래 모드를 지원해야 합니다.

```env
TONEVYRA_VISION_BACKEND=mock
TONEVYRA_LIGHTROOM_BACKEND=fake
TONEVYRA_WORKER_CONCURRENCY=1
TONEVYRA_MODEL_OFFLINE=true
```

Backward compatibility가 필요한 경우 기존 `MW_*` env를 읽을 수는 있지만, 문서와 신규 구현의 기준은 `TONEVYRA_*`입니다.

필수 backend:

```text
MockVisionBackend
FakeLightroomBridge 또는 file-based bridge + fake_lightroom_worker.py
```

금지:

```text
real Qwen backend
real Lightroom Lua Plugin
network model loading
remote AI API fallback
```

## 3. Lightroom request JSON 계약

Python Agent가 작성하는 request JSON은 최소한 아래 필드를 포함해야 합니다.

```json
{
  "request_id": "task_0001",
  "task_id": "task_0001",
  "source_path": "C:/absolute/path/to/source.jpg",
  "export_path": "C:/absolute/path/to/runtime/output/temp/task_0001.jpg",
  "correction_plan_path": "C:/absolute/path/to/runtime/artifacts/task_0001/correction_plan.json",
  "adjustments": {
    "exposure": 0.3,
    "contrast": 10,
    "highlights": -20,
    "shadows": 15,
    "temperature_delta": 800,
    "tint": 2,
    "dehaze": 8,
    "vibrance": 10,
    "saturation": 0
  }
}
```

중요:

```text
source_path와 export_path는 normalized absolute path여야 합니다.
DB에는 relative path를 저장할 수 있지만 Lightroom request payload는 absolute path를 사용합니다.
Lightroom request는 Correction Planner가 검증한 값만 직렬화합니다.
```

## 4. Lightroom response JSON 계약

Fake Lightroom과 실제 Lua Plugin은 최소한 아래 응답을 생성해야 합니다.

```json
{
  "request_id": "task_0001",
  "task_id": "task_0001",
  "status": "success",
  "export_path": "C:/absolute/path/to/runtime/output/temp/task_0001.jpg",
  "error_code": null,
  "error_message": null
}
```

실패 응답:

```json
{
  "request_id": "task_0001",
  "task_id": "task_0001",
  "status": "failed",
  "export_path": null,
  "error_code": "LIGHTROOM_EXPORT_FAILED",
  "error_message": "Fake export failed"
}
```

## 5. 필수 artifact 계약

Smoke Pipeline 통과를 위해 최소한 아래 artifact가 생성되어야 합니다.

```text
exif.json
preview_1024.jpg
vision_prompt.txt
vision_raw_response.json
vision_structured.json
correction_plan.json
lightroom_request.json
lightroom_response.json
quality_detail.json
```

Artifact는 temp write → flush/fsync 가능한 경우 수행 → atomic rename → checksum/size 계산 → DB 등록 순서로 저장합니다.

## 6. 최종 상태 계약

작업 최종 상태는 아래 중 하나여야 합니다.

```text
PASS
REVIEW_REQUIRED
FAILED
```

`SKIPPED`는 watcher/unsupported 파일 테스트에만 사용합니다.  
`requires_review=true`가 한 번 설정된 task는 quality gate에서 `PASS`로 확정할 수 없고, 최선의 결과는 `REVIEW_REQUIRED`입니다.

## 7. Skill evidence contract

하네스는 “에이전트가 문서를 읽었다” 자체를 직접 증명하지 않습니다. 대신 구현 결과가 스킬의 필수 규칙을 지키는지 검사합니다.

예:

```text
project-scope        → 금지 scope가 추가되지 않았는지
model-security       → runtime download, remote API, trust_remote_code 사용이 없는지
testing-harness      → mock/fake 검증 없이 real backend로 건너뛰지 않았는지
artifact-storage     → stage 완료 전 artifact가 durable하게 저장되었는지
recovery-error       → 로그가 아니라 DB + artifact로 복구하는지
loop-engineering     → task_events에 loop evidence가 남는지
```

구현에서 기록 가능한 경우 task_events.payload_json에 다음 정보를 남깁니다.

```text
skills_consulted
contract_version 또는 harness_contract_version
artifact_refs
```

이 필드는 권장값이며, 기존 DB schema가 없다면 payload_json에 저장합니다.

## 8. Loop Event Contract

하네스는 autonomous work가 명시적인 루프로 구현되었는지 task_events로 확인합니다.

Preferred task event fields:

```text
loop_name
loop_iteration
event_type
from_status
to_status
reason
artifact_refs
created_at
```

Allowed loop names:

```text
watch_loop
processing_loop
quality_loop
recovery_loop
feedback_loop
model_benchmark_loop
```

MVP smoke tests must cover at least:

```text
processing_loop
quality_loop
```

Recovery harness must cover:

```text
recovery_loop
```

Watcher harness must cover:

```text
watch_loop
```

Feedback harness must cover:

```text
feedback_loop
```

Benchmark harness must cover:

```text
model_benchmark_loop
```

## 9. Feedback Learning Contract

Feedback learning은 local-only입니다. 하네스는 아래 테이블 또는 명시적으로 staged된 placeholder를 확인할 수 있습니다.

```text
feedback_records
learning_samples
```

향후 확장 후보는 별도 migration 티켓 전까지 placeholder로만 둡니다.

```text
manual_edit_records
style_profiles
```

Feedback artifacts:

```text
ai_settings.json
final_settings.json
manual_edit_delta.json
user_feedback.json
training_sample_manifest.json
```

MVP는 live model fine-tuning을 요구하지 않습니다. Learning readiness는 local data capture, 명시 승인 flag, future offline training compatibility를 뜻합니다.

## 10. Model benchmark contract

모델 benchmark는 default backend를 자동 변경하지 않습니다.

```text
benchmark 실행 → model_benchmark_result.json 저장 → task/event evidence 기록 → 사람이 default 승격 결정
```

Qwen 계열 backend는 다음 조건을 통과하기 전 production/commercial default로 승격하지 않습니다.

```text
local-only model path
license review 기록
security harness 통과
Lightroom 동시 실행 상태 benchmark 통과
OOM / worker crash 없음
rollback path 문서화
```
