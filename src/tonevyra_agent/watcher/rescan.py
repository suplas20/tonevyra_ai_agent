"""T-030 bounded rescan and task registration adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from tonevyra_agent.agent.watcher import FolderWatcher
from tonevyra_agent.core.config import Settings, get_settings
from tonevyra_agent.watcher.exclusion_policy import ExclusionDecision, WatchExclusionPolicy
from tonevyra_agent.watcher.file_stability import FileStabilityChecker, StabilityPolicy


@dataclass
class RescanResult:
    scanned_count: int = 0
    queued_task_ids: list[str] = field(default_factory=list)
    ignored_count: int = 0
    duplicate_count: int = 0
    unstable_count: int = 0
    evidence: list[dict[str, object]] = field(default_factory=list)


class BoundedRescanner:
    """Apply T-030 exclusion/stability gates, then delegate DB registration to the existing watcher."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.policy = WatchExclusionPolicy(self.settings)
        self.stability = FileStabilityChecker()

    def rescan_once(self, session: Session, *, input_dir: Path | None = None, max_files: int = 500) -> RescanResult:
        root = self.settings.project_path(input_dir or self.settings.input_dir)
        result = RescanResult()
        if not root.exists():
            return result

        stability_policy = StabilityPolicy(
            interval_seconds=self.settings.watch_stability_interval_seconds,
            required_stable_samples=self.settings.watch_required_stable_samples,
            timeout_seconds=self.settings.watch_stability_timeout_seconds,
        )
        candidates: list[Path] = []
        iterator = root.rglob("*") if self.settings.watch_recursive else root.glob("*")
        for path in sorted(item for item in iterator if item.is_file()):
            if result.scanned_count >= max_files:
                break
            result.scanned_count += 1
            decision = self.policy.classify(path)
            if decision != ExclusionDecision.CANDIDATE:
                result.ignored_count += 1
                result.evidence.append(_evidence(path=path, decision=decision.value))
                continue
            stable = self.stability.wait_until_stable(path, stability_policy)
            if not stable.stable:
                result.unstable_count += 1
                result.evidence.append(_evidence(path=path, decision="WAIT_STABLE", stability=stable.evidence()))
                continue
            candidates.append(path)

        # Reuse the existing DB registration/idempotency path for supported files.
        scan = FolderWatcher(self.settings).scan_once(session, input_dir=root)
        result.queued_task_ids.extend(scan.created_task_ids)
        result.duplicate_count += len(scan.duplicate_paths)
        result.unstable_count += len(scan.unstable_paths)
        for path in candidates:
            result.evidence.append(_evidence(path=path, decision="QUEUE"))
        return result


def _evidence(
    *,
    path: Path,
    decision: str,
    stability: dict[str, object] | None = None,
) -> dict[str, object]:
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    return {
        "path": str(path.resolve(strict=False)),
        "decision": decision,
        "observed_at": now,
        "stability": stability or {},
    }
