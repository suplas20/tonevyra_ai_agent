# Agent Worker Pipeline Skill

## Purpose
Connect all implemented modules into one bounded one-photo processing pipeline.

## Required Flow
metadata -> preview -> vision -> correction_plan -> lightroom -> export -> quality -> final status

## Rules
- Worker concurrency is 1 in MVP.
- Persist artifacts before marking stages complete.
- Use mock vision and fake Lightroom until real integration tickets are approved.
- Record stage_results and task_events.

## Final Status
`PASS`, `REVIEW_REQUIRED`, or `FAILED`.

## T-030 Background runtime rule

The background Worker owns the processing loop. The Tray Shell may display status and send allowlisted commands but cannot call Provider, Planner, Lightroom, quality, or repository transition logic directly. Main model and Lightroom concurrency remains 1.

## T-031 inference process boundary

Always-on watcher/queue code must not own model objects. Start one child inference process lazily and terminate it after bounded idle grace. Persist lifecycle evidence and prohibit duplicate workers.
