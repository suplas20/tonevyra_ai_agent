#!/usr/bin/env python3
"""Verify that the active harness gate uses real local runtime evidence."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from _common import PROJECT_ROOT

SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tonevyra_agent.core.config import Settings


REAL_VISION_BACKENDS = {"qwen", "qwen2.5-vl", "qwen25vl", "qwen3vl", "qwen3-vl", "qwen3"}
MODULE_VISION_BACKENDS = {"module", "module-analysis", "t021_module"}


def _error(message: str, failures: list[str]) -> None:
    failures.append(message)


def _load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise AssertionError(f"invalid JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise AssertionError(f"JSON root must be an object: {path}")
    return value


def _check_settings(settings: Settings, *, allow_module_backend: bool = False) -> list[str]:
    failures: list[str] = []
    backend = settings.vision_backend.lower()
    if allow_module_backend and backend in MODULE_VISION_BACKENDS:
        model_path = None
    elif backend not in REAL_VISION_BACKENDS:
        _error(f"TONEVYRA_VISION_BACKEND must be a real local model backend, got {settings.vision_backend}", failures)
        model_path = None
    elif backend in {"qwen3vl", "qwen3-vl", "qwen3"}:
        model_path = settings.project_path(settings.qwen3_model_path).resolve()
    else:
        model_path = settings.project_path(settings.qwen_model_path).resolve()
    if model_path is not None and not model_path.exists():
        _error(f"local model path does not exist: {model_path}", failures)

    manifest_path = settings.project_path(settings.model_manifest_path).resolve()
    if not manifest_path.exists():
        _error(f"model manifest does not exist: {manifest_path}", failures)
    else:
        manifest = _load_json(manifest_path)
        for key in ("remote_api_enabled", "runtime_download_enabled", "external_image_url_enabled", "network_required"):
            if manifest.get(key) is not False:
                _error(f"model manifest must set {key}=false", failures)

    if settings.lightroom_backend.lower() != "lightroom":
        _error(f"TONEVYRA_LIGHTROOM_BACKEND must be lightroom, got {settings.lightroom_backend}", failures)
    if not settings.model_offline:
        _error("TONEVYRA_MODEL_OFFLINE must be true", failures)
    if settings.worker_concurrency != 1:
        _error(f"TONEVYRA_WORKER_CONCURRENCY must remain 1, got {settings.worker_concurrency}", failures)
    return failures


def _run(command: list[str]) -> int:
    return subprocess.run(command, cwd=PROJECT_ROOT).returncode


def _run_quiet(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=PROJECT_ROOT, text=True, capture_output=True)


def _validate_post_quality_moved_export(result_json: Path, final_output_file: Path) -> list[str]:
    failures: list[str] = []
    result = _load_json(result_json)
    final_path = final_output_file.resolve()
    source_path = Path(str(result.get("source_path", ""))).resolve()
    file_result = result.get("file_result") if isinstance(result.get("file_result"), dict) else {}
    expected_size = file_result.get("size_bytes")

    if result.get("status") != "exported":
        failures.append("post-quality moved export requires export result status=exported")
    if not final_path.exists():
        failures.append(f"post-quality moved export output does not exist: {final_path}")
        return failures
    size_bytes = final_path.stat().st_size
    if size_bytes <= 0:
        failures.append(f"post-quality moved export output is empty: {final_path}")
    if source_path == final_path:
        failures.append("post-quality moved export output must differ from source_path")
    if isinstance(expected_size, int) and expected_size != size_bytes:
        failures.append(f"post-quality moved export size mismatch: result={expected_size} final={size_bytes}")
    if str(result.get("export_path", "")) == str(final_path):
        failures.append("post-quality moved export fallback should only be used when export_path was moved")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify real local model + Lightroom harness gate.")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--apply-evidence", type=Path, help="Real Lightroom apply result/live evidence JSON")
    parser.add_argument("--export-result", type=Path, help="Real Lightroom export result JSON")
    parser.add_argument("--final-output-file", type=Path, help="Final PASS/REVIEW/FAILED output moved after quality gate")
    parser.add_argument("--allow-module-backend", action="store_true", help="Allow deterministic local module provider evidence")
    parser.add_argument("--require-lightroom-evidence", action="store_true")
    args = parser.parse_args()

    failures = _check_settings(Settings(), allow_module_backend=args.allow_module_backend)

    if args.apply_evidence:
        result = _run([sys.executable, "harness/scripts/verify_lightroom_live_test_evidence.py", "--evidence", str(args.apply_evidence)])
        if result != 0:
            failures.append(f"Lightroom apply live evidence failed validation: {args.apply_evidence}")
    elif args.require_lightroom_evidence:
        failures.append("--apply-evidence is required when --require-lightroom-evidence is set")

    if args.export_result:
        command = [
            sys.executable,
            "harness/scripts/verify_lightroom_export_adapter.py",
            "--project-root",
            str(args.project_root),
            "--plugin-dir",
            str(args.project_root / "lightroom" / "TonevyraAI.lrplugin"),
            "--result-json",
            str(args.export_result),
            "--require-output-file",
            "--strict",
        ]
        result = _run_quiet(command)
        if result.returncode != 0:
            if args.final_output_file:
                moved_failures = _validate_post_quality_moved_export(args.export_result, args.final_output_file)
                if moved_failures:
                    failures.append(f"Lightroom export live evidence failed validation: {args.export_result}")
                    failures.extend(moved_failures)
                    if result.stdout.strip():
                        failures.append(result.stdout.strip())
                    if result.stderr.strip():
                        failures.append(result.stderr.strip())
            else:
                failures.append(f"Lightroom export live evidence failed validation: {args.export_result}")
                if result.stdout.strip():
                    failures.append(result.stdout.strip())
                if result.stderr.strip():
                    failures.append(result.stderr.strip())
    elif args.require_lightroom_evidence:
        failures.append("--export-result is required when --require-lightroom-evidence is set")

    if failures:
        print("FAIL: live runtime gate")
        for failure in failures:
            print(f"- {failure}")
        return 1

    if args.allow_module_backend and Settings().vision_backend.lower() in MODULE_VISION_BACKENDS:
        print("PASS: active harness gate uses local module provider + Lightroom configuration")
    else:
        print("PASS: active harness gate uses real local model + Lightroom configuration")
    if args.apply_evidence:
        print(f"PASS: real Lightroom apply evidence validated: {args.apply_evidence}")
    if args.export_result:
        print(f"PASS: real Lightroom export evidence validated: {args.export_result}")
    if args.final_output_file:
        print(f"PASS: final moved Lightroom output validated: {args.final_output_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
