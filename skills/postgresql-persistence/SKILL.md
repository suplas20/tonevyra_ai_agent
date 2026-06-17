# PostgreSQL Persistence Skill

## Purpose
Use PostgreSQL as the durable source of truth for Tonevyra AI task state.

The filesystem stores heavy artifacts. PostgreSQL stores task state, artifact registry, stage summaries, quality summaries, feedback records, and event evidence.

## Rules
- Runtime database: `tonevyra_agent`.
- Runtime user: `tonevyra_app`.
- Runtime env var: `TONEVYRA_DATABASE_URL`.
- Do not use SQLite as the main DB.
- Do not use the `postgres` superuser for runtime.
- Do not create, drop, or alter tables unless the current ticket explicitly requires a migration.
- Do not store image blobs or heavy payloads in PostgreSQL.
- Store loop evidence in `task_events.payload_json` when no dedicated columns exist.
- Store enough artifact references to recover without reading logs.

## Required Objects
Tables: `image_tasks`, `task_artifacts`, `task_events`, `stage_results`, `quality_results`, `feedback_records`, `learning_samples`.
View: `v_task_summary`.

## Required Event Payload Fields
Where applicable:
`loop_name`, `loop_iteration`, `event_type`, `from_status`, `to_status`, `reason`, `artifact_refs`.

## Validation
- `current_database()` is `tonevyra_agent`.
- `current_user` is `tonevyra_app`.
- Required tables and view exist.
- DB smoke test can create/read/delete test rows.
- `verify_db_state.py` and `verify_loop_events.py` can inspect task state and event evidence.
