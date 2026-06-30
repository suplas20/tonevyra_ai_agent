"""T-030 tray state to icon/tooltip mapping."""

from __future__ import annotations

from dataclasses import dataclass

from tonevyra_agent.agent.runtime_state import AgentRuntimeState


@dataclass(frozen=True)
class TrayPresentation:
    icon_name: str
    tooltip: str


def tray_presentation(state: AgentRuntimeState, *, queue_depth: int = 0, failed_count: int = 0) -> TrayPresentation:
    if state == AgentRuntimeState.PROCESSING:
        return TrayPresentation("tonevyra_tray_processing.ico", f"Tonevyra AI - processing, queue {queue_depth}")
    if state == AgentRuntimeState.PAUSED:
        return TrayPresentation("tonevyra_tray_warning.ico", "Tonevyra AI - watching paused")
    if state == AgentRuntimeState.DEGRADED:
        return TrayPresentation("tonevyra_tray_warning.ico", "Tonevyra AI - degraded, check dependencies")
    if state == AgentRuntimeState.ERROR:
        return TrayPresentation("tonevyra_tray_error.ico", f"Tonevyra AI - error, failed {failed_count}")
    if state in {AgentRuntimeState.STOPPING, AgentRuntimeState.STOPPED}:
        return TrayPresentation("tonevyra_tray_warning.ico", "Tonevyra AI - stopping")
    return TrayPresentation("tonevyra_tray.ico", f"Tonevyra AI - watching, queue {queue_depth}")
