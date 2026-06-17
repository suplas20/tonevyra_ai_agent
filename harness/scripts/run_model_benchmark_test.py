from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tonevyra_agent.core.config import Settings
from tonevyra_agent.vision.benchmark import run_model_benchmark


RUNTIME_DIR = PROJECT_ROOT / "runtime" / "harness" / "benchmark_t018"
QWEN25_DIR = RUNTIME_DIR / "models" / "qwen2.5-vl-3b-instruct-4bit"
QWEN3_DIR = RUNTIME_DIR / "models" / "qwen3-vl-4b-instruct-4bit"
REQUIRED_METRICS = {
    "inference_time",
    "peak_memory",
    "json_validity",
    "quality_impact",
    "error_rate",
    "lightroom_simultaneous_operation_stability",
    "10_photo_stability",
    "100_photo_stability",
}


class FakeBenchmarkRuntime:
    def __init__(self, candidate_id: str) -> None:
        self.candidate_id = candidate_id

    def generate(self, *, preview_path: Path, metadata: dict[str, Any], prompt: str) -> dict[str, Any]:
        confidence = 0.83 if self.candidate_id == "qwen2_5_vl_3b_4bit" else 0.88
        return {
            "schema_version": "1.0",
            "model_backend": "qwen",
            "model_name": self.candidate_id,
            "scene_type": "underwater",
            "main_subject": "reef and diver",
            "usable": True,
            "issues": {
                "exposure": "slightly_underexposed",
                "color_cast": "blue_green",
                "haze": "moderate",
                "contrast": "low",
                "sharpness": "acceptable",
                "noise": "low",
            },
            "edit_intent": "restore color and contrast for underwater photo",
            "confidence": confidence,
            "risk_flags": [],
        }


def _settings() -> Settings:
    return Settings(
        runtime_dir=RUNTIME_DIR,
        input_dir=RUNTIME_DIR / "input",
        output_dir=RUNTIME_DIR / "output",
        artifact_dir=RUNTIME_DIR / "artifacts",
        preview_dir=RUNTIME_DIR / "previews",
        bridge_dir=RUNTIME_DIR / "bridge",
        log_dir=RUNTIME_DIR / "logs",
        models_dir=RUNTIME_DIR / "models",
        vision_backend="mock",
        qwen_model_path=QWEN25_DIR,
        qwen3_model_path=QWEN3_DIR,
        model_offline=True,
    )


def _reset_runtime(settings: Settings) -> None:
    runtime_dir = settings.project_path(settings.runtime_dir)
    if runtime_dir.exists():
        shutil.rmtree(runtime_dir)
    for path in settings.required_runtime_dirs():
        path.mkdir(parents=True, exist_ok=True)
    QWEN25_DIR.mkdir(parents=True, exist_ok=True)
    QWEN3_DIR.mkdir(parents=True, exist_ok=True)
    (QWEN25_DIR / "LOCAL_MODEL_PLACEHOLDER.txt").write_text("local qwen2.5 placeholder", encoding="utf-8")
    (QWEN3_DIR / "LOCAL_MODEL_PLACEHOLDER.txt").write_text("local qwen3 placeholder", encoding="utf-8")


def _fail(message: str) -> int:
    print(f"FAIL {message}")
    return 1


