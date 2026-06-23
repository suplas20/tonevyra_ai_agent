"""Qwen3-VL local runtime runner for T-022.

Implements LocalRuntimeRunner protocol using the Transformers library.
Requires torch and transformers with Qwen3-VL support.
Network must be blocked: local_files_only=True, trust_remote_code=False.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from tonevyra_agent.core.enums import ErrorCode, Stage
from tonevyra_agent.core.errors import TonevyraError

REQUIRED_OFFLINE_ENV = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "HF_HUB_DISABLE_TELEMETRY": "1",
    "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1",
    "HF_HUB_DISABLE_UPDATE_CHECK": "1",
}

ANALYSIS_SYSTEM_PROMPT = """\
You are a professional photo analysis AI for Tonevyra AI. Your task is to analyze a photograph
and return structured JSON describing scene, subjects, technical findings, and quality risks.

Rules:
- Return ONLY a valid JSON object, no markdown fences, no extra text.
- Do NOT include Lightroom values, develop_settings, preset_path, or final correction decisions.
- Be concise and factual about observable photographic characteristics.
- Express confidence as a float between 0.0 and 1.0.
"""

ANALYSIS_USER_TEMPLATE = """\
Analyze the photo shown. Metadata: {metadata_json}

Return a JSON object with this exact structure:
{{
  "scene": {{"type": "<scene_type>", "genre": "<photo_genre>", "mood": "<mood>"}},
  "subjects": [{{"type": "<subject_type>", "priority": "<primary|secondary>", "notes": "<brief>"}}],
  "technical_findings": [
    {{"category": "exposure", "severity": "<ok|mild|moderate|severe>", "description": "<brief>"}},
    {{"category": "sharpness", "severity": "<ok|mild|moderate|severe>", "description": "<brief>"}},
    {{"category": "noise", "severity": "<ok|mild|moderate|severe>", "description": "<brief>"}}
  ],
  "color_findings": [
    {{"category": "white_balance", "severity": "<ok|mild|moderate|severe>", "description": "<brief>"}},
    {{"category": "color_cast", "severity": "<ok|mild|moderate|severe>", "description": "<brief>"}}
  ],
  "quality_risks": ["<risk_1>", "<risk_2>"],
  "confidence": 0.85
}}
"""

QUALITY_SYSTEM_PROMPT = """\
You are a professional photo quality evaluator for Tonevyra AI. Compare a source photo and
an exported (corrected) photo and return a structured JSON quality evaluation.

Rules:
- Return ONLY a valid JSON object, no markdown fences, no extra text.
- Do NOT include Lightroom values, develop_settings, or final correction decisions.
- Evaluate actual observable improvement or issues in the exported photo.
- status must be one of: APPROVED, RETRY_REQUIRED, SOURCE_LIMITED, TECHNICAL_FAILED.
"""

QUALITY_USER_TEMPLATE = """\
Compare the source image (first) and the corrected export (second). Analysis context: {analysis_json}

