from __future__ import annotations

import pytest

from tonevyra_agent.agent.runtime_snapshot import AgentRuntimeSnapshot
from tonevyra_agent.agent.runtime_state import AgentRuntimeState, reduce_runtime_state


def test_runtime_state_reducer_priority() -> None:
    assert reduce_runtime_state(initialized=True, processing_count=1) == AgentRuntimeState.PROCESSING
    assert reduce_runtime_state(initialized=True, watch_paused=True, processing_count=1) == AgentRuntimeState.PAUSED
    assert reduce_runtime_state(initialized=True, fatal_error=True) == AgentRuntimeState.ERROR
    assert reduce_runtime_state(initialized=True, shutdown_requested=True) == AgentRuntimeState.STOPPING


def test_runtime_snapshot_validates_degraded_reasons() -> None:
    with pytest.raises(ValueError):
        AgentRuntimeSnapshot(
            agent_instance_id="agent-1",
            state=AgentRuntimeState.DEGRADED,
            watching_enabled=True,
            watch_path="runtime/input",
            queue_depth=0,
            processing_count=0,
            failed_count=0,
            lightroom_connected=False,
            model_ready=True,
            db_ready=True,
            worker_restart_count=0,
        )


def test_runtime_snapshot_allows_watching() -> None:
    snapshot = AgentRuntimeSnapshot(
        agent_instance_id="agent-1",
        state=AgentRuntimeState.WATCHING,
        watching_enabled=True,
        watch_path="runtime/input",
        queue_depth=0,
        processing_count=0,
        failed_count=0,
        lightroom_connected=True,
        model_ready=True,
        db_ready=True,
        worker_restart_count=0,
    )

    assert snapshot.schema_version == "t030.agent_runtime_snapshot.v1"
