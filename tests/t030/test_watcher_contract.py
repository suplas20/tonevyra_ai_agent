from __future__ import annotations

from datetime import datetime, timedelta

from tonevyra_agent.core.config import Settings
from tonevyra_agent.watcher.event_coalescer import EventCoalescer, RawWatchEvent, WatchEventType
from tonevyra_agent.watcher.exclusion_policy import ExclusionDecision, WatchExclusionPolicy
from tonevyra_agent.watcher.file_stability import FileStabilityChecker, StabilityPolicy


def test_event_coalescer_collapses_duplicate_modified_events(tmp_path) -> None:
    path = tmp_path / "photo.arw"
    coalescer = EventCoalescer(debounce_seconds=2)
    now = datetime.utcnow()

    coalescer.ingest(RawWatchEvent(WatchEventType.CREATED, path, now))
    coalescer.ingest(RawWatchEvent(WatchEventType.MODIFIED, path, now + timedelta(seconds=0.5)))
    ready = coalescer.pop_ready(now + timedelta(seconds=3))

    assert len(ready) == 1
    assert ready[0].coalesced_event_count == 2
    assert ready[0].event_type == WatchEventType.CREATED


def test_file_stability_requires_size_and_mtime_to_stop_changing(tmp_path) -> None:
    path = tmp_path / "stable.jpg"
    path.write_bytes(b"image")
    checker = FileStabilityChecker()
    result = checker.wait_until_stable(
        path,
        StabilityPolicy(interval_seconds=0.5, required_stable_samples=2, timeout_seconds=10),
    )

    assert result.stable is True
    assert result.read_probe_passed is True
    assert result.size_bytes > 0


def test_exclusion_policy_ignores_temp_and_runtime_paths(tmp_path) -> None:
    settings = Settings(
        runtime_dir=tmp_path / "runtime",
        input_dir=tmp_path / "input",
        output_dir=tmp_path / "runtime" / "output",
        artifact_dir=tmp_path / "runtime" / "artifacts",
        preview_dir=tmp_path / "runtime" / "previews",
        bridge_dir=tmp_path / "runtime" / "bridge",
        log_dir=tmp_path / "logs",
    )
    policy = WatchExclusionPolicy(settings)

    assert policy.classify(tmp_path / "input" / "copy.crdownload") == ExclusionDecision.IGNORE_TEMPORARY
    assert policy.classify(tmp_path / "runtime" / "output" / "result.jpg") == ExclusionDecision.IGNORE_EXCLUDED
    assert policy.classify(tmp_path / "input" / "photo.arw") == ExclusionDecision.CANDIDATE
