# Lightroom Plugin Bridge - Lightroom 연동

> Agent-readable design document. Follow these instructions exactly when implementing.

## Global MVP Decisions

- Model input: `1024px sRGB JPEG preview + EXIF/basic metadata`.
- Deferred: `2048px high-quality preview`, `subject crop`, `multi-view input`, `Lightroom neutral preview`, and default high-capacity Qwen2.5-VL-7B/Qwen3-VL-8B before benchmark.
- Commercial default model: `Qwen3-VL-4B-Instruct 4bit/GGUF`.
- Main DB: `PostgreSQL`.
- Detailed outputs: local `Artifact Storage`.
- Debug traces: file logs only.

## 1. Protocol

Use file-based JSON bridge. Python writes requests, Lua reads and writes responses.

## 2. Folders

bridge/requests, bridge/processing, bridge/responses, bridge/errors.

## 3. Commands

PING, IMPORT_PHOTO, APPLY_PRESET, APPLY_ADJUSTMENTS_AND_EXPORT, EXPORT_PHOTO.

## 4. Lua Boundaries

Lua plugin must not perform AI, DB writes, quality scoring, or queue management.

## 5. Priority

Validate plugin load, request read, adjustment apply, export, response write before other features.

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

## Feedback Loop Through Lightroom

Lightroom Bridge must support not only apply/export, but also feedback sync.

The plugin should eventually support:

```text
- read AI-applied Develop Settings after correction
- save AI-applied settings snapshot
- later read current Develop Settings
- return current settings to Python Agent
- allow Python Agent to compare hashes and compute manual edit delta
```

Feedback detection flow:

```text
AI applied settings snapshot
-> user edits in Lightroom
-> sync current Develop Settings
-> compare hash
-> manual_edit_delta.json
-> feedback_records / training_samples
```

Python must not directly read or modify Lightroom catalog files. Lightroom Plugin reads Lightroom state and writes JSON responses.

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
