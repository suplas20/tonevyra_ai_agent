# CLI Operations Skill

## Purpose
Expose MVP operations through CLI while keeping business logic outside CLI handlers.

CLI commands are orchestration entry points only. They should call service/repository layers and remain testable by harness scripts.

## Required Commands
`init`, `doctor`, `start`, `stop`, `status`, `tasks`, `task`, `scan`, `retry`, `process`, `test-lightroom`, `test-vision`, `loop-events`, `feedback`, `benchmark-models`.

## Rules
- CLI should call service/repository layers.
- Do not put core business logic inside CLI commands.
- CLI commands must respect configured mock/fake backends.
- `doctor` validates runtime dirs, PostgreSQL connection, offline model env, backend selection, and hardware profile.
- `loop-events` should render task loop evidence from `task_events`.
- `feedback` records explicit user feedback locally; it must not train a model.
- `benchmark-models` runs a bounded local benchmark and must not change the default backend automatically.

## Harness Validation
`harness/scripts/verify_cli_operations.py`
