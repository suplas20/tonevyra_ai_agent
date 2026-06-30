"""T-030 watcher exclusion and recursion-safety policy."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from tonevyra_agent.agent.watcher import parse_supported_extensions
from tonevyra_agent.core.config import Settings, get_settings
from tonevyra_agent.watcher.file_identity import normalize_path


class ExclusionDecision(StrEnum):
    CANDIDATE = "CANDIDATE"
    IGNORE_TEMPORARY = "IGNORE_TEMPORARY"
    IGNORE_EXCLUDED = "IGNORE_EXCLUDED"
    SKIP_UNSUPPORTED = "SKIP_UNSUPPORTED"


TEMP_SUFFIXES = {".tmp", ".part", ".crdownload", ".xmp", ".lrcat", ".lrprev"}
IGNORED_NAMES = {".ds_store"}


@dataclass(frozen=True)
class WatchExclusionPolicy:
    settings: Settings | None = None

    def classify(self, path: Path) -> ExclusionDecision:
        settings = self.settings or get_settings()
        name = path.name.lower()
        suffix = path.suffix.lower()

        if name in IGNORED_NAMES or name.startswith(".") or name.startswith("._"):
            return ExclusionDecision.IGNORE_TEMPORARY
        if suffix in TEMP_SUFFIXES:
            return ExclusionDecision.IGNORE_TEMPORARY
        if _is_internal_path(path, settings):
            return ExclusionDecision.IGNORE_EXCLUDED
        if suffix not in parse_supported_extensions(settings.supported_extensions):
            return ExclusionDecision.SKIP_UNSUPPORTED
        return ExclusionDecision.CANDIDATE


def input_output_recursion_risk(settings: Settings | None = None) -> bool:
    config = settings or get_settings()
    input_path = normalize_path(config.project_path(config.input_dir))
    internal = [
        normalize_path(config.project_path(config.output_dir)),
        normalize_path(config.project_path(config.runtime_dir)),
        normalize_path(config.project_path(config.artifact_dir)),
        normalize_path(config.project_path(config.preview_dir)),
        normalize_path(config.project_path(config.bridge_dir)),
    ]
    return any(other.startswith(input_path) or input_path.startswith(other) for other in internal)


def _is_internal_path(path: Path, settings: Settings) -> bool:
    normalized = normalize_path(path)
    internal_roots = [
        settings.project_path(settings.output_dir),
        settings.project_path(settings.runtime_dir),
        settings.project_path(settings.artifact_dir),
        settings.project_path(settings.preview_dir),
        settings.project_path(settings.bridge_dir),
        settings.project_path(settings.log_dir),
    ]
    for root in internal_roots:
        root_norm = normalize_path(root)
        if normalized == root_norm or normalized.startswith(root_norm + "\\"):
            return True
    return False
