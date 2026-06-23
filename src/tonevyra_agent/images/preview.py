"""1024px long-edge sRGB JPEG preview generation."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import UUID

from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError
from sqlalchemy.orm import Session

from tonevyra_agent.core.config import Settings, get_settings
from tonevyra_agent.core.enums import ArtifactType, ErrorCode, Stage
from tonevyra_agent.core.errors import TonevyraError
from tonevyra_agent.images.raw_preview import extract_largest_embedded_jpeg, is_raw_source
from tonevyra_agent.storage.artifacts import ArtifactRef, ArtifactStorage


@dataclass(frozen=True)
class PreviewBytes:
    data: bytes
    width: int
    height: int
    format: str
    mode: str
    color_space: str
    long_edge: int


@dataclass(frozen=True)
class PreviewArtifactResult:
    artifact: ArtifactRef
    width: int
    height: int
    long_edge: int
    format: str
    mode: str
    color_space: str

    def summary(self) -> dict[str, Any]:
        return {
            "artifact_id": str(self.artifact.artifact_id),
            "artifact_type": self.artifact.artifact_type,
            "artifact_path": self.artifact.relative_path,
            "sha256": self.artifact.sha256,
            "size_bytes": self.artifact.size_bytes,
            "width": self.width,
            "height": self.height,
            "long_edge": self.long_edge,
            "format": self.format,
            "mode": self.mode,
            "color_space": self.color_space,
        }


def create_preview_bytes(source_path: Path, *, max_long_edge: int = 1024) -> PreviewBytes:
    """Create JPEG bytes for model input without exposing the original image."""

    if max_long_edge < 1:
        raise ValueError("max_long_edge must be positive")

    path = source_path.resolve()
    try:
        with _open_preview_source(path) as image:
            data, width, height = _render_preview_jpeg(image, max_long_edge=max_long_edge)
    except (OSError, UnidentifiedImageError) as exc:
        raise TonevyraError(
            code=ErrorCode.PREVIEW_GENERATION_FAILED,
            message=f"Unable to create preview from image: {path}",
            failed_stage=Stage.PREVIEW.value,
        ) from exc

    return PreviewBytes(
        data=data,
        width=width,
        height=height,
        format="JPEG",
        mode="RGB",
        color_space="sRGB",
        long_edge=max(width, height),
    )


def _open_preview_source(path: Path) -> Image.Image:
    try:
        return Image.open(path)
    except (OSError, UnidentifiedImageError):
        if not is_raw_source(path):
            raise
        embedded = extract_largest_embedded_jpeg(path)
        if embedded is None:
            raise
        return Image.open(BytesIO(embedded))


def _render_preview_jpeg(image: Image.Image, *, max_long_edge: int) -> tuple[bytes, int, int]:
    image = ImageOps.exif_transpose(image)
    image = _to_srgb_rgb(image)
    image.thumbnail((max_long_edge, max_long_edge), Image.Resampling.LANCZOS)

    buffer = BytesIO()
    save_kwargs: dict[str, Any] = {
        "format": "JPEG",
        "quality": 92,
        "optimize": True,
    }
    icc_profile = _srgb_profile_bytes()
    if icc_profile is not None:
        save_kwargs["icc_profile"] = icc_profile
    image.save(buffer, **save_kwargs)
    data = buffer.getvalue()
    width, height = image.size
    return data, width, height


def create_preview_artifact(
    session: Session,
    *,
    task_id: UUID,
    source_path: Path,
    settings: Settings | None = None,
    storage: ArtifactStorage | None = None,
) -> PreviewArtifactResult:
    config = settings or get_settings()
    artifact_storage = storage or ArtifactStorage(config)
    preview = create_preview_bytes(source_path, max_long_edge=config.preview_long_edge)
    artifact = artifact_storage.save_bytes(
        session,
        task_id=task_id,
        artifact_type=ArtifactType.PREVIEW_JPEG,
        name="preview_1024.jpg",
        data=preview.data,
        mime_type="image/jpeg",
    )
    return PreviewArtifactResult(
        artifact=artifact,
        width=preview.width,
        height=preview.height,
        long_edge=preview.long_edge,
        format=preview.format,
        mode=preview.mode,
        color_space=preview.color_space,
    )


def _to_srgb_rgb(image: Image.Image) -> Image.Image:
    icc_profile = image.info.get("icc_profile")
    if icc_profile:
        try:
            source_profile = ImageCms.ImageCmsProfile(BytesIO(icc_profile))
            target_profile = ImageCms.createProfile("sRGB")
            converted = ImageCms.profileToProfile(image, source_profile, target_profile, outputMode="RGB")
            return converted
        except (OSError, ValueError, ImageCms.PyCMSError):
            pass
    return image.convert("RGB")


def _srgb_profile_bytes() -> bytes | None:
    try:
        profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))
        return profile.tobytes()
    except (OSError, AttributeError, ImageCms.PyCMSError):
        return None
