"""Deterministic semantic subject analyzer for T-023."""

from __future__ import annotations

from typing import Any

from tonevyra_agent.schemas.analysis import AnalysisResult
from tonevyra_agent.semantic.schemas import SemanticAnalysis, SemanticRegion, find_forbidden_t023_keys


class SemanticSubjectAnalyzer:
    """Normalize provider-neutral analysis into semantic region evidence."""

    analyzer_version = "semantic-subject-analyzer-v1"

    def __init__(self, min_region_confidence: float = 0.3) -> None:
        self.min_region_confidence = min_region_confidence

    def analyze(self, analysis: AnalysisResult | dict[str, Any]) -> SemanticAnalysis:
        payload = analysis.model_dump(mode="json") if isinstance(analysis, AnalysisResult) else dict(analysis)
        forbidden = find_forbidden_t023_keys(payload)
        if forbidden:
            raise ValueError(f"analysis payload contains forbidden execution fields: {forbidden}")

        job_id = str(payload["job_id"])
        attempt_id = str(payload["attempt_id"])
        provider_type = str(payload.get("provider_type", "module"))
        confidence = float(payload.get("confidence", 0.75))
        source = f"{provider_type}-normalized"
        scene_type = str((payload.get("scene") or {}).get("type") or (payload.get("scene") or {}).get("genre") or "").lower()
        subjects = [subject for subject in payload.get("subjects", []) if isinstance(subject, dict)]
        risks = _risk_labels(payload.get("quality_risks", []))

        regions: list[SemanticRegion] = []
        seen_region_types: set[str] = set()

        for subject in sorted(subjects, key=lambda item: int(item.get("priority", 99))):
            subject_type = str(subject.get("type") or subject.get("category") or "object").lower()
            region_type = _subject_region_type(subject_type)
            if region_type in seen_region_types:
                continue
            regions.append(
                self._make_region(
                    region_type=region_type,
                    priority=len(regions) + 1,
                    confidence=_subject_confidence(subject, confidence),
                    source=source,
                    attributes={key: value for key, value in subject.items() if key not in {"type", "category", "priority"}},
                    inherited_risks=risks,
                )
            )
            seen_region_types.add(region_type)

        if not regions:
            fallback_type = "person" if any(token in scene_type for token in ("portrait", "wedding", "people")) else "primary_subject"
            regions.append(
                self._make_region(
                    region_type=fallback_type,
                    priority=1,
                    confidence=max(confidence - 0.12, self.min_region_confidence),
                    source=source,
                    attributes={"inferred_from_scene": bool(scene_type)},
                    inherited_risks=risks,
                )
            )
            seen_region_types.add(fallback_type)

        if "sky" in scene_type or any(str(subject.get("type", "")).lower() == "sky" for subject in subjects):
            if "sky" not in seen_region_types:
                regions.append(
                    self._make_region(
                        region_type="sky",
                        priority=len(regions) + 1,
                        confidence=min(confidence + 0.04, 0.98),
                        source=source,
                        attributes={"detected_from_scene": "sky" in scene_type},
                        inherited_risks=risks,
                    )
                )
                seen_region_types.add("sky")

        if _needs_background_region(scene_type, risks) and "background" not in seen_region_types:
            regions.append(
                self._make_region(
                    region_type="background",
                    priority=len(regions) + 1,
                    confidence=max(min(confidence - 0.08, 0.88), self.min_region_confidence),
                    source=source,
                    attributes={"context_region": True},
                    inherited_risks=risks,
                )
            )

        accepted_regions = [region for region in regions if region.confidence >= self.min_region_confidence]
        primary_region_id = accepted_regions[0].region_id if accepted_regions else None
        return SemanticAnalysis(
            job_id=job_id,
            attempt_id=attempt_id,
            provider_type=provider_type,  # type: ignore[arg-type]
            primary_region_id=primary_region_id,
            regions=accepted_regions,
        )

    def _make_region(
        self,
        *,
        region_type: str,
        priority: int,
        confidence: float,
        source: str,
        attributes: dict[str, Any],
        inherited_risks: list[str],
    ) -> SemanticRegion:
        return SemanticRegion(
            region_id=f"region-{region_type.replace('_', '-')}-1",
            region_type=region_type,  # type: ignore[arg-type]
            priority=priority,
            confidence=round(min(max(confidence, 0.0), 1.0), 4),
            attributes=_attributes_for(region_type, attributes),
            quality_risks=_quality_risks_for(region_type, inherited_risks),
            recommended_intents=_recommended_intents_for(region_type),
            source=source,
        )


def _subject_region_type(subject_type: str) -> str:
    if subject_type in {"person", "people", "portrait", "face", "human", "diver"}:
        return "person"
    if subject_type in {"skin", "hair", "sky", "background", "foreground", "product"}:
        return subject_type
    if subject_type in {"primary_subject", "secondary_subject"}:
        return subject_type
    return "object"


def _subject_confidence(subject: dict[str, Any], fallback: float) -> float:
    raw = subject.get("confidence", fallback)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return fallback


def _risk_labels(risks: list[Any]) -> list[str]:
    labels: list[str] = []
    for risk in risks:
        if isinstance(risk, dict):
            label = str(risk.get("code") or risk.get("type") or risk.get("label") or "").lower()
        else:
            label = str(risk).lower()
        if label:
            labels.append(label)
    return labels


def _attributes_for(region_type: str, extra: dict[str, Any]) -> dict[str, Any]:
    attributes = dict(extra)
    if region_type == "person":
        attributes.setdefault("portrait", True)
    if region_type == "sky":
        attributes.setdefault("coverage", 0.3)
    if region_type == "background":
        attributes.setdefault("context", "background_balance")
    return attributes


def _quality_risks_for(region_type: str, inherited_risks: list[str]) -> list[str]:
    risks: list[str] = []
    if region_type in {"person", "face", "skin"}:
        if any("highlight" in risk or "overexposed" in risk or "clipping" in risk for risk in inherited_risks):
            risks.append("face_highlight")
        if any("cast" in risk or "white_balance" in risk for risk in inherited_risks):
            risks.append("skin_tone_shift")
    if region_type == "sky" and any("saturation" in risk or "over" in risk for risk in inherited_risks):
        risks.append("over_saturation")
    if region_type == "background" and any("cast" in risk for risk in inherited_risks):
        risks.append("background_color_cast")
    return risks


def _recommended_intents_for(region_type: str) -> list[str]:
    if region_type in {"person", "face", "skin"}:
        return ["protect_face_highlights", "natural_skin_tone"]
    if region_type == "sky":
        return ["preserve_sky_detail"]
    if region_type == "background":
        return ["separate_background_balance"]
    if region_type == "product":
        return ["protect_product_color"]
    return ["preserve_subject_detail"]


def _needs_background_region(scene_type: str, risks: list[str]) -> bool:
    return "underwater" in scene_type or "landscape" in scene_type or any("cast" in risk for risk in risks)
