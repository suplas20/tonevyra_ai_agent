from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from tonevyra_agent.lightroom.bridge import LightroomBridge, _mask_payload_from_local_adjustments
from tonevyra_agent.lightroom.schemas import (
    LightroomMaskApplyRequestPayload,
    LightroomMaskApplyResultPayload,
)


FIXTURE_ROOT = Path("harness/fixtures/t029_radial_masking")


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def test_t029_native_mask_request_fixture_validates() -> None:
    payload = LightroomMaskApplyRequestPayload.model_validate(_load_fixture("valid_mask_apply_request.json"))

    operation = payload.mask_plan.operations[0]
    assert payload.command == "APPLY_LIGHTROOM_MASK_PLAN"
    assert operation.strategy == "native_ai"
    assert operation.native_assessment.target_detected is True


def test_t029_native_mask_result_fixture_validates() -> None:
    payload = LightroomMaskApplyResultPayload.model_validate(_load_fixture("valid_mask_apply_result.json"))

    assert payload.status == "applied"
    assert payload.capability_snapshot.native_mask_command_supported is True
    assert payload.operation_results[0].strategy == "native_ai"


def test_t029_request_rejects_radial_template_strategy() -> None:
    data = _load_fixture("valid_mask_apply_request.json")
    data["mask_plan"]["operations"][0]["strategy"] = "radial_template"

    with pytest.raises(ValidationError):
        LightroomMaskApplyRequestPayload.model_validate(data)


def test_t029_request_rejects_template_ref_field() -> None:
    data = _load_fixture("valid_mask_apply_request.json")
    data["mask_plan"]["operations"][0]["template_ref"] = {"template_id": "forbidden"}

    with pytest.raises(ValidationError):
        LightroomMaskApplyRequestPayload.model_validate(data)


def test_t029_native_ai_requires_detected_target() -> None:
    data = _load_fixture("valid_mask_apply_request.json")
    data["mask_plan"]["operations"][0]["native_assessment"]["target_detected"] = False
    data["mask_plan"]["operations"][0]["native_assessment"]["reason_code"] = "NATIVE_TARGET_NOT_DETECTED"

    with pytest.raises(ValidationError):
        LightroomMaskApplyRequestPayload.model_validate(data)


def test_t029_review_required_requires_detection_failure() -> None:
    data = _load_fixture("valid_mask_apply_request.json")
    data["mask_plan"]["operations"][0]["strategy"] = "review_required"

    with pytest.raises(ValidationError):
        LightroomMaskApplyRequestPayload.model_validate(data)


def test_t029_result_rejects_applied_without_native_capability() -> None:
    data = _load_fixture("valid_mask_apply_result.json")
    data["capability_snapshot"]["native_mask_command_supported"] = False

    with pytest.raises(ValidationError):
        LightroomMaskApplyResultPayload.model_validate(data)


def test_t029_result_accepts_explicit_native_capability_skip() -> None:
    data = _load_fixture("valid_mask_apply_result.json")
    data["status"] = "skipped"
    data["capability_snapshot"]["native_mask_command_supported"] = False
    data["capability_snapshot"]["native_ai_mask_types"] = []
    data["operation_results"][0]["status"] = "skipped"
    data["operation_results"][0]["mask_created_or_reused"] = "not_created"
    data["operation_results"][0]["applied_adjustments"] = {}
    data["message"] = "Native Lightroom mask execution is not enabled in this plugin build."

    payload = LightroomMaskApplyResultPayload.model_validate(data)

    assert payload.status == "skipped"
    assert payload.capability_snapshot.native_mask_command_supported is False


def test_t029_result_accepts_lua_empty_table_for_native_mask_types() -> None:
    data = _load_fixture("valid_mask_apply_result.json")
    data["status"] = "skipped"
    data["capability_snapshot"]["native_mask_command_supported"] = False
    data["capability_snapshot"]["native_ai_mask_types"] = {}
    data["operation_results"][0]["status"] = "skipped"
    data["operation_results"][0]["mask_created_or_reused"] = "not_created"
    data["operation_results"][0]["applied_adjustments"] = {}
    data["message"] = "Native Lightroom mask execution is not enabled in this plugin build."

    payload = LightroomMaskApplyResultPayload.model_validate(data)

    assert payload.status == "skipped"
    assert payload.capability_snapshot.native_ai_mask_types == []


def test_t029_bridge_writes_mask_request_atomically(tmp_path: Path) -> None:
    data = _load_fixture("valid_mask_apply_request.json")
    source = tmp_path / "source.jpg"
    source.write_bytes(b"source")
    data["source_path"] = str(source)
    payload = LightroomMaskApplyRequestPayload.model_validate(data)

    bridge = LightroomBridge()
    bridge.settings.bridge_dir = tmp_path / "bridge"
    path = bridge.write_mask_apply_request_payload(payload)

    assert path.name == "mask-request-001.json"
    assert path.parent.name == "lightroom_mask_requests"
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["command"] == "APPLY_LIGHTROOM_MASK_PLAN"


def test_t029_builds_native_mask_request_from_t023_local_bundle(tmp_path: Path) -> None:
    source = tmp_path / "source.arw"
    source.write_bytes(b"raw")

    payload = _mask_payload_from_local_adjustments(
        task_id="task-local-mask-001",
        source_path=str(source),
        local_adjustments={
            "schema_version": "tonevyra.local_adjustments.bundle.v1",
            "local_adjustment_plan": {
                "job_id": "vision-qwen",
                "attempt_id": "vision-qwen-attempt-0",
                "capability_snapshot_id": "lr-cap-1",
                "plans": [
                    {
                        "mask_plan_id": "mask-plan-1",
                        "region_id": "region-primary-subject-1",
                        "supported_mask_type": "subject",
                        "bounded_adjustment_intents": {
                            "exposure_delta": 0.7,
                            "shadows_delta": 0.5,
                            "texture_delta": 0.08,
                            "noise_reduction_delta": 8.0,
                        },
                    },
                    {
                        "mask_plan_id": "mask-plan-2",
                        "region_id": "region-background-1",
                        "supported_mask_type": "background",
                        "bounded_adjustment_intents": {
                            "exposure_delta": 0.25,
                            "shadows_delta": 0.2,
                            "saturation_delta": -0.02,
                        },
                    },
                ],
            },
        },
    )

    assert payload is not None
    assert payload.command == "APPLY_LIGHTROOM_MASK_PLAN"
    assert len(payload.mask_plan.operations) == 2
    subject = payload.mask_plan.operations[0]
    assert subject.strategy == "native_ai"
    assert subject.native_assessment.attempted_types == ["subject"]
    assert subject.local_adjustments["Exposure2012"] == 0.7
    assert subject.local_adjustments["Shadows2012"] == 40.0
    assert subject.local_adjustments["Texture"] == 8.0
    assert "noise_reduction_delta" not in subject.local_adjustments
