# Harness Contract

이 문서는 하네스가 프로젝트 코드에 기대하는 최소 계약입니다.

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
VISION_BACKEND=mock
LIGHTROOM_BACKEND=fake
WORKER_CONCURRENCY=1
MODEL_OFFLINE=true
```

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
    "temperature": 8,
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


## T-019 Lightroom Apply Adapter Contract

T-019 real Lightroom Classic plugin work uses a separate apply-adapter contract while preserving the existing fake worker contract above.

Correct role separation:

```text
input folder file
→ Python Agent folder watcher
→ Python Agent task
→ vision analysis
→ correction plan
→ runtime/bridge/lightroom_apply_requests/<request_id>.json
→ Lightroom Apply Adapter plugin
→ source_path find/import in Lightroom catalog
→ Develop settings or preset apply
→ runtime/bridge/lightroom_apply_results/<request_id>.json
→ Agent DB/task_events evidence
```

The Lightroom plugin must not watch `runtime/input`, create tasks, run AI analysis, generate correction plans, compute quality scores, make DB decisions, or own lifecycle orchestration. Detailed rules live in `harness/CONTRACT_LIGHTROOM_APPLY_ADAPTER.md`.

## 5. 필수 artifact 계약

Smoke Pipeline 통과를 위해 최소한 아래 artifact가 생성되어야 합니다.

```text
exif.json
vision_prompt.txt
vision_raw_response.json
vision_structured.json
correction_plan.json
lightroom_request.json
lightroom_response.json
quality_detail.json
```

## 6. 최종 상태 계약

작업 최종 상태는 아래 중 하나여야 합니다.

```text
PASS
REVIEW_REQUIRED
FAILED
```

`SKIPPED`는 watcher/unsupported 파일 테스트에만 사용합니다.


## Loop Event Contract

The harness expects task events to prove that autonomous work is implemented as explicit loops.

Preferred task event fields:

```text
loop_name
loop_iteration
event_type
from_status
to_status
reason
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

## Feedback Learning Contract

Feedback learning is local-only. The harness may check for these tables or explicitly documented placeholders:

```text
manual_edit_records
feedback_records
training_samples
style_profiles
```

Feedback artifacts may include:

```text
ai_applied_develop_settings.json
current_develop_settings.json
manual_edit_delta.json
user_feedback.json
training_sample_manifest.json
```

The MVP must not require live model fine-tuning to pass the harness. Learning readiness means local data capture, approval flags, and future offline training compatibility.
