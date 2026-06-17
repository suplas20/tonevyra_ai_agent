# Loop Engineering Skill

## Purpose
Ensure every autonomous behavior is bounded, observable, recoverable, and evidence-backed.

## Required Loop Fields
`loop_name`, `loop_iteration`, `event_type`, `from_status`, `to_status`, `reason`, `artifact_refs`.

If no DB columns exist for these fields, store them in `task_events.payload_json`.

## Required Loops
`watch_loop`, `processing_loop`, `quality_loop`, `recovery_loop`, `feedback_loop`, `model_benchmark_loop`.

## Rules
- No open-ended loops.
- Every repeated action needs retry, timeout, and exit conditions.
