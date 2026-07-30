from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from _common import PROJECT_ROOT

SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tonevyra_agent.core.config import Settings
from tonevyra_agent.core.enums import ErrorCode
from tonevyra_agent.core.errors import TonevyraError
from tonevyra_agent.vision.model import create_vision_backend

REQUIRED_OFFLINE_ENV = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "HF_HUB_DISABLE_TELEMETRY": "1",
    "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1",
    "HF_HUB_DISABLE_UPDATE_CHECK": "1",
}

STATIC_BANNED_PATTERNS = [
    (re.compile(r"trust_remote_code\s*=\s*True"), "trust_remote_code=True is prohibited"),
    (re.compile(r"\b(snapshot_download|hf_hub_download)\s*\("), "runtime model download helper found"),
    (re.compile(r"\brequests\.(get|post|put|delete|patch)\s*\("), "requests network call found"),
    (re.compile(r"\bhttpx\.(get|post|put|delete|patch)\s*\("), "httpx network call found"),
    (re.compile(r"\baiohttp\.ClientSession\s*\("), "aiohttp network client found"),
    (re.compile(r"\burllib\.request\.urlopen\s*\("), "urllib network call found"),
    (re.compile(r"\b(openai|anthropic)\."), "remote AI API client usage found"),
    (re.compile(r"Image\.open\s*\(\s*[\"']https?://"), "external URL image loading found"),
]

FROM_PRETRAINED_PATTERN = re.compile(r"\.from_pretrained\s*\((?P<args>.*?)\)", re.DOTALL)
HTTP_LITERAL_PATTERN = re.compile(r"[\"']https?://")
SCAN_DIRS = ("src", "harness", "tests")
EXCLUDE_PARTS = {".venv", "__pycache__", ".git", "runtime", "logs", "agent-transcripts"}
EXCLUDE_FILES = {
    Path("harness/scripts/run_security_check.py"),
    Path("harness/scripts/run_t032_planner_api_live_probe.py"),
    Path("harness/scripts/verify_t032_planner_api_separation.py"),
    Path("harness/prompts/02_security_harness_prompt.md"),
}
TEXT_SUFFIXES = {".py", ".md", ".toml", ".yaml", ".yml", ".json"}
JSON_SCHEMA_DRAFT_URL = "https://json-schema.org/draft/2020-12/schema"
TONEVYRA_SCHEMA_ID_PREFIX = "https://tonevyra.local/schemas/"


@dataclass(frozen=True)
class Finding:
    path: Path
    line_no: int
    message: str

    def render(self, root: Path) -> str:
        return f"{self.path.relative_to(root)}:{self.line_no}: {self.message}"


def should_scan(path: Path) -> bool:
    if any(part in EXCLUDE_PARTS for part in path.parts):
        return False
    try:
        relative = path.resolve().relative_to(PROJECT_ROOT)
    except ValueError:
        return False
    if relative in EXCLUDE_FILES:
        return False
    return path.suffix.lower() in TEXT_SUFFIXES


def _line_no(text: str, index: int) -> int:
    return text[:index].count("\n") + 1


