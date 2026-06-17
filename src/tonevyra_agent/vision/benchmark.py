"""Bounded local model benchmark loop for Tonevyra AI."""

from __future__ import annotations

import json
import os
import statistics
import tempfile
import time
import tracemalloc
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from tonevyra_agent.agent.loops import MODEL_BENCHMARK_LOOP, make_loop_payload
from tonevyra_agent.core.config import PROJECT_ROOT, Settings, get_settings
from tonevyra_agent.core.enums import TaskStatus
from tonevyra_agent.storage.artifacts import calculate_sha256
from tonevyra_agent.vision.model import QwenVisionBackend, QwenVisionRuntime
from tonevyra_agent.vision.schemas import VisionAnalysisResult

BENCHMARK_ARTIFACT_NAME = "model_benchmark_result.json"
DEFAULT_BENCHMARK_TIMEOUT_SECONDS = 600
HARNESS_FIXTURE_IMAGE = PROJECT_ROOT / "harness" / "fixtures" / "images" / "sample_underwater_01.jpg"


@dataclass(frozen=True)
class BenchmarkCandidate:
    candidate_id: str
    display_name: str
    model_path: Path
    model_revision: str
    model_sha256: str | None
    commercial_policy: str
    promotion_role: str


@dataclass(frozen=True)
class BenchmarkArtifact:
    path: Path
    relative_path: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class ModelBenchmarkRunResult:
    artifact: BenchmarkArtifact
    payload: dict[str, Any]


RuntimeFactory = Callable[[BenchmarkCandidate], QwenVisionRuntime]


