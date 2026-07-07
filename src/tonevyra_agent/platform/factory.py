"""Platform runtime selection."""

from __future__ import annotations

import sys

from tonevyra_agent.platform.contracts import PlatformRuntime
from tonevyra_agent.platform.windows.runtime import WindowsRuntime


def create_platform_runtime() -> PlatformRuntime:
    if sys.platform == "win32":
        return WindowsRuntime()
    if sys.platform == "darwin":
        from tonevyra_agent.platform.macos.runtime import MacOSRuntime

        return MacOSRuntime()
    from tonevyra_agent.platform.posix.runtime import PosixRuntime

    return PosixRuntime()

