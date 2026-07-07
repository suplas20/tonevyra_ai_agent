from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from tonevyra_agent.core.config import Settings
from tonevyra_agent.core.enums import ErrorCode
from tonevyra_agent.core.errors import TonevyraError
from tonevyra_agent.planner_api.client import PlannerApiClient
from tonevyra_agent.planner_api.contracts import (
    build_planner_request,
    forbidden_key_paths,
    response_to_correction_plan,
    sha256_digest,
    validate_request_digest,
)
from tonevyra_agent.vision.schemas import VisionAnalysisResult, VisionIssues


def _settings() -> Settings:
    return Settings(
        planner_api_device_id_hash="sha256:" + "2" * 64,
        planner_api_supported_planner_versions="1.0.0",
        planner_api_supported_policy_versions="2026-07-07.1",
    )


def _analysis() -> VisionAnalysisResult:
    return VisionAnalysisResult(
        model_backend="qwen",
        model_name="Qwen3-VL-4B-Instruct",
        scene_type="underwater",
        main_subject="person",
        usable=True,
        issues=VisionIssues(
            exposure="severely_underexposed",
            color_cast="blue_green",
            contrast="low",
            sharpness="soft",
            noise="moderate",
        ),
        confidence=0.91,
    )


def _metadata() -> dict[str, object]:
    return {
        "source_path": "F:/private/customer/photo.CR3",
        "file": {"name": "photo.CR3"},
        "image": {"width": 6000, "height": 4000},
        "basic": {
            "orientation": 1,
            "iso": 800,
            "exposure_time": 0.008,
            "f_number": 5.6,
            "focal_length": 24.0,
            "camera_serial_number": "secret",
        },
    }


def test_planner_request_uses_allowlist_and_canonical_digest() -> None:
    request = build_planner_request(
        request_id=str(uuid4()),
        analysis=_analysis(),
        metadata=_metadata(),
        settings=_settings(),
    )

    payload = request.model_dump(mode="json")
    assert forbidden_key_paths(payload) == []
    assert payload["analysis"]["scene_type"] == "underwater"
    assert payload["image_context"]["width"] == 6000
    body_without_digest = {key: value for key, value in payload.items() if key != "input_digest"}
    assert payload["input_digest"] == sha256_digest(body_without_digest)


def test_planner_request_digest_matches_transmitted_body_when_optional_metadata_missing() -> None:
    metadata = {
        "source_path": "F:/private/customer/photo.ARW",
        "file": {"name": "photo.ARW", "extension": ".arw"},
        "image": {"width": 7008, "height": 4672},
        "basic": {},
    }
    request = build_planner_request(
        request_id=str(uuid4()),
        analysis=_analysis(),
        metadata=metadata,
        settings=_settings(),
    )

    payload = request.model_dump(mode="json")
    validate_request_digest(payload)
    assert payload["image_context"]["iso"] is None
    assert payload["input_digest"] == sha256_digest({key: value for key, value in payload.items() if key != "input_digest"})


def test_planner_response_maps_contract_plan_to_local_correction_plan() -> None:
    fixtures = Path("harness/fixtures/t032_planner_api")
    request = build_planner_request(
        request_id="4a6c3f98-0be7-4dbe-bc72-24c065f40874",
        analysis=_analysis(),
        metadata=_metadata(),
        settings=_settings(),
    )
    response = json.loads((fixtures / "valid_response.json").read_text(encoding="utf-8"))
    response["input_digest"] = request.input_digest
    response["plan_digest"] = sha256_digest(response["plan"])

    plan = response_to_correction_plan(
        request=request,
        response_payload=response,
        supported_planner_versions={"1.0.0"},
        supported_policy_versions={"2026-07-07.1"},
    )

    assert plan.adjustments_json["temp"] == 7100
    assert plan.adjustments_json["exposure"] == 1.25
    assert plan.source["plan_digest"] == response["plan_digest"]


def test_planner_response_rejects_forbidden_execution_fields() -> None:
    request = build_planner_request(
        request_id=str(uuid4()),
        analysis=_analysis(),
        metadata=_metadata(),
        settings=_settings(),
    )
    response = {
        "schema_version": "t032.planner.response.v1",
        "status": "success",
        "request_id": request.request_id,
        "server_request_id": "srv-test",
        "planner_version": "1.0.0",
        "policy_version": "2026-07-07.1",
        "input_digest": request.input_digest,
        "replayed": False,
        "plan": {
            "global_adjustments": {"exposure": 1.0},
            "command": "run-this",
            "requires_review": False,
            "reason_summary": "bad",
        },
    }
    response["plan_digest"] = sha256_digest(response["plan"])

    with pytest.raises(TonevyraError) as exc:
        response_to_correction_plan(
            request=request,
            response_payload=response,
            supported_planner_versions={"1.0.0"},
            supported_policy_versions={"2026-07-07.1"},
        )

    assert exc.value.code == ErrorCode.PLANNER_REQUEST_PRIVACY_VIOLATION


def test_planner_api_client_requires_https() -> None:
    client = PlannerApiClient(
        Settings(
            planner_api_base_url="http" + "://planner.example.test",
            planner_api_key="secret",
            planner_api_allowed_host="planner.example.test",
        )
    )
    request = build_planner_request(
        request_id=str(uuid4()),
        analysis=_analysis(),
        metadata=_metadata(),
        settings=_settings(),
    )

    with pytest.raises(TonevyraError) as exc:
        client.create_plan(request=request, idempotency_key="task:test")

    assert exc.value.code == ErrorCode.SECURITY_NETWORK_ACCESS_BLOCKED


def test_planner_api_client_accepts_configured_ca_bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ca_bundle = tmp_path / "planner-ca.pem"
    ca_bundle.write_text("", encoding="utf-8")
    settings = Settings(planner_api_ca_bundle=ca_bundle)
    seen: dict[str, str | None] = {}

    class _Handler:
        pass

    def fake_context(*, cafile: str | None = None):
        seen["cafile"] = cafile
        return object()

    def fake_opener(handler):
        assert handler is not None
        return _Handler()

    monkeypatch.setattr("tonevyra_agent.planner_api.client.ssl.create_default_context", fake_context)
    monkeypatch.setattr("tonevyra_agent.planner_api.client.build_opener", fake_opener)

    client = PlannerApiClient(settings)

    assert client.settings.planner_api_ca_bundle == ca_bundle
    assert seen["cafile"] == str(ca_bundle.resolve())
