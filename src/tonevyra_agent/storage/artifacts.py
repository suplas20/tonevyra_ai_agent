"""Durable local artifact storage with atomic writes and DB registration."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from tonevyra_agent.core.config import PROJECT_ROOT, Settings, get_settings
from tonevyra_agent.core.enums import ArtifactType
from tonevyra_agent.db.models import TaskArtifact
from tonevyra_agent.db.repositories import TaskArtifactRepository


@dataclass(frozen=True)
class ArtifactRef:
    artifact_id: UUID
    task_id: UUID
    artifact_type: str
    relative_path: str
    absolute_path: Path
    sha256: str
    size_bytes: int
    mime_type: str | None
    version: int


class ArtifactStorage:
    """Save and verify task artifacts under the configured artifact root."""

    def __init__(self, settings: Settings | None = None, repository: TaskArtifactRepository | None = None) -> None:
        self.settings = settings or get_settings()
        self.repository = repository or TaskArtifactRepository()
        self.root = self.settings.project_path(self.settings.artifact_dir).resolve()

    def save_json(
        self,
        session: Session,
        *,
        task_id: UUID,
        artifact_type: ArtifactType | str,
        name: str,
        data: Any,
        version: int = 1,
        mime_type: str = "application/json",
    ) -> ArtifactRef:
        payload = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
        return self.save_bytes(
            session,
            task_id=task_id,
            artifact_type=artifact_type,
            name=name,
            data=payload,
            version=version,
            mime_type=mime_type,
        )

    def save_text(
        self,
        session: Session,
        *,
        task_id: UUID,
        artifact_type: ArtifactType | str,
        name: str,
        text: str,
        version: int = 1,
        mime_type: str = "text/plain",
        encoding: str = "utf-8",
    ) -> ArtifactRef:
        return self.save_bytes(
            session,
            task_id=task_id,
            artifact_type=artifact_type,
            name=name,
            data=text.encode(encoding),
            version=version,
            mime_type=f"{mime_type}; charset={encoding}",
        )

    def save_bytes(
        self,
        session: Session,
        *,
        task_id: UUID,
        artifact_type: ArtifactType | str,
        name: str,
        data: bytes,
        version: int = 1,
        mime_type: str | None = "application/octet-stream",
    ) -> ArtifactRef:
        if version < 1:
            raise ValueError("artifact version must be >= 1")

        artifact_type_value = self._artifact_type_value(artifact_type)
        final_path = self._artifact_path(task_id, name)
        self._write_atomic(final_path, data)
        sha256 = calculate_sha256(final_path)
        size_bytes = final_path.stat().st_size
        relative_path = final_path.relative_to(PROJECT_ROOT).as_posix()

        row = self.repository.register_or_update(
            session,
            task_id=task_id,
            artifact_type=artifact_type_value,
            artifact_path=relative_path,
            sha256=sha256,
            size_bytes=size_bytes,
            mime_type=mime_type,
            version=version,
        )
        return self._to_ref(row)

    def load_json(self, artifact: ArtifactRef | TaskArtifact | str | Path) -> Any:
        return json.loads(self.load_text(artifact))

    def load_text(self, artifact: ArtifactRef | TaskArtifact | str | Path, encoding: str = "utf-8") -> str:
        path = self.resolve_path(artifact)
        return path.read_text(encoding=encoding)

    def exists(self, artifact: ArtifactRef | TaskArtifact | str | Path) -> bool:
        return self.resolve_path(artifact).exists()

    def verify_checksum(
        self,
        artifact: ArtifactRef | TaskArtifact | str | Path,
        expected_sha256: str | None = None,
    ) -> bool:
        path = self.resolve_path(artifact)
        if not path.exists():
            return False
        expected = expected_sha256 or getattr(artifact, "sha256", None)
        if expected is None:
            raise ValueError("expected_sha256 is required when artifact does not include sha256")
        return calculate_sha256(path) == expected

    def resolve_path(self, artifact: ArtifactRef | TaskArtifact | str | Path) -> Path:
        if isinstance(artifact, ArtifactRef):
            candidate = artifact.absolute_path
        elif isinstance(artifact, TaskArtifact):
            candidate = Path(artifact.artifact_path)
        else:
            candidate = Path(artifact)

        if candidate.is_absolute():
            resolved = candidate.resolve()
        else:
            project_candidate = (PROJECT_ROOT / candidate).resolve()
            resolved = project_candidate if self._is_under_root(project_candidate) else (self.root / candidate).resolve()

        if not self._is_under_root(resolved):
            raise ValueError(f"artifact path escapes artifact root: {resolved}")
        return resolved

    def _artifact_type_value(self, artifact_type: ArtifactType | str) -> str:
        if isinstance(artifact_type, ArtifactType):
            return artifact_type.value
        return ArtifactType(str(artifact_type)).value

    def _artifact_path(self, task_id: UUID, name: str) -> Path:
        name_path = Path(name)
        if name_path.is_absolute() or ".." in name_path.parts:
            raise ValueError(f"unsafe artifact name: {name}")
        final_path = (self.root / str(task_id) / name_path).resolve()
        if not self._is_under_root(final_path):
            raise ValueError(f"artifact path escapes artifact root: {final_path}")
        return final_path

    def _is_under_root(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self.root)
        except ValueError:
            return False
        return True

    def _write_atomic(self, final_path: Path, data: bytes) -> None:
        final_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                delete=False,
                dir=final_path.parent,
                prefix=f".{final_path.name}.",
                suffix=".tmp",
            ) as handle:
                temp_path = Path(handle.name)
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, final_path)
        except Exception:
            if temp_path and temp_path.exists():
                temp_path.unlink()
            raise

    def _to_ref(self, row: TaskArtifact) -> ArtifactRef:
        absolute_path = self.resolve_path(row)
        return ArtifactRef(
            artifact_id=row.id,
            task_id=row.task_id,
            artifact_type=row.artifact_type,
            relative_path=row.artifact_path,
            absolute_path=absolute_path,
            sha256=row.sha256 or "",
            size_bytes=row.size_bytes or 0,
            mime_type=row.mime_type,
            version=row.version,
        )


def calculate_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
