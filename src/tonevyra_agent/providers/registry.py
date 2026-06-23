"""T-021 provider registry."""

from __future__ import annotations

from dataclasses import dataclass

from tonevyra_agent.providers.base import AnalysisProvider, QualityProvider
from tonevyra_agent.providers.model_analysis import ModelAnalysisProvider
from tonevyra_agent.providers.model_quality import ModelQualityProvider
from tonevyra_agent.providers.module_analysis import ModuleAnalysisProvider
from tonevyra_agent.providers.module_quality import ModuleQualityProvider


@dataclass(frozen=True)
class ProviderRegistry:
    analysis_providers: dict[str, AnalysisProvider]
    quality_providers: dict[str, QualityProvider]

    def analysis(self, provider_type: str) -> AnalysisProvider:
        return self.analysis_providers[provider_type]

    def quality(self, provider_type: str) -> QualityProvider:
        return self.quality_providers[provider_type]


def create_provider_registry() -> ProviderRegistry:
    return ProviderRegistry(
        analysis_providers={
            "module": ModuleAnalysisProvider(),
            "model": ModelAnalysisProvider(),
        },
        quality_providers={
            "module": ModuleQualityProvider(),
            "model": ModelQualityProvider(),
        },
    )
