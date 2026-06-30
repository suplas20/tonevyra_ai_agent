# T-030 Codex 실행 프롬프트

다음 프롬프트를 Codex CLI 작업 시작점으로 사용한다.

```text
Read AGENTS.md first.
Then read CLAUDE.md.
Then read:
- .docs/t030/T-030_Windows_Background_Watcher_and_Tray_Agent_Work_Order.md
- .docs/t030/T-030_Implementation_Specification.md
- .docs/t030/T-030_Windows_Live_Test_Checklist.md
- .docs/t030/T-030_Tray_Icon_Asset_Guide.md
- .docs/11_Folder_Watcher_File_Pipeline_Agent.md
- .docs/13_Crash_Recovery_Error_Handling_Agent.md
- skills/folder-watcher/SKILL.md
- skills/resumable-idempotent-jobs/SKILL.md
- skills/production-reliability-operations/SKILL.md
- skills/windows-background-agent-lifecycle/SKILL.md
- skills/system-tray-operations/SKILL.md
- skills/testing-harness/SKILL.md
- harness/CONTRACT_T030_WINDOWS_BACKGROUND_TRAY.md

Implement T-030 only.

Goal:
Run Tonevyra as a Windows per-user background agent with a system tray icon. Continuously watch the configured folder, wait until each photo is fully stable, register it idempotently in the existing PostgreSQL queue, and automatically start the existing correction pipeline.

Mandatory architecture:
1. Keep the Tray Shell thin. It may display status and send allowlisted commands only.
2. Keep watcher, stabilization, PostgreSQL task registration, processing, recovery, and Lightroom work in the Background Agent Worker.
3. Use the existing PostgreSQL persistence and repositories. Do not add SQLite.
4. Implement a per-user single-instance primitive for Tray and Worker.
5. Use a bounded heartbeat/restart policy. Do not create an infinite restart loop.
6. Preserve all existing T-019 through T-029 behavior and tests.
7. Preserve worker/model/Lightroom main concurrency=1.
8. Do not introduce new image_tasks status values. T-030 Agent runtime states are separate.

Required capabilities:
- Tray icon lifecycle and status mapping
- right-click menu and double-click/open behavior
- WATCHING, PROCESSING, PAUSED, DEGRADED, ERROR runtime states
- pause, resume, rescan, open folders, open status/dashboard, logs, exit
- Created/Modified/Renamed/Moved-In event handling
- event debounce/coalescing
- file stability gate using size + mtime + read probe
- supported/ignored extension policy
- source/output/internal folder recursion prevention
- transaction-safe task register-or-get-existing
- restart recovery and queue reconciliation
- graceful Windows shutdown/logoff/app exit
- autostart enable/disable/status abstraction under current user
- worker heartbeat and bounded restart
- structured runtime/evidence JSON

Production tray icon rule:
Use the approved Tonevyra symbol source. Do not crop the supplied screenshot. If the repository does not contain an approved SVG or transparent high-resolution symbol, report BLOCKED_TRAY_ICON_ASSET_MISSING for production acceptance. A temporary development icon may not be reported as final.

Do not implement:
- Windows Service
- AutoHotkey, pyautogui, UI coordinate automation
- SQLite queue/fallback
- source photo overwrite/delete
- FastAPI-first server or external listener
- new React dashboard
- worker pool or model concurrency > 1
- installer, code signing, obfuscation, encryption, licensing
- model training or fine-tuning

Implementation behavior:
- Inspect the existing repository before creating files.
- Reuse and extend existing watcher, worker, recovery, repository, CLI, and configuration modules.
- Do not create a parallel pipeline.
- Add migrations only if durable new DB fields are genuinely required; prefer existing task_events/stage_results/artifacts for evidence.
- Keep all retries and waits bounded.
- Record explicit incidents for overflow, stabilization timeout, worker crash, and dependency outages.
- Keep all data local.

Required validation:
1. Run the existing full static/unit regression suite.
2. Run:
   python harness/scripts/verify_t030_windows_background_tray.py --project-root .
3. Produce implementation runtime evidence using the implemented code.
4. Execute the Windows live checklist manually or through a Windows UI-capable test environment.
5. Run strict verification with implementation runtime evidence and Windows live evidence.

Hard gates:
- A file still being copied must never enter ANALYZING.
- Multiple filesystem events for one file must create one task/effect.
- A second process instance must not process jobs.
- Pause/resume/rescan must be idempotent.
- Tray must remain available when Worker crashes and must use bounded restart.
- Exit must remove the tray icon and leave no orphan Worker.
- Source files must not be changed, moved, deleted, or overwritten by T-030.
- A missing production logo asset blocks production acceptance.

Stop conditions:
- If the existing architecture cannot support a per-user single instance safely, stop with BLOCKED_SINGLE_INSTANCE_PRIMITIVE.
- If Worker crash recovery causes duplicate external Lightroom effects, stop with BLOCKED_WORKER_RECOVERY_REGRESSION.
- If Windows tray/live testing is unavailable, complete static implementation but report BLOCKED_WINDOWS_SESSION_TEST_UNAVAILABLE; do not claim T-030 complete.
- Stop after T-030. Do not continue to packaging or code-protection work.

Final report format:
Ticket ID:
Implemented scope:
Architecture used:
Changed files:
Database/migration changes:
Commands run:
Unit and harness results:
Regression results:
Windows live test result:
Tray icon asset status:
Single-instance evidence:
File-stability evidence:
Deduplication evidence:
Crash/restart evidence:
Shutdown/orphan-process evidence:
Out-of-scope items not implemented:
Blocked items:
Risks and follow-up:
Waiting for user approval:
```
