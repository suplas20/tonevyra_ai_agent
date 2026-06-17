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
