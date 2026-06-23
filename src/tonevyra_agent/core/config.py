"""Configuration for Tonevyra AI Agent."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]

REQUIRED_DB_TABLES: tuple[str, ...] = (
    "image_tasks",
    "task_artifacts",
    "task_events",
    "stage_results",
    "quality_results",
    "feedback_records",
    "learning_samples",
)
REQUIRED_DB_VIEWS: tuple[str, ...] = ("v_task_summary",)


class Settings(BaseSettings):
    """Runtime configuration loaded from TONEVYRA_* variables."""

    model_config = SettingsConfigDict(env_prefix="TONEVYRA_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://tonevyra_app:tonevyra_app@localhost:5432/tonevyra_agent"
    database_schema: str = "public"
    runtime_dir: Path = Field(default=PROJECT_ROOT / "runtime")
    input_dir: Path = Field(default=PROJECT_ROOT / "runtime" / "input")
    output_dir: Path = Field(default=PROJECT_ROOT / "runtime" / "output")
    artifact_dir: Path = Field(default=PROJECT_ROOT / "runtime" / "artifacts")
    preview_dir: Path = Field(default=PROJECT_ROOT / "runtime" / "previews")
    bridge_dir: Path = Field(default=PROJECT_ROOT / "runtime" / "bridge")
    log_dir: Path = Field(default=PROJECT_ROOT / "logs")
    models_dir: Path = Field(default=PROJECT_ROOT / "models")
    vision_backend: str = "mock"
    vision_mock_fixture: Path = Field(default=PROJECT_ROOT / "harness" / "fixtures" / "vision" / "valid_underwater.json")
    qwen_model_path: Path = Field(default=PROJECT_ROOT / "models" / "qwen2.5-vl-3b-instruct-4bit")
    qwen_model_name: str = "Qwen2.5-VL-3B-Instruct-4bit"
    qwen_model_revision: str = "local"
    qwen_model_sha256: str | None = None
    qwen3_model_path: Path = Field(default=PROJECT_ROOT / "models" / "qwen3-vl-4b-instruct-4bit")
    qwen3_model_name: str = "Qwen3-VL-4B-Instruct-4bit"
    qwen3_model_revision: str = "local"
    qwen3_model_sha256: str | None = None
    qwen_max_new_tokens: int = 768
    model_manifest_path: Path = Field(default=PROJECT_ROOT / "models" / "tonevyra-local-vision" / "model_manifest.json")
    model_confidence_threshold: float = 0.7
    model_runtime_version: str = "1.0.0"
    vision_review_confidence_threshold: float = 0.7
    planner_review_confidence_threshold: float = 0.7
    lightroom_backend: str = "fake"
    model_offline: bool = True
    worker_concurrency: int = 1
    quality_pass_threshold: int = 85
    quality_review_threshold: int = 70
    quality_exposure_weight: float = 0.20
    quality_color_weight: float = 0.30
    quality_sharpness_weight: float = 0.20
    quality_noise_weight: float = 0.10
    quality_saturation_weight: float = 0.10
    quality_underwater_cast_weight: float = 0.10
    supported_extensions: str = ".cr3,.cr2,.nef,.arw,.dng,.jpg,.jpeg"
    file_stable_checks: int = 3
    file_stable_interval_seconds: float = 1.0
    file_stable_timeout_seconds: float = 120.0
    preview_long_edge: int = 1024
    lightroom_response_timeout_seconds: int = 300

    def project_path(self, path: Path) -> Path:
        """Resolve relative configured paths from the project root."""

        return path if path.is_absolute() else PROJECT_ROOT / path

    def required_runtime_dirs(self) -> tuple[Path, ...]:
        """Directories that must exist before the MVP pipeline can run."""

        output_dir = self.project_path(self.output_dir)
        bridge_dir = self.project_path(self.bridge_dir)
        return (
            self.project_path(self.runtime_dir),
            self.project_path(self.input_dir),
            output_dir,
            output_dir / "temp",
            output_dir / "pass",
            output_dir / "review_required",
            output_dir / "failed",
            self.project_path(self.artifact_dir),
            self.project_path(self.preview_dir),
            bridge_dir,
            bridge_dir / "requests",
            bridge_dir / "processing",
            bridge_dir / "responses",
            bridge_dir / "errors",
            bridge_dir / "lightroom_apply_requests",
            bridge_dir / "lightroom_apply_processing",
            bridge_dir / "lightroom_apply_processed",
            bridge_dir / "lightroom_apply_results",
            bridge_dir / "lightroom_apply_errors",
            bridge_dir / "lightroom_live_evidence",
            bridge_dir / "lightroom_export_requests",
            bridge_dir / "lightroom_export_processing",
            bridge_dir / "lightroom_export_processed",
            bridge_dir / "lightroom_export_results",
            bridge_dir / "lightroom_export_errors",
            self.project_path(self.log_dir),
            self.project_path(self.models_dir),
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
