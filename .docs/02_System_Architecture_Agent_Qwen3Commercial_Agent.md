# System Architecture - 전체 시스템 구조

> Agent-readable design document. Follow these instructions exactly when implementing.

## Global MVP Decisions

- Model input: `1024px sRGB JPEG preview + EXIF/basic metadata`.
- Deferred: `2048px high-quality preview`, `subject crop`, `multi-view input`, `Lightroom neutral preview`, and default high-capacity Qwen2.5-VL-7B/Qwen3-VL-8B before benchmark.
- Commercial default model: `Qwen3-VL-4B-Instruct 4bit/GGUF`.
- Main DB: `PostgreSQL`.
- Detailed outputs: local `Artifact Storage`.
- Debug traces: file logs only.

## 1. Architecture

Python Agent is the orchestrator. Vision, correction, Lightroom bridge, quality, db, and storage are modules called by Agent Core.

## 2. Process Flow

watch -> stabilize -> create task -> create 1024px preview -> vision -> correction -> Lightroom request -> export -> quality -> final status.

## 3. Processes

MVP: postgres + python agent + Lightroom Classic. Dashboard/API is later.

## 4. Rules

Agent must work headless. UI cannot own business logic. Lightroom is controlled only by Lua plugin bridge.

## 5. Deferred

2048px preview, multi-crop, Lightroom neutral preview, high-capacity default mode before benchmarkl are not MVP requirements.

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

## Loop Engineering Layer

Add a product-level Loop Engineering layer above the pipeline modules. This is not a separate microservice. It is a design rule that every autonomous process must be an explicit loop with state, evidence, retry limits, and exit conditions.

Architecture view:

```text
Folder Watcher      -> Watch Loop
Agent Worker        -> Processing Loop
Quality Gate        -> Quality Loop
Recovery Manager    -> Recovery Loop
Lightroom Sync      -> Feedback Loop
Benchmark Runner    -> Model Benchmark Loop
```

The loop controller must use PostgreSQL for state, Artifact Storage for evidence, and Harness scripts for verification. The agent must not rely on logs as loop memory.

Feedback learning architecture:

```text
AI applied settings snapshot
-> user Lightroom edit detection
-> manual edit delta artifact
-> feedback record
-> training sample candidate
-> style profile / planner calibration
```

No learning data may leave the local machine.

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
