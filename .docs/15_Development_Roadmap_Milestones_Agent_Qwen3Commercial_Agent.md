# Development Roadmap & Milestones - 개발 로드맵

> Agent-readable design document. Follow these instructions exactly when implementing.

## Global MVP Decisions

- Model input: `1024px sRGB JPEG preview + EXIF/basic metadata`.
- Deferred: `2048px high-quality preview`, `subject crop`, `multi-view input`, `Lightroom neutral preview`, and default high-capacity Qwen2.5-VL-7B/Qwen3-VL-8B before benchmark.
- Commercial default model: `Qwen3-VL-4B-Instruct 4bit/GGUF`.
- Main DB: `PostgreSQL`.
- Detailed outputs: local `Artifact Storage`.
- Debug traces: file logs only.

## 1. Phase 1

DB schema, ArtifactStorage, config, CLI doctor.

## 2. Phase 2

Lightroom Plugin JSON Bridge PoC.

## 3. Phase 3

End-to-end mock pipeline with MockVisionBackend.

## 4. Phase 4

Integrate Qwen3-VL-4B-Instruct 4bit/GGUF with 1024px preview as the commercial default candidate.

## 5. Phase 5

Quality validation and decision on deferred improvements.

## 6. Rule

Do not implement dashboard before core pipeline is stable.

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

## Roadmap Update: Loop Engineering and Learning

Add a dedicated loop-engineering milestone before real Qwen/Lightroom hardening.

Updated roadmap additions:

```text
Phase 1.5 - Loop Engineering Foundation
- define loop names and exit rules
- add task_events loop fields
- add loop-engineering skill
- add verify_loop_events harness

Phase 2.5 - Feedback Learning Foundation
- store AI-applied Develop Settings snapshot
- add manual edit detection contract
- add feedback_records and training_samples design
- add feedback sync CLI skeleton

Phase 4.5 - Model Benchmark Loop
- benchmark Qwen3-VL-4B-Instruct 4bit/GGUF as commercial default candidate and optionally compare Qwen2.5-VL-7B-Instruct 4bit
- test with Lightroom running
- promote candidate only after benchmark pass
```

Direct model fine-tuning remains post-MVP and must be offline, local, opt-in, versioned, and evaluated before activation.

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
