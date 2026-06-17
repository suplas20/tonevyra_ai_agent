# Vision Analysis Design - 모델 분석 설계

> Agent-readable design document. Follow these instructions exactly when implementing.

## Global MVP Decisions

- Model input: `1024px sRGB JPEG preview + EXIF/basic metadata`.
- Deferred: `2048px high-quality preview`, `subject crop`, `multi-view input`, `Lightroom neutral preview`, and default high-capacity Qwen2.5-VL-7B/Qwen3-VL-8B before benchmark.
- Commercial default model: `Qwen3-VL-4B-Instruct 4bit/GGUF`.
- Main DB: `PostgreSQL`.
- Detailed outputs: local `Artifact Storage`.
- Debug traces: file logs only.

## 1. Role

Model diagnoses image issues only. It does not edit images and does not directly control Lightroom.

## 2. MVP Input

1024px sRGB JPEG preview + EXIF/basic metadata.

## 3. Deferred

2048px preview, subject crop, multi-view, Lightroom neutral preview, high-capacity default mode before benchmark.

## 4. Default Model

Qwen3-VL-4B-Instruct 4bit/GGUF is the commercial default candidate. Mock backend remains required. Qwen2.5-VL-7B-Instruct 4bit is an optional commercial quality candidate when hardware allows. Qwen2.5-VL-3B-Instruct is research/non-commercial only unless separately licensed.

## 5. Output Schema

scene_type, main_subject, usable, issues, edit_intent, confidence, risk_flags.

## 6. Validation

Save raw response artifact, extract JSON, validate schema, save structured artifact, then write DB summary.

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

## Vision Model and Learning Boundary

The vision model is part of the Processing Loop, but it is not a self-training component during MVP runtime.

Allowed:

```text
- return structured analysis from 1024px preview + metadata
- record raw/structured output locally
- compare Qwen3 commercial default candidate and optional commercial quality candidates through benchmark loop
- collect approved samples for future offline fine-tuning
```

Not allowed:

```text
- online model training
- sending data to remote training services
- silent fine-tuning while processing photos
- producing final Lightroom values without Correction Planner validation
```

Learning should first improve Correction Planner calibration and user style profiles. Direct VLM fine-tuning is a later offline process.

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
