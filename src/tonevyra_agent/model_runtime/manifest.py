"""Local model manifest validation for T-022."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from tonevyra_agent.core.config import PROJECT_ROOT, Settings
from tonevyra_agent.core.enums import ErrorCode, Stage
from tonevyra_agent.core.errors import TonevyraError


class LocalModelManifest(BaseModel):
    """Allowlisted local model identity and integrity metadata."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["t022.local_model_manifest.v1"] = "t022.local_model_manifest.v1"
    model_id: str
    model_revision: str
    model_root: Path
    model_checksum: str
    runtime_backend: str
    remote_api_enabled: bool = False
    runtime_download_enabled: bool = False
    external_image_url_enabled: bool = False
    allowed_model_root: Path = Path("models")
    network_required: bool = False
    device: str = "cpu"
    dtype: str = "float32"
    quantization: str = "none"
    # checksum_mode controls how model integrity is verified.
    # "directory" (default): hash all files recursively — correct but slow for large models.
    # "index_file": hash only the named file inside model_root — fast for sharded models.
    checksum_mode: Literal["directory", "index_file"] = "directory"
    checksum_target_file: Optional[str] = None

    @field_validator("model_id", "model_revision", "runtime_backend")
    @classmethod
    def non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be empty")
        return value

    @field_validator("model_checksum")
    @classmethod
    def checksum_format(cls, value: str) -> str:
        if not value.startswith("sha256:") or len(value) <= len("sha256:"):
            raise ValueError("model_checksum must use sha256:<hex>")
        return value

    @model_validator(mode="after")
    def reject_remote_behavior(self) -> "LocalModelManifest":
        if self.remote_api_enabled or self.runtime_download_enabled or self.external_image_url_enabled or self.network_required:
            raise ValueError("local model manifest enables forbidden remote behavior")
        for path in (self.model_root, self.allowed_model_root):
            text = str(path).lower()
            if text.startswith(("http:", "https:")):
                raise ValueError("model paths must be local paths")
        return self

    @classmethod
    def load(cls, manifest_path: Path, settings: Settings) -> "LocalModelManifest":
        path = settings.project_path(manifest_path).resolve()
        if not path.exists():
            raise TonevyraError(
                code=ErrorCode.MODEL_LOAD_FAILED,
                message=f"Local model manifest is missing: {path}",
                failed_stage=Stage.VISION.value,
            )
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return cls.model_validate(payload)
        except TonevyraError:
            raise
        except Exception as exc:
            raise TonevyraError(
                code=ErrorCode.MODEL_LOAD_FAILED,
                message=f"Local model manifest is invalid: {path}",
                failed_stage=Stage.VISION.value,
            ) from exc

    def resolve_model_path(self, settings: Settings) -> Path:
        allowed_root = _resolve_project_path(settings.project_path(self.allowed_model_root)).resolve()
        model_path = _resolve_project_path(settings.project_path(self.model_root)).resolve()
        try:
            model_path.relative_to(allowed_root)
        except ValueError as exc:
            raise TonevyraError(
                code=ErrorCode.SECURITY_NETWORK_ACCESS_BLOCKED,
                message=f"Model path must stay under allowed root: {allowed_root}",
                failed_stage=Stage.VISION.value,
            ) from exc
        if not model_path.exists():
            raise TonevyraError(
                code=ErrorCode.MODEL_LOAD_FAILED,
                message=f"Local model path does not exist: {model_path}",
                failed_stage=Stage.VISION.value,
            )
        if model_path.is_symlink():
            raise TonevyraError(
                code=ErrorCode.SECURITY_NETWORK_ACCESS_BLOCKED,
                message=f"Model path must not be a symlink: {model_path}",
                failed_stage=Stage.VISION.value,
            )
        return model_path

    def verify_checksum(self, settings: Settings) -> Path:
        model_path = self.resolve_model_path(settings)
        if self.checksum_mode == "index_file":
            target_name = self.checksum_target_file or "model.safetensors.index.json"
            target = (model_path / target_name) if model_path.is_dir() else model_path
            if not target.exists():
                raise TonevyraError(
                    code=ErrorCode.MODEL_LOAD_FAILED,
                    message=f"Checksum target file does not exist: {target}",
                    failed_stage=Stage.VISION.value,
                )
            actual = f"sha256:{hashlib.sha256(target.read_bytes()).hexdigest()}"
        else:
            actual = f"sha256:{_hash_path(model_path)}"
        if actual != self.model_checksum:
            raise TonevyraError(
                code=ErrorCode.MODEL_LOAD_FAILED,
                message="Local model checksum does not match manifest.",
                failed_stage=Stage.VISION.value,
            )
        return model_path


def _resolve_project_path(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def _hash_path(path: Path) -> str:
    digest = hashlib.sha256()
    if path.is_file():
        digest.update(path.read_bytes())
        return digest.hexdigest()

    files = sorted(item for item in path.rglob("*") if item.is_file())
    for item in files:
        relative = item.relative_to(path).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        digest.update(item.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()
