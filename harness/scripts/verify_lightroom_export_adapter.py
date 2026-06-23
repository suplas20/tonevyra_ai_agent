#!/usr/bin/env python3
"""Verify T-020 Lightroom Final Export Adapter contracts and evidence.

This harness validates T-020 documents, fixtures, optional plugin source, and
optional real export result/output evidence. It does not launch Lightroom.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Iterable

REQUIRED_REQUEST_FIELDS = {
    "schema_version",
    "request_id",
    "task_id",
    "apply_request_id",
    "source_path",
    "export_path",
    "command",
    "export_settings",
    "created_at",
}

REQUIRED_RESULT_FIELDS = {
    "schema_version",
    "request_id",
    "task_id",
    "apply_request_id",
    "source_path",
    "export_path",
    "status",
    "export_settings",
    "lightroom_result",
    "file_result",
    "error_code",
    "message",
    "completed_at",
}

REQUIRED_EXPORT_SETTINGS = {"format", "quality", "color_space", "resize"}
SUPPORTED_SOURCE_EXTENSIONS = {".cr3", ".cr2", ".nef", ".arw", ".dng", ".jpg", ".jpeg"}
RAW_SOURCE_EXTENSIONS = {".cr3", ".cr2", ".nef", ".arw", ".dng"}

REQUIRED_PLUGIN_TERMS = [
    "lightroom_export_requests",
    "lightroom_export_results",
    "source_path",
    "export_path",
    "request_id",
    "task_id",
]

PROHIBITED_PATTERNS = [
    (re.compile(r"runtime[\\/]+input", re.IGNORECASE), "plugin must not watch or scan runtime/input"),
    (re.compile(r"watch(?:er|ing)?[_ -]?(?:folder|input|image)", re.IGNORECASE), "plugin must not own image folder watching"),
    (re.compile(r"getTargetPhoto\s*\(", re.IGNORECASE), "selected-photo targeting must not be the product path"),
    (re.compile(r"selected[_ -]?photo", re.IGNORECASE), "selected-photo product workflow is prohibited"),
    (re.compile(r"quality[_ -]?(?:score|gate)", re.IGNORECASE), "plugin must not compute quality scores"),
    (re.compile(r"model[_ -]?inference|vision[_ -]?model|qwen|onnx|torch", re.IGNORECASE), "plugin must not run models"),
    (re.compile(r"correction[_ -]?plan(?:ner)?", re.IGNORECASE), "plugin must not generate correction plans"),
    (re.compile(r"postgres|sqlalchemy|psycopg", re.IGNORECASE), "plugin must not access the operational database"),
]

IMPLEMENTATION_SUFFIXES = {".lua", ".json", ".txt"}


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise AssertionError(f"Invalid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise AssertionError(f"JSON root must be an object: {path}")
    return value


def assert_fields(data: dict, required: set[str], path: Path) -> None:
    missing = sorted(required - set(data))
    if missing:
        raise AssertionError(f"{path} missing required fields: {missing}")


def source_extension(data: dict) -> str:
    return Path(str(data.get("source_path") or "")).suffix.lower()


def validate_supported_source_path(data: dict, path: Path) -> list[str]:
    source = data.get("source_path")
    if not source:
        return [f"{path} source_path must be non-empty"]
    suffix = source_extension(data)
    if suffix not in SUPPORTED_SOURCE_EXTENSIONS:
        return [f"{path} source_path must use a supported photo extension, got {suffix!r}"]
    return []


def iter_implementation_files(path: Path) -> Iterable[Path]:
    if path.is_file():
        if path.suffix.lower() in IMPLEMENTATION_SUFFIXES:
            yield path
        return
    for item in path.rglob("*"):
        if item.is_file() and item.suffix.lower() in IMPLEMENTATION_SUFFIXES:
            yield item


def scan_plugin(plugin_dir: Path) -> list[str]:
    failures: list[str] = []
    texts: list[str] = []
    for file in iter_implementation_files(plugin_dir):
        try:
            text = file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        texts.append(text)
        for pattern, reason in PROHIBITED_PATTERNS:
            if pattern.search(text):
                failures.append(f"{file}: {reason} ({pattern.pattern})")

    combined = "\n".join(texts).lower()
    missing = [term for term in REQUIRED_PLUGIN_TERMS if term.lower() not in combined]
    if missing:
        failures.append(f"Plugin appears not to implement required export adapter terms: {missing}")

    has_export_api_hint = any(
        token in combined
        for token in ("lrexportsession", "rendition", "export session", "export_completed")
    )
    if not has_export_api_hint:
        failures.append("Plugin source has no recognizable Lightroom export-session/rendition implementation hint")

    manual_terms = ("process pending export request", "export corrected image")
    if any(term in combined for term in manual_terms) and "diagnostic" not in combined and "auto_bridge" not in combined:
        failures.append("Manual export action appears to be the product path; automatic bridge processing evidence is required")

    return failures


def validate_request(data: dict, path: Path) -> list[str]:
    failures: list[str] = []
    try:
        assert_fields(data, REQUIRED_REQUEST_FIELDS, path)
    except AssertionError as exc:
        return [str(exc)]

    if data.get("command") != "EXPORT_CORRECTED_IMAGE":
        failures.append(f"{path} command must be EXPORT_CORRECTED_IMAGE")
    source = data.get("source_path")
    export = data.get("export_path")
    if not source or not export:
        failures.append(f"{path} source_path and export_path must be non-empty")
    elif Path(str(source)) == Path(str(export)):
        failures.append(f"{path} export_path must not equal source_path")
    failures.extend(validate_supported_source_path(data, path))
    if source_extension(data) not in RAW_SOURCE_EXTENSIONS:
        failures.append(f"{path} must use a RAW source extension to prevent JPG-only export adapter assumptions")

    settings = data.get("export_settings")
    if not isinstance(settings, dict):
        failures.append(f"{path} export_settings must be an object")
    else:
        missing = sorted(REQUIRED_EXPORT_SETTINGS - set(settings))
        if missing:
            failures.append(f"{path} export_settings missing: {missing}")
        if settings.get("format") != "JPEG":
            failures.append(f"{path} MVP format must be JPEG")
        quality = settings.get("quality")
        if not isinstance(quality, int) or not 1 <= quality <= 100:
            failures.append(f"{path} quality must be an integer from 1 to 100")
        if settings.get("color_space") != "sRGB":
            failures.append(f"{path} MVP color_space must be sRGB")
        if settings.get("resize") is not False:
            failures.append(f"{path} MVP resize must be false")
        if settings.get("overwrite") is not False:
            failures.append(f"{path} overwrite must be false")
    return failures


def validate_result(data: dict, path: Path, *, require_output_file: bool) -> list[str]:
    failures: list[str] = []
    try:
        assert_fields(data, REQUIRED_RESULT_FIELDS, path)
    except AssertionError as exc:
        return [str(exc)]

    status = data.get("status")
    if status not in {"exported", "failed"}:
        failures.append(f"{path} status must be exported or failed, got {status!r}")

    source = data.get("source_path")
    export = data.get("export_path")
    if source and export and Path(str(source)) == Path(str(export)):
        failures.append(f"{path} export_path must not equal source_path")
    failures.extend(validate_supported_source_path(data, path))
    if source_extension(data) not in RAW_SOURCE_EXTENSIONS:
        failures.append(f"{path} must use a RAW source extension to prove RAW source to JPEG export behavior")

    lr = data.get("lightroom_result")
    fr = data.get("file_result")
    if not isinstance(lr, dict):
        failures.append(f"{path} lightroom_result must be an object")
        lr = {}
    if not isinstance(fr, dict):
        failures.append(f"{path} file_result must be an object")
        fr = {}

    if status == "exported":
        for field in ("plugin_loaded", "worker_running", "source_photo_found", "export_started", "export_completed"):
            if lr.get(field) is not True:
                failures.append(f"{path} exported result requires lightroom_result.{field}=true")
        if fr.get("exists") is not True:
            failures.append(f"{path} exported result requires file_result.exists=true")
        size = fr.get("size_bytes")
        if not isinstance(size, int) or size <= 0:
            failures.append(f"{path} exported result requires file_result.size_bytes > 0")
        if data.get("error_code") not in (None, ""):
            failures.append(f"{path} exported result must not contain an error_code")
        if require_output_file:
            output = Path(str(export))
            if not output.exists():
                failures.append(f"Output file does not exist: {output}")
            elif not output.is_file() or output.stat().st_size <= 0:
                failures.append(f"Output file is missing or empty: {output}")
    else:
        if not data.get("error_code"):
            failures.append(f"{path} failed result must contain error_code")

    return failures


def verify_fixtures(project_root: Path) -> list[str]:
    failures: list[str] = []
    root = project_root / "harness" / "fixtures" / "lightroom_export_adapter"
    required = {
        "valid_export_request.json",
        "valid_export_result.json",
        "failed_export_result.json",
        "invalid_missing_export_path_request.json",
    }
    if not root.exists():
        return [f"Missing fixture directory: {root}"]
    missing = sorted(name for name in required if not (root / name).exists())
    if missing:
        return [f"Missing T-020 fixtures: {missing}"]

    try:
        failures.extend(validate_request(load_json(root / "valid_export_request.json"), root / "valid_export_request.json"))
        failures.extend(validate_result(load_json(root / "valid_export_result.json"), root / "valid_export_result.json", require_output_file=False))
        failures.extend(validate_result(load_json(root / "failed_export_result.json"), root / "failed_export_result.json", require_output_file=False))
        invalid = load_json(root / "invalid_missing_export_path_request.json")
        if invalid.get("export_path"):
            failures.append("invalid_missing_export_path_request.json must omit export_path")
    except AssertionError as exc:
        failures.append(str(exc))
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify T-020 Lightroom Final Export Adapter")
    parser.add_argument("--project-root", default=".", help=r"Project root, e.g. F:\tonevyra_ai_agent")
    parser.add_argument("--plugin-dir", default=None, help="Optional TonevyraAI.lrplugin directory")
    parser.add_argument("--result-json", default=None, help="Optional real export result JSON")
    parser.add_argument("--require-output-file", action="store_true", help="Require result export_path to exist and be non-empty")
    parser.add_argument("--strict", action="store_true", help="Require --plugin-dir and, with --require-output-file, --result-json")
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    failures: list[str] = []

    required_docs = [
        root / "harness" / "CONTRACT_LIGHTROOM_EXPORT_ADAPTER.md",
        root / "skills" / "lightroom-final-export-adapter" / "SKILL.md",
    ]
    for path in required_docs:
        if not path.exists():
            failures.append(f"Missing T-020 file: {path}")

    # T-019 preservation is a hard prerequisite.
    t019_required = [
        root / "harness" / "CONTRACT_LIGHTROOM_APPLY_ADAPTER.md",
        root / "skills" / "lightroom-apply-adapter" / "SKILL.md",
        root / "harness" / "scripts" / "verify_lightroom_apply_adapter_role.py",
    ]
    for path in t019_required:
        if not path.exists():
            failures.append(f"T-019 preservation failure: missing {path}")

    failures.extend(verify_fixtures(root))

    if args.plugin_dir:
        plugin_dir = Path(args.plugin_dir).resolve()
        if not plugin_dir.exists():
            failures.append(f"Plugin directory does not exist: {plugin_dir}")
        else:
            failures.extend(scan_plugin(plugin_dir))
    elif args.strict:
        failures.append("--plugin-dir is required in --strict mode")

    if args.result_json:
        result_path = Path(args.result_json).resolve()
        if not result_path.exists():
            failures.append(f"Result JSON does not exist: {result_path}")
        else:
            try:
                failures.extend(validate_result(load_json(result_path), result_path, require_output_file=args.require_output_file))
            except AssertionError as exc:
                failures.append(str(exc))
    elif args.require_output_file or (args.strict and args.require_output_file):
        failures.append("--result-json is required when --require-output-file is used")

    if failures:
        print("FAIL: Lightroom Final Export Adapter verification failed")
        for item in failures:
            print(f" - {item}")
        return 1

    print("PASS: T-020 contract, skill, fixtures, T-019 preservation, and optional plugin/live evidence checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