def _scan_static(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for scan_dir in SCAN_DIRS:
        base = root / scan_dir
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or not should_scan(path):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for pattern, message in STATIC_BANNED_PATTERNS:
                for match in pattern.finditer(text):
                    findings.append(Finding(path=path, line_no=_line_no(text, match.start()), message=message))
            for match in FROM_PRETRAINED_PATTERN.finditer(text):
                if "local_files_only=True" not in re.sub(r"\s+", "", match.group("args")):
                    findings.append(
                        Finding(
                            path=path,
                            line_no=_line_no(text, match.start()),
                            message="from_pretrained must include local_files_only=True",
                        )
                    )
            for match in HTTP_LITERAL_PATTERN.finditer(text):
                if _allowed_http_literal(path, text, match.start()):
                    continue
                findings.append(Finding(path=path, line_no=_line_no(text, match.start()), message="external URL literal found"))
    return findings


def _allowed_http_literal(path: Path, text: str, index: int) -> bool:
    line_start = text.rfind("\n", 0, index) + 1
    line_end = text.find("\n", index)
    if line_end == -1:
        line_end = len(text)
    line = text[line_start:line_end]
    relative = path.resolve().relative_to(PROJECT_ROOT)
    if relative == Path("src/tonevyra_agent.egg-info/PKG-INFO"):
        return True
    if "sqlalche.me/e/" in line:
        return True
    if _is_json_schema_declaration(relative, line):
        return True
    if _is_negative_remote_fixture(relative, line):
        return True
    if _is_remote_detection_test_code(relative, line):
        return True
    if _is_approved_network_contract_literal(relative, line):
        return True
    return False


def _is_json_schema_declaration(relative: Path, line: str) -> bool:
    if JSON_SCHEMA_DRAFT_URL in line and ("$schema" in line or "schema" in line):
        return True
    return (
        relative.parts[:2] == ("harness", "schemas")
        and relative.name.endswith(".schema.json")
        and '"$id"' in line
        and TONEVYRA_SCHEMA_ID_PREFIX in line
    )


def _is_negative_remote_fixture(relative: Path, line: str) -> bool:
    return (
        relative == Path("harness/fixtures/t022_model_provider/invalid_remote_config.json")
        and '"model_root"' in line
        and "https://example.invalid/model" in line
    )


def _is_remote_detection_test_code(relative: Path, line: str) -> bool:
    return (
        relative == Path("harness/scripts/verify_t022_model_provider_pipeline.py")
        and "invalid_remote.get" in line
        and "model_root" in line
        and "startswith" in line
    )


def _is_approved_network_contract_literal(relative: Path, line: str) -> bool:
    """Allow only explicit T-032 Planner and T-033 installer network contracts."""

    planner_test_files = {
        Path("tests/test_t032_planner_api_contract.py"),
        Path("tests/test_local_planner_server.py"),
    }
    if relative in planner_test_files and (
        "planner.example.test" in line or "http://127.0.0.1:8000" in line
    ):
        return True

    postgres_fixture_files = {
        Path("harness/fixtures/t033_installer/invalid_postgresql_prerelease.json"),
        Path("harness/fixtures/t033_installer/valid_postgresql_resolution_macos.json"),
        Path("harness/fixtures/t033_installer/valid_postgresql_resolution_windows.json"),
        Path("tests/test_t033_installer_common.py"),
    }
    if relative in postgres_fixture_files and "postgresql" in line:
        return True
    if relative == Path("harness/scripts/build_tonevyra_windows_installer.py"):
        return "$PinnedPostgresUrl" in line and "get.enterprisedb.com/postgresql/" in line
    if relative == Path("harness/scripts/verify_t033_cross_platform_installer.py"):
        return "PostgreSQL URL must use HTTPS" in line and 'startswith("https://")' in line
    return False


def _check_env_contract(root: Path, *, strict_env: bool) -> list[str]:
    errors: list[str] = []
    env_example = root / ".env.example"
    harness_env = root / "harness" / "HARNESS_ENV.example"
    for path in (env_example, harness_env):
        if not path.exists():
            errors.append(f"{path.relative_to(root)} is missing")
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for name, value in REQUIRED_OFFLINE_ENV.items():
            if not re.search(rf"^{re.escape(name)}={re.escape(value)}\s*$", text, flags=re.MULTILINE):
                errors.append(f"{path.relative_to(root)} must contain {name}={value}")

    if strict_env:
        for name, value in REQUIRED_OFFLINE_ENV.items():
            if os.environ.get(name) != value:
                errors.append(f"current environment must set {name}={value}")
    return errors


def _check_runtime_settings() -> list[str]:
    settings = Settings()
    errors: list[str] = []
    vision_backend = settings.vision_backend.lower()
    if vision_backend == "mock":
        errors.append("active vision backend must be a real local backend, got mock")
    if vision_backend in {"qwen3vl", "qwen3-vl", "qwen3"}:
        model_path = settings.project_path(settings.qwen3_model_path).resolve()
    elif vision_backend in {"qwen", "qwen2.5-vl", "qwen25vl"}:
        model_path = settings.project_path(settings.qwen_model_path).resolve()
    elif vision_backend in {"module", "module-analysis", "t021_module"}:
        model_path = None
    else:
        errors.append(f"unsupported active vision backend: {settings.vision_backend}")
        model_path = None
    if model_path is not None and not model_path.exists():
        errors.append(f"active local model path is missing: {model_path}")

    manifest_path = settings.project_path(settings.model_manifest_path).resolve()
    if not manifest_path.exists():
        errors.append(f"active model manifest is missing: {manifest_path}")

    if settings.lightroom_backend.lower() != "lightroom":
        errors.append(f"active Lightroom backend must be lightroom, got {settings.lightroom_backend}")
    if not settings.model_offline:
        errors.append("TONEVYRA_MODEL_OFFLINE default must be true")
    if settings.worker_concurrency != 1:
        errors.append(f"worker concurrency must remain 1, got {settings.worker_concurrency}")
    models_dir = settings.project_path(settings.models_dir).resolve()
    project_root = PROJECT_ROOT.resolve()
    try:
        models_dir.relative_to(project_root)
    except ValueError:
        errors.append(f"models_dir must remain under project root: {models_dir}")
    return errors


def _check_backend_behavior(root: Path) -> list[str]:
    errors: list[str] = []
    try:
        create_vision_backend(
            Settings(
                vision_backend="qwen",
                model_offline=True,
                qwen_model_path=root / "models" / "missing-qwen-model",
            )
        )
    except TonevyraError as exc:
        if exc.code != ErrorCode.MODEL_LOAD_FAILED:
            errors.append(f"missing qwen model path should fail with MODEL_LOAD_FAILED, got {exc.code.value}")
    else:
        errors.append("qwen backend should require an existing local model path")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Run static security harness checks.")
    parser.add_argument("--root", default=str(PROJECT_ROOT))
    parser.add_argument("--strict-env", action="store_true", help="Require current process offline env vars to be set.")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    findings = _scan_static(root)
    env_errors = _check_env_contract(root, strict_env=args.strict_env)
    settings_errors = _check_runtime_settings()
    backend_errors = _check_backend_behavior(root)

    if findings or env_errors or settings_errors or backend_errors:
        print("Security harness failed:")
        for finding in findings:
            print("-", finding.render(root))
        for error in [*env_errors, *settings_errors, *backend_errors]:
            print("-", error)
        return 1

    print("OK static scan found no remote API, runtime download, unsafe model loading, or URL image loading")
    print("OK offline env contract is present in .env.example and harness/HARNESS_ENV.example")
    print(f"OK active runtime settings use {Settings().vision_backend} + Lightroom, offline mode, and worker_concurrency=1")
    print("OK qwen backend requires an existing local model path before any model load")
    print("Security harness passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
