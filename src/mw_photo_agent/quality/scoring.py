"""Quality decision scoring helpers."""

from mw_photo_agent.core.enums import QualityDecision


def decide_quality(
    overall_score: float,
    pass_threshold: int = 85,
    review_threshold: int = 70,
) -> QualityDecision:
    if overall_score >= pass_threshold:
        return QualityDecision.PASS
    if overall_score >= review_threshold:
        return QualityDecision.REVIEW_REQUIRED
    return QualityDecision.FAILED

