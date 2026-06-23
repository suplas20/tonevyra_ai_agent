from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from tonevyra_agent.agent.plan_policy import get_plan_policy
from tonevyra_agent.core.config import Settings
from tonevyra_agent.core.enums import ErrorCode
from tonevyra_agent.core.errors import TonevyraError
from tonevyra_agent.model_runtime.manifest import LocalModelManifest
from tonevyra_agent.providers.model_analysis import ModelAnalysisProvider
from tonevyra_agent.providers.model_quality import ModelQualityProvider
from tonevyra_agent.schemas.analysis import AnalysisRequest
from tonevyra_agent.schemas.quality import QualityRequest


class StaticRunner:
    def __init__(self, responses: dict[str, dict[str, Any]]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def generate(self, *, operation: str, request_payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(operation)
        return self.responses[operation]


def test_model_analysis_provider_uses_local_runtime_envelope(tmp_path: Path) -> None:
    manifest_path, settings = _write_manifest(tmp_path)
    preview = tmp_path / "preview.jpg"
    _write_image(preview, color=(128, 118, 104))
    runner = StaticRunner(
        {
            "analysis": {
                "scene": {"genre": "portrait", "lighting": "mixed_indoor"},
                "subjects": [{"type": "person", "priority": "primary"}],
                "technical_findings": [{"code": "HIGHLIGHT_RISK_FACE", "severity": 0.55}],
                "color_findings": [{"code": "WARM_SKIN_CAST", "severity": 0.62}],
                "quality_risks": [{"code": "BACKGROUND_CONTRAST_HIGH", "severity": 0.48}],
                "confidence": 0.91,
            }
        }
    )

    provider = ModelAnalysisProvider(settings=settings, manifest_path=manifest_path, runner=runner)
    result = provider.analyze(
        AnalysisRequest(
            job_id="job-t022",
            attempt_id="attempt-0",
            preview_path=preview,
            metadata={"file": {"name": "portrait.jpg"}},
            plan="standard",
        )
    )

    assert result.provider_type == "model"
    assert result.scene["genre"] == "portrait"
    assert provider.last_runtime_envelope is not None
    assert provider.last_runtime_envelope.operation == "analysis"
    assert provider.last_runtime_envelope.model_checksum.startswith("sha256:")
    assert runner.calls == ["analysis"]


def test_model_quality_provider_evaluates_source_export_pair(tmp_path: Path) -> None:
    manifest_path, settings = _write_manifest(tmp_path)
    source = tmp_path / "source.jpg"
    export = tmp_path / "export.jpg"
    _write_image(source, color=(95, 100, 120))
    _write_image(export, color=(130, 126, 118))
    analysis_provider = ModelAnalysisProvider(
        settings=settings,
        manifest_path=manifest_path,
        runner=StaticRunner(
            {
                "analysis": {
                    "scene": {"type": "general_photo"},
                    "subjects": [],
                    "technical_findings": [],
                    "color_findings": [],
                    "quality_risks": [],
                    "confidence": 0.88,
                }
            }
        ),
    )
    analysis = analysis_provider.analyze(
        AnalysisRequest(job_id="job-t022", attempt_id="attempt-0", preview_path=source, plan="standard")
    )
    quality_provider = ModelQualityProvider(
        settings=settings,
        manifest_path=manifest_path,
        runner=StaticRunner(
            {
                "quality": {
                    "status": "RETRY_REQUIRED",
                    "scores": {"color": 0.68, "source_to_export_improvement": 0.73},
                    "reason_codes": ["SKIN_TOO_WARM"],
                    "retry_recommendation": {
                        "recommended": True,
                        "strategy": ["reduce warm skin cast", "protect facial highlights"],
                        "expected_improvement": 0.16,
                    },
                    "source_limit_evidence": [],
                    "confidence": 0.86,
                    "improvement_summary": "Export improved exposure but remains too warm.",
                }
            }
        ),
    )

    result = quality_provider.evaluate(
        QualityRequest(
            job_id="job-t022",
            attempt_id="attempt-0",
            source_path=source,
            export_path=export,
            analysis=analysis,
            applied_adjustment_plan={"planner_version": "test"},
            plan="standard",
        )
    )

    assert result.provider_type == "model"
    assert result.status == "RETRY_REQUIRED"
    assert result.retry_recommendation.strategy == "reduce warm skin cast; protect facial highlights"
    assert result.retry_recommendation.expected_gain == pytest.approx(0.16)
    assert quality_provider.last_runtime_envelope is not None
    assert quality_provider.last_runtime_envelope.source_checksum
    assert quality_provider.last_runtime_envelope.export_checksum


def test_model_provider_rejects_direct_lightroom_fields(tmp_path: Path) -> None:
    manifest_path, settings = _write_manifest(tmp_path)
    preview = tmp_path / "preview.jpg"
    _write_image(preview)
    provider = ModelAnalysisProvider(
        settings=settings,
        manifest_path=manifest_path,
        runner=StaticRunner(
            {
                "analysis": {
                    "scene": {"type": "general_photo"},
                    "subjects": [],
                    "technical_findings": [],
                    "color_findings": [],
                    "quality_risks": [],
                    "confidence": 0.95,
                    "lightroom_adjustments": {"Temperature": -12},
                }
            }
        ),
    )

    with pytest.raises(TonevyraError) as exc:
        provider.analyze(AnalysisRequest(job_id="job-t022", attempt_id="attempt-0", preview_path=preview))

    assert exc.value.code == ErrorCode.MODEL_OUTPUT_INVALID


def test_local_model_manifest_rejects_remote_config(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "t022.local_model_manifest.v1",
                "model_id": "remote",
                "model_revision": "latest",
                "model_root": "__remote_model_endpoint__",
                "model_checksum": "sha256:bad",
                "runtime_backend": "remote_api",
                "remote_api_enabled": True,
                "runtime_download_enabled": True,
                "external_image_url_enabled": True,
                "allowed_model_root": "models",
                "network_required": True,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(TonevyraError):
        LocalModelManifest.load(manifest, Settings(models_dir=tmp_path / "models"))


def test_t022_plan_routing_keeps_free_lite_model_loading_off() -> None:
    free = get_plan_policy("free")
    lite = get_plan_policy("lite")
    standard = get_plan_policy("standard")
    pro = get_plan_policy("pro")

    assert free.analysis_provider == "module"
    assert free.allow_model_loading is False
    assert lite.quality_provider == "module"
    assert lite.allow_model_loading is False
    assert standard.analysis_provider == "model"
    assert standard.allow_model_loading is True
    assert standard.allow_module_fallback is False
    assert pro.quality_provider == "model"
    assert pro.allow_module_fallback is False


def _write_manifest(tmp_path: Path) -> tuple[Path, Settings]:
    model_root = tmp_path / "models"
    model_root.mkdir()
    model_file = model_root / "local_model.json"
    model_file.write_text("{}", encoding="utf-8")
    checksum = hashlib.sha256(model_file.read_bytes()).hexdigest()
    manifest_path = tmp_path / "model_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "t022.local_model_manifest.v1",
                "model_id": "tonevyra-local-test",
                "model_revision": "test-revision",
                "model_root": str(model_file),
                "model_checksum": f"sha256:{checksum}",
                "runtime_backend": "local_test_runner",
                "remote_api_enabled": False,
                "runtime_download_enabled": False,
                "external_image_url_enabled": False,
                "allowed_model_root": str(model_root),
                "network_required": False,
                "device": "cpu",
                "dtype": "float32",
                "quantization": "none",
            }
        ),
        encoding="utf-8",
    )
    return manifest_path, Settings(
        models_dir=model_root,
        model_manifest_path=manifest_path,
        model_confidence_threshold=0.7,
    )


def _write_image(path: Path, *, color: tuple[int, int, int] = (128, 128, 128)) -> None:
    Image.new("RGB", (32, 32), color).save(path, quality=90)
