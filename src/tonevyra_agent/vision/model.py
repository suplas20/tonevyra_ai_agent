"""Replaceable vision model backends."""

from __future__ import annotations

import hashlib
import json
import os
import gc
from pathlib import Path
from typing import Any, Protocol

from tonevyra_agent.core.config import Settings, get_settings
from tonevyra_agent.core.enums import ErrorCode, Stage
from tonevyra_agent.core.errors import TonevyraError
from tonevyra_agent.learning.recipe_calibration import build_recipe_model_guidance
from tonevyra_agent.providers.module_analysis import ModuleAnalysisProvider, analysis_to_vision_payload
from tonevyra_agent.schemas.analysis import AnalysisRequest
from tonevyra_agent.vision.vocabulary import normalize_issues

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
        payload = _coerce_vision_result(payload)
        payload.setdefault("model_backend", self.backend_name)
        payload.setdefault("model_name", self.model_name)
        return payload

    def close(self) -> None:
        close = getattr(self.runtime, "close", None)
        if callable(close):
            close()


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
            import torch

            model_path_text = str(model_path)
            self.processor = AutoProcessor.from_pretrained(
                model_path_text,
                local_files_only=True,
                trust_remote_code=False,
            )
            use_cuda = torch.cuda.is_available()
            self.model = ModelClass.from_pretrained(
                model_path_text,
                local_files_only=True,
                trust_remote_code=False,
                dtype=torch.bfloat16 if use_cuda else torch.float32,
                low_cpu_mem_usage=True,
            )
            if hasattr(self.model, "to"):
                self.model = self.model.to("cuda:0" if use_cuda else "cpu")
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
        input_length = inputs["input_ids"].shape[1]
        device = getattr(self.model, "device", None)
        if device is not None:
            inputs = {key: value.to(device) if hasattr(value, "to") else value for key, value in inputs.items()}
        generated_ids = self.model.generate(**inputs, max_new_tokens=self.max_new_tokens, do_sample=False)
        # Decode only the newly generated tokens so the echoed prompt (which contains a
        # JSON example) does not corrupt downstream JSON parsing.
        new_tokens = generated_ids[:, input_length:]
        if hasattr(self.processor, "batch_decode"):
            return self.processor.batch_decode(new_tokens, skip_special_tokens=True)[0]
        if hasattr(self.processor, "decode"):
            return self.processor.decode(new_tokens[0], skip_special_tokens=True)
        return str(new_tokens)

    def close(self) -> None:
        self.model = None
        self.processor = None
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
        except Exception:
            pass


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
    if backend_name in {"qwen3vl", "qwen3-vl", "qwen3"}:
        return QwenVisionBackend(config, model_path=config.qwen3_model_path, model_name=config.qwen3_model_name)
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
    allowed_roots = [settings.project_path(settings.models_dir).resolve()]
    if settings.external_models_dir is not None:
        allowed_roots.append(settings.project_path(settings.external_models_dir).resolve())
    if not any(_is_relative_to(path, root) for root in allowed_roots):
        roots_str = ", ".join(str(r) for r in allowed_roots)
        raise TonevyraError(
            code=ErrorCode.SECURITY_NETWORK_ACCESS_BLOCKED,
            message=f"Qwen model path must be inside configured models_dir or external_models_dir: {roots_str}",
            failed_stage=Stage.VISION.value,
        )
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
    recipe_guidance = build_recipe_model_guidance()
    return (
        f"{prompt}\n"
        "Use only the local preview image and metadata supplied in this request.\n"
        "Return ONE JSON object only, no Markdown fences, no natural-language correction prose.\n"
        "The numeric correction_intents are advisory model suggestions. The planner will validate and clamp them.\n"
        "Do not use forbidden keys: lightroom_adjustments, develop_settings, final_develop_settings, preset_path, plugin_command.\n"
        "The JSON object MUST use this structure. Replace every <number> with an image-specific numeric value;\n"
        "do not copy placeholder zeros unless that field truly needs no correction:\n"
        "{\n"
        '  "scene_type": "<short scene label, e.g. underwater, portrait, landscape>",\n'
        '  "main_subject": "<short subject label>",\n'
        '  "usable": true,\n'
        '  "issues": {\n'
        '    "exposure": "<none|slightly_underexposed|underexposed|severely_underexposed|overexposed|severely_overexposed>",\n'
        '    "color_cast": "<none|cool|strong_cool|warm|strong_warm|green|magenta>",\n'
        '    "contrast": "<none|low|very_low|high>",\n'
        '    "sharpness": "<ok|soft|very_soft>",\n'
        '    "noise": "<none|low|moderate|high>"\n'
        "  },\n"
        '  "correction_intents": {\n'
        '    "exposure": <number>,\n'
        '    "contrast": <number>,\n'
        '    "highlights": <number>,\n'
        '    "shadows": <number>,\n'
        '    "whites": <number>,\n'
        '    "blacks": <number>,\n'
        '    "temp": <number>,\n'
        '    "temperature_delta": <number>,\n'
        '    "tint": <number>,\n'
        '    "vibrance": <number>,\n'
        '    "saturation": <number>,\n'
        '    "texture": <number>,\n'
        '    "clarity": <number>,\n'
        '    "dehaze": <number>,\n'
        '    "noise_reduction": <number>,\n'
        '    "sharpening": <number>,\n'
        '    "aqua_saturation": <number>,\n'
        '    "blue_saturation": <number>,\n'
        '    "red_saturation": <number>,\n'
        '    "orange_luminance": <number>\n'
        "  },\n"
        '  "confidence": 0.85,\n'
        '  "risk_flags": []\n'
        "}\n"
        "Use Tonevyra planner units for correction_intents: exposure in stops; temp as absolute Kelvin; temperature_delta in Kelvin delta;\n"
        "all other fields in Lightroom-like slider delta units. Use 0.0 for no correction.\n"
        "Stay within these advisory ranges before planner validation: exposure -2..2, contrast -50..50,\n"
        "highlights -80..40, shadows -40..80, whites -50..50, blacks -50..50,\n"
        "temp 2500..50000, temperature_delta -3500..3500, tint -50..50, vibrance -30..60, saturation -30..30,\n"
        "texture -20..35, clarity -20..35, dehaze 0..35, noise_reduction 0..60, sharpening 0..80.\n"
        "HSL color mixer advisory ranges are -100..100 for hue/saturation/luminance keys.\n"
        "Magnitude guide: cool cast usually needs temperature_delta +500..+1200; strong_cool underwater\n"
        "near the calibrated action reference should prefer temp around 8200K, tint around +24, highlights near -70,\n"
        "whites near -28, shadows around +38, and blue/aqua saturation mildly reduced rather than crushed.\n"
        "Warm cast uses negative temperature_delta. Green cast uses positive tint; magenta cast uses negative tint.\n"
        "High contrast usually uses contrast -5..-25; low contrast uses contrast +10..+35.\n"
        "Underexposed images usually need exposure +0.8..+1.8 and shadows +35..+75; very dark or severely underexposed RAW previews may need exposure +1.6..+2.0.\n"
        "Overexposed images usually need exposure -0.2..-1.0 and highlights -10..-60.\n"
        "Hazy/turbid underwater images usually need dehaze +8..+28, clarity +4..+18, texture +4..+18.\n"
        "Soft images need sharpening +20..+60; high noise needs noise_reduction +25..+60.\n"
        "Consistency rule: if an issue is not 'none' or 'ok', at least one directly related correction_intents field must be non-zero.\n"
        "For strong_cool underwater, temperature_delta and tint must be non-zero, and vibrance should be non-zero unless saturation is already excessive.\n"
        "Judge color_cast by the dominant unwanted tint: underwater or blue/cyan scenes are\n"
        "usually 'cool' or 'strong_cool'; describe the strength honestly.\n"
        "All issues subfields are required and must be non-empty strings.\n"
        f"{recipe_guidance}\n"
        f"Metadata visible to model: {metadata}\n"
    )


