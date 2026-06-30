# Folder Watcher Skill

## Purpose

Detect supported input files, coalesce noisy filesystem events, wait until files are fully stable, and register exactly one durable image task through PostgreSQL.

## Supported Extensions

Required baseline:

```text
.cr3 .cr2 .nef .arw .dng .jpg .jpeg
```

Additional formats may be enabled only after decoder and Lightroom validation:

```text
.raf .rw2 .orf .tif .tiff .png
```

## Ignore Silently

```text
hidden/system files
.tmp .part .crdownload
.xmp .lrcat .lrprev
.DS_Store ._*
0-byte files
Tonevyra runtime/cache/temp/output/failed paths
```

## Event Rules

- Handle Created, Modified, Renamed, Moved-In, and bounded rescan discovery.
- Assume one copy operation can produce many filesystem events.
- Normalize Windows paths case-insensitively.
- Debounce and coalesce by normalized path before stability checks.
- A watcher overflow must create an incident and trigger a bounded rescan.

## Stability Rules

Default policy:

```text
interval_seconds=2
required_stable_samples=3
timeout_seconds=300
```

A file is stable only when:

```text
size is unchanged
mtime is unchanged
read probe succeeds
size > 0
extension is supported
path is not excluded
```

Do not treat the initial Created event or an open-file check alone as proof of completion.

## Duplicate Prevention

Use layered idempotency:

```text
event coalescing
normalized path + size + mtime identity
source hash when available
transactional PostgreSQL register-or-get-existing
existing DB uniqueness/idempotency rules
```

Do not add SQLite as a watcher queue or fallback.

## Source Safety

- Do not overwrite, move, rename, or delete source files in T-030.
- Reject or explicitly exclude overlapping input/output/internal paths.
- Prevent recursive ingestion of Tonevyra outputs.
- Handle junction/symlink loops safely.

## Pause and Resume

- Pause stops new intake; it does not corrupt an active atomic stage.
- Do not accumulate an unbounded in-memory event list while paused.
- Resume performs a bounded rescan and applies the same stability/dedup policy.

## Evidence

```text
watch_event.json
file_stability_evidence.json
task_registration_result.json
deduplication_evidence.json
rescan_evidence.json
```

## Acceptance

- A file still being copied never enters analysis.
- Event storms create one task/effect.
- Restart and rescan do not duplicate completed work.
- Unsupported or temporary files are safely ignored/skipped.
- Source file integrity remains unchanged.

## T-031 macOS FSEvents rule

On macOS, FSEvents is a change hint. Rescan affected roots and reuse the existing stability and dedup gates; never map one event directly to one job.
