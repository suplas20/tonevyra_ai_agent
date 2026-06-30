"""T-030 size/mtime/read-probe stability gate."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StabilityPolicy:
    interval_seconds: float = 2.0
    required_stable_samples: int = 3
    timeout_seconds: float = 300.0
    minimum_size_bytes: int = 1
    require_read_probe: bool = True

    def __post_init__(self) -> None:
        if not 0.5 <= self.interval_seconds <= 30:
            raise ValueError("interval_seconds must be between 0.5 and 30")
        if not 2 <= self.required_stable_samples <= 10:
            raise ValueError("required_stable_samples must be between 2 and 10")
        if not 10 <= self.timeout_seconds <= 3600:
            raise ValueError("timeout_seconds must be between 10 and 3600")


@dataclass(frozen=True)
class StabilitySnapshot:
    size_bytes: int
    mtime_ns: int
    read_probe_passed: bool


@dataclass(frozen=True)
class FileStabilityResult:
    stable: bool
    sample_count: int
    stable_samples: int
    size_bytes: int
    mtime_ns: int
    read_probe_passed: bool
    reason: str | None = None

    def evidence(self) -> dict[str, int | bool]:
        return {
            "sample_count": self.sample_count,
            "stable_samples": self.stable_samples,
            "size_bytes": self.size_bytes,
            "mtime_ns": self.mtime_ns,
            "read_probe_passed": self.read_probe_passed,
        }


class FileStabilityChecker:
    def sample(self, path: Path, policy: StabilityPolicy) -> StabilitySnapshot:
        stat = path.stat()
        read_probe_passed = False
        if stat.st_size >= policy.minimum_size_bytes:
            try:
                with path.open("rb") as handle:
                    handle.read(1)
                read_probe_passed = True
            except OSError:
                read_probe_passed = False
        return StabilitySnapshot(
            size_bytes=max(0, stat.st_size),
            mtime_ns=max(0, stat.st_mtime_ns),
            read_probe_passed=read_probe_passed,
        )

    def wait_until_stable(self, path: Path, policy: StabilityPolicy) -> FileStabilityResult:
        deadline = time.monotonic() + policy.timeout_seconds
        previous: StabilitySnapshot | None = None
        stable_samples = 0
        sample_count = 0
        last = StabilitySnapshot(size_bytes=0, mtime_ns=0, read_probe_passed=False)

        while time.monotonic() <= deadline:
            try:
                current = self.sample(path, policy)
            except OSError as exc:
                return FileStabilityResult(False, sample_count + 1, 0, 0, 0, False, str(exc))
            sample_count += 1
            last = current

            if (
                previous is not None
                and current.size_bytes == previous.size_bytes
                and current.mtime_ns == previous.mtime_ns
                and current.size_bytes >= policy.minimum_size_bytes
                and (current.read_probe_passed or not policy.require_read_probe)
            ):
                stable_samples += 1
            else:
                stable_samples = 1 if current.size_bytes >= policy.minimum_size_bytes else 0
            previous = current

            if stable_samples >= policy.required_stable_samples:
                return FileStabilityResult(
                    True,
                    sample_count,
                    stable_samples,
                    current.size_bytes,
                    current.mtime_ns,
                    current.read_probe_passed,
                )
            time.sleep(policy.interval_seconds)

        return FileStabilityResult(
            False,
            sample_count,
            stable_samples,
            last.size_bytes,
            last.mtime_ns,
            last.read_probe_passed,
            "file did not satisfy size/mtime/read-probe stability before timeout",
        )
