"""Local-only runtime adapter used by T-022 model providers."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from tonevyra_agent.core.config import Settings, get_settings
from tonevyra_agent.core.enums import ErrorCode, Stage
from tonevyra_agent.core.errors import TonevyraError
from tonevyra_agent.model_runtime.manifest import LocalModelManifest
from tonevyra_agent.model_runtime.output_normalizer import normalize_analysis_output, normalize_quality_output
from tonevyra_agent.model_runtime.schemas import ModelRuntimeEnvelope
from tonevyra_agent.schemas.analysis import AnalysisRequest, AnalysisResult
from tonevyra_agent.schemas.quality import QualityRequest, T021QualityResult


class LocalRuntimeRunner(Protocol):
    def generate(self, *, operation: str, request_payload: dict[str, Any]) -> str | dict[str, Any]:
        ...


class JsonLocalRuntimeRunner:
    """Small local runner for tests and pre-provisioned JSON model fixtures."""

    def __init__(self, model_path: Path) -> None:
        self.model_path = model_path

    def generate(self, *, operation: str, request_payload: dict[str, Any]) -> dict[str, Any]:
        if not self.model_path.is_file() or self.model_path.suffix.lower() != ".json":
            raise TonevyraError(
                code=ErrorCode.MODEL_LOAD_FAILED,
                message="Local model runtime needs an injected runner or a local JSON model fixture.",
                failed_stage=Stage.VISION.value,
            )
        payload = json.loads(self.model_path.read_text(encoding="utf-8"))
        operation_payload = payload.get(operation)
        if isinstance(operation_payload, dict):
            return operation_payload
        if isinstance(payload, dict):
            return payload
        raise TonevyraError(
            code=ErrorCode.MODEL_INFERENCE_FAILED,
            message="Local JSON model fixture did not return an object.",
            failed_stage=Stage.VISION.value,
        )


class LocalVisionModelRuntime:
    """Validate local model artifacts and wrap model calls with runtime evidence."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        manifest_path: Path | None = None,
        runner: LocalRuntimeRunner | None = None,
        runtime_version: str | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.manifest_path = manifest_path or self.settings.model_manifest_path
        self._runner = runner
        self.runtime_version = runtime_version or self.settings.model_runtime_version
        self._manifest: LocalModelManifest | None = None
        self._model_path: Path | None = None
        self.model_runtime_retry_count = 0
        self.last_envelope: ModelRuntimeEnvelope | None = None

    @property
    def manifest(self) -> LocalModelManifest:
        if self._manifest is None:
            self._manifest = LocalModelManifest.load(self.manifest_path, self.settings)
            self._model_path = self._manifest.verify_checksum(self.settings)
        return self._manifest

    @property
    def runner(self) -> LocalRuntimeRunner:
        if self._runner is None:
            model_path = self._model_path or self.manifest.verify_checksum(self.settings)
            self._runner = JsonLocalRuntimeRunner(model_path)
        return self._runner

    def analyze(self, request: AnalysisRequest) -> tuple[AnalysisResult, ModelRuntimeEnvelope]:
        raw, envelope_base = self._call_model(
            operation="analysis",
            job_id=request.job_id,
            attempt_id=request.attempt_id,
            request_payload={
                "job_id": request.job_id,
                "attempt_id": request.attempt_id,
                "preview_path": str(request.preview_path),
                "metadata": request.metadata,
                "plan": request.plan,
                "previous_attempt_context": request.previous_attempt_context,
            },
        )
        result = normalize_analysis_output(raw, request, provider_version=self.provider_version)
        envelope = self._finish_envelope(envelope_base, normalized_output=result.model_dump(mode="json"), confidence=result.confidence)
        self.last_envelope = envelope
        return result, envelope

    def evaluate_quality(self, request: QualityRequest) -> tuple[T021QualityResult, ModelRuntimeEnvelope]:
        source_checksum = _file_checksum(request.source_path)
        export_checksum = _file_checksum(request.export_path)
        raw, envelope_base = self._call_model(
            operation="quality",
            job_id=request.job_id,
            attempt_id=request.attempt_id,
            request_payload={
                "job_id": request.job_id,
                "attempt_id": request.attempt_id,
                "source_path": str(request.source_path),
                "export_path": str(request.export_path),
                "source_checksum": source_checksum,
                "export_checksum": export_checksum,
                "analysis": request.analysis.model_dump(mode="json"),
                "applied_adjustment_plan": request.applied_adjustment_plan,
                "previous_quality_result": request.previous_quality_result,
                "plan": request.plan,
            },
            source_checksum=source_checksum,
            export_checksum=export_checksum,
        )
        result = normalize_quality_output(raw, request)
        envelope = self._finish_envelope(envelope_base, normalized_output=result.model_dump(mode="json"), confidence=result.confidence)
        self.last_envelope = envelope
        return result, envelope

    @property
    def provider_version(self) -> str:
        manifest = self.manifest
        return f"{manifest.model_id}:{manifest.model_revision}"

    def _call_model(
        self,
        *,
        operation: str,
        job_id: str,
        attempt_id: str,
        request_payload: dict[str, Any],
        source_checksum: str | None = None,
        export_checksum: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        manifest = self.manifest
        started = _utc_now()
        start = time.monotonic()
        try:
            raw_output = self.runner.generate(operation=operation, request_payload=request_payload)
            raw_payload = _parse_raw_output(raw_output)
            latency_ms = int((time.monotonic() - start) * 1000)
        except TonevyraError:
            raise
        except Exception as exc:
            self.model_runtime_retry_count += 1
            raise TonevyraError(
                code=ErrorCode.MODEL_INFERENCE_FAILED,
                message=f"Local model inference failed: {exc}",
                failed_stage=Stage.VISION.value if operation == "analysis" else Stage.QUALITY.value,
            ) from exc
        completed = _utc_now()
        base = {
            "request_id": f"{operation}-{job_id}-{attempt_id}",
            "job_id": job_id,
            "attempt_id": attempt_id,
            "operation": operation,
            "model_id": manifest.model_id,
            "model_revision": manifest.model_revision,
            "model_checksum": manifest.model_checksum,
            "runtime_backend": manifest.runtime_backend,
            "runtime_version": self.runtime_version,
            "device": manifest.device,
            "dtype": manifest.dtype,
            "quantization": manifest.quantization,
            "started_at": started,
            "completed_at": completed,
            "latency_ms": latency_ms,
            "parse_status": "SUCCESS",
            "raw_output_checksum": _payload_checksum(raw_payload),
            "source_checksum": source_checksum,
            "export_checksum": export_checksum,
            "model_runtime_retry_count": self.model_runtime_retry_count,
            "quality_retry_count": int(request_payload.get("quality_retry_count", 0) or 0),
        }
        return raw_payload, base

    def _finish_envelope(self, base: dict[str, Any], *, normalized_output: dict[str, Any], confidence: float) -> ModelRuntimeEnvelope:
        payload = {**base, "confidence": confidence, "normalized_output": normalized_output}
        envelope = ModelRuntimeEnvelope.model_validate(payload)
        if confidence < self.settings.model_confidence_threshold:
            raise TonevyraError(
                code=ErrorCode.MODEL_OUTPUT_INVALID,
                message="Local model output confidence is below threshold.",
                failed_stage=Stage.VISION.value if envelope.operation == "analysis" else Stage.QUALITY.value,
            )
        return envelope


def _parse_raw_output(raw_output: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw_output, dict):
        return raw_output
    try:
        payload = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        raise TonevyraError(
            code=ErrorCode.MODEL_OUTPUT_INVALID,
            message="Local model output was not valid JSON.",
            failed_stage=Stage.VISION.value,
        ) from exc
    if not isinstance(payload, dict):
        raise TonevyraError(
            code=ErrorCode.MODEL_OUTPUT_INVALID,
            message="Local model output JSON root must be an object.",
            failed_stage=Stage.VISION.value,
        )
    return payload


def _payload_checksum(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _file_checksum(path: Path) -> str:
    return f"sha256:{hashlib.sha256(Path(path).read_bytes()).hexdigest()}"


def _utc_now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"