# Fields VisionAnalysisResult accepts at the top level (model_backend/model_name added later).
_VISION_KNOWN_FIELDS = {
    "schema_version",
    "scene_type",
    "main_subject",
    "usable",
    "issues",
    "correction_intents",
    "edit_intent",
    "confidence",
    "risk_flags",
    "requires_review",
}
_VISION_ISSUE_FIELDS = {
    "exposure",
    "color_cast",
    "haze",
    "haze_turbidity",
    "contrast",
    "sharpness",
    "noise",
    "skin_tone",
}
_REQUIRED_ISSUE_FIELDS = ("exposure", "color_cast", "contrast", "sharpness", "noise")
_VISION_CORRECTION_INTENT_FIELDS = {
    "exposure",
    "contrast",
    "highlights",
    "shadows",
    "whites",
    "blacks",
    "temp",
    "temperature_delta",
    "tint",
    "vibrance",
    "saturation",
    "texture",
    "clarity",
    "dehaze",
    "noise_reduction",
    "sharpening",
    "red_saturation",
    "orange_saturation",
    "yellow_saturation",
    "green_saturation",
    "aqua_saturation",
    "blue_saturation",
    "purple_saturation",
    "magenta_saturation",
    "red_hue",
    "orange_hue",
    "yellow_hue",
    "green_hue",
    "aqua_hue",
    "blue_hue",
    "purple_hue",
    "magenta_hue",
    "red_luminance",
    "orange_luminance",
    "yellow_luminance",
    "green_luminance",
    "aqua_luminance",
    "blue_luminance",
    "purple_luminance",
    "magenta_luminance",
}


