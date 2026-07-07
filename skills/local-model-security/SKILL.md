# Local Model Security Skill

## Purpose
Ensure local model usage is safe for Tonevyra AI, with no external data transmission, no runtime downloads, and no unsafe model loading.

## Core Rules
- Local inference only.
- No remote API fallback.
- No runtime model download.
- No external URL image loading.
- No telemetry.
- No upload of previews, metadata, RAW files, settings, feedback, or artifacts.

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
- Pin model path, model version, and hash when possible.
- Model worker should be OS-firewall/network-blockable.

## Commercial Model Policy
- Commercial default candidate should be license-safe.
- Do not use Qwen2.5-VL-3B-Instruct as a commercial default unless a separate commercial license is obtained.
- Prefer Qwen3-VL-4B-Instruct 4bit/GGUF as the commercial-safe default candidate, subject to benchmark validation.
- Qwen2.5-VL-7B-Instruct 4bit may be considered a commercial quality candidate, subject to local hardware performance.

## Data Boundary
The model may receive only:
- 1024px long-edge sRGB JPEG preview
- EXIF/basic metadata required for analysis

The model must not receive:
- original RAW file
- Lightroom catalog
- private database dump
- unrelated user files

## Security Harness
The security harness must check offline env vars, no `trust_remote_code=True`, no remote API calls, no runtime downloads, no external image URL loading, and offline-safe model behavior.

## Failure
Use existing error codes only:
- `MODEL_LOAD_FAILED`
- `MODEL_INFERENCE_FAILED`
- `SECURITY_NETWORK_ACCESS_BLOCKED`

## T-032 Network Exception

The local model remains offline/local-only. T-032 authorizes network access only from the dedicated Planner API client after analysis. The inference Worker must still be network-blockable; it must not receive API credentials or send model/image data directly.
