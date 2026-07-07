"""GPU/process memory telemetry for T-031 evidence."""

from __future__ import annotations

import csv
import platform
import subprocess
from dataclasses import dataclass
from io import StringIO


@dataclass(frozen=True)
class NvidiaProcessMemory:
    pid: int
    process_name: str
    used_memory_mb: float


@dataclass(frozen=True)
class WindowsGpuTelemetry:
    gpu_name: str | None
    rows: tuple[NvidiaProcessMemory, ...]
    error: str | None = None


def collect_windows_gpu_telemetry() -> WindowsGpuTelemetry:
    if platform.system().lower() != "windows":
        return WindowsGpuTelemetry(None, (), error="UNSUPPORTED_PLATFORM")
    try:
        gpu_name = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            text=True,
            timeout=15,
            creationflags=_creationflags(),
        ).strip()
        raw = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-compute-apps=pid,process_name,used_memory",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=15,
            creationflags=_creationflags(),
        )
    except Exception as exc:  # noqa: BLE001 - telemetry failure is evidence, not a crash
        return WindowsGpuTelemetry(None, (), error=f"{exc.__class__.__name__}: {exc}")
    return WindowsGpuTelemetry(gpu_name or "unknown", _parse_nvidia_rows(raw))


def process_used_memory_mb(rows: tuple[NvidiaProcessMemory, ...], pid: int | None) -> float:
    if pid is None:
        return 0.0
    return sum(row.used_memory_mb for row in rows if row.pid == pid)


def _parse_nvidia_rows(raw: str) -> tuple[NvidiaProcessMemory, ...]:
    parsed: list[NvidiaProcessMemory] = []
    for row in csv.reader(StringIO(raw)):
        if len(row) < 3:
            continue
        try:
            parsed.append(
                NvidiaProcessMemory(
                    pid=int(row[0].strip()),
                    process_name=row[1].strip(),
                    used_memory_mb=float(row[2].strip()),
                )
            )
        except ValueError:
            continue
    return tuple(parsed)


def _creationflags() -> int:
    return subprocess.CREATE_NO_WINDOW if platform.system().lower() == "windows" else 0