def _coerce_vision_result(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize raw model output into a VisionAnalysisResult-compatible dict.

    The schema uses extra="forbid", so unknown keys produced by the model must be
    dropped, and required issue subfields must be guaranteed to exist. This keeps
    the real-model worker path resilient without inventing analysis content.
    """

    if not isinstance(payload, dict):
        return payload

    coerced: dict[str, Any] = {key: value for key, value in payload.items() if key in _VISION_KNOWN_FIELDS}

    raw_issues = payload.get("issues")
    issues: dict[str, Any] = {}
    if isinstance(raw_issues, dict):
        issues = {key: value for key, value in raw_issues.items() if key in _VISION_ISSUE_FIELDS}
    # Map the model's free-text issue values onto canonical planner vocabulary so
    # the Correction Planner can translate them into Lightroom adjustments.
    issues = normalize_issues(issues)
    for field in _REQUIRED_ISSUE_FIELDS:
        value = issues.get(field)
        if not isinstance(value, str) or not value.strip():
            issues[field] = "none"
    coerced["issues"] = issues
    raw_intents = payload.get("correction_intents")
    if isinstance(raw_intents, dict):
        intents: dict[str, float] = {}
        for key, value in raw_intents.items():
            if key not in _VISION_CORRECTION_INTENT_FIELDS:
                continue
            try:
                intents[key] = float(value)
            except (TypeError, ValueError):
                continue
        if intents:
            coerced["correction_intents"] = intents

    scene = coerced.get("scene_type")
    if not isinstance(scene, str) or not scene.strip():
        coerced["scene_type"] = "general_photo"
    intent = coerced.get("edit_intent")
    if not isinstance(intent, str) or not intent.strip():
        coerced["edit_intent"] = "structured_numeric_correction"
    if not isinstance(coerced.get("usable"), bool):
        coerced["usable"] = True
    try:
        confidence = float(coerced.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    coerced["confidence"] = max(0.0, min(1.0, confidence))
    if not isinstance(coerced.get("risk_flags"), list):
        coerced["risk_flags"] = []
    return coerced


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
