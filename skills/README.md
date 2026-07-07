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
- Do not add React dashboard, FastAPI-first local Agent architecture (dedicated T-032 Planner Service excepted), Redis, Celery, MinIO, message brokers, or worker pools.

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


## T-020 Lightroom Final Export Adapter Gate

The T-020 Lightroom Plugin export path starts only after T-019 has returned a verified `status=applied` result. The Agent creates an export request, the Plugin automatically exports the corrected catalog rendition, and the Agent verifies both the export result JSON and the actual non-empty output file before `EXPORT_DONE`.

Canonical T-020 references:

```text
skills/lightroom-final-export-adapter/SKILL.md
harness/CONTRACT_LIGHTROOM_EXPORT_ADAPTER.md
harness/scripts/verify_lightroom_export_adapter.py
harness/fixtures/lightroom_export_adapter/
```

## Cumulative Skill Inventory (T-020 preservation check)

This inventory is additive. Existing skill files are preserved, and T-019/T-020 skills are added without replacing earlier Lightroom skills.

Total `SKILL.md` files: **25**

```text
agent-worker-pipeline
artifact-storage
cli-operations
correction-planner
correction-planning
feedback-learning
folder-watcher
image-metadata-preview
lightroom-apply-adapter
lightroom-bridge
lightroom-final-export-adapter
lightroom-live-test
lightroom-plugin-implementation
local-model-security
loop-engineering
model-benchmark-loop
model-security
postgresql-persistence
project-scope
python-mvp-structure
quality-gate
recovery-error-handling
recovery-loop
testing-harness
vision-analysis
```

## T-021 Dual-Mode Agent Core and Closed-Loop Gate

T-021 keeps one Common Agent Core and selects Module or Model Providers through plan policy. Provider output is normalized analysis evidence; the Adjustment Planner remains the only component that creates bounded Lightroom values. Post-export quality is classified by the Agent, not the Plugin.

Canonical T-021 references:

```text
skills/dual-mode-agent-core/SKILL.md
skills/closed-loop-quality-reprocessing/SKILL.md
harness/CONTRACT_T021_DUAL_MODE_CLOSED_LOOP.md
harness/scripts/verify_t021_dual_mode_closed_loop.py
harness/fixtures/t021_dual_mode/
```

T-021 adds two skills without removing or merging the 25 T-020 skills.

## Cumulative Skill Inventory (T-021 preservation check)

Total `SKILL.md` files: **27**

```text
agent-worker-pipeline
artifact-storage
cli-operations
closed-loop-quality-reprocessing
correction-planner
correction-planning
dual-mode-agent-core
feedback-learning
folder-watcher
image-metadata-preview
lightroom-apply-adapter
lightroom-bridge
lightroom-final-export-adapter
lightroom-live-test
lightroom-plugin-implementation
local-model-security
loop-engineering
model-benchmark-loop
model-security
postgresql-persistence
project-scope
python-mvp-structure
quality-gate
recovery-error-handling
recovery-loop
testing-harness
vision-analysis
```


## T-029 Lightroom Radial Mask Execution and Template Library

T-029 adds two skills without deleting, merging, or renaming the 41-skill T-028 baseline.

| Skill | Area | Use When |
|---|---|---|
| `lightroom-radial-mask-execution` | Plugin-side validated local-mask execution | Applying T-029 native/radial plans, snapshots, rollback, and idempotency. |
| `radial-mask-template-library` | Versioned radial preset generation and selection | Building manifests, verifying checksums, and selecting deterministic geometry templates. |

Canonical T-029 references:

```text
skills/lightroom-radial-mask-execution/SKILL.md
skills/radial-mask-template-library/SKILL.md
harness/CONTRACT_T029_LIGHTROOM_RADIAL_MASKING.md
harness/scripts/verify_t029_lightroom_radial_masking.py
harness/fixtures/t029_radial_masking/
```

## Cumulative Skill Inventory (T-029 preservation check)

Baseline before T-029: **41** `SKILL.md` files  
Added by T-029: **2**  
Required cumulative total: **43**

The authoritative machine-readable inventory is `skills/T029_SKILL_INVENTORY.json`.

## T-030 Windows Background Agent and System Tray

T-030 preserves the 43-skill T-029 baseline and adds:

| Skill | Purpose |
|---|---|
| `windows-background-agent-lifecycle` | Per-user single instance, Worker supervision, autostart, shutdown, and recovery. |
| `system-tray-operations` | Tonevyra tray icon, state/menu mapping, validated commands, and asset gate. |

The existing `folder-watcher` skill is expanded for event coalescing, size/mtime/read-probe stability, PostgreSQL idempotency, pause/resume rescan, and output recursion safety.

Required cumulative count: **45** `SKILL.md` files. The authoritative inventory is `skills/T030_SKILL_INVENTORY.json`.

## T-031 additions

- `macos-apple-silicon-runtime`
- `inference-worker-memory-lifecycle`

T-031 expected total: 47 skills.

## T-032 additions

T-032 preserves all 47 T-031 skills and adds:

```text
planner-api-contract
planner-api-client
planner-api-service
planner-api-security
```

Required cumulative total: **51** `SKILL.md` files. The authoritative inventory is `skills/T032_SKILL_INVENTORY.json`.
