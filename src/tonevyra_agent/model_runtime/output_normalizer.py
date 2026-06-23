"""Normalize T-022 model outputs into T-021 provider schemas."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from tonevyra_agent.core.enums import ErrorCode, Stage
from tonevyra_agent.core.errors import TonevyraError
from tonevyra_agent.schemas.analysis import AnalysisRequest, AnalysisResult, FORBIDDEN_ANALYSIS_FIELDS
from tonevyra_agent.schemas.quality import QualityRequest, RetryRecommendation, T021QualityResult


FORBIDDEN_MODEL_FIELDS = FORBIDDEN_ANALYSIS_FIELDS | {"force_state_transition"}


def reject_forbidden_model_fields(payload: Any) -> None:
    forbidden = _find_forbidden(payload)
    if forbidden:
        raise TonevyraError(
            code=ErrorCode.MODEL_OUTPUT_INVALID,
            message=f"Model output contains forbidden execution fields: {forbidden}",
            failed_stage=Stage.VISION.value,
        )


def normalize_analysis_output(raw_payload: dict[str, Any], request: AnalysisRequest, *, provider_version: str) -> AnalysisResult:
    reject_forbidden_model_fields(raw_payload)
    candidate = _candidate_payload(raw_payload)
    scene = candidate.get("scene") if isinstance(candidate.get("scene"), dict) else {}
    if "type" not in scene and "genre" not in scene:
        scene = {"type": str(candidate.get("scene_type") or "general_photo"), **scene}
    payload = {
        "schema_version": "t021.analysis.result.v1",
        "job_id": str(candidate.get("job_id") or request.job_id),
        "attempt_id": str(candidate.get("attempt_id") or request.attempt_id),
        "provider_type": "model",
        "provider_version": str(candidate.get("provider_version") or provider_version),
        "scene": scene,
        "subjects": _as_list_of_dicts(candidate.get("subjects")),
        "technical_findings": _as_list_of_dicts(candidate.get("technical_findings")),
        "color_findings": _as_list_of_dicts(candidate.get("color_findings")),
        "quality_risks": _as_list(candidate.get("quality_risks")),
        "confidence": float(candidate.get("confidence", raw_payload.get("confidence", 0.0))),
        "analysis_evidence": {
            "normalizer": "t022-analysis-normalizer-v1",
            "model_raw_keys": sorted(str(key) for key in raw_payload.keys()),
        },
        "created_at": candidate.get("created_at"),
    }
    if payload["created_at"] is None:
        payload.pop("created_at")
    try:
        return AnalysisResult.model_validate(payload)
    except ValidationError as exc:
        raise TonevyraError(
            code=ErrorCode.MODEL_OUTPUT_INVALID,
            message="Model analysis output failed T-021 schema validation.",
            failed_stage=Stage.VISION.value,
        ) from exc


def normalize_quality_output(raw_payload: dict[str, Any], request: QualityRequest) -> T021QualityResult:
    reject_forbidden_model_fields(raw_payload)
    candidate = _candidate_payload(raw_payload)
    recommendation = _retry_recommendation(candidate.get("retry_recommendation"))
    improvement_summary = candidate.get("improvement_summary", {})
    if isinstance(improvement_summary, str):
        improvement_summary = {"summary": improvement_summary}
    payload = {
        "schema_version": "t021.quality.result.v1",
        "job_id": str(candidate.get("job_id") or request.job_id),
        "attempt_id": str(candidate.get("attempt_id") or request.attempt_id),
        "provider_type": "model",
        "status": str(candidate.get("status") or "TECHNICAL_FAILED"),
        "scores": candidate.get("scores") or {},
        "reason_codes": _as_list(candidate.get("reason_codes")),
        "retry_recommendation": recommendation,
        "source_limit_evidence": _as_list(candidate.get("source_limit_evidence")),
        "confidence": float(candidate.get("confidence", raw_payload.get("confidence", 0.0))),
        "improvement_summary": improvement_summary,
        "created_at": candidate.get("created_at"),
    }
    if payload["created_at"] is None:
        payload.pop("created_at")
    if payload["status"] == "TECHNICAL_FAILED" and payload["scores"]:
        raise TonevyraError(
            code=ErrorCode.MODEL_OUTPUT_INVALID,
            message="TECHNICAL_FAILED quality output must not fabricate scores.",
            failed_stage=Stage.QUALITY.value,
        )
    try:
        return T021QualityResult.model_validate(payload)
    except ValidationError as exc:
        raise TonevyraError(
            code=ErrorCode.MODEL_OUTPUT_INVALID,
            message="Model quality output failed T-021 schema validation.",
            failed_stage=Stage.QUALITY.value,
        ) from exc


def _candidate_payload(raw_payload: dict[str, Any]) -> dict[str, Any]:
    normalized = raw_payload.get("normalized_output")
    if isinstance(normalized, dict):
        return normalized
    output = raw_payload.get("output")
    if isinstance(output, dict):
        return output
    return raw_payload


def _retry_recommendation(value: Any) -> RetryRecommendation:
    if not isinstance(value, dict):
        return RetryRecommendation(recommended=False)
    strategy = value.get("strategy")
    if isinstance(strategy, list):
        strategy_list = [str(item) for item in strategy if str(item).strip()]
    elif strategy is None:
        strategy_list = []
    else:
        strategy_list = [str(strategy)] if str(strategy).strip() else []
    expected = value.get("expected_improvement", value.get("expected_gain", 0.0))
    extra = {k: v for k, v in value.items() if k not in {"recommended", "strategy", "expected_improvement", "expected_gain"}}
    return RetryRecommendation(
        recommended=bool(value.get("recommended", False)),
        strategy=strategy_list,
        expected_improvement=min(1.0, float(expected or 0.0)),
        **extra,
    )


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _as_list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _find_forbidden(value: Any, prefix: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}"
            if key in FORBIDDEN_MODEL_FIELDS:
                found.append(path)
            found.extend(_find_forbidden(child, path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_find_forbidden(child, f"{prefix}[{index}]"))
    return found
