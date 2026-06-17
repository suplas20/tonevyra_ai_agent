# Prompt — Implement Harness Support

Read `AGENTS.md` first.
Then read:

- `skills/testing-harness/SKILL.md`
- `skills/python-mvp-structure/SKILL.md`
- `skills/agent-worker-pipeline/SKILL.md`
- `skills/lightroom-bridge/SKILL.md`
- `harness/CONTRACT.md`

Implement only the minimum project code needed for the harness smoke pipeline. The goal is to prove skill compliance with deterministic evidence, not to connect real services.

Requirements:

- Use `MockVisionBackend` only.
- Use fake/file-based Lightroom bridge only.
- Do not connect real Qwen.
- Do not connect real Lightroom.
- Do not add React, FastAPI, Redis, Celery, MinIO, or worker pools.
- `harness/scripts/run_smoke_pipeline.py` must pass.
- Add or update pytest tests for touched modules.

The smoke pipeline must verify:

- task creation
- 1024px preview artifact
- vision artifact
- correction plan artifact
- Lightroom request artifact
- fake export file
- quality result artifact
- final status `PASS`, `REVIEW_REQUIRED`, or `FAILED`
