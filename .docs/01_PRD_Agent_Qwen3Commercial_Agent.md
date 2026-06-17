# PRD - 제품 요구사항

> Agent-readable design document. Follow these instructions exactly when implementing.

## Global MVP Decisions

- Model input: `1024px sRGB JPEG preview + EXIF/basic metadata`.
- Deferred: `2048px high-quality preview`, `subject crop`, `multi-view input`, `Lightroom neutral preview`, and default high-capacity Qwen2.5-VL-7B/Qwen3-VL-8B before benchmark.
- Commercial default model: `Qwen3-VL-4B-Instruct 4bit/GGUF`.
- Main DB: `PostgreSQL`.
- Detailed outputs: local `Artifact Storage`.
- Debug traces: file logs only.

## 1. MVP Goal

Implement a local photo correction agent that runs end-to-end without React UI.

## 2. Must Build

Folder watcher, task state machine, PostgreSQL persistence, local artifact storage, vision analysis with 1024px preview, correction planner, Lightroom JSON bridge, quality gate, CLI, recovery.

## 3. Do Not Build

Do not build blog/Instagram/homepage features. Do not build full dashboard first. Do not use SQLite as the main DB. Do not make Qwen2.5-VL-7B/Qwen3-VL-8B or 2048px multi-crop analysis required for MVP.

## 4. Model Input Policy

MVP model input is 1024px sRGB JPEG preview + EXIF/basic metadata. High-quality preview, multi-crop, Lightroom neutral preview, and high-capacity default mode before benchmark are deferred.

## 5. Acceptance

Agent can process photos from input folder to PASS/REVIEW_REQUIRED/FAILED output with persisted status and artifacts, recover after restart, and run through CLI.

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

## Loop Engineering & Feedback Learning Requirements

The MVP must be treated as an automatic agent product, not a one-shot script. The product requirements include explicit loop behavior.

Required product loops:

```text
- Watch Loop: observe input folder, stabilize files, register tasks.
- Processing Loop: analyze, plan, apply, export, and finalize one photo.
- Quality Loop: score exported output and decide PASS / REVIEW_REQUIRED / FAILED.
- Recovery Loop: resume unfinished work after crash or shutdown.
- Feedback Loop: record whether the user re-edited the AI result in Lightroom.
- Model Benchmark Loop: benchmark Qwen3-VL-4B-Instruct 4bit/GGUF as the commercial default candidate; optionally compare Qwen2.5-VL-7B-Instruct 4bit; keep Qwen2.5-VL-3B-Instruct as research-only reference.
```

MVP acceptance must include loop termination rules. A task must end in PASS, REVIEW_REQUIRED, FAILED, or SKIPPED. The product must not allow infinite automatic correction attempts.

The product must also be learning-ready. User feedback, manual Lightroom edits, and final approved settings must be stored locally so that Correction Planner calibration and style profiles can improve later. Direct model fine-tuning is not an MVP runtime feature.

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
