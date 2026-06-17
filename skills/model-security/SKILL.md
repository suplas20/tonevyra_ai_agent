---
name: model-security
description: Local-only, network-blocked, replaceable vision model runtime, model worker isolation, hardware profiles, model paths, benchmark logic, and backend selection.
---

# Model Security & Model Policy

## Backend Policy

```text
VisionModelBackend
  - MockVisionBackend        # development/CI default; must pass first
  - Qwen25VLBackend          # technical stable candidate: Qwen2.5-VL-3B-Instruct 4bit
  - Qwen3VLBackend           # commercial/default candidate: Qwen3-VL-4B 4bit, gated
  - FutureAlternativeBackend # replaceable backend slot
```

- Qwen2.5-VL-3B 4bit is the technical stable candidate.
- Qwen2.5-VL-3B must not be treated as the commercial/default backend unless a separate license review explicitly approves it.
- Qwen3-VL-4B 4bit/GGUF is the commercial/default candidate.
- Qwen3-VL-4B may become the default backend only after license review, local benchmark evidence, rollback documentation, and human approval.
- Qwen2.5-VL-7B / Qwen3-VL-8B or larger models are quality-mode candidates only and must not be MVP defaults.
- No model may be a hard dependency; the backend must remain replaceable and disableable.
- Code outside `vision/model.py` or future `vision/backends/` modules must not assume a specific model family.

## Hardware Profiles

```text
Minimum development:
  Windows RAM 16GB / VRAM 8GB
  MockVisionBackend or constrained local test only.

Technical stable profile:
  Windows RAM 32GB / VRAM 8GB+
  Mac mini 24GB unified memory
  Qwen2.5-VL-3B 4bit + Lightroom Classic simultaneous operation target.

Commercial/default candidate profile:
  Qwen3-VL-4B 4bit/GGUF
  Requires license review and Lightroom-running benchmark evidence.

Quality profile:
  Qwen2.5-VL-7B / Qwen3-VL-8B+
  High-spec option only; not the MVP default.
```

Actual memory must be measured by benchmark. Do not rely on model file size alone.

## Local-Only Loading

Required:

```text
local model files only
local_files_only=True
trust_remote_code=False
offline env vars set
no runtime model download
no remote API fallback
no external URL image loading
model path under models/ or configured local model root
model version/revision and hash recorded when possible
model worker can be blocked by OS firewall
```

Required env vars:

```bash
HF_HUB_OFFLINE=1
TRANSFORMERS_OFFLINE=1
HF_HUB_DISABLE_TELEMETRY=1
HF_HUB_DISABLE_IMPLICIT_TOKEN=1
HF_HUB_DISABLE_UPDATE_CHECK=1
```

## Data Boundary

The model may receive only:

```text
1024px long-edge sRGB JPEG preview
EXIF/basic metadata required for analysis
```

The model must not receive:

```text
original RAW file
Lightroom catalog
private database dump
unrelated user files
external image URLs
```

## Installation Boundary

Network access is allowed only during an explicit model installation/setup step outside normal photo processing. Runtime processing and harness validation must not download model files.

Allowed installation sources, when explicitly approved:

```text
Hugging Face official Qwen organization
ModelScope official Qwen organization
```

## Qwen3 Promotion Gate

Qwen3-VL-4B can be promoted to commercial/default only when all of these are true:

```text
license review completed
security harness passes
benchmark artifact exists
10-photo stability passes
100-photo stability passes
Lightroom simultaneous operation stability passes
quality impact is acceptable
rollback path is documented
human approval is explicit
```

The system must never silently promote Qwen3 or replace the active backend automatically.

## Acceptance Criteria

Mock backend works before real backend; local-only loading is enforced; unsafe remote behavior is blocked; raw and structured responses are persisted as local artifacts when appropriate; structured output is schema-validated before use; Qwen2.5 remains a technical candidate; Qwen3 remains gated until license review and benchmark approval.
