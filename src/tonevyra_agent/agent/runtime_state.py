"""T-030 Agent runtime state reducer.

These states describe the background Agent process, not image task rows.
"""

from __future__ import annotations

from enum import StrEnum


class AgentRuntimeState(StrEnum):
    STARTING = "STARTING"
    WATCHING = "WATCHING"
    PROCESSING = "PROCESSING"
    PAUSED = "PAUSED"
    DEGRADED = "DEGRADED"
    ERROR = "ERROR"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"


def reduce_runtime_state(
    *,
    initialized: bool,
    shutdown_requested: bool = False,
    stopped: bool = False,
    watch_paused: bool = False,
    fatal_error: bool = False,
    degraded_reasons: list[str] | None = None,
    processing_count: int = 0,
) -> AgentRuntimeState:
    """Compute the T-030 runtime state from facts instead of arbitrary setters."""

    if stopped:
        return AgentRuntimeState.STOPPED
    if fatal_error:
        return AgentRuntimeState.ERROR
    if shutdown_requested:
        return AgentRuntimeState.STOPPING
    if watch_paused:
        return AgentRuntimeState.PAUSED
    if degraded_reasons:
        return AgentRuntimeState.DEGRADED
    if processing_count > 0:
        return AgentRuntimeState.PROCESSING
    if initialized:
        return AgentRuntimeState.WATCHING
    return AgentRuntimeState.STARTING
