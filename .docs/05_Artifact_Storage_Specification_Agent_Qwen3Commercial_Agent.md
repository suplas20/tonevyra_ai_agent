# Artifact Storage Specification - 산출물 저장소

> Agent-readable design document. Follow these instructions exactly when implementing.

## Global MVP Decisions

- Model input: `1024px sRGB JPEG preview + EXIF/basic metadata`.
- Deferred: `2048px high-quality preview`, `subject crop`, `multi-view input`, `Lightroom neutral preview`, and default high-capacity Qwen2.5-VL-7B/Qwen3-VL-8B before benchmark.
- Commercial default model: `Qwen3-VL-4B-Instruct 4bit/GGUF`.
- Main DB: `PostgreSQL`.
- Detailed outputs: local `Artifact Storage`.
- Debug traces: file logs only.

## 1. Interface

ArtifactStorage.save/load/exists/verify must be used. Do not write artifact files directly from business modules.

## 2. Path

storage/artifacts/{job_id}/{task_id}/{artifact_name}

## 3. Atomic Write

write .tmp -> flush/fsync -> atomic rename -> insert/update task_artifacts.

## 4. Artifact Types

EXIF, OPENCV_ANALYSIS, VISION_PROMPT, VISION_RAW_RESPONSE, VISION_STRUCTURED, CORRECTION_PLAN, LIGHTROOM_REQUEST, LIGHTROOM_RESPONSE, QUALITY_DETAIL, RETRY_HISTORY.

## 5. Future

Keep storage backend replaceable for MinIO/S3 later.

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

## Loop Evidence Artifacts

Artifact Storage must store evidence for loop verification and feedback learning.

Additional loop artifacts:

```text
loop_trace.json
retry_history.json
recovery_decision.json
model_benchmark_result.json
```

Additional feedback/learning artifacts:

```text
ai_applied_develop_settings.json
ai_applied_develop_hash.txt
current_develop_settings.json
current_develop_hash.txt
manual_edit_delta.json
user_feedback.json
training_sample_manifest.json
style_profile_update.json
```

These are durable processing artifacts, not debug logs. They must be written atomically and registered in PostgreSQL with checksum metadata.

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
