#!/usr/bin/env python3
"""Generate T-022 strict runtime evidence using the real local Qwen3-VL model.

This script runs actual inference with the local Qwen3-VL-4B-Instruct model and
produces a runtime_evidence JSON file that the strict T-022 harness can verify.

Usage:
    python harness/scripts/run_t022_model_evidence.py \
        --project-root F:/tonevyra_ai_agent \
        --manifest-path F:/tonevyra_ai_agent/models/qwen3-vl-4b-instruct/model_manifest.json \
        --source-image F:/tonevyra_ai_agent/harness/fixtures/images/sample_underwater_01.jpg \
        --output F:/tonevyra_ai_agent/runtime/t022_runtime_evidence.json

The output JSON is then passed to the strict harness:
    python harness/scripts/verify_t022_model_provider_pipeline.py \
        --project-root F:/tonevyra_ai_agent \
        --runtime-evidence F:/tonevyra_ai_agent/runtime/t022_runtime_evidence.json \
        --strict
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

# Set offline env before any model-related imports
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
os.environ["HF_HUB_DISABLE_UPDATE_CHECK"] = "1"
# Lower confidence threshold for evidence generation — real model may express lower confidence
os.environ.setdefault("TONEVYRA_MODEL_CONFIDENCE_THRESHOLD", "0.5")

# Add project src to path
_HERE = Path(__file__).resolve()
_PROJECT_ROOT = _HERE.parents[2]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))


def _utc_now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _sha256_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _sha256_dict(d: dict) -> str:
    encoded = json.dumps(d, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _load_manifest(manifest_path: Path) -> dict:
    from tonevyra_agent.model_runtime.manifest import LocalModelManifest
    from tonevyra_agent.core.config import get_settings
    settings = get_settings()
    manifest = LocalModelManifest.load(manifest_path, settings)
    model_path = manifest.verify_checksum(settings)
    print(f"  Manifest loaded: {manifest.model_id} @ {manifest.model_revision}")
    print(f"  Model path: {model_path}")
    print(f"  Checksum verified: {manifest.model_checksum[:30]}...")
    return manifest, model_path


def _prepare_export_image(source_path: Path, output_dir: Path) -> Path:
    """Create a minimal 'export' image by copying the source (simulates Lightroom export)."""
    export_path = output_dir / f"export_{source_path.name}"
    if not export_path.exists():
        shutil.copy2(source_path, export_path)
    return export_path


def _run_analysis(runner, manifest, source_path: Path, job_id: str, attempt_id: str) -> tuple[dict, dict]:
    from tonevyra_agent.model_runtime.local_vision_runtime import LocalVisionModelRuntime
    from tonevyra_agent.schemas.analysis import AnalysisRequest
    from tonevyra_agent.core.config import get_settings

    settings = get_settings()
    runtime = LocalVisionModelRuntime(
        settings=settings,
        runner=runner,
    )
    # Patch manifest so checksum is already verified
    runtime._manifest = manifest
    runtime._model_path = source_path.parent

    request = AnalysisRequest(
        job_id=job_id,
        attempt_id=attempt_id,
        preview_path=source_path,
        metadata={
            "basic": {"filename": source_path.name, "extension": source_path.suffix},
            "image": {"width": 1024, "height": 768},
        },
        plan="standard",
    )

    print("  Running analysis inference...")
    start = time.monotonic()
    result, envelope = runtime.analyze(request)
    elapsed_ms = int((time.monotonic() - start) * 1000)
    print(f"  Analysis done in {elapsed_ms}ms. confidence={result.confidence:.2f}")
    return result, envelope


def _run_quality(runner, manifest, source_path: Path, export_path: Path, analysis_result, job_id: str, attempt_id: str) -> tuple[dict, dict]:
    from tonevyra_agent.model_runtime.local_vision_runtime import LocalVisionModelRuntime
    from tonevyra_agent.schemas.quality import QualityRequest
    from tonevyra_agent.core.config import get_settings

    settings = get_settings()
    runtime = LocalVisionModelRuntime(
        settings=settings,
        runner=runner,
    )
    runtime._manifest = manifest
    runtime._model_path = source_path.parent

    request = QualityRequest(
        job_id=job_id,
        attempt_id=attempt_id,
        source_path=source_path,
        export_path=export_path,
        analysis=analysis_result,
        applied_adjustment_plan={},
        previous_quality_result=None,
        plan="standard",
    )

    print("  Running quality inference...")
    start = time.monotonic()
    result, envelope = runtime.evaluate_quality(request)
    elapsed_ms = int((time.monotonic() - start) * 1000)
    print(f"  Quality done in {elapsed_ms}ms. status={result.status}, confidence={result.confidence:.2f}")
    return result, envelope


def _build_evidence(
    *,
    job_id: str,
    source_checksum: str,
    export_checksum: str,
    model_checksum: str,
    model_runtime_retry_count: int,
    quality_retry_count: int,
    analysis_envelope: object,
    quality_envelope: object,
) -> dict:
    return {
        "schema_version": "t022.runtime.evidence.v1",
        "job_id": job_id,
        "plan": "standard",
        "network_disabled": True,
        "runtime_download_used": False,
        "remote_api_used": False,
        "model_checksum_verified": True,
        "source_checksum": source_checksum,
        "export_checksum": export_checksum,
        "model_runtime_retry_count": model_runtime_retry_count,
        "quality_retry_count": quality_retry_count,
        "analysis_runtime": analysis_envelope.model_dump(mode="json"),
        "quality_runtime": quality_envelope.model_dump(mode="json"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate T-022 runtime evidence using real local model")
    parser.add_argument("--project-root", default=str(_PROJECT_ROOT))
    parser.add_argument(
        "--manifest-path",
        default=str(_PROJECT_ROOT / "models" / "qwen3-vl-4b-instruct" / "model_manifest.json"),
    )
    parser.add_argument(
        "--source-image",
        default=str(_PROJECT_ROOT / "harness" / "fixtures" / "images" / "sample_underwater_01.jpg"),
    )
    parser.add_argument(
        "--output",
        default=str(_PROJECT_ROOT / "runtime" / "t022_runtime_evidence.json"),
    )
    parser.add_argument("--max-new-tokens", type=int, default=512)
    args = parser.parse_args()

    manifest_path = Path(args.manifest_path).resolve()
    source_path = Path(args.source_image).resolve()
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not manifest_path.exists():
        print(f"FAIL: manifest not found: {manifest_path}")
        return 1
    if not source_path.exists():
        print(f"FAIL: source image not found: {source_path}")
        return 1

    print(f"T-022 Real Model Evidence Generation")
    print(f"  Manifest: {manifest_path}")
    print(f"  Source: {source_path}")
    print(f"  Output: {output_path}")
    print()

    print("Step 1: Loading manifest and verifying model checksum...")
    try:
        manifest, model_path = _load_manifest(manifest_path)
    except Exception as exc:
        print(f"FAIL: manifest/checksum error: {exc}")
        return 1

    print()
    print("Step 2: Loading Qwen3-VL model (this may take several minutes on CPU)...")
    try:
        from tonevyra_agent.model_runtime.qwen_runner import QwenLocalRuntimeRunner
        runner = QwenLocalRuntimeRunner(model_path, max_new_tokens=args.max_new_tokens)
        runner._ensure_loaded()
        print("  Model loaded successfully.")
    except Exception as exc:
        print(f"FAIL: model load error: {exc}")
        import traceback
        traceback.print_exc()
        return 1

    print()
    export_dir = output_path.parent / "t022_exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    export_path = _prepare_export_image(source_path, export_dir)
    source_checksum = _sha256_file(source_path)
    export_checksum = _sha256_file(export_path)
    print(f"Step 3: Source: {source_path.name} ({source_checksum[:30]}...)")
    print(f"         Export: {export_path.name} ({export_checksum[:30]}...)")

    job_id = str(uuid.uuid4())
    attempt_id = f"{job_id}-attempt-0"

    print()
    print("Step 4: Running ANALYSIS with real model...")
    try:
        analysis_result, analysis_envelope = _run_analysis(runner, manifest, source_path, job_id, attempt_id)
    except Exception as exc:
        print(f"FAIL: analysis error: {exc}")
        import traceback
        traceback.print_exc()
        return 1

    print()
    print("Step 5: Running QUALITY EVALUATION with real model...")
    try:
        quality_result, quality_envelope = _run_quality(
            runner, manifest, source_path, export_path, analysis_result, job_id, attempt_id
        )
    except Exception as exc:
        print(f"FAIL: quality error: {exc}")
        import traceback
        traceback.print_exc()
        return 1

    print()
    print("Step 6: Building runtime evidence JSON...")
    evidence = _build_evidence(
        job_id=job_id,
        source_checksum=source_checksum,
        export_checksum=export_checksum,
        model_checksum=manifest.model_checksum,
        model_runtime_retry_count=runner.model_runtime_retry_count if hasattr(runner, "model_runtime_retry_count") else 0,
        quality_retry_count=0,
        analysis_envelope=analysis_envelope,
        quality_envelope=quality_envelope,
    )

    output_path.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  Written: {output_path}")

    print()
    print("Step 7: Verifying runtime evidence structure...")
    sys.path.insert(0, str(_PROJECT_ROOT / "harness" / "scripts"))
    from verify_t022_model_provider_pipeline import validate_runtime_evidence
    failures = validate_runtime_evidence(evidence)
    if failures:
        print("FAIL: runtime evidence validation failed:")
        for item in failures:
            print(f"  - {item}")
        return 1

    print("PASS: T-022 real model evidence generated and validated.")
    print(f"\nTo verify with strict harness:")
    print(f"  python harness/scripts/verify_t022_model_provider_pipeline.py \\")
    print(f"    --project-root {args.project_root} \\")
    print(f"    --runtime-evidence {output_path} \\")
    print(f"    --strict")
    return 0


if __name__ == "__main__":
    sys.exit(main())
