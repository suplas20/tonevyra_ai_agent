# Model Benchmark Loop Skill

## Purpose
Benchmark local vision model candidates before changing the default model.

## Required Loop Name
`model_benchmark_loop`

## Required Artifact
`model_benchmark_result.json`

## Required Metrics
inference time, peak memory, JSON validity, quality impact, error rate, Lightroom simultaneous operation stability, 10-photo stability, 100-photo batch stability.

## Model Policy
- Do not automatically promote a model.
- Recommend promotion only with benchmark evidence.
- Document rollback path.
- Qwen3-VL-4B 4bit/GGUF is the commercial-safe default candidate.
- Qwen2.5-VL-3B is research/non-commercial only unless separately licensed.

## Rules
- No online benchmark upload.
- No silent model replacement.
- Keep mock backend available.
