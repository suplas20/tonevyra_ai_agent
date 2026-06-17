"""Configuration for the local agent."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TONEVYRA_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://tonevyra_app:tonevyra_app@localhost:5432/tonevyra_agent"
    runtime_dir: Path = Field(default=PROJECT_ROOT / "runtime")
    input_dir: Path = Field(default=PROJECT_ROOT / "runtime" / "input")
    output_dir: Path = Field(default=PROJECT_ROOT / "runtime" / "output")
    artifact_dir: Path = Field(default=PROJECT_ROOT / "runtime" / "artifacts")
    preview_dir: Path = Field(default=PROJECT_ROOT / "runtime" / "previews")
    bridge_dir: Path = Field(default=PROJECT_ROOT / "runtime" / "bridge")
    log_dir: Path = Field(default=PROJECT_ROOT / "logs")
    models_dir: Path = Field(default=PROJECT_ROOT / "models")
    vision_backend: str = "mock"
    lightroom_backend: str = "file"
    model_offline: bool = True
    worker_concurrency: int = 1
    quality_pass_threshold: int = 85
    quality_review_threshold: int = 70
    file_stable_checks: int = 3
    file_stable_interval_seconds: float = 1.0
    lightroom_response_timeout_seconds: int = 300


@lru_cache
def get_settings() -> Settings:
    return Settings()
