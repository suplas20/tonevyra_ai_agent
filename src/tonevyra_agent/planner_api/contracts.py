"""T-032 Planner API request/response contracts and integrity helpers."""

from __future__ import annotations

import hashlib
import json
import platform
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from tonevyra_agent.core.config import Settings
from tonevyra_agent.core.enums import ErrorCode, Stage
from tonevyra_agent.core.errors import TonevyraError
from tonevyra_agent.correction.schemas import ADJUSTMENT_RANGES, CorrectionPlan
from tonevyra_agent.vision.schemas import VisionAnalysisResult


REQUEST_SCHEMA_VERSION = "t032.planner.request.v1"
RESPONSE_SCHEMA_VERSION = "t032.planner.response.v1"
ERROR_SCHEMA_VERSION = "t032.planner.error.v1"

FORBIDDEN_KEYS = {
    "original_image",
    "preview_image",
    "image_bytes",
    "base64_image",
    "filename",
    "file_name",
    "absolute_path",
    "relative_path",
    "source_path",
    "input_folder",
    "output_folder",
    "gps",
    "latitude",
    "longitude",
    "camera_serial_number",
    "serial_number",
    "user_name",
    "customer_name",
    "email",
    "raw_prompt",
    "prompt",
    "raw_model_response",
    "lightroom_catalog_path",
    "catalog_path",
    "preset_path",
    "plugin_path",
    "command",
    "executable",
}

FORBIDDEN_RESPONSE_KEYS = FORBIDDEN_KEYS | {
    "develop_settings",
    "lightroom_adjustments",
    "local_path",
    "script",
}


class PlannerClientInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_version: str = Field(min_length=1)
    platform: Literal["windows", "macos"]
    device_id_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class PlannerImageContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    width: int = Field(ge=1)
    height: int = Field(ge=1)
    orientation: int = Field(ge=1, le=8)
    iso: int | None = Field(default=None, ge=1)
    shutter_seconds: float | None = Field(default=None, gt=0)
    aperture: float | None = Field(default=None, gt=0)
    focal_length_mm: float | None = Field(default=None, gt=0)


class PlannerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = REQUEST_SCHEMA_VERSION
    request_id: str
    client: PlannerClientInfo
    image_context: PlannerImageContext
    analysis: dict[str, Any]
    preferences: dict[str, Any] = Field(default_factory=dict)
    input_digest: str

    @field_validator("request_id")
    @classmethod
    def request_id_must_be_uuid(cls, value: str) -> str:
        UUID(value)
        return value


class PlannerSuccessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    status: Literal["success"]
    request_id: str
    server_request_id: str = Field(min_length=1)
    planner_version: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    input_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    replayed: bool
    plan: dict[str, Any]
    plan_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class PlannerErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    retryable: bool
    retry_after_seconds: float | None = None


class PlannerErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    status: Literal["error"]
    request_id: str | None = None
    server_request_id: str | None = None
    error: PlannerErrorDetail


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_digest(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def request_body_without_digest(request: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in request.items() if key != "input_digest"}


def attach_input_digest(request: dict[str, Any]) -> dict[str, Any]:
    body = dict(request)
    body["input_digest"] = sha256_digest(request_body_without_digest(body))
    return body


def forbidden_key_paths(payload: Any, *, response: bool = False, prefix: str = "") -> list[str]:
    forbidden = FORBIDDEN_RESPONSE_KEYS if response else FORBIDDEN_KEYS
    paths: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if str(key).lower() in forbidden:
                paths.append(path)
            paths.extend(forbidden_key_paths(value, response=response, prefix=path))
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            paths.extend(forbidden_key_paths(value, response=response, prefix=f"{prefix}[{index}]"))
    return paths


def assert_privacy_safe(payload: Any, *, response: bool = False) -> None:
    bad_paths = forbidden_key_paths(payload, response=response)
    if bad_paths:
        raise TonevyraError(
            code=ErrorCode.PLANNER_REQUEST_PRIVACY_VIOLATION,
            message=f"Planner API payload contains forbidden private/executable fields: {', '.join(bad_paths)}",
            failed_stage=Stage.CORRECTION_PLAN.value,
        )


def build_planner_request(
    *,
    request_id: str,
    analysis: VisionAnalysisResult,
    metadata: dict[str, Any],
    settings: Settings,
) -> PlannerRequest:
    image_context = _image_context_from_metadata(metadata)
    body = {
        "schema_version": REQUEST_SCHEMA_VERSION,
        "request_id": request_id,
        "client": {
            "agent_version": "0.32.0",
            "platform": _platform_name(),
            "device_id_hash": _device_id_hash(settings),
        },
        "image_context": image_context,
        "analysis": _analysis_allowlist(analysis),
        "preferences": {
            "correction_strength": "standard",
            "style_profile_id": settings.planner_api_style_profile_id,
        },
    }
    normalized_body = PlannerRequest.model_validate(
        {**body, "input_digest": "sha256:" + "0" * 64}
    ).model_dump(mode="json")
    body_with_digest = attach_input_digest(normalized_body)
    assert_privacy_safe(body_with_digest)
    return PlannerRequest.model_validate(body_with_digest)


def validate_request_digest(request: dict[str, Any]) -> None:
    expected = sha256_digest(request_body_without_digest(request))
    if request.get("input_digest") != expected:
        raise TonevyraError(
            code=ErrorCode.PLANNER_API_RESPONSE_DIGEST_MISMATCH,
            message="Planner request input_digest does not match canonical request body.",
            failed_stage=Stage.CORRECTION_PLAN.value,
        )


def response_to_correction_plan(
    *,
    request: PlannerRequest,
    response_payload: dict[str, Any],
    supported_planner_versions: set[str],
    supported_policy_versions: set[str],
) -> CorrectionPlan:
    try:
        response = PlannerSuccessResponse.model_validate(response_payload)
    except Exception as exc:
        raise TonevyraError(
            code=ErrorCode.PLANNER_API_RESPONSE_INVALID,
            message="Planner API response did not match the success schema.",
            failed_stage=Stage.CORRECTION_PLAN.value,
        ) from exc

    if response.schema_version != RESPONSE_SCHEMA_VERSION:
        raise TonevyraError(
            code=ErrorCode.PLANNER_API_VERSION_UNSUPPORTED,
            message=f"Unsupported Planner response schema: {response.schema_version}",
            failed_stage=Stage.CORRECTION_PLAN.value,
        )
    if response.request_id != request.request_id or response.input_digest != request.input_digest:
        raise TonevyraError(
            code=ErrorCode.PLANNER_API_RESPONSE_INVALID,
            message="Planner response is not bound to the persisted request.",
            failed_stage=Stage.CORRECTION_PLAN.value,
        )
    if response.planner_version not in supported_planner_versions:
        raise TonevyraError(
            code=ErrorCode.PLANNER_API_VERSION_UNSUPPORTED,
            message=f"Unsupported Planner engine version: {response.planner_version}",
            failed_stage=Stage.CORRECTION_PLAN.value,
        )
    if response.policy_version not in supported_policy_versions:
        raise TonevyraError(
            code=ErrorCode.PLANNER_API_VERSION_UNSUPPORTED,
            message=f"Unsupported Planner policy version: {response.policy_version}",
            failed_stage=Stage.CORRECTION_PLAN.value,
        )
    if response.plan_digest != sha256_digest(response.plan):
        raise TonevyraError(
            code=ErrorCode.PLANNER_API_RESPONSE_DIGEST_MISMATCH,
            message="Planner response plan_digest does not match canonical plan body.",
            failed_stage=Stage.CORRECTION_PLAN.value,
        )
    assert_privacy_safe(response.plan, response=True)

    adjustments = _normalize_global_adjustments(response.plan.get("global_adjustments", {}))
    local_adjustments = _normalize_local_adjustments(response.plan.get("local_adjustments", []))
    plan = CorrectionPlan(
        planner_version=response.planner_version,
        base_preset=str(response.plan.get("base_preset") or "Tonevyra Remote Planner Standard"),
        style_target=str(request.preferences.get("style_profile_id") or "remote_planner"),
        adjustments_json=adjustments,
        local_adjustments_json=local_adjustments,
        confidence=float(response.plan.get("confidence") or request.analysis.get("confidence") or 0.0),
        requires_review=bool(response.plan.get("requires_review", False)),
        clamped=bool(response.plan.get("clamped", False)),
        reason_summary=str(response.plan.get("reason_summary") or "validated remote Planner API plan"),
        source={
            "planner_api_schema_version": response.schema_version,
            "planner_version": response.planner_version,
            "policy_version": response.policy_version,
            "server_request_id": response.server_request_id,
            "input_digest": response.input_digest,
            "plan_digest": response.plan_digest,
            "replayed": response.replayed,
        },
    )
    return plan


def _normalize_global_adjustments(payload: Any) -> dict[str, float]:
    if not isinstance(payload, dict):
        raise TonevyraError(
            code=ErrorCode.PLANNER_API_RESPONSE_INVALID,
            message="Planner response plan.global_adjustments must be an object.",
            failed_stage=Stage.CORRECTION_PLAN.value,
        )
    normalized: dict[str, float] = {}
    for raw_key, raw_value in payload.items():
        key = "temp" if raw_key == "temperature" else str(raw_key)
        if key not in ADJUSTMENT_RANGES:
            raise TonevyraError(
                code=ErrorCode.PLANNER_API_RESPONSE_INVALID,
                message=f"Planner response contained unsupported Lightroom adjustment: {raw_key}",
                failed_stage=Stage.CORRECTION_PLAN.value,
            )
        try:
            value = float(raw_value)
        except (TypeError, ValueError) as exc:
            raise TonevyraError(
                code=ErrorCode.PLANNER_API_RESPONSE_INVALID,
                message=f"Planner response adjustment is not numeric: {raw_key}",
                failed_stage=Stage.CORRECTION_PLAN.value,
            ) from exc
        minimum, maximum = ADJUSTMENT_RANGES[key]
        if value < minimum or value > maximum:
            raise TonevyraError(
                code=ErrorCode.PLANNER_API_RESPONSE_INVALID,
                message=f"Planner response adjustment {raw_key}={value} outside range {minimum}..{maximum}.",
                failed_stage=Stage.CORRECTION_PLAN.value,
            )
        normalized[key] = round(value, 3)
    if not normalized:
        raise TonevyraError(
            code=ErrorCode.PLANNER_API_RESPONSE_INVALID,
            message="Planner response did not include any usable global adjustments.",
            failed_stage=Stage.CORRECTION_PLAN.value,
        )
    return normalized


def _normalize_local_adjustments(payload: Any) -> dict[str, Any]:
    if payload in (None, [], {}):
        return {}
    if isinstance(payload, dict):
        assert_privacy_safe(payload, response=True)
        return payload
    if isinstance(payload, list):
        assert_privacy_safe(payload, response=True)
        return {
            "schema_version": "tonevyra.remote_local_adjustments.v1",
            "execution_intent": "request_lightroom_classic_masks_when_supported",
            "remote_local_adjustments": payload,
            "degraded_mode": False,
        }
    raise TonevyraError(
        code=ErrorCode.PLANNER_API_RESPONSE_INVALID,
        message="Planner response plan.local_adjustments must be an object or list.",
        failed_stage=Stage.CORRECTION_PLAN.value,
    )


def _analysis_allowlist(analysis: VisionAnalysisResult) -> dict[str, Any]:
    issues = analysis.issues.model_dump(exclude_none=True)
    return {
        "analysis_schema_version": "vision.analysis.v1",
        "scene_type": analysis.scene_type,
        "exposure_state": issues.get("exposure"),
        "dominant_color_cast": issues.get("color_cast"),
        "contrast_state": issues.get("contrast"),
        "sharpness_state": issues.get("sharpness"),
        "noise_state": issues.get("noise"),
        "haze_state": issues.get("haze") or issues.get("haze_turbidity"),
        "subject_type": analysis.main_subject,
        "usable": analysis.usable,
        "requires_review": analysis.requires_review,
        "risk_flags": list(analysis.risk_flags),
        "confidence": analysis.confidence,
    }


def _image_context_from_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    image = metadata.get("image", {}) if isinstance(metadata, dict) else {}
    basic = metadata.get("basic", {}) if isinstance(metadata, dict) else {}
    width = int(image.get("width") or 1)
    height = int(image.get("height") or 1)
    orientation = int(basic.get("orientation") or 1)
    context: dict[str, Any] = {"width": width, "height": height, "orientation": orientation}
    iso = _positive_int(basic.get("iso"))
    shutter = _positive_float(basic.get("exposure_time"))
    aperture = _positive_float(basic.get("f_number"))
    focal = _positive_float(basic.get("focal_length"))
    if iso is not None:
        context["iso"] = iso
    if shutter is not None:
        context["shutter_seconds"] = shutter
    if aperture is not None:
        context["aperture"] = aperture
    if focal is not None:
        context["focal_length_mm"] = focal
    return context


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _positive_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _platform_name() -> Literal["windows", "macos"]:
    system = platform.system().lower()
    return "macos" if system == "darwin" else "windows"


def _device_id_hash(settings: Settings) -> str:
    if settings.planner_api_device_id_hash:
        return settings.planner_api_device_id_hash
    seed = str(settings.project_path(settings.runtime_dir).resolve()).encode("utf-8")
    return "sha256:" + hashlib.sha256(seed).hexdigest()


def csv_set(value: str) -> set[str]:
    return {item.strip() for item in value.split(",") if item.strip()}
