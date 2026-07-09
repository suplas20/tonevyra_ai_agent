# Windows Background Agent Lifecycle Skill

## Purpose

Implement and verify Tonevyra as a per-user Windows background application with a thin tray shell, one Worker instance, bounded supervision, graceful shutdown, and restart recovery.

## Use When

```text
- adding background startup or shutdown behavior
- implementing per-user single instance
- supervising the Agent Worker
- handling Windows logoff/restart/session events
- implementing pause/resume runtime state
- adding current-user autostart registration
```

## Required Reading

```text
AGENTS.md
.docs/t030/T-030_Windows_Background_Watcher_and_Tray_Agent_Work_Order.md
.docs/t030/T-030_Implementation_Specification.md
skills/production-reliability-operations/SKILL.md
skills/resumable-idempotent-jobs/SKILL.md
skills/testing-harness/SKILL.md
```

## Core Rules

1. Implement a Windows user-session application, not a Windows Service.
2. Keep Tray Shell and Background Worker as separate logical responsibilities.
3. UI code must not own watcher, Planner, Lightroom, DB, or quality decisions.
4. Use a per-user named mutex or equivalent kernel primitive for single instance.
5. A second launch may activate the existing shell but must not start a second Worker.
6. Worker heartbeat and restart are bounded; crash loops transition to explicit ERROR.
7. Use existing T-028 checkpoint, incident, idempotency, and recovery mechanisms.
8. Shutdown stops intake, checkpoints safely, flushes evidence, joins child processes, and removes the tray icon.
9. Use current-user autostart only; do not require administrator rights.
10. Do not add SQLite, a local server exposed externally, or a second operational queue.

## Runtime State

```text
STARTING
WATCHING
PROCESSING
PAUSED
DEGRADED
ERROR
STOPPING
STOPPED
```

These values are Agent runtime states, not `image_tasks.status` values.

## Single-Instance Pattern

```text
Tray launch
→ acquire Local\\TonevyraAI.Tray.<UserSID>
→ start/connect Worker

Second Tray launch
→ mutex already owned
→ send ACTIVATE command to existing Tray
→ exit without starting Worker
```

Worker uses a separate per-user mutex.

## Supervision Pattern

```text
heartbeat received
→ update runtime snapshot

heartbeat timeout
→ verify process state
→ record incident
→ bounded restart if policy allows
→ recover from last safe checkpoint

restart limit exceeded
→ WORKER_CRASH_LOOP
→ ERROR
→ require explicit user action
```

## Shutdown Pattern

```text
STOPPING
→ stop watcher intake
→ checkpoint current stage
→ persist queue/runtime evidence
→ close IPC
→ terminate/join Worker within timeout
→ remove tray icon
→ STOPPED
```

## Forbidden

```text
Windows Service for tray runtime
unbounded restart loop
force-kill as normal shutdown path
multiple Workers sharing one queue lease
Tray writing DB business state directly
admin-only startup registration
orphan processes after exit
```

## Evidence

```text
single_instance_evidence.json
worker_heartbeat_evidence.json
worker_crash_recovery_evidence.json
shutdown_result.json
autostart_status.json
agent_runtime_snapshot.json
```

## Acceptance

- One Tray and one Worker per user.
- Tray remains responsive when Worker crashes.
- Worker recovery creates no duplicate Lightroom effects.
- Exit leaves no orphan process.
- Restart restores unfinished durable work.

## T-031 idle model lifecycle

The Windows background agent stays resident, but the model worker does not. Use lazy start and bounded idle termination so Lightroom can reclaim GPU capacity when no Tonevyra job is active.

## T-033 Windows Installation Boundary

The Windows Agent remains per-user and non-service. Machine elevation is limited to prerequisites such as PostgreSQL. The installer must preserve single-instance, startup and shutdown behavior and prove Authenticode status in release evidence.
