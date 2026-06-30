# T-030 Windows Background Watcher and System Tray Harness Contract

## Contract

- Tonevyra runs as a per-user Windows background application, not a Windows Service.
- Exactly one Tray Shell and one Background Worker may process jobs per user.
- The tray is a thin status/command surface and owns no pipeline business logic.
- Created, Modified, Renamed, Moved-In, and rescan events are coalesced before processing.
- A photo is queued only after bounded size/mtime/read-probe stability checks pass.
- PostgreSQL remains the durable queue and source of truth; SQLite fallback is prohibited.
- Duplicate events, rescans, restarts, and second launches must not create duplicate external effects.
- Input, output, cache, runtime, and failed paths must not create recursive ingestion.
- Source photos are never overwritten, moved, deleted, or renamed by T-030.
- Main model and Lightroom execution concurrency remains 1.
- Pause/resume/rescan and tray commands are idempotent and auditable.
- Worker supervision uses heartbeat, bounded restart, crash-loop detection, and T-028 recovery.
- Graceful exit removes the tray icon, persists evidence, and leaves no orphan Worker.
- Production completion requires an approved Tonevyra symbol source and real Windows live evidence.
- T-019 through T-029 regressions remain mandatory.
