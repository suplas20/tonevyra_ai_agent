"""Structured exceptions for Tonevyra AI Agent."""

from dataclasses import dataclass

from tonevyra_agent.core.enums import ErrorCode


@dataclass
class TonevyraError(Exception):
    code: ErrorCode
    message: str
    failed_stage: str | None = None

    def __str__(self) -> str:
        stage = f" stage={self.failed_stage}" if self.failed_stage else ""
        return f"{self.code.value}:{stage} {self.message}"