def _verify_payload(payload: dict[str, Any], artifact_path: Path) -> str | None:
    if not artifact_path.exists():
        return f"benchmark artifact does not exist: {artifact_path}"
    if payload.get("artifact_type") != "MODEL_BENCHMARK_RESULT":
        return "benchmark artifact_type is incorrect"
    if payload.get("loop_name") != "model_benchmark_loop":
        return "benchmark loop_name is incorrect"
    if payload.get("automatic_promotion") is not False:
        return "benchmark must not automatically promote a model"
    if payload.get("default_backend_before") != payload.get("default_backend_after"):
        return "benchmark changed the default backend"
    if "rollback_path" not in payload or not payload["rollback_path"].get("steps"):
        return "rollback path is missing"
    recommendation = payload.get("recommendation", {})
    if recommendation.get("decision") == "promote_automatically":
        return "recommendation must not promote automatically"
    if not recommendation.get("evidence_summary"):
        return "recommendation is missing evidence summary"
    candidates = payload.get("candidates", [])
    if {candidate.get("candidate_id") for candidate in candidates} != {"qwen2_5_vl_3b_4bit", "qwen3_vl_4b_4bit"}:
        return "benchmark did not compare both required candidates"
    for candidate in candidates:
        metrics = candidate.get("metrics", {})
        missing = REQUIRED_METRICS - set(metrics)
        if missing:
            return f"candidate {candidate.get('candidate_id')} missing metrics: {sorted(missing)}"
        if metrics["json_validity"]["validity_rate"] != 1.0:
            return f"candidate {candidate.get('candidate_id')} did not produce valid JSON"
        if not metrics["10_photo_stability"]["passed"]:
            return f"candidate {candidate.get('candidate_id')} failed 10-photo stability"
        if not metrics["100_photo_stability"]["passed"]:
            return f"candidate {candidate.get('candidate_id')} failed 100-photo stability"
        if metrics["lightroom_simultaneous_operation_stability"]["status"] != "not_measured_in_local_harness":
            return "Lightroom simultaneous stability should remain explicitly unmeasured in local harness"
        loop_payload = candidate.get("loop_evidence", {})
        if loop_payload.get("loop_name") != "model_benchmark_loop":
            return "candidate loop evidence is missing model_benchmark_loop"
    if payload.get("recommendation", {}).get("recommended_candidate") is not None:
        return "candidate should not be recommended while Lightroom simultaneous stability is unmeasured"
    return None


def _run_cli(settings: Settings) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": str(SRC_ROOT),
            "TONEVYRA_RUNTIME_DIR": str(settings.project_path(settings.runtime_dir)),
            "TONEVYRA_INPUT_DIR": str(settings.project_path(settings.input_dir)),
            "TONEVYRA_OUTPUT_DIR": str(settings.project_path(settings.output_dir)),
            "TONEVYRA_ARTIFACT_DIR": str(settings.project_path(settings.artifact_dir)),
            "TONEVYRA_PREVIEW_DIR": str(settings.project_path(settings.preview_dir)),
            "TONEVYRA_BRIDGE_DIR": str(settings.project_path(settings.bridge_dir)),
            "TONEVYRA_LOG_DIR": str(settings.project_path(settings.log_dir)),
            "TONEVYRA_MODELS_DIR": str(settings.project_path(settings.models_dir)),
            "TONEVYRA_QWEN_MODEL_PATH": str(settings.project_path(settings.qwen_model_path)),
            "TONEVYRA_QWEN3_MODEL_PATH": str(settings.project_path(settings.qwen3_model_path)),
            "TONEVYRA_VISION_BACKEND": "mock",
        }
    )
    return subprocess.run(
        [sys.executable, "-m", "tonevyra_agent.cli", "benchmark-models", "--sample-set", "harness"],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def main() -> int:
    settings = _settings()
    _reset_runtime(settings)
    result = run_model_benchmark(
        settings=settings,
        sample_set="harness",
        include_100_photo=True,
        runtime_factory=lambda candidate: FakeBenchmarkRuntime(candidate.candidate_id),
    )
    payload = json.loads(result.artifact.path.read_text(encoding="utf-8"))
    error = _verify_payload(payload, result.artifact.path)
    if error:
        return _fail(error)
    print("OK model_benchmark_result.json exists with required metrics and loop evidence")

    cli_result = _run_cli(settings)
    if cli_result.returncode != 0:
        return _fail(f"benchmark-models CLI failed: stdout={cli_result.stdout} stderr={cli_result.stderr}")
    if "model benchmark artifact" not in cli_result.stdout or "default_backend_after=mock" not in cli_result.stdout:
        return _fail(f"benchmark-models CLI did not report artifact/default backend: {cli_result.stdout}")
    print("OK benchmark-models CLI writes artifact without changing default backend")

    shutil.rmtree(settings.project_path(settings.runtime_dir), ignore_errors=True)
    print("Model benchmark loop verification complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
