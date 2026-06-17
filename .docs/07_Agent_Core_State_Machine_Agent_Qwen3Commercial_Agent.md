# Agent Core State Machine - 작업 상태 머신

> Agent-readable design document. Follow these instructions exactly when implementing.

## Global MVP Decisions

- Model input: `1024px sRGB JPEG preview + EXIF/basic metadata`.
- Deferred: `2048px high-quality preview`, `subject crop`, `multi-view input`, `Lightroom neutral preview`, and default high-capacity Qwen2.5-VL-7B/Qwen3-VL-8B before benchmark.
- Commercial default model: `Qwen3-VL-4B-Instruct 4bit/GGUF`.
- Main DB: `PostgreSQL`.
- Detailed outputs: local `Artifact Storage`.
- Debug traces: file logs only.

## 1. Statuses

DETECTED, STABILIZING, QUEUED, ANALYZING, ANALYSIS_DONE, CORRECTION_PLANNED, LIGHTROOM_REQUESTED, LIGHTROOM_PROCESSING, EXPORT_DONE, QUALITY_CHECK, PASS, REVIEW_REQUIRED, FAILED, SKIPPED.

## 2. Workers

MVP defaults: model_worker=1, lightroom_worker=1.

## 3. Transition Rule

stage work -> artifact save -> db summary -> task_event -> status update.

## 4. Retry

Increment retry_count and write retry_history artifact. Avoid infinite retry.

## 5. Final

PASS/REVIEW_REQUIRED/FAILED/SKIPPED are final unless explicit retry.

## Implementation Guardrails

- Do not build the full React dashboard before the agent core is stable.
- Do not replace PostgreSQL with SQLite.
- Do not store image binaries in PostgreSQL.
- Do not store heavy raw model payloads in PostgreSQL unless explicitly requested.
- Do not make high-quality preview or 7B model mandatory in MVP.
- Do not let the model directly edit images or bypass Correction Planner.
- Do not skip artifact persistence or crash recovery.

---

<!-- LOOP_ENGINEERING_UPDATE_V3 -->

## Loop Engineering in the State Machine

The state machine is the concrete implementation of product loop engineering.

Every transition must record:

```text
loop_name
loop_iteration
event_type
from_status
to_status
reason
artifact references
```

Processing Loop must terminate in a final status. Retry is allowed only with explicit max retry limits. No loop may run indefinitely.

Suggested loop names:

```text
watch_loop
processing_loop
quality_loop
recovery_loop
feedback_loop
model_benchmark_loop
```

Feedback Loop should not change the final task status by default. It creates learning records and may update planner calibration only when the user explicitly approves the current settings for learning.

---

## Commercial Model Policy Update - Qwen3 Default

Tonevyra AI uses a commercial-safe local model policy.

```text
Commercial default vision model candidate:
Qwen3-VL-4B-Instruct 4bit/GGUF

Commercial quality candidate:
Qwen2.5-VL-7B-Instruct 4bit, hardware permitting

Research/non-commercial reference only:
Qwen2.5-VL-3B-Instruct 4bit
```

Rules:

```text
- Qwen3-VL-4B-Instruct 4bit/GGUF is the commercial default candidate, subject to local benchmark validation.
- Qwen2.5-VL-7B-Instruct 4bit may be evaluated as a quality candidate when hardware allows.
- Qwen2.5-VL-3B-Instruct must not be used as the commercial default unless a separate commercial license is obtained.
- All model inference must remain local-only and offline-capable.
- The model may receive only 1024px sRGB JPEG preview + EXIF/basic metadata.
- The model must not receive original RAW files, Lightroom catalog files, private DB dumps, unrelated user files, or external URLs.
- Model loading must use local files only, no runtime downloads, no remote API fallback, and no `trust_remote_code=True`.
```



---

## Model License Verification Rule

Before real model deployment or public/commercial distribution, the agent or developer must re-check the live model card and license file for the selected model and record:

```text
model_id
model_version_or_revision
local_path
license
sha256 or verified file hash
commercial_allowed flag
verification_date
```

Do not assume that a model license remains unchanged across revisions.
