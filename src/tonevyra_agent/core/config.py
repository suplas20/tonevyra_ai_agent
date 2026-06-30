"""Configuration for Tonevyra AI Agent."""

from functools import lru_cache
import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(os.environ.get("TONEVYRA_PROJECT_ROOT", Path(__file__).resolve().parents[3])).resolve()

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
    calibration_recipe_dir: Path = Field(default=PROJECT_ROOT / "runtime" / "calibration" / "recipes")
    preview_dir: Path = Field(default=PROJECT_ROOT / "runtime" / "previews")
    bridge_dir: Path = Field(default=PROJECT_ROOT / "runtime" / "bridge")
    log_dir: Path = Field(default=PROJECT_ROOT / "logs")
    models_dir: Path = Field(default=PROJECT_ROOT / "models")
    external_models_dir: Path | None = None
    vision_backend: str = "mock"
    vision_mock_fixture: Path = Field(default=PROJECT_ROOT / "harness" / "fixtures" / "vision" / "valid_underwater.json")
    qwen_model_path: Path = Field(default=PROJECT_ROOT / "models" / "qwen2.5-vl-3b-instruct-4bit")
    qwen_model_name: str = "Qwen2.5-VL-3B-Instruct-4bit"
    qwen_model_revision: str = "local"
    qwen_model_sha256: str | None = None
    qwen3_model_path: Path = Field(default=Path("D:/Tonevyra/models/Qwen3-VL-4B-Instruct"))
    qwen3_model_name: str = "Qwen3-VL-4B-Instruct"
    qwen3_model_revision: str = "local-2025-06"
    qwen3_model_sha256: str | None = None
    qwen3_manifest_path: Path = Field(default=PROJECT_ROOT / "models" / "qwen3-vl-4b-instruct" / "model_manifest.json")
    qwen_max_new_tokens: int = 768
    model_manifest_path: Path = Field(default=PROJECT_ROOT / "models" / "qwen3-vl-4b-instruct" / "model_manifest.json")
    model_confidence_threshold: float = 0.6
    model_runtime_version: str = "1.0.0"
    vision_review_confidence_threshold: float = 0.7
    planner_review_confidence_threshold: float = 0.7
    # Correction Planner selection. "legacy" keeps the original rule mapping.
    # "target_based" enables the measurement-driven target planner. Default stays
    # legacy so existing pipelines are unchanged until explicitly opted in.
    planner_mode: str = "legacy"
    # Nominal as-shot temperature (Kelvin) used to convert the planner's relative
    # temperature_delta into an ABSOLUTE Lightroom temperature in the apply
    # request. Sending an absolute temperature keeps reprocessing/retries
    # idempotent; the plugin's relative-delta path reads the photo's current
    # temperature and would otherwise accumulate the delta on every run.
    nominal_as_shot_temperature: float = 6500.0
    # Underwater color calibration OWNED BY THE PLANNER (not hardcoded magic
    # numbers). Underwater red is absorbed and is recovered with a magenta TINT
    # that is PROPORTIONAL to the white-balance warming, not with HSL red. Warming
    # scales with the measured blue cast but stays cool. Calibrated to a Lightroom
    # reference: temperature_delta 1500 (=> ~8000K) <-> tint +64.
    underwater_temp_per_cast: float = 32.0
    underwater_temp_delta_min: float = 800.0
    underwater_temp_delta_max: float = 1800.0
    underwater_tint_per_temp_delta: float = 64.0 / 1500.0
    underwater_tint_max: float = 90.0
    underwater_red_saturation: float = 55.0
    underwater_red_luminance: float = 42.0
    lightroom_backend: str = "fake"
    # When enabled, the real Lightroom pipeline sends planner-owned local
    # adjustment plans through the T-029 native mask bridge after global Develop
    # settings are applied and before final export. If the plugin reports skip or
    # times out, the worker continues with the already-strong global fallback.
    lightroom_native_mask_execution_enabled: bool = False
    lightroom_mask_response_timeout_seconds: int = 60
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
    # Scene-aware quality tolerances. Underwater scenes naturally retain higher
    # chroma and a blue-green channel balance; scoring them with neutral-scene
    # ideals over-penalizes correctly-corrected, colorful results (and rewards the
    # washed-out / near-monochrome look). These are configurable and reversible.
    quality_saturation_ideal: float = 0.34
    # Underwater scenes are blue-green dominant with the red channel absorbed by
    # water, so a vibrant, clean underwater result legitimately has high
    # saturation, an imbalanced channel spread, and a residual cool cast. The
    # underwater tolerances are therefore much more lenient than neutral scenes.
    quality_underwater_saturation_ideal: float = 0.74
    quality_color_spread_scale: float = 90.0
    quality_underwater_color_spread_scale: float = 480.0
    quality_cast_allowance: float = 12.0
    quality_underwater_cast_allowance: float = 85.0
    supported_extensions: str = ".cr3,.cr2,.nef,.arw,.dng,.jpg,.jpeg"
    file_stable_checks: int = 3
    file_stable_interval_seconds: float = 1.0
    file_stable_timeout_seconds: float = 120.0
    watch_enabled: bool = True
    watch_recursive: bool = False
    watch_stability_interval_seconds: float = 2.0
    watch_required_stable_samples: int = 3
    watch_stability_timeout_seconds: float = 300.0
    tray_enabled: bool = True
    autostart_enabled: bool = False
    worker_restart_limit: int = 3
    worker_heartbeat_timeout_seconds: float = 20.0
    worker_restart_window_seconds: float = 300.0
    graceful_shutdown_timeout_seconds: float = 20.0
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
            bridge_dir / "lightroom_mask_requests",
            bridge_dir / "lightroom_mask_processing",
            bridge_dir / "lightroom_mask_processed",
            bridge_dir / "lightroom_mask_results",
            bridge_dir / "lightroom_mask_errors",
            self.project_path(self.log_dir),
            self.project_path(self.models_dir),
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
