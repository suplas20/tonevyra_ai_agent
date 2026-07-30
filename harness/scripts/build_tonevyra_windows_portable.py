#!/usr/bin/env python3
"""Assemble the Windows Agent, loopback Planner Server, model, and helpers."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tomllib
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MODEL_RELATIVE = Path("models") / "qwen3-vl-4b-instruct"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--output-root", type=Path, default=Path("runtime/portable_windows"))
    parser.add_argument("--model-source", type=Path)
    parser.add_argument("--skip-model", action="store_true")
    args = parser.parse_args()

    root = args.project_root.resolve()
    version = _version(root)
    output_root = args.output_root if args.output_root.is_absolute() else root / args.output_root
    destination = output_root / f"TonevyraAI-Portable-{version}"

    agent_source = root / "runtime" / "windows_dist" / "TonevyraAI"
    planner_source = root / "runtime" / "windows_dist" / "TonevyraPlannerServer"
    _require_file(agent_source / "TonevyraAI.exe")
    _require_file(planner_source / "TonevyraPlannerServer.exe")

    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)

    shutil.copytree(agent_source, destination / "Agent")
    shutil.copytree(planner_source, destination / "PlannerServer")
    shutil.copytree(root / "lightroom" / "TonevyraAI.lrplugin", destination / "lightroom" / "TonevyraAI.lrplugin")
    shutil.copytree(root / "resources", destination / "resources")
    shutil.copytree(root / "portable" / "windows" / "scripts", destination / "scripts")
    shutil.copy2(root / "portable" / "windows" / "Tonevyra.local.env.example", destination / ".env.example")
    shutil.copy2(root / "portable" / "windows" / "README_KO.md", destination / "README_KO.md")

    model_source: Path | None = None
    if not args.skip_model:
        model_source = _resolve_model_source(root, args.model_source)
        shutil.copytree(
            model_source,
            destination / MODEL_RELATIVE,
            ignore=shutil.ignore_patterns(".cache", ".git", "__pycache__"),
        )
        _write_portable_model_manifest(root, destination / MODEL_RELATIVE)

    for relative in (
        "runtime/input",
        "runtime/output/temp",
        "runtime/output/pass",
        "runtime/output/review_required",
        "runtime/output/failed",
        "runtime/artifacts",
        "runtime/previews",
        "runtime/bridge",
        "runtime/planner_server",
        "logs",
    ):
        (destination / relative).mkdir(parents=True, exist_ok=True)

    manifest = {
        "schema_version": "tonevyra.windows_portable.v1",
        "product": "Tonevyra AI",
        "version": version,
        "platform": "windows",
        "architecture": "x64",
        "python_runtime_bundled": True,
        "system_python_required": False,
        "planner_server_separate_process": True,
        "planner_bind_host": "127.0.0.1",
        "model_included": model_source is not None,
        "model_source": str(model_source) if model_source else None,
        "agent_executable": _file_record(destination / "Agent" / "TonevyraAI.exe", destination),
        "planner_executable": _file_record(
            destination / "PlannerServer" / "TonevyraPlannerServer.exe",
            destination,
        ),
        "model_index": (
            _file_record(destination / MODEL_RELATIVE / "model.safetensors.index.json", destination)
            if model_source
            else None
        ),
        "authenticode_signed": False,
        "release_ready": False,
        "release_blockers": [
            "WINDOWS_AUTHENTICODE_SIGNATURE_MISSING",
            "TARGET_PC_GPU_AND_LIGHTROOM_LIVE_VALIDATION_REQUIRED",
        ],
    }
    manifest_path = destination / "portable-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"OK: portable={destination}")
    print(f"OK: manifest={manifest_path}")
    print(f"OK: model_included={model_source is not None}")
    return 0


def _version(root: Path) -> str:
    payload = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    return str(payload["project"]["version"])


def _resolve_model_source(root: Path, override: Path | None) -> Path:
    if override is not None:
        source = override if override.is_absolute() else root / override
    else:
        manifest_path = root / MODEL_RELATIVE / "model_manifest.json"
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        configured = Path(str(payload["model_root"]))
        source = configured if configured.is_absolute() else root / configured
    source = source.resolve()
    _require_file(source / "model.safetensors.index.json")
    if not list(source.glob("*.safetensors")):
        raise SystemExit(f"model source has no safetensors weights: {source}")
    return source


def _write_portable_model_manifest(root: Path, destination: Path) -> None:
    template = json.loads((root / MODEL_RELATIVE / "model_manifest.json").read_text(encoding="utf-8"))
    template["model_root"] = MODEL_RELATIVE.as_posix()
    template["allowed_model_root"] = "models"
    template["remote_api_enabled"] = False
    template["runtime_download_enabled"] = False
    template["external_image_url_enabled"] = False
    template["network_required"] = False
    (destination / "model_manifest.json").write_text(
        json.dumps(template, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _file_record(path: Path, root: Path) -> dict[str, Any]:
    _require_file(path)
    return {
        "path": path.relative_to(root).as_posix(),
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_file(path: Path) -> None:
    if not path.is_file():
        raise SystemExit(f"required file missing: {path}")


if __name__ == "__main__":
    raise SystemExit(main())
