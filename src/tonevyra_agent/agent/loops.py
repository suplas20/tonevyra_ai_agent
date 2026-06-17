"""Loop evidence definitions and payload validation for Tonevyra AI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tonevyra_agent.core.enums import TaskStatus


WATCH_LOOP = "watch_loop"
PROCESSING_LOOP = "processing_loop"
QUALITY_LOOP = "quality_loop"
RECOVERY_LOOP = "recovery_loop"
FEEDBACK_LOOP = "feedback_loop"
MODEL_BENCHMARK_LOOP = "model_benchmark_loop"

ALLOWED_LOOP_NAMES: frozenset[str] = frozenset(
    {
        WATCH_LOOP,
        PROCESSING_LOOP,
        QUALITY_LOOP,
        RECOVERY_LOOP,
        FEEDBACK_LOOP,
        MODEL_BENCHMARK_LOOP,
    }
)

IMPLEMENTED_MVP_LOOPS: frozenset[str] = frozenset(
    {
        WATCH_LOOP,
        PROCESSING_LOOP,
        QUALITY_LOOP,
        RECOVERY_LOOP,
        FEEDBACK_LOOP,
        MODEL_BENCHMARK_LOOP,
    }
)

REQUIRED_LOOP_PAYLOAD_KEYS: tuple[str, ...] = (
    "loop_name",
    "loop_iteration",
    "event_type",
    "from_status",
    "to_status",
    "reason",
    "evidence_artifacts",
)


@dataclass(frozen=True)
class LoopDefinition:
    loop_name: str
    entry_condition: str
    allowed_actions: tuple[str, ...]
    state_transitions: tuple[str, ...]
    retry_limit: str
    timeout: str
    exit_condition: str
    failure_condition: str
    human_review_condition: str
    persisted_evidence: str
    harness_verification: str


@dataclass(frozen=True)
class LoopPayloadValidation:
    ok: bool
    errors: tuple[str, ...]


LOOP_DEFINITIONS: dict[str, LoopDefinition] = {
    WATCH_LOOP: LoopDefinition(
        loop_name=WATCH_LOOP,
        entry_condition="input folder scan requested",
        allowed_actions=("ignore file", "stabilize file", "register task", "skip unsupported file"),
        state_transitions=("DETECTED -> QUEUED", "DETECTED -> SKIPPED"),
        retry_limit="file stabilization checks are bounded by settings",
        timeout="file_stable_timeout_seconds",
        exit_condition="scan completes for current input snapshot",
        failure_condition="file does not stabilize or unsupported visible file is skipped",
        human_review_condition="unsupported visible files are operator-visible as SKIPPED",
        persisted_evidence="task_events.payload_json and image_tasks row",
        harness_verification="run_watcher_test.py and verify_loop_events.py",
    ),
    PROCESSING_LOOP: LoopDefinition(
        loop_name=PROCESSING_LOOP,
        entry_condition="queued image task exists",
        allowed_actions=("metadata", "preview", "vision", "correction plan", "Lightroom request", "export"),
        state_transitions=(
            "QUEUED -> ANALYZING",
            "ANALYZING -> ANALYSIS_DONE",
            "ANALYSIS_DONE -> CORRECTION_PLANNED",
            "CORRECTION_PLANNED -> LIGHTROOM_REQUESTED",
            "LIGHTROOM_REQUESTED -> LIGHTROOM_PROCESSING",
            "LIGHTROOM_PROCESSING -> EXPORT_DONE",
        ),
        retry_limit="no automatic retry in T-012",
        timeout="Lightroom response timeout is bounded by settings",
        exit_condition="task reaches quality loop or structured failure",
        failure_condition="stage failure records TASK_FAILED with controlled error code",
        human_review_condition="planner or quality may force REVIEW_REQUIRED",
        persisted_evidence="task_events.payload_json, stage_results, task_artifacts",
        harness_verification="run_worker_pipeline_test.py, run_smoke_pipeline.py, verify_loop_events.py",
    ),
    QUALITY_LOOP: LoopDefinition(
        loop_name=QUALITY_LOOP,
        entry_condition="exported image evidence exists",
        allowed_actions=("score export", "persist quality detail", "finalize task"),
        state_transitions=("QUALITY_CHECK -> PASS", "QUALITY_CHECK -> REVIEW_REQUIRED", "QUALITY_CHECK -> FAILED"),
        retry_limit="no automatic re-correction loop in MVP",
        timeout="single bounded quality evaluation",
        exit_condition="final quality decision is persisted",
        failure_condition="quality failure marks task FAILED with controlled error code",
        human_review_condition="borderline score or planner review flag forces REVIEW_REQUIRED",
        persisted_evidence="quality_detail.json, quality_results, task_events.payload_json",
        harness_verification="run_quality_gate_test.py, run_smoke_pipeline.py, verify_loop_events.py",
    ),
    RECOVERY_LOOP: LoopDefinition(
        loop_name=RECOVERY_LOOP,
        entry_condition="unfinished task exists",
        allowed_actions=("inspect evidence", "resume safely", "fail safely"),
        state_transitions=("unfinished status -> safe resume status", "unfinished status -> FAILED"),
        retry_limit="one recovery decision per inspected task in T-011/T-012 harness",
        timeout="no unbounded wait; Lightroom evidence is inspected from durable files",
        exit_condition="task is resumed, finalized, or failed with reason",
        failure_condition="inconsistent or missing required evidence fails safely",
        human_review_condition="terminal REVIEW_REQUIRED is not automatically resumed",
        persisted_evidence="recovery_decision.json and task_events.payload_json",
        harness_verification="run_recovery_test.py and verify_loop_events.py",
    ),
    FEEDBACK_LOOP: LoopDefinition(
        loop_name=FEEDBACK_LOOP,
        entry_condition="explicit local user feedback is available",
        allowed_actions=("store feedback", "register learning candidate"),
        state_transitions=("final task status unchanged",),
        retry_limit="single explicit capture in T-013",
        timeout="single local DB/artifact transaction",
        exit_condition="feedback evidence is persisted locally",
        failure_condition="feedback persistence fails with controlled DB/artifact error",
        human_review_condition="all feedback is explicit local user review",
        persisted_evidence="feedback_records, learning_samples, feedback artifacts, task_events.payload_json",
        harness_verification="verify_feedback_learning.py",
    ),
    MODEL_BENCHMARK_LOOP: LoopDefinition(
        loop_name=MODEL_BENCHMARK_LOOP,
        entry_condition="explicit benchmark command is requested",
        allowed_actions=("run local candidate", "measure", "record recommendation", "document rollback path"),
        state_transitions=("candidate evaluated without automatic promotion",),
        retry_limit="bounded 10-photo sample by default; optional bounded 100-photo gate",
        timeout="model benchmark timeout is bounded by the benchmark runner",
        exit_condition="benchmark artifact is written",
        failure_condition="candidate failure is recorded without changing default backend",
        human_review_condition="model promotion always requires explicit review",
        persisted_evidence="model_benchmark_result.json with model_benchmark_loop payload",
        harness_verification="run_model_benchmark_test.py",
    ),
}


def make_loop_payload(
    *,
    loop_name: str,
    event_type: str,
    from_status: str | TaskStatus,
    to_status: str | TaskStatus,
    reason: str,
    loop_iteration: int = 1,
    evidence_artifacts: list[dict[str, Any]] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Build the canonical MVP payload stored in task_events.payload_json."""

    payload = {
        "loop_name": _require_allowed_loop(loop_name),
        "loop_iteration": _require_positive_iteration(loop_iteration),
        "event_type": str(event_type),
        "from_status": _status_value(from_status),
        "to_status": _status_value(to_status),
        "reason": _require_reason(reason),
        "evidence_artifacts": evidence_artifacts or [],
    }
    payload.update(extra)
    return payload


