"""Replaceable vision model backends."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Protocol

from tonevyra_agent.core.config import Settings, get_settings
from tonevyra_agent.core.enums import ErrorCode, Stage
from tonevyra_agent.core.errors import TonevyraError
from tonevyra_agent.providers.module_analysis import ModuleAnalysisProvider, analysis_to_vision_payload
from tonevyra_agent.schemas.analysis import AnalysisRequest

REQUIRED_OFFLINE_ENV = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "HF_HUB_DISABLE_TELEMETRY": "1",
    "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1",
    "HF_HUB_DISABLE_UPDATE_CHECK": "1",
}


class VisionModelBackend(Protocol):
    """Backend interface. Backends return raw model-like payloads."""

    backend_name: str
    model_name: str

    def analyze(self, *, preview_path: Path, metadata: dict[str, Any], prompt: str) -> dict[str, Any]:
        ...


class MockVisionBackend:
    """Fixture-backed backend used before any real local model is connected."""

    backend_name = "mock"

    def __init__(self, fixture_path: Path, *, model_name: str = "mock-fixture-v1") -> None:
        self.fixture_path = fixture_path
        self.model_name = model_name

    def analyze(self, *, preview_path: Path, metadata: dict[str, Any], prompt: str) -> dict[str, Any]:
        if not preview_path.exists():
            raise TonevyraError(
                code=ErrorCode.MODEL_INFERENCE_FAILED,
                message=f"Preview artifact is missing: {preview_path}",
                failed_stage=Stage.VISION.value,
            )
        if not self.fixture_path.exists():
            raise TonevyraError(
                code=ErrorCode.MODEL_LOAD_FAILED,
                message=f"Mock vision fixture is missing: {self.fixture_path}",
                failed_stage=Stage.VISION.value,
            )

        with self.fixture_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, dict):
            payload.setdefault("model_backend", self.backend_name)
            payload.setdefault("model_name", self.model_name)
        return payload


class ModuleVisionBackend:
    """T-021 deterministic module provider adapted to the existing vision contract."""

    backend_name = "module"
    model_name = "module-analysis-v1"

    def __init__(self, provider: ModuleAnalysisProvider | None = None) -> None:
        self.provider = provider or ModuleAnalysisProvider()

    def analyze(self, *, preview_path: Path, metadata: dict[str, Any], prompt: str) -> dict[str, Any]:
        if not preview_path.exists():
            raise TonevyraError(
                code=ErrorCode.MODEL_INFERENCE_FAILED,
                message=f"Preview artifact is missing: {preview_path}",
                failed_stage=Stage.VISION.value,
            )

        job_id = _job_id_from_preview(preview_path)
        request = AnalysisRequest(
            job_id=job_id,
            attempt_id=f"{job_id}-attempt-0",
            preview_path=preview_path,
            metadata=metadata,
            plan="t021_mvp",
            previous_attempt_context=None,
        )
        try:
            result = self.provider.analyze(request)
        except TonevyraError:
            raise
        except Exception as exc:
            raise TonevyraError(
                code=ErrorCode.MODEL_INFERENCE_FAILED,
                message=f"Module analysis provider failed: {exc}",
                failed_stage=Stage.VISION.value,
            ) from exc
        return analysis_to_vision_payload(result)


class QwenVisionRuntime(Protocol):
    """Runtime adapter for local Qwen inference."""

    def generate(self, *, preview_path: Path, metadata: dict[str, Any], prompt: str) -> str | dict[str, Any]:
        ...


class QwenVisionBackend:
    """Local-only Qwen candidate backend.

    The backend is opt-in, replaceable, and keeps all model loading behind local
    path validation so Qwen is never a hard dependency of the default MVP path.
    """

    backend_name = "qwen"

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        model_path: Path | None = None,
        runtime: QwenVisionRuntime | None = None,
        model_name: str | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.model_path = _validated_model_path(self.settings, model_path or self.settings.qwen_model_path)
        self.model_name = model_name or self.settings.qwen_model_name
        _ensure_offline_environment()
        _verify_model_hash_if_configured(self.model_path, self.settings.qwen_model_sha256)
        self.runtime = runtime or TransformersQwenRuntime(
            model_path=self.model_path,
            model_name=self.model_name,
            max_new_tokens=self.settings.qwen_max_new_tokens,
        )

    def analyze(self, *, preview_path: Path, metadata: dict[str, Any], prompt: str) -> dict[str, Any]:
        preview = _validated_preview_path(self.settings, preview_path)
        try:
            raw_output = self.runtime.generate(
                preview_path=preview,
                metadata=_model_visible_metadata(metadata),
                prompt=prompt,
            )
        except TonevyraError:
            raise
        except Exception as exc:
            raise TonevyraError(
                code=ErrorCode.MODEL_INFERENCE_FAILED,
                message=f"Local Qwen inference failed: {exc}",
                failed_stage=Stage.VISION.value,
            ) from exc

        payload = raw_output if isinstance(raw_output, dict) else _parse_model_json(raw_output)
        payload.setdefault("model_backend", self.backend_name)
        payload.setdefault("model_name", self.model_name)
        return payload


class TransformersQwenRuntime:
    """Thin adapter around a locally installed Transformers-compatible Qwen model."""

    def __init__(self, *, model_path: Path, model_name: str, max_new_tokens: int) -> None:
        _ensure_offline_environment()
        self.model_path = model_path
        self.model_name = model_name
        self.max_new_tokens = max_new_tokens
        try:
            from PIL import Image
            from transformers import AutoProcessor

            try:
                from transformers import AutoModelForImageTextToText as ModelClass
            except ImportError:
                from transformers import AutoModelForVision2Seq as ModelClass
        except ImportError as exc:
            raise TonevyraError(
                code=ErrorCode.MODEL_LOAD_FAILED,
                message="Local Qwen backend requires optional local model runtime packages.",
                failed_stage=Stage.VISION.value,
            ) from exc

        self._image_class = Image
        try:
            model_path_text = str(model_path)
            self.processor = AutoProcessor.from_pretrained(
                model_path_text,
                local_files_only=True,
                trust_remote_code=False,
            )
            self.model = ModelClass.from_pretrained(
                model_path_text,
                local_files_only=True,
                trust_remote_code=False,
            )
            if hasattr(self.model, "eval"):
                self.model.eval()
        except Exception as exc:
            raise TonevyraError(
                code=ErrorCode.MODEL_LOAD_FAILED,
                message=f"Failed to load local Qwen model from {model_path}.",
                failed_stage=Stage.VISION.value,
            ) from exc

    def generate(self, *, preview_path: Path, metadata: dict[str, Any], prompt: str) -> str:
        image = self._image_class.open(preview_path).convert("RGB")
        instruction = _qwen_instruction(prompt=prompt, metadata=metadata)
        if hasattr(self.processor, "apply_chat_template"):
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": str(preview_path)},
                        {"type": "text", "text": instruction},
                    ],
                }
            ]
            text = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        else:
            text = instruction

        inputs = self.processor(text=[text], images=[image], return_tensors="pt")
        device = getattr(self.model, "device", None)
        if device is not None:
            inputs = {key: value.to(device) if hasattr(value, "to") else value for key, value in inputs.items()}
        generated_ids = self.model.generate(**inputs, max_new_tokens=self.max_new_tokens)
        if hasattr(self.processor, "batch_decode"):
            return self.processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
        if hasattr(self.processor, "decode"):
            return self.processor.decode(generated_ids[0], skip_special_tokens=True)
        return str(generated_ids)


def create_vision_backend(settings: Settings | None = None, *, fixture_path: Path | None = None) -> VisionModelBackend:
    config = settings or get_settings()
    backend_name = config.vision_backend.lower()
    if backend_name == "mock":
        configured_fixture = fixture_path or config.project_path(config.vision_mock_fixture)
        return MockVisionBackend(configured_fixture)
    if backend_name in {"module", "module-analysis", "t021_module"}:
        return ModuleVisionBackend()
    if backend_name in {"qwen", "qwen2.5-vl", "qwen25vl"}:
        return QwenVisionBackend(config)
    raise TonevyraError(
        code=ErrorCode.MODEL_LOAD_FAILED,
        message=f"Unsupported vision backend for current MVP ticket: {config.vision_backend}",
        failed_stage=Stage.VISION.value,
    )


def _ensure_offline_environment() -> None:
    for name, value in REQUIRED_OFFLINE_ENV.items():
        os.environ[name] = value


def _validated_model_path(settings: Settings, model_path: Path) -> Path:
    path = settings.project_path(model_path).resolve()
    models_root = settings.project_path(settings.models_dir).resolve()
    try:
        path.relative_to(models_root)
    except ValueError as exc:
        raise TonevyraError(
            code=ErrorCode.SECURITY_NETWORK_ACCESS_BLOCKED,
            message=f"Qwen model path must be inside configured models_dir: {models_root}",
            failed_stage=Stage.VISION.value,
        ) from exc
    if not path.exists():
        raise TonevyraError(
            code=ErrorCode.MODEL_LOAD_FAILED,
            message=f"Local Qwen model path does not exist: {path}",
            failed_stage=Stage.VISION.value,
        )
    return path


def _validated_preview_path(settings: Settings, preview_path: Path) -> Path:
    preview = Path(preview_path)
    if str(preview).lower().startswith(("http:", "https:")):
        raise TonevyraError(
            code=ErrorCode.SECURITY_NETWORK_ACCESS_BLOCKED,
            message="Vision backend input must be a local generated preview path.",
            failed_stage=Stage.VISION.value,
        )
    preview = preview.resolve()
    if not preview.exists():
        raise TonevyraError(
            code=ErrorCode.MODEL_INFERENCE_FAILED,
            message=f"Preview artifact is missing: {preview}",
            failed_stage=Stage.VISION.value,
        )
    allowed_roots = (
        settings.project_path(settings.preview_dir).resolve(),
        settings.project_path(settings.artifact_dir).resolve(),
    )
    if not any(_is_relative_to(preview, root) for root in allowed_roots):
        raise TonevyraError(
            code=ErrorCode.SECURITY_NETWORK_ACCESS_BLOCKED,
            message="Vision backend input must come from runtime previews or artifacts.",
            failed_stage=Stage.VISION.value,
        )
    return preview


def _verify_model_hash_if_configured(model_path: Path, configured_sha256: str | None) -> None:
    expected = (configured_sha256 or "").strip()
    if not expected:
        return
    if not model_path.is_file():
        return
    actual = hashlib.sha256(model_path.read_bytes()).hexdigest()
    if actual != expected:
        raise TonevyraError(
            code=ErrorCode.MODEL_LOAD_FAILED,
            message="Configured Qwen model SHA-256 does not match the local model file.",
            failed_stage=Stage.VISION.value,
        )


def _model_visible_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "basic": metadata.get("basic", {}),
        "image": metadata.get("image", {}),
    }


def _qwen_instruction(*, prompt: str, metadata: dict[str, Any]) -> str:
    return (
        f"{prompt}\n"
        "Use only the local preview image and metadata supplied in this request.\n"
        "Return one JSON object matching Tonevyra AI VisionAnalysisResult. "
        "Do not include Markdown fences or Lightroom adjustment values.\n"
        f"Metadata visible to model: {metadata}\n"
    )


def _parse_model_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end < start:
        return {"model_backend": "qwen", "model_name": "unknown", "raw_text": text}
    try:
        payload = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return {"model_backend": "qwen", "model_name": "unknown", "raw_text": text}
    if not isinstance(payload, dict):
        return {"model_backend": "qwen", "model_name": "unknown", "raw_text": text}
    return payload


def _job_id_from_preview(preview_path: Path) -> str:
    parent_name = preview_path.parent.name.strip()
    if parent_name:
        return parent_name
    return preview_path.stem or "module-job"


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