class ModelBenchmarkLoop:
    """Compare configured local model candidates without changing defaults."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        runtime_factory: RuntimeFactory | None = None,
        timeout_seconds: int = DEFAULT_BENCHMARK_TIMEOUT_SECONDS,
    ) -> None:
        self.settings = settings or get_settings()
        self.runtime_factory = runtime_factory
        self.timeout_seconds = timeout_seconds

    def run(self, *, sample_set: str = "harness", include_100_photo: bool = False) -> ModelBenchmarkRunResult:
        started = time.monotonic()
        started_at = _utc_now()
        candidates = benchmark_candidates(self.settings)
        preview_path = self._prepare_preview_sample(sample_set)
        metadata = _sample_metadata(sample_set)
        prompt = _benchmark_prompt(metadata)
        candidate_results = []
        for index, candidate in enumerate(candidates, start=1):
            if time.monotonic() - started > self.timeout_seconds:
                candidate_results.append(_timeout_candidate_result(candidate))
                continue
            candidate_results.append(
                self._evaluate_candidate(
                    candidate,
                    preview_path=preview_path,
                    metadata=metadata,
                    prompt=prompt,
                    loop_iteration=index,
                    include_100_photo=include_100_photo,
                )
            )

        recommendation = _build_recommendation(candidate_results, default_backend=self.settings.vision_backend)
        finished_at = _utc_now()
        payload = {
            "schema_version": "1.0",
            "artifact_type": "MODEL_BENCHMARK_RESULT",
            "loop_name": MODEL_BENCHMARK_LOOP,
            "started_at": started_at,
            "finished_at": finished_at,
            "sample_set": sample_set,
            "default_backend_before": self.settings.vision_backend,
            "default_backend_after": self.settings.vision_backend,
            "automatic_promotion": False,
            "online_upload": False,
            "silent_model_replacement": False,
            "input_boundary": {
                "preview_path": _project_relative_or_absolute(preview_path),
                "metadata_keys": sorted(metadata.keys()),
                "original_raw_sent_to_model": False,
                "external_services_used": False,
            },
            "required_metrics": [
                "inference_time",
                "peak_memory",
                "json_validity",
                "quality_impact",
                "error_rate",
                "lightroom_simultaneous_operation_stability",
                "10_photo_stability",
                "100_photo_stability",
            ],
            "candidates": candidate_results,
            "recommendation": recommendation,
            "rollback_path": {
                "default_backend": self.settings.vision_backend,
                "steps": [
                    "Keep TONEVYRA_VISION_BACKEND unchanged until a human approves promotion.",
                    "If a candidate regresses, set TONEVYRA_VISION_BACKEND=mock or the prior approved backend.",
                    "Keep previous local model directory and configuration until the promoted backend passes production smoke checks.",
                ],
            },
            "loop_evidence": make_loop_payload(
                loop_name=MODEL_BENCHMARK_LOOP,
                event_type="MODEL_BENCHMARK_COMPLETED",
                from_status=TaskStatus.QUEUED,
                to_status=TaskStatus.SKIPPED,
                reason="explicit bounded benchmark completed without automatic model promotion",
                evidence_artifacts=[
                    {
                        "artifact_type": "MODEL_BENCHMARK_RESULT",
                        "artifact_path": self._result_relative_path(),
                    }
                ],
                candidate_count=len(candidate_results),
                automatic_promotion=False,
            ),
        }
        artifact = self._write_result(payload)
        return ModelBenchmarkRunResult(artifact=artifact, payload=payload)

    def _evaluate_candidate(
        self,
        candidate: BenchmarkCandidate,
        *,
        preview_path: Path,
        metadata: dict[str, Any],
        prompt: str,
        loop_iteration: int,
        include_100_photo: bool,
    ) -> dict[str, Any]:
        base = {
            "candidate_id": candidate.candidate_id,
            "display_name": candidate.display_name,
            "model_path": _project_relative_or_absolute(candidate.model_path),
            "model_revision": candidate.model_revision,
            "model_sha256": candidate.model_sha256,
            "commercial_policy": candidate.commercial_policy,
            "promotion_role": candidate.promotion_role,
            "loop_evidence": make_loop_payload(
                loop_name=MODEL_BENCHMARK_LOOP,
                event_type="MODEL_BENCHMARK_CANDIDATE_EVALUATED",
                from_status=TaskStatus.QUEUED,
                to_status=TaskStatus.SKIPPED,
                reason=f"candidate {candidate.candidate_id} evaluated without promotion",
                loop_iteration=loop_iteration,
                evidence_artifacts=[],
            ),
        }
        if not candidate.model_path.exists():
            return {
                **base,
                "status": "unavailable",
                "error": "local model path does not exist",
                "metrics": _empty_metrics(),
                "promotion_eligible": False,
            }

        runtime = self.runtime_factory(candidate) if self.runtime_factory is not None else None
        try:
            backend = QwenVisionBackend(
                self.settings,
                model_path=candidate.model_path,
                runtime=runtime,
                model_name=candidate.display_name,
            )
        except Exception as exc:
            return {
                **base,
                "status": "load_failed",
                "error": str(exc),
                "metrics": _empty_metrics(),
                "promotion_eligible": False,
            }

        metrics = _measure_backend(
            backend=backend,
            preview_path=preview_path,
            metadata=metadata,
            prompt=prompt,
            include_100_photo=include_100_photo,
        )
        return {
            **base,
            "status": "completed" if metrics["json_validity"]["valid_outputs"] else "failed",
            "error": None,
            "metrics": metrics,
            "promotion_eligible": _candidate_promotion_eligible(metrics),
        }

    def _prepare_preview_sample(self, sample_set: str) -> Path:
        preview_dir = self.settings.project_path(self.settings.preview_dir).resolve()
        preview_dir.mkdir(parents=True, exist_ok=True)
        target = preview_dir / f"benchmark_{sample_set}_sample.jpg"
        if HARNESS_FIXTURE_IMAGE.exists():
            target.write_bytes(HARNESS_FIXTURE_IMAGE.read_bytes())
        else:
            target.write_bytes(b"Tonevyra benchmark placeholder preview")
        return target

    def _write_result(self, payload: dict[str, Any]) -> BenchmarkArtifact:
        artifact_dir = self.settings.project_path(self.settings.artifact_dir).resolve() / "model_benchmarks"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        path = artifact_dir / BENCHMARK_ARTIFACT_NAME
        data = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
        _write_atomic(path, data)
        sha256 = calculate_sha256(path)
        return BenchmarkArtifact(
            path=path,
            relative_path=path.relative_to(PROJECT_ROOT).as_posix(),
            sha256=sha256,
            size_bytes=path.stat().st_size,
        )

    def _result_relative_path(self) -> str:
        path = self.settings.project_path(self.settings.artifact_dir).resolve() / "model_benchmarks" / BENCHMARK_ARTIFACT_NAME
        return _project_relative_or_absolute(path)


def benchmark_candidates(settings: Settings) -> list[BenchmarkCandidate]:
    return [
        BenchmarkCandidate(
            candidate_id="qwen2_5_vl_3b_4bit",
            display_name=settings.qwen_model_name,
            model_path=settings.project_path(settings.qwen_model_path).resolve(),
            model_revision=settings.qwen_model_revision,
            model_sha256=settings.qwen_model_sha256,
            commercial_policy="technical_stable_candidate_not_commercial_default_without_license_review",
            promotion_role="technical_stable_candidate",
        ),
        BenchmarkCandidate(
            candidate_id="qwen3_vl_4b_4bit",
            display_name=settings.qwen3_model_name,
            model_path=settings.project_path(settings.qwen3_model_path).resolve(),
            model_revision=settings.qwen3_model_revision,
            model_sha256=settings.qwen3_model_sha256,
            commercial_policy="commercial_default_candidate_requires_license_review_and_benchmark",
            promotion_role="commercial_default_candidate",
        ),
    ]


def run_model_benchmark(
    *,
    settings: Settings | None = None,
    sample_set: str = "harness",
    include_100_photo: bool = False,
    runtime_factory: RuntimeFactory | None = None,
) -> ModelBenchmarkRunResult:
    return ModelBenchmarkLoop(settings=settings, runtime_factory=runtime_factory).run(
        sample_set=sample_set,
        include_100_photo=include_100_photo,
    )


def _measure_backend(
    *,
    backend: QwenVisionBackend,
    preview_path: Path,
    metadata: dict[str, Any],
    prompt: str,
    include_100_photo: bool,
) -> dict[str, Any]:
    outputs: list[VisionAnalysisResult] = []
    errors: list[str] = []
    inference_times: list[float] = []
    tracemalloc.start()
    peak_bytes = 0
    for _ in range(10):
        started = time.perf_counter()
        try:
            payload = backend.analyze(preview_path=preview_path, metadata=metadata, prompt=prompt)
            outputs.append(VisionAnalysisResult.model_validate(payload))
        except Exception as exc:
            errors.append(str(exc))
        inference_times.append((time.perf_counter() - started) * 1000)
        _, peak = tracemalloc.get_traced_memory()
        peak_bytes = max(peak_bytes, peak)
    tracemalloc.stop()

    hundred_status = "not_run"
    hundred_valid = 0
    hundred_errors = 0
    if include_100_photo:
        hundred_status = "completed"
        for _ in range(100):
            try:
                payload = backend.analyze(preview_path=preview_path, metadata=metadata, prompt=prompt)
                VisionAnalysisResult.model_validate(payload)
                hundred_valid += 1
            except Exception:
                hundred_errors += 1

    total = len(outputs) + len(errors)
    return {
        "inference_time": {
            "iterations": len(inference_times),
            "mean_ms": round(statistics.fmean(inference_times), 2) if inference_times else None,
            "max_ms": round(max(inference_times), 2) if inference_times else None,
        },
        "peak_memory": {
            "python_tracemalloc_peak_mb": round(peak_bytes / (1024 * 1024), 2),
            "note": "Runtime process, GPU, framework, and Lightroom memory must be measured in the real benchmark environment.",
        },
        "json_validity": {
            "valid_outputs": len(outputs),
            "invalid_outputs": len(errors),
            "validity_rate": round(len(outputs) / total, 4) if total else 0.0,
        },
        "quality_impact": {
            "mean_confidence": round(statistics.fmean([output.confidence for output in outputs]), 4) if outputs else 0.0,
            "requires_review_count": sum(1 for output in outputs if output.requires_review),
            "estimated_quality_delta": "requires full Lightroom export + quality gate benchmark before promotion",
        },
        "error_rate": round(len(errors) / total, 4) if total else 1.0,
        "lightroom_simultaneous_operation_stability": {
            "status": "not_measured_in_local_harness",
            "required_before_promotion": True,
        },
        "10_photo_stability": {
            "status": "completed",
            "valid_outputs": len(outputs),
            "errors": len(errors),
            "passed": len(outputs) == 10 and not errors,
        },
        "100_photo_stability": {
            "status": hundred_status,
            "valid_outputs": hundred_valid,
            "errors": hundred_errors,
            "passed": include_100_photo and hundred_valid == 100 and hundred_errors == 0,
            "required_before_promotion": True,
        },
        "errors": errors[:5],
    }


def _candidate_promotion_eligible(metrics: dict[str, Any]) -> bool:
    return bool(
        metrics["json_validity"]["validity_rate"] == 1.0
        and metrics["error_rate"] == 0.0
        and metrics["10_photo_stability"]["passed"]
        and metrics["100_photo_stability"]["passed"]
        and metrics["lightroom_simultaneous_operation_stability"].get("status") == "passed"
    )


def _build_recommendation(candidate_results: list[dict[str, Any]], *, default_backend: str) -> dict[str, Any]:
    eligible = [candidate for candidate in candidate_results if candidate.get("promotion_eligible")]
    if not eligible:
        return {
            "decision": "do_not_promote_automatically",
            "recommended_candidate": None,
            "evidence_summary": "No candidate completed all required gates, including 100-photo and Lightroom simultaneous stability.",
            "human_review_required": True,
            "default_backend_remains": default_backend,
        }
    return {
        "decision": "human_review_required_before_promotion",
        "recommended_candidate": eligible[0]["candidate_id"],
        "evidence_summary": "Candidate met local benchmark gates; explicit human approval is still required.",
        "human_review_required": True,
        "default_backend_remains": default_backend,
    }


def _empty_metrics() -> dict[str, Any]:
    return {
        "inference_time": {"iterations": 0, "mean_ms": None, "max_ms": None},
        "peak_memory": {"python_tracemalloc_peak_mb": None},
        "json_validity": {"valid_outputs": 0, "invalid_outputs": 0, "validity_rate": 0.0},
        "quality_impact": {"mean_confidence": 0.0, "requires_review_count": 0, "estimated_quality_delta": "not_available"},
        "error_rate": 1.0,
        "lightroom_simultaneous_operation_stability": {"status": "not_measured", "required_before_promotion": True},
        "10_photo_stability": {"status": "not_run", "valid_outputs": 0, "errors": 0, "passed": False},
        "100_photo_stability": {"status": "not_run", "valid_outputs": 0, "errors": 0, "passed": False, "required_before_promotion": True},
        "errors": [],
    }


def _timeout_candidate_result(candidate: BenchmarkCandidate) -> dict[str, Any]:
    return {
        "candidate_id": candidate.candidate_id,
        "display_name": candidate.display_name,
        "status": "timeout",
        "error": "benchmark timeout reached before candidate evaluation",
        "metrics": _empty_metrics(),
        "promotion_eligible": False,
    }


def _sample_metadata(sample_set: str) -> dict[str, Any]:
    return {
        "basic": {"sample_set": sample_set, "source": "local_benchmark_harness"},
        "image": {"width": 1024, "height": 768, "color_mode": "RGB", "preview_profile": "sRGB"},
    }


def _benchmark_prompt(metadata: dict[str, Any]) -> str:
    return (
        "Analyze the local benchmark preview for Tonevyra AI. "
        "Return JSON only with scene_type, main_subject, usable, issues, edit_intent, confidence, and risk_flags. "
        f"Metadata: {metadata}"
    )


def _write_atomic(path: Path, data: bytes) -> None:
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            delete=False,
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except Exception:
        if temp_path and temp_path.exists():
            temp_path.unlink()
        raise


def _project_relative_or_absolute(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
