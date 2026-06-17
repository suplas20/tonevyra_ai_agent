# Model Benchmark Loop Skill

## Purpose
Benchmark local vision model candidates before changing the default model.

The benchmark loop creates evidence for a human promotion decision. It must not silently replace the active backend.

## Required Loop Name
`model_benchmark_loop`

## Required Artifact
`model_benchmark_result.json`

## Required Metrics
inference time, peak memory, JSON validity, quality impact, error rate, Lightroom simultaneous operation stability, 10-photo stability, 100-photo batch stability, worker crash count, OOM count, configured backend, model path/hash when available.

## Model Policy
- Do not automatically promote a model.
- Recommend promotion only with benchmark evidence.
- Document rollback path.
- Qwen3-VL-4B 4bit/GGUF is the commercial/default candidate after license review and benchmark validation.
- Qwen2.5-VL-3B is a technical stable candidate; commercial default requires separate license review.
- Qwen2.5-VL-7B / Qwen3-VL-8B class models are quality-mode candidates only.

## Rules
- No online benchmark upload.
- No silent model replacement.
- Keep mock backend available.
- Benchmark must run bounded sample sets.
- Benchmark output must be stored as a local artifact and referenced from loop evidence.
- A failed benchmark should produce a structured result, not crash the whole project process.

## Acceptance Criteria
- `harness/scripts/run_model_benchmark_test.py` passes.
- `benchmark-models` CLI writes a benchmark artifact.
- Default backend remains unchanged after benchmark.
- `task_events` or benchmark event output contains `model_benchmark_loop` evidence.
