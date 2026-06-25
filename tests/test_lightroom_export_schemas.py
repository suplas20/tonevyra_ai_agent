from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from tonevyra_agent.lightroom.schemas import LightroomApplyRequestPayload, LightroomExportRequestPayload, LightroomExportResultPayload
from tonevyra_agent.lightroom.schemas import LightroomApplyResultPayload
from tonevyra_agent.correction.schemas import CorrectionPlan
from tonevyra_agent.lightroom.bridge import _develop_settings_from_plan


def test_lightroom_export_request_rejects_source_overwrite(tmp_path: Path) -> None:
    source = tmp_path / "image.jpg"
    source.write_bytes(b"source")

    with pytest.raises(ValidationError):
        LightroomExportRequestPayload(
            request_id="export-task-001",
            task_id="task-001",
            apply_request_id="task-001",
            source_path=str(source),
            export_path=str(source),
            created_at="2026-06-22T00:00:00Z",
        )


def test_lightroom_export_result_requires_verified_file_result(tmp_path: Path) -> None:
    source = tmp_path / "image.jpg"
    export = tmp_path / "output.jpg"
    source.write_bytes(b"source")
    export.write_bytes(b"export")

    result = LightroomExportResultPayload(
        request_id="export-task-001",
        task_id="task-001",
        apply_request_id="task-001",
        source_path=str(source),
        export_path=str(export),
        status="exported",
        export_settings={
            "format": "JPEG",
            "quality": 95,
            "color_space": "sRGB",
            "resize": False,
        },
        lightroom_result={
            "plugin_loaded": True,
            "worker_running": True,
            "source_photo_found": True,
            "export_started": True,
            "export_completed": True,
        },
        file_result={
            "exists": True,
            "size_bytes": 6,
        },
        error_code=None,
        message="Export completed successfully",
        completed_at="2026-06-22T00:00:01Z",
    )

    assert result.status == "exported"
    assert result.file_result["size_bytes"] == 6


def test_lightroom_export_result_rejects_unverified_success(tmp_path: Path) -> None:
    source = tmp_path / "image.jpg"
    export = tmp_path / "output.jpg"
    source.write_bytes(b"source")

    with pytest.raises(ValidationError):
        LightroomExportResultPayload(
            request_id="export-task-001",
            task_id="task-001",
            apply_request_id="task-001",
            source_path=str(source),
            export_path=str(export),
            status="exported",
            export_settings={
                "format": "JPEG",
                "quality": 95,
                "color_space": "sRGB",
                "resize": False,
            },
            lightroom_result={
                "plugin_loaded": True,
                "worker_running": True,
                "source_photo_found": True,
                "export_started": True,
                "export_completed": True,
            },
            file_result={
                "exists": False,
                "size_bytes": 0,
            },
            error_code=None,
            message="Export completed successfully",
            completed_at="2026-06-22T00:00:01Z",
        )


def test_lightroom_apply_result_accepts_write_access_evidence(tmp_path: Path) -> None:
    source = tmp_path / "image.jpg"
    source.write_bytes(b"source")

    result = LightroomApplyResultPayload(
        schema_version="t019.lightroom_apply.result.v1",
        request_id="task-001",
        request_origin="lightroom_plugin",
        command="APPLY_LIGHTROOM_SETTINGS",
        task_id="task-001",
        status="applied",
        source_path=str(source),
        catalog_action="imported",
        applied_settings={"exposure": 0.25},
        skipped_settings={},
        lightroom_result={
            "plugin_loaded": True,
            "worker_running": True,
            "source_photo_imported": True,
            "source_photo_found": False,
            "develop_settings_applied": True,
        },
        evidence={
            "adapter_role": "apply_adapter",
            "write_access_retry_count": 0,
            "write_access_wait_ms": 0,
        },
        write_access_retry_count=0,
        write_access_wait_ms=0,
    )

    assert result.status == "applied"
    assert result.write_access_retry_count == 0


def test_lightroom_apply_request_resolves_temperature_delta_to_absolute() -> None:
    # The relative delta is converted to an ABSOLUTE temperature in the request so
    # reprocessing/retries stay idempotent (the plugin's relative path would
    # accumulate the delta onto the photo's current temperature on every run).
    plan = CorrectionPlan(
        base_preset="underwater-clean",
        style_target="natural",
        adjustments_json={
            "exposure": 0.25,
            "temperature_delta": 1200,
            "tint": 18,
        },
        confidence=0.86,
        reason_summary="Relative temperature is resolved to an absolute Kelvin value.",
    )

    settings = _develop_settings_from_plan(plan)

    assert settings["exposure"] == 0.25
    assert settings["tint"] == 18
    assert "temperature_delta" not in settings
    # nominal as-shot (6500 default) + delta 1200.
    assert settings["temp"] == 7700.0


def test_lightroom_apply_request_keeps_hsl_color_mixer_settings() -> None:
    plan = CorrectionPlan(
        base_preset="underwater-clean",
        style_target="color-recovery",
        adjustments_json={
            "blue_saturation": -82,
            "aqua_saturation": -75,
            "red_saturation": 55,
            "red_luminance": 38,
        },
        confidence=0.86,
        reason_summary="HSL color mixer settings should be passed to Lightroom.",
    )

    settings = _develop_settings_from_plan(plan)

    assert settings["blue_saturation"] == -82
    assert settings["aqua_saturation"] == -75
    assert settings["red_saturation"] == 55
    assert settings["red_luminance"] == 38


def test_lightroom_apply_request_prefers_absolute_temp_over_delta() -> None:
    plan = CorrectionPlan(
        base_preset="underwater-clean",
        style_target="calibrated-reference",
        adjustments_json={
            "temp": 8200,
            "temperature_delta": 3500,
            "tint": 24,
        },
        confidence=0.86,
        reason_summary="Reference recipe absolute temperature wins over relative delta.",
    )

    settings = _develop_settings_from_plan(plan)

    assert settings["temp"] == 8200
    assert settings["tint"] == 24
    assert "temperature_delta" not in settings


def test_lightroom_apply_request_drops_zero_temperature_delta_noop() -> None:
    plan = CorrectionPlan(
        base_preset="neutral-clean",
        style_target="normal-planner",
        adjustments_json={
            "exposure": 0.45,
            "temperature_delta": 0.0,
            "shadows": 38,
        },
        confidence=0.82,
        reason_summary="No-op temperature delta must not require plugin-side base temperature.",
    )

    settings = _develop_settings_from_plan(plan)

    assert settings["exposure"] == 0.45
    assert settings["shadows"] == 38
    assert "temperature_delta" not in settings


def test_lightroom_apply_request_accepts_planner_owned_local_adjustments(tmp_path: Path) -> None:
    source = tmp_path / "image.arw"
    source.write_bytes(b"raw")

    payload = LightroomApplyRequestPayload(
        request_id="task-local-001",
        task_id="task-local-001",
        source_path=str(source),
        correction_plan_id="plan-001",
        created_at="2026-06-25T00:00:00Z",
        develop_settings={"exposure": 1.15, "shadows": 65},
        local_adjustments={
            "schema_version": "tonevyra.local_adjustments.bundle.v1",
            "local_adjustment_plan": {
                "plans": [
                    {
                        "mask_plan_id": "mask-plan-1",
                        "region_id": "region-primary-subject-1",
                        "supported_mask_type": "subject",
                        "bounded_adjustment_intents": {"exposure_delta": 0.7, "shadows_delta": 0.5},
                    }
                ]
            },
        },
    )

    assert payload.local_adjustments["local_adjustment_plan"]["plans"][0]["supported_mask_type"] == "subject"
