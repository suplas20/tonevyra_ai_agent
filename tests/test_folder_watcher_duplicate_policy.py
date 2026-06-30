from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

from tonevyra_agent.agent.watcher import FolderWatcher
from tonevyra_agent.agent.watcher import _file_arrival_timestamp
from tonevyra_agent.core.enums import TaskStatus


class _FakeTaskRepository:
    def __init__(self, *, exact=None, non_failed_same_hash=None) -> None:
        self.exact = exact
        self.non_failed_same_hash = non_failed_same_hash

    def get_by_source_path_hash(self, _session, _source_path, _source_hash):
        return self.exact

    def get_non_failed_by_source_hash(self, _session, _source_hash):
        return self.non_failed_same_hash


def test_same_path_failed_task_blocks_unchanged_repeated_scan() -> None:
    existing = SimpleNamespace(status=TaskStatus.FAILED.value, updated_at=datetime.now())
    watcher = FolderWatcher(task_repository=_FakeTaskRepository(exact=existing))

    duplicate = watcher._is_duplicate(None, source_path="same.ARW", source_hash="hash", file_mtime=_seconds_ago(60))

    assert duplicate is True


def test_same_path_failed_task_allows_operator_redrop_after_failure() -> None:
    existing = SimpleNamespace(status=TaskStatus.FAILED.value, updated_at=datetime.now() - timedelta(minutes=5))
    watcher = FolderWatcher(task_repository=_FakeTaskRepository(exact=existing))

    duplicate = watcher._is_duplicate(None, source_path="same.ARW", source_hash="hash", file_mtime=_seconds_ago(1))

    assert duplicate is False


def test_same_filename_different_hash_is_not_duplicate() -> None:
    watcher = FolderWatcher(task_repository=_FakeTaskRepository())

    duplicate = watcher._is_duplicate(None, source_path="same-name.ARW", source_hash="new-hash", file_mtime=_seconds_ago(1))

    assert duplicate is False


def test_same_content_non_failed_elsewhere_is_duplicate() -> None:
    existing = SimpleNamespace(status=TaskStatus.PASS.value, updated_at=datetime.now())
    watcher = FolderWatcher(task_repository=_FakeTaskRepository(non_failed_same_hash=existing))

    duplicate = watcher._is_duplicate(None, source_path="renamed.ARW", source_hash="same-hash", file_mtime=_seconds_ago(1))

    assert duplicate is True


def test_file_arrival_uses_creation_time_when_mtime_is_preserved(tmp_path) -> None:
    source = tmp_path / "same-name.ARW"
    source.write_bytes(b"raw")
    now = datetime.now().timestamp()
    old = now - 3600
    import os

    os.utime(source, (old, old))

    assert _file_arrival_timestamp(source) >= old


def _seconds_ago(seconds: int) -> float:
    return (datetime.now() - timedelta(seconds=seconds)).timestamp()
