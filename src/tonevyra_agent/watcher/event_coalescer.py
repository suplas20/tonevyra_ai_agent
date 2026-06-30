"""T-030 filesystem event coalescing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from tonevyra_agent.watcher.file_identity import normalize_path


class WatchEventType(StrEnum):
    CREATED = "CREATED"
    MODIFIED = "MODIFIED"
    RENAMED = "RENAMED"
    MOVED_IN = "MOVED_IN"
    RESCAN_DISCOVERED = "RESCAN_DISCOVERED"


@dataclass(frozen=True)
class RawWatchEvent:
    event_type: WatchEventType
    path: Path
    observed_at: datetime


@dataclass(frozen=True)
class CoalescedWatchEvent:
    event_id: str
    event_type: WatchEventType
    observed_path: Path
    normalized_path: str
    first_seen_at: datetime
    last_seen_at: datetime
    coalesced_event_count: int


@dataclass
class _PendingEvent:
    event_id: str
    event_type: WatchEventType
    observed_path: Path
    normalized_path: str
    first_seen_at: datetime
    last_seen_at: datetime
    coalesced_event_count: int = 1


class EventCoalescer:
    def __init__(self, *, debounce_seconds: float = 2.0, ttl_seconds: float = 300.0) -> None:
        self.debounce = timedelta(seconds=debounce_seconds)
        self.ttl = timedelta(seconds=ttl_seconds)
        self._pending: dict[str, _PendingEvent] = {}

    def ingest(self, event: RawWatchEvent) -> None:
        key = normalize_path(event.path)
        pending = self._pending.get(key)
        if pending is None:
            self._pending[key] = _PendingEvent(
                event_id=str(uuid4()),
                event_type=event.event_type,
                observed_path=event.path,
                normalized_path=key,
                first_seen_at=event.observed_at,
                last_seen_at=event.observed_at,
            )
            return
        pending.last_seen_at = event.observed_at
        pending.observed_path = event.path
        pending.event_type = _dominant_event_type(pending.event_type, event.event_type)
        pending.coalesced_event_count += 1

    def pop_ready(self, now: datetime) -> list[CoalescedWatchEvent]:
        ready: list[CoalescedWatchEvent] = []
        expired: list[str] = []
        for key, pending in self._pending.items():
            age = now - pending.first_seen_at
            quiet = now - pending.last_seen_at
            if quiet >= self.debounce or age >= self.ttl:
                ready.append(
                    CoalescedWatchEvent(
                        event_id=pending.event_id,
                        event_type=pending.event_type,
                        observed_path=pending.observed_path,
                        normalized_path=pending.normalized_path,
                        first_seen_at=pending.first_seen_at,
                        last_seen_at=pending.last_seen_at,
                        coalesced_event_count=pending.coalesced_event_count,
                    )
                )
                expired.append(key)
        for key in expired:
            self._pending.pop(key, None)
        return ready


def _dominant_event_type(previous: WatchEventType, current: WatchEventType) -> WatchEventType:
    priority = {
        WatchEventType.MOVED_IN: 4,
        WatchEventType.RENAMED: 3,
        WatchEventType.CREATED: 2,
        WatchEventType.RESCAN_DISCOVERED: 1,
        WatchEventType.MODIFIED: 0,
    }
    return current if priority[current] >= priority[previous] else previous
