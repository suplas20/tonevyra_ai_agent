# Tonevyra AI Agent - Loop Engineering & Feedback Learning Addendum

Version: v3.1-qwen3-commercial

## Purpose

This addendum defines the product-level Loop Engineering concept for the Tonevyra AI Agent. In this project, Loop Engineering is not a development methodology. It is the operating design of the finished automatic agent: how the product repeatedly observes work, decides what to do, executes a step, verifies the result, recovers from failure, records evidence, and learns from user behavior.

## Product Loop Definition

Every autonomous behavior in the product must be designed as an explicit loop. A loop must define:

```text
- entry condition
- allowed actions
- state transitions
- retry limit
- timeout
- exit condition
- failure condition
- human review condition
- persisted evidence
- harness verification
```

The agent must never run an open-ended loop without a termination rule.

## Required Product Loops

```text
1. Watch Loop
   input folder observation -> file stabilization -> task registration -> next file

2. Processing Loop
   task load -> preview -> vision analysis -> correction plan -> Lightroom request -> export -> finalization

3. Quality Loop
   export inspection -> scoring -> PASS / REVIEW_REQUIRED / FAILED

4. Recovery Loop
   unfinished task discovery -> artifact/DB/export verification -> safe resume or fail

5. Feedback Loop
   AI applied settings snapshot -> user Lightroom behavior scan -> delta extraction -> feedback record -> learning dataset candidate

6. Model Benchmark Loop
   candidate model test -> speed/memory/quality comparison -> promotion or rejection
```

MVP must implement Watch Loop, Processing Loop, Quality Loop, and Recovery Loop. MVP must also store feedback/learning-ready data when available, but it must not automatically fine-tune the vision model during normal photo processing.

## Feedback and Learning Policy

The product must be designed so user feedback and user behavior can improve future results. The first learning target is Correction Planner calibration and user style profiling, not direct Qwen fine-tuning.

Allowed in MVP or near-MVP:

```text
- store AI-applied Lightroom settings snapshot
- detect whether the user manually edited the AI result
- store current Lightroom develop settings snapshot
- compute manual edit delta
- store explicit user feedback such as PASS / REVIEW_REQUIRED / FAILED / too_blue / too_dark
- mark approved samples as training dataset candidates
- update local style/profile calibration after explicit approval
```

Not allowed in MVP runtime:

```text
- automatic online training
- sending photos, previews, metadata, prompts, correction plans, or feedback to external services
- silent fine-tuning of Qwen while processing photos
- using user behavior for learning without local storage and explicit policy controls
```

Future model fine-tuning may be supported only as an offline, opt-in, versioned training process with a held-out evaluation set and rollback path.

## Loop Evidence

Each loop iteration must leave evidence in PostgreSQL and Artifact Storage.

PostgreSQL evidence examples:

```text
task_events.loop_name
task_events.loop_iteration
task_events.event_type
task_events.from_status
task_events.to_status
task_events.reason
manual_edit_records
feedback_records
training_samples
style_profiles
```

Artifact evidence examples:

```text
loop_trace.json
ai_applied_develop_settings.json
ai_applied_develop_hash.txt
current_develop_settings.json
current_develop_hash.txt
manual_edit_delta.json
user_feedback.json
training_sample_manifest.json
model_benchmark_result.json
```

## Safety Rule

The purpose of Loop Engineering is not to let the agent run forever. The purpose is to ensure the agent knows when to proceed, when to retry, when to stop, when to recover, and when to hand off to a human.


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
