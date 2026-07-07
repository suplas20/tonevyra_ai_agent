"""Agent orchestration package.

Submodules are imported lazily so always-on shells can load lightweight agent
boundaries without importing Lightroom, correction, or model analysis code.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

_LAZY_EXPORTS = {
    "LOOP_DEFINITIONS": ("tonevyra_agent.agent.loops", "LOOP_DEFINITIONS"),
    "validate_loop_payload": ("tonevyra_agent.agent.loops", "validate_loop_payload"),
    "RecoveryManager": ("tonevyra_agent.agent.recovery", "RecoveryManager"),
    "RecoveryRunResult": ("tonevyra_agent.agent.recovery", "RecoveryRunResult"),
    "RecoveryTaskResult": ("tonevyra_agent.agent.recovery", "RecoveryTaskResult"),
    "recover_all": ("tonevyra_agent.agent.recovery", "recover_all"),
    "recover_task": ("tonevyra_agent.agent.recovery", "recover_task"),
    "FaultClass": ("tonevyra_agent.agent.reliability", "FaultClass"),
    "LeaseDecision": ("tonevyra_agent.agent.reliability", "LeaseDecision"),
    "ReliabilityStore": ("tonevyra_agent.agent.reliability", "ReliabilityStore"),
    "ReconciliationStatus": ("tonevyra_agent.agent.reliability", "ReconciliationStatus"),
    "FolderWatcher": ("tonevyra_agent.agent.watcher", "FolderWatcher"),
    "WatchScanResult": ("tonevyra_agent.agent.watcher", "WatchScanResult"),
    "AgentRunOnceResult": ("tonevyra_agent.agent.runner", "AgentRunOnceResult"),
    "AgentRunner": ("tonevyra_agent.agent.runner", "AgentRunner"),
    "run_once": ("tonevyra_agent.agent.runner", "run_once"),
    "AgentWorker": ("tonevyra_agent.agent.worker", "AgentWorker"),
    "WorkerPipelineResult": ("tonevyra_agent.agent.worker", "WorkerPipelineResult"),
    "process_next_queued_task": ("tonevyra_agent.agent.worker", "process_next_queued_task"),
    "process_task": ("tonevyra_agent.agent.worker", "process_task"),
}

__all__ = sorted(_LAZY_EXPORTS)


def __getattr__(name: str) -> Any:
    if name not in _LAZY_EXPORTS:
        raise AttributeError(name)
    module_name, attr_name = _LAZY_EXPORTS[name]
    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value

