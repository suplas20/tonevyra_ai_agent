# PostgreSQL Persistence Skill

## Purpose
Use PostgreSQL as the durable source of truth for Tonevyra AI task state.

## Rules
- Runtime database: `tonevyra_agent`.
- Runtime user: `tonevyra_app`.
- Runtime env var: `TONEVYRA_DATABASE_URL`.
- Do not use SQLite as the main DB.
- Do not use the `postgres` superuser for runtime.
- Do not create, drop, or alter tables unless the current ticket explicitly requires a migration.

## Required Objects
Tables: `image_tasks`, `task_artifacts`, `task_events`, `stage_results`, `quality_results`, `feedback_records`, `learning_samples`.
View: `v_task_summary`.

## Validation
- `current_database()` is `tonevyra_agent`.
- `current_user` is `tonevyra_app`.
- Required tables and view exist.
- DB smoke test can create/read/delete test rows.
