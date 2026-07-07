# System Tray Operations Skill

## Purpose

Build a thin Windows notification-area interface for Tonevyra that shows Agent status and exposes only safe, allowlisted operational commands.

## Use When

```text
- creating or updating the Tonevyra tray icon
- mapping Agent states to icons/tooltips
- implementing tray menus or notifications
- opening configured folders/status UI
- sending pause/resume/rescan/shutdown commands
```

## Required Reading

```text
AGENTS.md
.docs/t030/T-030_Windows_Background_Watcher_and_Tray_Agent_Work_Order.md
.docs/t030/T-030_Tray_Icon_Asset_Guide.md
skills/windows-background-agent-lifecycle/SKILL.md
skills/testing-harness/SKILL.md
```

## Core Rules

1. Use the Tonevyra symbol only; do not place the wordmark in the tray icon.
2. Production icons must come from an approved SVG or transparent high-resolution asset, never a screenshot crop.
3. Include required ICO sizes from 16 through 256 pixels.
4. Keep the base brand symbol stable and use a small shape/color badge for state.
5. The tray is a command client and status renderer, not a business-logic owner.
6. All commands use validated IPC, an allowlist, timeout, and idempotency ID.
7. Opening a folder is limited to configured trusted paths.
8. Notifications are rate-limited; do not show a toast for every successful photo.
9. Removing the icon is part of graceful shutdown.
10. A missing approved icon source blocks production acceptance.

## State Mapping

```text
WATCHING   base Tonevyra icon
PROCESSING base icon + activity badge
PAUSED     base icon + warning/pause badge
DEGRADED   base icon + warning/offline badge
ERROR      base icon + error badge
```

## Required Menu

```text
status summary
open dashboard/status
open input folder
open output folder
pause/resume watching
rescan
view failed jobs
settings
open diagnostic logs
exit Tonevyra
```

## Command Contract

Allowed commands:

```text
GET_STATUS
PAUSE_WATCHING
RESUME_WATCHING
RESCAN
OPEN_INPUT_FOLDER
OPEN_OUTPUT_FOLDER
RETRY_FAILED_JOB
SHUTDOWN
```

Do not add arbitrary shell execution, arbitrary paths, SQL commands, model prompts, or Lightroom payloads to the tray protocol.

## Asset Gate

```text
approved source missing
→ BLOCKED_TRAY_ICON_ASSET_MISSING
```

A temporary development icon may be used for functional tests but cannot satisfy production completion.

## Evidence

```text
tray_state_evidence.json
tray_command_result.json
tray_icon_manifest.json
light_theme_screenshot
dark_theme_screenshot
DPI test notes
```

## Acceptance

- Icon is visible and recognizable on light/dark themes.
- Menu commands are idempotent and reflected in Worker state.
- Tray remains responsive during processing.
- Tray survives Worker crash and reports bounded recovery.
- Exit removes icon and leaves no Worker orphan.

## T-031 macOS menu bar mapping

Map the Windows tray contract to a macOS NSStatusItem-style menu bar shell. Keep status and allowlisted commands only; use a monochrome template icon and do not load the model in the shell.

## T-032 Planner Connectivity State

Tray/menu bar status may display Planner API connected, retrying, auth error, or unavailable states, but it must not own retry logic or Planner business logic. Operator actions may expose a bounded connectivity test and open logs/status only.
