"""T-024 photo set grouping and consistency evaluation."""

from __future__ import annotations

from statistics import median

from tonevyra_agent.batch.schemas import (
    PhotoSetItemEvidence,
    RepresentativeSelection,
    SetBaseline,
    SetConsistencyItemResult,
    SetConsistencyResult,
    SetGrouping,
)


OUTLIER_SCENES = {"night_flash", "flash", "backlit", "intentionally_different"}


class PhotoSetConsistencyEngine:
    """Deterministic set consistency evaluator for batch evidence."""

    def __init__(self, *, min_grouping_confidence: float = 0.7) -> None:
        self.min_grouping_confidence = min_grouping_confidence

    def group(
        self,
        items: list[PhotoSetItemEvidence],
        *,
        batch_id: str,
        default_set_id: str = "set-a",
    ) -> SetGrouping:
        grouped: list[str] = []
        outliers: list[str] = []
        reasons = ["capture_group", "scene_similarity", "grouping_confidence"]
        confidences: list[float] = []
        selected_group = self._selected_capture_group(items)
        for item in sorted(items, key=lambda candidate: candidate.job_id):
            if self._is_outlier(item, selected_group):
                outliers.append(item.job_id)
                continue
            grouped.append(item.job_id)
            confidences.append(item.grouping_confidence)
        confidence = round(min(confidences), 4) if confidences else 0.0
        return SetGrouping(
            batch_id=batch_id,
            set_id=default_set_id,
            grouped_job_ids=grouped,
            outlier_job_ids=outliers,
            grouping_confidence=confidence,
            reasons=reasons,
        )

    def select_representative(
        self,
        items: list[PhotoSetItemEvidence],
        grouping: SetGrouping,
    ) -> RepresentativeSelection:
        candidates = [item for item in items if item.job_id in set(grouping.grouped_job_ids)]
        if not candidates:
            raise ValueError("cannot select representative without grouped items")
        exposure_median = median([item.exposure for item in candidates])
        wb_median = median([item.white_balance for item in candidates])
        ranked = sorted(
            candidates,
            key=lambda item: (
                item.source_limited,
                -item.technical_quality_score,
                abs(item.exposure - exposure_median),
                abs(item.white_balance - wb_median),
                item.job_id,
            ),
        )
        selected = ranked[0]
        return RepresentativeSelection(
            batch_id=grouping.batch_id,
            set_id=grouping.set_id,
            representative_job_id=selected.job_id,
            reasons=[
                "highest_technical_quality",
                "source_limitations_avoided",
                "median_like_exposure_color",
            ],
        )

    def baseline(self, items: list[PhotoSetItemEvidence], grouping: SetGrouping) -> SetBaseline:
        grouped = [item for item in items if item.job_id in set(grouping.grouped_job_ids)]
        if not grouped:
            raise ValueError("cannot extract set baseline without grouped items")
        return SetBaseline(
            batch_id=grouping.batch_id,
            set_id=grouping.set_id,
            exposure_target_range=_bounded_range([item.exposure for item in grouped], 0.15, -1.0, 1.0),
            wb_delta_range=_bounded_range([item.white_balance for item in grouped], 200.0, -2000.0, 2000.0),
            color_cast_delta_range=_bounded_range([item.color_cast for item in grouped], 0.12, -1.0, 1.0),
            contrast_delta_range=_bounded_range([item.contrast for item in grouped], 0.12, -1.0, 1.0),
            skin_tone_delta_range=_bounded_range([item.skin_tone for item in grouped], 0.1, -1.0, 1.0),
            subject_emphasis_delta_range=_bounded_range([item.subject_emphasis for item in grouped], 0.12, -1.0, 1.0),
            style_intent_delta_range=_bounded_range([item.style_intent for item in grouped], 0.1, -1.0, 1.0),
        )

    def evaluate(
        self,
        items: list[PhotoSetItemEvidence],
        grouping: SetGrouping,
        selection: RepresentativeSelection,
        baseline: SetBaseline,
    ) -> SetConsistencyResult:
        grouped = set(grouping.grouped_job_ids)
        outliers = set(grouping.outlier_job_ids)
        item_results: list[SetConsistencyItemResult] = []
        for item in sorted(items, key=lambda candidate: candidate.job_id):
            if item.job_id in outliers:
                item_results.append(
                    SetConsistencyItemResult(
                        job_id=item.job_id,
                        consistency_score=60.0,
                        outlier=True,
                        outlier_reason=self._outlier_reason(item),
                        individual_quality_status=item.quality_status,
                    )
                )
                continue
            if item.job_id not in grouped:
                continue
            score = self._score_item(item, baseline)
            item_results.append(
                SetConsistencyItemResult(
                    job_id=item.job_id,
                    consistency_score=score,
                    outlier=False,
                    individual_quality_status=item.quality_status,
                )
            )
        scored_non_outliers = [result.consistency_score for result in item_results if not result.outlier]
        overall = round(sum(scored_non_outliers) / len(scored_non_outliers), 2) if scored_non_outliers else 0.0
        return SetConsistencyResult(
            batch_id=grouping.batch_id,
            set_id=grouping.set_id,
            representative_job_id=selection.representative_job_id,
            grouping_confidence=grouping.grouping_confidence,
            baseline={
                "exposure_target_range": list(baseline.exposure_target_range),
                "wb_delta_range": list(baseline.wb_delta_range),
                "color_cast_delta_range": list(baseline.color_cast_delta_range),
                "contrast_delta_range": list(baseline.contrast_delta_range),
                "skin_tone_delta_range": list(baseline.skin_tone_delta_range),
                "subject_emphasis_delta_range": list(baseline.subject_emphasis_delta_range),
                "style_intent_delta_range": list(baseline.style_intent_delta_range),
                "baseline_method": baseline.baseline_method,
            },
            item_results=item_results,
            overall_score=overall,
        )

    def _selected_capture_group(self, items: list[PhotoSetItemEvidence]) -> str | None:
        counts: dict[str, int] = {}
        for item in items:
            if item.capture_group:
                counts[item.capture_group] = counts.get(item.capture_group, 0) + 1
        if not counts:
            return None
        return sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))[0][0]

    def _is_outlier(self, item: PhotoSetItemEvidence, selected_group: str | None) -> bool:
        if item.grouping_confidence < self.min_grouping_confidence:
            return True
        if item.scene in OUTLIER_SCENES:
            return True
        if selected_group and item.capture_group and item.capture_group != selected_group:
            return True
        return False

    def _outlier_reason(self, item: PhotoSetItemEvidence) -> str:
        if item.grouping_confidence < self.min_grouping_confidence:
            return "low_grouping_confidence"
        if item.scene in OUTLIER_SCENES:
            return "different_lighting"
        return "different_capture_group"

    def _score_item(self, item: PhotoSetItemEvidence, baseline: SetBaseline) -> float:
        penalties = [
            _range_penalty(item.exposure, baseline.exposure_target_range, 35.0),
            _range_penalty(item.white_balance, baseline.wb_delta_range, 0.04),
            _range_penalty(item.color_cast, baseline.color_cast_delta_range, 25.0),
            _range_penalty(item.contrast, baseline.contrast_delta_range, 15.0),
            _range_penalty(item.skin_tone, baseline.skin_tone_delta_range, 20.0),
            _range_penalty(item.subject_emphasis, baseline.subject_emphasis_delta_range, 15.0),
            _range_penalty(item.style_intent, baseline.style_intent_delta_range, 15.0),
        ]
        return round(max(0.0, min(100.0, 100.0 - sum(penalties))), 2)


def _bounded_range(values: list[float], radius: float, low: float, high: float) -> tuple[float, float]:
    center = median(values)
    return (round(max(low, center - radius), 4), round(min(high, center + radius), 4))


def _range_penalty(value: float, allowed: tuple[float, float], weight: float) -> float:
    low, high = allowed
    if low <= value <= high:
        return 0.0
    distance = low - value if value < low else value - high
    return abs(distance) * weight
