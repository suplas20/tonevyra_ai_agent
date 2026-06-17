"""Structured exceptions for task failures."""

from dataclasses import dataclass

from mw_photo_agent.core.enums import ErrorCode


@dataclass
class AgentError(Exception):
    code: ErrorCode
    message: str
    failed_stage: str | None = None

    def __str__(self) -> str:
        stage = f" stage={self.failed_stage}" if self.failed_stage else ""
        return f"{self.code.value}:{stage} {self.message}"

