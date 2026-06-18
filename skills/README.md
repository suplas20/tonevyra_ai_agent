# Tonevyra AI Agent Skills

`AGENTS.md` is the highest-level rule set. Each `skills/*/SKILL.md` file defines area-specific procedure. If a skill conflicts with `AGENTS.md`, follow `AGENTS.md`.

## Usage Rules

1. Read `AGENTS.md` before any implementation work.
2. Read the relevant `skills/*/SKILL.md` file before editing that area.
3. Implement only the requested scope.
4. Add or update an appropriate unit test, harness check, smoke test, recovery test, or security check.
5. Mock Vision and Fake Lightroom must pass before real model or real Lightroom integration.
6. Artifacts, database state, and task events must make recovery possible.

## Skill Map

| Skill | Area | Use When |
|---|---|---|
| `project-scope` | MVP scope and forbidden items | Starting or reviewing any task. |
| `python-mvp-structure` | Simple Python package structure | Creating or moving modules. |
| `postgresql-persistence` | PostgreSQL models and repositories | DB, ORM, query, or migration work. |
| `artifact-storage` | Atomic local artifacts and checksums | Saving durable task evidence. |
| `model-security` | Local model policy and isolation | Model loading, backend selection, benchmark logic. |
| `local-model-security` | Offline and no-network checks | Security harness or runtime model boundary work. |
| `vision-analysis` | Preview + metadata analysis | `vision/` implementation. |
| `correction-planning` / `correction-planner` | Safe Lightroom plans | `correction/` implementation. |
| `lightroom-bridge` | Agent-owned JSON bridge transport | Request/result bridge, fake worker, and result ingestion. |
| `lightroom-apply-adapter` | T-019 real Lightroom Classic plugin role | Plugin applies Agent-created correction values to `source_path` photos inside Lightroom. |
| `agent-worker-pipeline` | Pipeline orchestration | `agent/worker.py`, `agent/runner.py`. |
| `recovery-loop` / `recovery-error-handling` | Recovery and controlled failures | `agent/recovery.py`. |
| `quality-gate` | Export scoring and decisions | `quality/` implementation. |
| `testing-harness` | Acceptance gate validation | Harness and smoke checks. |
| `loop-engineering` | Product loop evidence | Watch, processing, quality, recovery, feedback, benchmark loops. |
| `feedback-learning` | Local feedback and learning candidates | Feedback records, learning samples, training manifests. |
| `cli-operations` | CLI commands and doctor checks | `cli.py`. |
| `folder-watcher` | File detection and stabilization | `agent/watcher.py`. |
| `model-benchmark-loop` | T-018 model comparison | Benchmark artifacts and candidate promotion rules. |

## Common Guardrails

- Main DB is PostgreSQL only. Do not add SQLite as an operational fallback.
- Heavy payloads stay in Artifact Storage, not database blobs.
- No user data leaves the machine.
- Model input is `1024px sRGB JPEG preview + EXIF/basic metadata`.
- Worker concurrency is `1` in MVP.
- Do not add React dashboard, FastAPI-first architecture, Redis, Celery, MinIO, message brokers, or worker pools.

## Model Policy

| Role | Model | Notes |
|---|---|---|
| Development / CI | MockVisionBackend | Must pass before real backends. |
| Technical stable candidate | Qwen2.5-VL-3B-Instruct 4bit | Local-only candidate; not commercial/default without license review. |
| Commercial/default candidate | Qwen3-VL-4B 4bit/GGUF | Requires license review, benchmark evidence, rollback path, and human approval before promotion. |
| Quality mode only | Qwen2.5-VL-7B / Qwen3-VL-8B+ | High-spec option only; not MVP default. |

## Harness Position

The harness is an acceptance gate. It verifies implementation compliance with contracts, security, recovery, loop evidence, artifact integrity, feedback learning, and model promotion rules. It is not just a mock runtime.

## T-019 Lightroom Apply Adapter Gate

The T-019 Lightroom Classic plugin is **not** the input-folder watcher. The Agent watches the input folder, analyzes the photo, produces correction values, and writes an apply request. The plugin reads that request, uses `source_path` to find/import the photo in Lightroom, applies the supplied Develop settings or preset, and writes an apply result.

Canonical T-019 references:

```text
skills/lightroom-apply-adapter/SKILL.md
harness/CONTRACT_LIGHTROOM_APPLY_ADAPTER.md
harness/scripts/verify_lightroom_apply_adapter_role.py
```