Return a JSON object with this exact structure:
{{
  "status": "<APPROVED|RETRY_REQUIRED|SOURCE_LIMITED>",
  "scores": {{
    "exposure": <0-100>,
    "color": <0-100>,
    "sharpness": <0-100>,
    "noise": <0-100>,
    "overall": <0-100>
  }},
  "reason_codes": ["<code1>", "<code2>"],
  "improvement_summary": {{"summary": "<brief improvement description>"}},
  "retry_recommendation": {{
    "recommended": <true|false>,
    "strategy": ["<strategy_1>", "<strategy_2>"],
    "expected_gain": <0-20>,
    "expected_improvement": "<brief>"
  }},
  "source_limit_evidence": [],
  "confidence": 0.85
}}
Only set recommended=true and fill strategy if status is RETRY_REQUIRED.
"""


def _set_offline_env() -> None:
    for name, value in REQUIRED_OFFLINE_ENV.items():
        os.environ[name] = value


def _load_transformers(model_path: Path) -> tuple[Any, Any]:
    _set_offline_env()
    try:
        import torch
        from transformers import AutoProcessor
    except ImportError as exc:
        raise TonevyraError(
            code=ErrorCode.MODEL_LOAD_FAILED,
            message="Qwen runner requires 'torch' and 'transformers' packages.",
            failed_stage=Stage.VISION.value,
        ) from exc

    try:
        from transformers import AutoModelForImageTextToText as ModelClass
    except ImportError:
        try:
            from transformers import AutoModelForVision2Seq as ModelClass
        except ImportError as exc:
            raise TonevyraError(
                code=ErrorCode.MODEL_LOAD_FAILED,
                message="No compatible vision model class found in installed transformers.",
                failed_stage=Stage.VISION.value,
            ) from exc

    model_path_str = str(model_path)
    try:
        processor = AutoProcessor.from_pretrained(
            model_path_str,
            local_files_only=True,
            trust_remote_code=False,
        )
    except Exception as exc:
        raise TonevyraError(
            code=ErrorCode.MODEL_LOAD_FAILED,
            message=f"Failed to load Qwen3-VL processor from {model_path}: {exc}",
            failed_stage=Stage.VISION.value,
        ) from exc

    try:
        import torch
        use_cuda = torch.cuda.is_available()
        model = ModelClass.from_pretrained(
            model_path_str,
            local_files_only=True,
            trust_remote_code=False,
            dtype=torch.bfloat16 if use_cuda else torch.float32,
            low_cpu_mem_usage=True,
        )
        if hasattr(model, "to"):
            model = model.to("cuda:0" if use_cuda else "cpu")
        if hasattr(model, "eval"):
            model.eval()
    except Exception as exc:
        raise TonevyraError(
            code=ErrorCode.MODEL_LOAD_FAILED,
            message=f"Failed to load Qwen3-VL model from {model_path}: {exc}",
            failed_stage=Stage.VISION.value,
        ) from exc

    return processor, model


class QwenLocalRuntimeRunner:
    """Real local Qwen3-VL inference runner implementing LocalRuntimeRunner protocol.

    Loaded lazily on first call to avoid GPU/RAM cost when Free/Lite plans skip model loading.
    """

    def __init__(self, model_path: Path, *, max_new_tokens: int = 512) -> None:
        _set_offline_env()
        self.model_path = model_path
        self.max_new_tokens = max_new_tokens
        self._processor: Any = None
        self._model: Any = None

    def _ensure_loaded(self) -> None:
        if self._processor is None or self._model is None:
            self._processor, self._model = _load_transformers(self.model_path)

    def generate(self, *, operation: str, request_payload: dict[str, Any]) -> dict[str, Any]:
        _set_offline_env()
        self._ensure_loaded()
        if operation == "analysis":
            return self._run_analysis(request_payload)
        if operation == "quality":
            return self._run_quality(request_payload)
        raise TonevyraError(
            code=ErrorCode.MODEL_INFERENCE_FAILED,
            message=f"Unknown operation: {operation}",
            failed_stage=Stage.VISION.value,
        )

    def _run_analysis(self, payload: dict[str, Any]) -> dict[str, Any]:
        preview_path = Path(str(payload.get("preview_path", "")))
        if not preview_path.exists():
            raise TonevyraError(
                code=ErrorCode.MODEL_INFERENCE_FAILED,
                message=f"Preview path does not exist: {preview_path}",
                failed_stage=Stage.VISION.value,
            )
        metadata = payload.get("metadata", {})
        metadata_json = json.dumps({"basic": metadata.get("basic", {}), "image": metadata.get("image", {})})
        user_text = ANALYSIS_USER_TEMPLATE.format(metadata_json=metadata_json)
        raw = self._infer_with_image(
            system_prompt=ANALYSIS_SYSTEM_PROMPT,
            user_text=user_text,
            image_path=preview_path,
        )
        result = _extract_json(raw)
        result.setdefault("job_id", str(payload.get("job_id", "")))
        result.setdefault("attempt_id", str(payload.get("attempt_id", "")))
        return result

    def _run_quality(self, payload: dict[str, Any]) -> dict[str, Any]:
        source_path = Path(str(payload.get("source_path", "")))
        export_path = Path(str(payload.get("export_path", "")))
        for path in (source_path, export_path):
            if not path.exists():
                raise TonevyraError(
                    code=ErrorCode.MODEL_INFERENCE_FAILED,
                    message=f"Quality evaluation path does not exist: {path}",
                    failed_stage=Stage.QUALITY.value,
                )
        analysis = payload.get("analysis", {})
        analysis_json = json.dumps(analysis, ensure_ascii=False)[:500]
        user_text = QUALITY_USER_TEMPLATE.format(analysis_json=analysis_json)
        raw = self._infer_with_two_images(
            system_prompt=QUALITY_SYSTEM_PROMPT,
            user_text=user_text,
            source_path=source_path,
            export_path=export_path,
        )
        result = _extract_json(raw)
        result.setdefault("job_id", str(payload.get("job_id", "")))
        result.setdefault("attempt_id", str(payload.get("attempt_id", "")))
        return result

    def _infer_with_image(self, *, system_prompt: str, user_text: str, image_path: Path) -> str:
        from PIL import Image
        image = Image.open(image_path).convert("RGB")
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": str(image_path)},
                    {"type": "text", "text": user_text},
                ],
            },
        ]
        return self._run_messages(messages, images=[image])

    def _infer_with_two_images(
        self, *, system_prompt: str, user_text: str, source_path: Path, export_path: Path
    ) -> str:
        from PIL import Image
        source_img = Image.open(source_path).convert("RGB")
        export_img = Image.open(export_path).convert("RGB")
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Source image (original):"},
                    {"type": "image", "image": str(source_path)},
                    {"type": "text", "text": "Corrected export image:"},
                    {"type": "image", "image": str(export_path)},
                    {"type": "text", "text": user_text},
                ],
            },
        ]
        return self._run_messages(messages, images=[source_img, export_img])

    def _run_messages(self, messages: list[dict[str, Any]], images: list[Any]) -> str:
        import torch
        processor = self._processor
        model = self._model

        if hasattr(processor, "apply_chat_template"):
            text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        else:
            text = "\n".join(
                msg.get("content") if isinstance(msg.get("content"), str)
                else " ".join(c.get("text", "") for c in msg.get("content", []) if isinstance(c, dict))
                for msg in messages
            )

        inputs = processor(text=[text], images=images, return_tensors="pt")
        input_length = inputs["input_ids"].shape[1]
        device = next(model.parameters()).device if hasattr(model, "parameters") else None
        if device is not None and str(device) != "cpu":
            inputs = {k: v.to(device) if hasattr(v, "to") else v for k, v in inputs.items()}

        with torch.no_grad():
            generated_ids = model.generate(
                **inputs,
                max_new_tokens=self.max_new_tokens,
                do_sample=False,
            )

        # Decode only the newly generated tokens (exclude the input prompt)
        new_tokens = generated_ids[:, input_length:]
        if hasattr(processor, "batch_decode"):
            return processor.batch_decode(new_tokens, skip_special_tokens=True)[0]
        if hasattr(processor, "decode"):
            return processor.decode(new_tokens[0], skip_special_tokens=True)
        return str(new_tokens)


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        cleaned = "\n".join(line for line in lines if not line.strip().startswith("```"))
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {"raw_text": text, "confidence": 0.5}
    try:
        payload = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return {"raw_text": text, "confidence": 0.5}
    if not isinstance(payload, dict):
        return {"raw_text": text, "confidence": 0.5}
    return payload
