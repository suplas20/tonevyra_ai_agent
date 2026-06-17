"""Local artifact storage interface placeholder."""

from pathlib import Path

from mw_photo_agent.core.enums import ArtifactType


class ArtifactStorage:
    """Stores durable per-task artifacts using atomic writes."""

    def save(self, task_id: str, artifact_type: ArtifactType, content: bytes) -> Path:
        raise NotImplementedError

    def load(self, task_id: str, artifact_type: ArtifactType) -> bytes:
        raise NotImplementedError

    def exists(self, task_id: str, artifact_type: ArtifactType) -> bool:
        raise NotImplementedError

    def verify(self, task_id: str, artifact_type: ArtifactType) -> bool:
        raise NotImplementedError