def validate_loop_payload(payload: dict[str, Any], *, event_type: str | None = None) -> LoopPayloadValidation:
    errors: list[str] = []
    missing = [key for key in REQUIRED_LOOP_PAYLOAD_KEYS if key not in payload]
    if missing:
        errors.append(f"missing required keys: {missing}")

    loop_name = payload.get("loop_name")
    if loop_name not in ALLOWED_LOOP_NAMES:
        errors.append(f"invalid loop_name: {loop_name}")

    iteration = payload.get("loop_iteration")
    if not isinstance(iteration, int) or iteration < 1:
        errors.append(f"loop_iteration must be a positive integer: {iteration}")

    payload_event_type = payload.get("event_type")
    if not isinstance(payload_event_type, str) or not payload_event_type.strip():
        errors.append("event_type must be a non-empty string")
    elif event_type is not None and payload_event_type != event_type:
        errors.append(f"payload event_type {payload_event_type} does not match row event_type {event_type}")

    for status_key in ("from_status", "to_status"):
        value = payload.get(status_key)
        try:
            TaskStatus(str(value))
        except ValueError:
            errors.append(f"{status_key} is not a controlled task status: {value}")

    reason = payload.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        errors.append("reason must be a non-empty string")

    evidence = payload.get("evidence_artifacts")
    if not isinstance(evidence, list):
        errors.append("evidence_artifacts must be a list")
    else:
        for index, item in enumerate(evidence):
            if not isinstance(item, dict):
                errors.append(f"evidence_artifacts[{index}] must be an object")
                continue
            if item and not {"artifact_type", "artifact_path"}.issubset(item):
                errors.append(f"evidence_artifacts[{index}] is missing artifact_type or artifact_path")

    return LoopPayloadValidation(ok=not errors, errors=tuple(errors))


def is_loop_payload(payload: dict[str, Any]) -> bool:
    return payload.get("loop_name") in ALLOWED_LOOP_NAMES


def _status_value(value: str | TaskStatus) -> str:
    return value.value if isinstance(value, TaskStatus) else TaskStatus(str(value)).value


def _require_allowed_loop(loop_name: str) -> str:
    if loop_name not in ALLOWED_LOOP_NAMES:
        raise ValueError(f"unknown loop_name: {loop_name}")
    return loop_name


def _require_positive_iteration(loop_iteration: int) -> int:
    if loop_iteration < 1:
        raise ValueError("loop_iteration must be >= 1")
    return loop_iteration


def _require_reason(reason: str) -> str:
    if not reason.strip():
        raise ValueError("reason must not be empty")
    return reason
