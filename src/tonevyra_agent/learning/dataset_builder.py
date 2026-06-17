"""Local learning sample manifest construction."""

from __future__ import annotations

from typing import Any

from tonevyra_agent.core.enums import LearningSampleType
from tonevyra_agent.learning.schemas import TrainingSampleManifest
from tonevyra_agent.storage.artifacts import ArtifactRef


def build_training_sample_manifest(
    *,
    task_id: str,
    feedback_id: str,
    sample_type: LearningSampleType,
    approved_for_learning: bool,
    artifacts: dict[str, ArtifactRef],
    metadata: dict[str, Any] | None = None,
) -> TrainingSampleManifest:
    """Build a local-only manifest for future offline learning workflows."""

    return TrainingSampleManifest(
        task_id=task_id,
        feedback_id=feedback_id,
        sample_type=sample_type,
        approved_for_learning=approved_for_learning,
        artifacts={name: _artifact_summary(ref) for name, ref in artifacts.items()},
        metadata=metadata or {},
    )


def _artifact_summary(artifact: ArtifactRef) -> dict[str, Any]:
    return {
        "artifact_id": str(artifact.artifact_id),
        "artifact_type": artifact.artifact_type,
        "artifact_path": artifact.relative_path,
        "sha256": artifact.sha256,
        "size_bytes": artifact.size_bytes,
    }
