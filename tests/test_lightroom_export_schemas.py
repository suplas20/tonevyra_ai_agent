from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from tonevyra_agent.lightroom.schemas import LightroomExportRequestPayload, LightroomExportResultPayload
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


def test_lightroom_apply_request_keeps_relative_temperature_delta() -> None:
    plan = CorrectionPlan(
        base_preset="underwater-clean",
        style_target="natural",
        adjustments_json={
            "exposure": 0.25,
            "temperature_delta": 1200,
            "tint": 18,
        },
        confidence=0.86,
        reason_summary="Relative temperature is resolved by the Lightroom plugin.",
    )

    settings = _develop_settings_from_plan(plan)

    assert settings["exposure"] == 0.25
    assert settings["tint"] == 18
    assert settings["temperature_delta"] == 1200
    assert "temp" not in settings
