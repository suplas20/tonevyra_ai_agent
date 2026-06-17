# Local Model Security Skill

## Purpose
Ensure local model usage is safe for Tonevyra AI, with no external data transmission, no runtime downloads, and no unsafe model loading.

This skill is the practical runtime checklist for `model-security`.

## Core Rules
- Local inference only.
- No remote API fallback.
- No runtime model download.
- No external URL image loading.
- No telemetry.
- No upload of previews, metadata, RAW files, settings, feedback, or artifacts.
- Model backend must remain replaceable and disable-able.

## Required Environment Variables
- `HF_HUB_OFFLINE=1`
- `TRANSFORMERS_OFFLINE=1`
- `HF_HUB_DISABLE_TELEMETRY=1`
- `HF_HUB_DISABLE_IMPLICIT_TOKEN=1`
- `HF_HUB_DISABLE_UPDATE_CHECK=1`

## Model Loading Rules
- Use `local_files_only=True`.
- Do not use `trust_remote_code=True`.
- Prefer safetensors or verified GGUF.
- Pin model path, model version/revision, and hash when possible.
- Model worker should be OS-firewall/network-blockable.
- Reject model paths outside `models/` or the configured local model root.

## Commercial Model Policy
- Commercial release default requires explicit license review and benchmark evidence.
- Do not use Qwen2.5-VL-3B-Instruct as a commercial default unless a separate commercial/license review approves it.
- Prefer Qwen3-VL-4B-Instruct 4bit/GGUF as the commercial default candidate, subject to license review and benchmark validation.
- Qwen2.5-VL-7B / Qwen3-VL-8B class models may be considered quality candidates, subject to local hardware performance and license review.
- Benchmark results must not automatically promote a model.

## Data Boundary
The model may receive only:
- 1024px long-edge sRGB JPEG preview
- EXIF/basic metadata required for analysis

The model must not receive:
- original RAW file
- Lightroom catalog
- private database dump
- unrelated user files
- feedback dataset unless explicitly approved for local/offline training preparation

## Security Harness
The security harness must check:
- offline env vars are present
- no `trust_remote_code=True`
- no remote API calls
- no runtime downloads
- no external image URL loading
- `from_pretrained` uses `local_files_only=True`
- model path is local and allowed
- qwen backend fails safely when local model path is missing

## Failure
Use existing error codes only:
- `MODEL_LOAD_FAILED`
- `MODEL_INFERENCE_FAILED`
- `SECURITY_NETWORK_ACCESS_BLOCKED`
