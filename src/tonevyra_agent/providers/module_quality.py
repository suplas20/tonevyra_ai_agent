"""Deterministic T-021 module quality provider."""

from __future__ import annotations

from tonevyra_agent.quality.scoring import score_export_image
from tonevyra_agent.schemas.quality import QualityRequest, RetryRecommendation, T021QualityResult


class ModuleQualityProvider:
    """Evaluate exported images using deterministic local quality metrics."""

    provider_type = "module"
    provider_version = "module-quality-v1"

    def evaluate(self, request: QualityRequest) -> T021QualityResult:
        scores, metrics, reasons = score_export_image(request.export_path)
        reason_codes = _reason_codes(reasons)
        source_limit_evidence = _source_limit_evidence(metrics)

        if source_limit_evidence:
            status = "SOURCE_LIMITED"
            retry = RetryRecommendation(recommended=False)
        elif scores.overall_score >= 85:
            status = "APPROVED"
            retry = RetryRecommendation(recommended=False)
        elif scores.overall_score >= 45 and reason_codes:
            status = "RETRY_REQUIRED"
            retry = RetryRecommendation(
                recommended=True,
                strategy=_strategy_from_reasons(reason_codes),
                expected_improvement=0.08,
            )
        else:
            status = "FINAL_FAILED"
            retry = RetryRecommendation(recommended=False)

        return T021QualityResult(
            job_id=request.job_id,
            attempt_id=request.attempt_id,
            provider_type=self.provider_type,
            status=status,
            scores={
                "exposure": scores.exposure_score / 100.0,
                "color_naturalness": scores.color_score / 100.0,
                "sharpness": scores.sharpness_score / 100.0,
                "noise": scores.noise_score / 100.0,
                "saturation": scores.saturation_score / 100.0,
                "white_balance": scores.underwater_cast_score / 100.0,
                "overall": scores.overall_score / 100.0,
            },
            reason_codes=reason_codes,
            retry_recommendation=retry,
            source_limit_evidence=source_limit_evidence,
            confidence=0.86,
            improvement_summary={
                "legacy_overall_score": scores.overall_score,
                "metrics": metrics,
            },
        )


def _reason_codes(reasons: list[str]) -> list[str]:
    mapping = {
        "exposure": "UNDEREXPOSED",
        "highlight": "HIGHLIGHT_CLIPPED",
        "shadow": "SHADOW_CRUSHED",
        "color": "COLOR_CAST",
        "underwater": "WHITE_BALANCE_OFF",
        "noise": "NOISE_ELEVATED",
        "saturation": "OVERSATURATED",
        "sharpness": "BLUR_DETECTED",
    }
    codes: list[str] = []
    for reason in reasons:
        lowered = reason.lower()
        for needle, code in mapping.items():
            if needle in lowered and code not in codes:
                codes.append(code)
    return codes


def _source_limit_evidence(metrics: dict) -> list[str]:
    evidence: list[str] = []
    sharpness = metrics.get("sharpness", {}).get("laplacian_variance", 9999)
    exposure = metrics.get("exposure", {})
    if sharpness < 20:
        evidence.append("SOURCE_FOCUS_FAILURE")
    if exposure.get("clipped_highlight_ratio", 0) > 0.22 or exposure.get("clipped_shadow_ratio", 0) > 0.35:
        evidence.append("SOURCE_IRRECOVERABLE_CLIPPING")
    return evidence


def _strategy_from_reasons(reason_codes: list[str]) -> list[str]:
    strategies: list[str] = []
    if "UNDEREXPOSED" in reason_codes or "SHADOW_CRUSHED" in reason_codes:
        strategies.append("recover_exposure_and_shadow_detail")
    if "WHITE_BALANCE_OFF" in reason_codes or "COLOR_CAST" in reason_codes:
        strategies.append("rebalance_white_balance_and_color_cast")
    if "NOISE_ELEVATED" in reason_codes:
        strategies.append("reduce_noise_and_limit_sharpening")
    if "HIGHLIGHT_CLIPPED" in reason_codes:
        strategies.append("reduce_highlights_protect_clipping")
    return strategies or ["conservative_quality_recovery"]
