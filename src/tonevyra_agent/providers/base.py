"""T-021 provider protocols."""

from __future__ import annotations

from typing import Literal, Protocol

from tonevyra_agent.schemas.analysis import AnalysisRequest, AnalysisResult
from tonevyra_agent.schemas.quality import QualityRequest, T021QualityResult


class AnalysisProvider(Protocol):
    provider_type: Literal["module", "model"]
    provider_version: str

    def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        ...


class QualityProvider(Protocol):
    provider_type: Literal["module", "model"]
    provider_version: str

    def evaluate(self, request: QualityRequest) -> T021QualityResult:
        ...
