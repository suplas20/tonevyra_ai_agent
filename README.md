# Tonevyra AI Agent

Tonevyra AI Agent is a local, CLI-first photo correction automation agent for Lightroom Classic.

The MVP processes photos end-to-end without a dashboard:

```text
runtime/input
-> file detection and stabilization
-> PostgreSQL task registration
-> 1024px sRGB JPEG preview
-> vision analysis
-> correction planning
-> Lightroom Classic JSON bridge
-> export
-> quality gate
-> PASS / REVIEW_REQUIRED / FAILED
```

## MVP Boundaries

- No external image, prompt, metadata, feedback, or model-response transmission.
- PostgreSQL stores operational state.
- Local artifacts store detailed payloads and checksums.
- Vision models analyze only; correction values are planned and clamped separately.
- Lightroom integration uses the Lua plugin plus file-based JSON bridge.
- React, FastAPI-first, Redis, Celery, MinIO, and worker pools are deferred.
- Worker concurrency remains `1` in the MVP.

## Model Policy

```text
Qwen2.5-VL-3B: technical stable candidate
Qwen3-VL-4B: commercial/default candidate
```

Qwen3-VL-4B can become the commercial/default runtime backend only after license review, benchmark evidence, rollback documentation, and explicit human approval. No benchmark or harness may silently promote a model.

## Initial Commands

```bash
tonevyra-agent init
tonevyra-agent doctor
tonevyra-agent start
tonevyra-agent status
tonevyra-agent scan
tonevyra-agent retry TASK_ID
tonevyra-agent process FILE_PATH
tonevyra-agent test-lightroom
tonevyra-agent test-vision
tonevyra-agent benchmark-models --sample-set harness
```

Legacy `mw-agent` names may appear only in migration references or compatibility wrappers.
