"""T-022 local model quality provider."""

from __future__ import annotations

from pathlib import Path

from tonevyra_agent.core.config import Settings, get_settings
from tonevyra_agent.model_runtime.local_vision_runtime import LocalRuntimeRunner, LocalVisionModelRuntime
from tonevyra_agent.model_runtime.schemas import ModelRuntimeEnvelope
from tonevyra_agent.schemas.quality import QualityRequest, T021QualityResult


class ModelQualityProvider:
    provider_type = "model"
    provider_version = "model-quality-runtime-v1"

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        runtime: LocalVisionModelRuntime | None = None,
        manifest_path: Path | None = None,
        runner: LocalRuntimeRunner | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._runtime = runtime
        self._manifest_path = manifest_path
        self._runner = runner
        self.last_runtime_envelope: ModelRuntimeEnvelope | None = None

    def evaluate(self, request: QualityRequest) -> T021QualityResult:
        result, envelope = self.runtime.evaluate_quality(request)
        self.last_runtime_envelope = envelope
        return result

    @property
    def runtime(self) -> LocalVisionModelRuntime:
        if self._runtime is None:
            self._runtime = LocalVisionModelRuntime(
                settings=self.settings,
                manifest_path=self._manifest_path,
                runner=self._runner,
            )
        return self._runtime
