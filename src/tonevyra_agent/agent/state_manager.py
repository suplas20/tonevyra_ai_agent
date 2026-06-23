"""T-021 state transition guard."""

from __future__ import annotations

from tonevyra_agent.schemas.job import T021State


LEGAL_TRANSITIONS: set[tuple[str, str]] = {
    ("CREATED", "ANALYZING"),
    ("ANALYZING", "ADJUSTMENT_READY"),
    ("ANALYZING", "TECHNICAL_FAILED"),
    ("ADJUSTMENT_READY", "LIGHTROOM_PROCESSING"),
    ("ADJUSTMENT_READY", "TECHNICAL_FAILED"),
    ("LIGHTROOM_PROCESSING", "EXPORTED"),
    ("LIGHTROOM_PROCESSING", "TECHNICAL_FAILED"),
    ("EXPORTED", "EVALUATING"),
    ("EXPORTED", "TECHNICAL_FAILED"),
    ("EVALUATING", "APPROVED"),
    ("EVALUATING", "RETRY_REQUIRED"),
    ("EVALUATING", "SOURCE_LIMITED"),
    ("EVALUATING", "TECHNICAL_FAILED"),
    ("EVALUATING", "FINAL_FAILED"),
    ("RETRY_REQUIRED", "ADJUSTMENT_READY"),
    ("RETRY_REQUIRED", "FINAL_FAILED"),
}

TERMINAL_STATES = {"APPROVED", "SOURCE_LIMITED", "TECHNICAL_FAILED", "FINAL_FAILED"}


def validate_transition(source: T021State | str, target: T021State | str) -> tuple[str, str]:
    edge = (str(source), str(target))
    if edge not in LEGAL_TRANSITIONS:
        raise ValueError(f"illegal T-021 state transition: {edge[0]} -> {edge[1]}")
    return edge
