# Loop Engineering Skill

## Purpose
Ensure every autonomous behavior is bounded, observable, recoverable, and evidence-backed.

Loop Engineering is the control design for an agent that repeatedly watches, processes, evaluates, retries, recovers, or learns. It is not the same thing as prompt engineering, and it is not merely a simulated test environment.

In this project, Loop Engineering is required because the agent can run without a human clicking each step.

## Required Loop Fields
`loop_name`, `loop_iteration`, `event_type`, `from_status`, `to_status`, `reason`, `artifact_refs`.

If no DB columns exist for these fields, store them in `task_events.payload_json`.

## Required Loops
`watch_loop`, `processing_loop`, `quality_loop`, `recovery_loop`, `feedback_loop`, `model_benchmark_loop`.

## Loop Definitions
| Loop | Responsibility | Required exit condition |
|---|---|---|
| `watch_loop` | Detect stable supported files and create tasks | queued task, skipped file, timeout, or duplicate detected |
| `processing_loop` | Move one task through metadata → vision → plan → Lightroom → export | PASS, REVIEW_REQUIRED, FAILED, or retry handoff |
| `quality_loop` | Score exported image and decide final status | PASS, REVIEW_REQUIRED, FAILED, or bounded retry request |
| `recovery_loop` | Resume or fail non-terminal tasks after interruption | resumed stage, safe failure, or no-op |
| `feedback_loop` | Capture explicit user feedback and manual edit delta | feedback stored, learning sample created only when approved |
| `model_benchmark_loop` | Benchmark model candidates without changing default backend | benchmark artifact written and recommendation recorded |

## Rules
- No open-ended loops.
- Every repeated action needs retry, timeout, and exit conditions.
- Each iteration must leave durable evidence in `task_events` or a referenced artifact.
- Loop evidence must be machine-checkable by `harness/scripts/verify_loop_events.py`.
- Do not create a loop around a failure without incrementing retry_count.
- Do not hide loop decisions only in logs.
- Final task status must be one of `PASS`, `REVIEW_REQUIRED`, or `FAILED` unless the watcher intentionally emits `SKIPPED`.

## Harness Evidence
Minimum payload shape:

```json
{
  "loop_name": "processing_loop",
  "loop_iteration": 1,
  "event_type": "STAGE_COMPLETED",
  "from_status": "ANALYZING",
  "to_status": "CORRECTION_PLANNED",
  "reason": "vision_structured artifact verified",
  "artifact_refs": ["vision_structured.json", "correction_plan.json"]
}
```

## Acceptance Criteria
- `verify_loop_events.py` can find processing and quality loop evidence after smoke pipeline.
- Recovery harness produces recovery_loop evidence.
- Feedback verification produces feedback_loop evidence.
- Benchmark verification produces model_benchmark_loop evidence.
- No loop can run forever under a repeated failure condition.
