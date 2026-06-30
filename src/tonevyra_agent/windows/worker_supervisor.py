"""T-030 bounded Worker supervision decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from tonevyra_agent.agent.runtime_snapshot import AgentRuntimeSnapshot


@dataclass(frozen=True)
class SupervisionPolicy:
    heartbeat_timeout_seconds: float = 20.0
    restart_window_seconds: float = 300.0
    maximum_restarts_in_window: int = 3
    restart_backoff_seconds: tuple[float, ...] = (2.0, 5.0, 15.0)


@dataclass(frozen=True)
class RestartDecision:
    allowed: bool
    reason: str
    restart_count: int
    backoff_seconds: float = 0.0
    error_code: str | None = None


@dataclass
class WorkerSupervisor:
    policy: SupervisionPolicy = field(default_factory=SupervisionPolicy)
    restart_times: list[datetime] = field(default_factory=list)
    last_snapshot: AgentRuntimeSnapshot | None = None

    def observe_heartbeat(self, snapshot: AgentRuntimeSnapshot) -> None:
        self.last_snapshot = snapshot

    def heartbeat_expired(self, now: datetime | None = None) -> bool:
        if self.last_snapshot is None:
            return True
        current = now or datetime.utcnow()
        heartbeat = datetime.fromisoformat(self.last_snapshot.last_heartbeat_at.replace("Z", "+00:00")).replace(tzinfo=None)
        return (current - heartbeat).total_seconds() > self.policy.heartbeat_timeout_seconds

    def restart_if_allowed(self, *, reason: str, now: datetime | None = None) -> RestartDecision:
        current = now or datetime.utcnow()
        window_start = current - timedelta(seconds=self.policy.restart_window_seconds)
        self.restart_times = [item for item in self.restart_times if item >= window_start]
        if len(self.restart_times) >= self.policy.maximum_restarts_in_window:
            return RestartDecision(
                allowed=False,
                reason=reason,
                restart_count=len(self.restart_times),
                error_code="WORKER_CRASH_LOOP",
            )
        self.restart_times.append(current)
        index = min(len(self.restart_times) - 1, len(self.policy.restart_backoff_seconds) - 1)
        return RestartDecision(
            allowed=True,
            reason=reason,
            restart_count=len(self.restart_times),
            backoff_seconds=self.policy.restart_backoff_seconds[index],
        )
