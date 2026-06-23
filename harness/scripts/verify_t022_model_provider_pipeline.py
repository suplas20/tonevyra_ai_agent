#!/usr/bin/env python3
"""Verify T-022 local model provider, premium quality pipeline, and regressions."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

BASELINE_SKILLS = {
    "agent-worker-pipeline",
    "artifact-storage",
    "cli-operations",
    "closed-loop-quality-reprocessing",
    "correction-planner",
    "correction-planning",
    "dual-mode-agent-core",
    "feedback-learning",
    "folder-watcher",
    "image-metadata-preview",
    "lightroom-apply-adapter",
    "lightroom-bridge",
    "lightroom-final-export-adapter",
    "lightroom-live-test",
    "lightroom-plugin-implementation",
    "local-model-security",
    "loop-engineering",
    "model-benchmark-loop",
    "model-security",
    "postgresql-persistence",
    "project-scope",
    "python-mvp-structure",
    "quality-gate",
    "recovery-error-handling",
    "recovery-loop",
    "testing-harness",
    "vision-analysis",
}

NEW_SKILLS = {
    "local-model-analysis-provider",
    "model-quality-evaluation-provider",
}

FORBIDDEN_MODEL_FIELDS = {
    "lightroom_adjustments",
    "develop_settings",
    "preset_path",
    "execute_command",
    "plugin_command",
    "force_state_transition",
}

ALLOWED_QUALITY_STATUSES = {
    "APPROVED",
    "RETRY_REQUIRED",
    "SOURCE_LIMITED",
    "TECHNICAL_FAILED",
    "FINAL_FAILED",
}

SHA256_RE = re.compile(r"^sha256:[A-Za-z0-9]+$")


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return data


def find_forbidden(value: Any, prefix: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{prefix}.{key}"
            if key in FORBIDDEN_MODEL_FIELDS:
                found.append(child_path)
            found.extend(find_forbidden(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(find_forbidden(child, f"{prefix}[{index}]"))
    return found


def validate_analysis(data: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    required = {
        "schema_version",
        "job_id",
        "attempt_id",
        "provider_type",
        "provider_version",
        "scene",
        "subjects",
        "technical_findings",
        "color_findings",
        "quality_risks",
        "confidence",
        "created_at",
    }
    missing = sorted(required - data.keys())
    if missing:
        failures.append(f"analysis missing fields: {missing}")
    if data.get("schema_version") != "t021.analysis.result.v1":
        failures.append("analysis schema_version must remain t021.analysis.result.v1")
    if data.get("provider_type") != "model":
        failures.append("analysis provider_type must be model")
    confidence = data.get("confidence")
    if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        failures.append("analysis confidence must be between 0 and 1")
    forbidden = find_forbidden(data)
    if forbidden:
        failures.append(f"analysis contains forbidden model fields: {forbidden}")
    return failures


def validate_quality(data: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    required = {
        "schema_version",
        "job_id",
        "attempt_id",
        "provider_type",
        "status",
        "scores",
        "reason_codes",
        "retry_recommendation",
        "source_limit_evidence",
        "created_at",
    }
    missing = sorted(required - data.keys())
    if missing:
        failures.append(f"quality missing fields: {missing}")
    if data.get("schema_version") != "t021.quality.result.v1":
        failures.append("quality schema_version must remain t021.quality.result.v1")
    if data.get("provider_type") != "model":
        failures.append("quality provider_type must be model")
    status = data.get("status")
    if status not in ALLOWED_QUALITY_STATUSES:
        failures.append(f"invalid quality status: {status}")
    confidence = data.get("confidence")
    if confidence is not None and (
        not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1
    ):
        failures.append("quality confidence must be between 0 and 1")
    forbidden = find_forbidden(data)
    if forbidden:
        failures.append(f"quality contains forbidden model fields: {forbidden}")

    if status == "RETRY_REQUIRED":
        recommendation = data.get("retry_recommendation")
        if not isinstance(recommendation, dict):
            failures.append("RETRY_REQUIRED retry_recommendation must be an object")
        else:
            if recommendation.get("recommended") is not True:
                failures.append("RETRY_REQUIRED must set recommended=true")
            strategy = recommendation.get("strategy")
            if not isinstance(strategy, list) or not strategy:
                failures.append("RETRY_REQUIRED must include a non-empty semantic strategy list")
            if not recommendation.get("expected_improvement"):
                failures.append("RETRY_REQUIRED must include expected_improvement")
    if status == "SOURCE_LIMITED" and not data.get("source_limit_evidence"):
        failures.append("SOURCE_LIMITED must include source_limit_evidence")
    if status == "TECHNICAL_FAILED" and data.get("scores"):
        failures.append("TECHNICAL_FAILED must not fabricate quality scores")
    return failures


def validate_runtime_envelope(data: dict[str, Any], expected_operation: str) -> list[str]:
    failures: list[str] = []
    required = {
        "schema_version",
        "request_id",
        "job_id",
        "attempt_id",
        "operation",
        "provider_type",
        "model_id",
        "model_revision",
        "model_checksum",
        "runtime_backend",
        "runtime_version",
        "device",
        "dtype",
        "quantization",
        "started_at",
        "completed_at",
        "latency_ms",
        "parse_status",
        "confidence",
        "raw_output_checksum",
        "normalized_output",
    }
    missing = sorted(required - data.keys())
    if missing:
        failures.append(f"runtime envelope missing fields: {missing}")
    if data.get("schema_version") != "t022.model.runtime.envelope.v1":
        failures.append("runtime envelope schema_version is invalid")
    if data.get("operation") != expected_operation:
        failures.append(
            f"runtime operation must be {expected_operation}, found {data.get('operation')}"
        )
    if data.get("provider_type") != "model":
        failures.append("runtime provider_type must be model")
    if data.get("parse_status") != "SUCCESS":
        failures.append("valid runtime fixture parse_status must be SUCCESS")
    latency = data.get("latency_ms")
    if not isinstance(latency, (int, float)) or latency < 0:
        failures.append("runtime latency_ms must be non-negative")
    confidence = data.get("confidence")
    if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        failures.append("runtime confidence must be between 0 and 1")
    checksum = data.get("model_checksum")
    if not isinstance(checksum, str) or not SHA256_RE.match(checksum):
        failures.append("runtime model_checksum must use sha256:<value>")
    raw_checksum = data.get("raw_output_checksum")
    if not isinstance(raw_checksum, str) or not SHA256_RE.match(raw_checksum):
        failures.append("runtime raw_output_checksum must use sha256:<value>")
    normalized = data.get("normalized_output")
    if not isinstance(normalized, dict):
        failures.append("runtime normalized_output must be an object")
    elif expected_operation == "analysis":
        failures.extend(validate_analysis(normalized))
    else:
        if not data.get("source_checksum") or not data.get("export_checksum"):
            failures.append("quality runtime must reference source_checksum and export_checksum")
        failures.extend(validate_quality(normalized))
    return failures


def validate_runtime_evidence(data: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    required = {
        "schema_version",
        "job_id",
        "plan",
        "network_disabled",
        "runtime_download_used",
        "remote_api_used",
        "model_checksum_verified",
        "source_checksum",
        "export_checksum",
        "model_runtime_retry_count",
        "quality_retry_count",
        "analysis_runtime",
        "quality_runtime",
    }
    missing = sorted(required - data.keys())
    if missing:
        return [f"runtime evidence missing fields: {missing}"]
    if data.get("schema_version") != "t022.runtime.evidence.v1":
        failures.append("runtime evidence schema_version is invalid")
    if data.get("plan") not in {"standard", "pro"}:
        failures.append("runtime evidence plan must be standard or pro")
    if data.get("network_disabled") is not True:
        failures.append("strict runtime evidence must prove network_disabled=true")
    if data.get("runtime_download_used") is not False:
        failures.append("strict runtime evidence must prove runtime_download_used=false")
    if data.get("remote_api_used") is not False:
        failures.append("strict runtime evidence must prove remote_api_used=false")
    if data.get("model_checksum_verified") is not True:
        failures.append("strict runtime evidence must prove model checksum verification")
    for key in ("model_runtime_retry_count", "quality_retry_count"):
        value = data.get(key)
        if not isinstance(value, int) or value < 0:
            failures.append(f"{key} must be a non-negative integer")
    analysis_runtime = data.get("analysis_runtime")
    quality_runtime = data.get("quality_runtime")
    if isinstance(analysis_runtime, dict):
        failures.extend(
            f"analysis_runtime: {item}"
            for item in validate_runtime_envelope(analysis_runtime, "analysis")
        )
    else:
        failures.append("analysis_runtime must be an object")
    if isinstance(quality_runtime, dict):
        failures.extend(
            f"quality_runtime: {item}"
            for item in validate_runtime_envelope(quality_runtime, "quality")
        )
    else:
        failures.append("quality_runtime must be an object")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify T-022 local model provider and premium quality pipeline"
    )
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--runtime-evidence")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    failures: list[str] = []

    required_paths = [
        root / "skills" / "local-model-analysis-provider" / "SKILL.md",
        root / "skills" / "model-quality-evaluation-provider" / "SKILL.md",
        root / "harness" / "CONTRACT_T022_MODEL_PROVIDER_PIPELINE.md",
        root / "harness" / "HARNESS_ENV_T022_MODEL_PROVIDER.example",
        root / "harness" / "schemas" / "t022_model_runtime_envelope.schema.json",
        root / "harness" / "schemas" / "t022_runtime_evidence.schema.json",
        root / "harness" / "fixtures" / "t022_model_provider" / "local_model_manifest.json",
        root / "harness" / "fixtures" / "t022_model_provider" / "valid_model_analysis_runtime.json",
        root / "harness" / "fixtures" / "t022_model_provider" / "valid_model_quality_runtime.json",
        root / "harness" / "fixtures" / "t022_model_provider" / "invalid_direct_adjustment_output.json",
        root / "harness" / "fixtures" / "t022_model_provider" / "invalid_remote_config.json",
        root / "harness" / "fixtures" / "t022_model_provider" / "plan_routing_cases.json",
        root / "harness" / "fixtures" / "t022_model_provider" / "controlled_fallback_cases.json",
        root / "harness" / "fixtures" / "t022_model_provider" / "retry_counter_separation.json",
        root / "harness" / "fixtures" / "t022_model_provider" / "module_model_comparison.json",
        root / "harness" / "scripts" / "verify_t022_model_provider_pipeline.py",
    ]
    for path in required_paths:
        if not path.exists():
            failures.append(f"missing T-022 file: {path}")

    regression_paths = [
        root / "harness" / "CONTRACT_LIGHTROOM_APPLY_ADAPTER.md",
        root / "harness" / "CONTRACT_LIGHTROOM_EXPORT_ADAPTER.md",
        root / "harness" / "CONTRACT_T021_DUAL_MODE_CLOSED_LOOP.md",
        root / "harness" / "scripts" / "verify_lightroom_apply_adapter_role.py",
        root / "harness" / "scripts" / "verify_lightroom_export_adapter.py",
        root / "harness" / "scripts" / "verify_t021_dual_mode_closed_loop.py",
        root / "harness" / "schemas" / "t021_analysis_result.schema.json",
        root / "harness" / "schemas" / "t021_quality_result.schema.json",
    ]
    for path in regression_paths:
        if not path.exists():
            failures.append(f"regression preservation failure: missing {path}")

    skill_names = {path.parent.name for path in (root / "skills").glob("*/SKILL.md")}
    missing_baseline = sorted(BASELINE_SKILLS - skill_names)
    if missing_baseline:
        failures.append(f"missing T-021 baseline skills: {missing_baseline}")
    missing_new = sorted(NEW_SKILLS - skill_names)
    if missing_new:
        failures.append(f"missing T-022 skills: {missing_new}")
    if len(skill_names) < 29:
        failures.append(f"expected at least 29 cumulative skills, found {len(skill_names)}")

    fixture_root = root / "harness" / "fixtures" / "t022_model_provider"
    if fixture_root.exists():
        manifest = load_json(fixture_root / "local_model_manifest.json")
        if manifest.get("remote_api_enabled") is not False:
            failures.append("local model manifest must disable remote API")
        if manifest.get("runtime_download_enabled") is not False:
            failures.append("local model manifest must disable runtime download")
        if manifest.get("external_image_url_enabled") is not False:
            failures.append("local model manifest must disable external image URLs")
        if manifest.get("network_required") is not False:
            failures.append("local model manifest must not require network")
        model_root = str(manifest.get("model_root", ""))
        allowed_root = str(manifest.get("allowed_model_root", ""))
        if not model_root or not allowed_root or not model_root.startswith(allowed_root + "/"):
            failures.append("model_root must be under allowed_model_root")
        if not SHA256_RE.match(str(manifest.get("model_checksum", ""))):
            failures.append("local model manifest checksum is invalid")

        invalid_remote = load_json(fixture_root / "invalid_remote_config.json")
        invalid_remote_detected = any(
            [
                invalid_remote.get("remote_api_enabled") is True,
                invalid_remote.get("runtime_download_enabled") is True,
                invalid_remote.get("external_image_url_enabled") is True,
                invalid_remote.get("network_required") is True,
                str(invalid_remote.get("model_root", "")).startswith(("http://", "https://")),
            ]
        )
        if not invalid_remote_detected:
            failures.append("invalid_remote_config does not test forbidden remote behavior")

        analysis_runtime = load_json(fixture_root / "valid_model_analysis_runtime.json")
        failures.extend(
            f"valid_model_analysis_runtime.json: {item}"
            for item in validate_runtime_envelope(analysis_runtime, "analysis")
        )

        quality_runtime = load_json(fixture_root / "valid_model_quality_runtime.json")
        failures.extend(
            f"valid_model_quality_runtime.json: {item}"
            for item in validate_runtime_envelope(quality_runtime, "quality")
        )

        invalid_adjustment = load_json(fixture_root / "invalid_direct_adjustment_output.json")
        forbidden = find_forbidden(invalid_adjustment)
        if not forbidden:
            failures.append("invalid direct-adjustment fixture does not contain a forbidden field")

        routing = load_json(fixture_root / "plan_routing_cases.json").get("cases", [])
        expected_routing = {
            "free": ("module", "module", False, False),
            "lite": ("module", "module", False, False),
            "standard": ("model", "model", True, False),
            "pro": ("model", "model", True, False),
        }
        actual_routing: dict[str, tuple[Any, Any, Any, Any]] = {}
        for case in routing:
            if isinstance(case, dict):
                actual_routing[str(case.get("plan"))] = (
                    case.get("analysis_provider"),
                    case.get("quality_provider"),
                    case.get("allow_model_loading"),
                    case.get("allow_module_fallback"),
                )
        if actual_routing != expected_routing:
            failures.append(f"plan routing mismatch: {actual_routing}")

        fallback_cases = load_json(
            fixture_root / "controlled_fallback_cases.json"
        ).get("cases", [])
        by_name = {
            str(case.get("name")): case for case in fallback_cases if isinstance(case, dict)
        }
        disabled = by_name.get("fallback_disabled_timeout", {})
        if (
            disabled.get("allow_module_fallback") is not False
            or disabled.get("expected_status") != "TECHNICAL_FAILED"
            or disabled.get("fallback_event") is not None
        ):
            failures.append("fallback-disabled case is invalid")
        enabled = by_name.get("fallback_enabled_timeout", {})
        event = enabled.get("fallback_event") if isinstance(enabled, dict) else None
        if not isinstance(event, dict):
            failures.append("fallback-enabled case must include fallback event")
        else:
            expected_event = {
                "requested_provider": "model",
                "executed_provider": "module",
                "fallback_reason": "MODEL_TIMEOUT",
                "degraded_mode": True,
            }
            for key, expected in expected_event.items():
                if event.get(key) != expected:
                    failures.append(f"fallback event mismatch for {key}: {event.get(key)}")
            if not event.get("fallback_event_id"):
                failures.append("fallback event must include fallback_event_id")

        retry = load_json(fixture_root / "retry_counter_separation.json")
        if retry.get("model_runtime_retry_count") != 1:
            failures.append("retry fixture model_runtime_retry_count must be 1")
        if retry.get("quality_retry_count") != 1:
            failures.append("retry fixture quality_retry_count must be 1")
        events = retry.get("events", [])
        if len(events) != 2:
            failures.append("retry fixture must contain two distinct events")
        else:
            runtime_event, quality_event = events
            if runtime_event.get("quality_retry_count_after") != 0:
                failures.append("model runtime retry incorrectly consumed quality retry")
            if quality_event.get("model_runtime_retry_count_after") != 1:
                failures.append("quality retry incorrectly changed model runtime retry count")
        if retry.get("quality_retry_count", 0) > retry.get("max_quality_retries", -1):
            failures.append("quality retry fixture exceeds plan budget")

        comparison = load_json(fixture_root / "module_model_comparison.json")
        if comparison.get("same_source_set") is not True:
            failures.append("module/model comparison must use the same source set")
        if comparison.get("same_lightroom_export_profile") is not True:
            failures.append("module/model comparison must use the same export profile")
        for provider in ("module", "model"):
            metrics = comparison.get(provider)
            if not isinstance(metrics, dict):
                failures.append(f"comparison missing {provider} metrics")
                continue
            for key in (
                "first_pass_approval_rate",
                "final_approval_rate",
                "average_quality_retries",
                "average_processing_ms",
                "peak_memory_mb",
            ):
                if not isinstance(metrics.get(key), (int, float)):
                    failures.append(f"comparison {provider}.{key} must be numeric")

    if args.runtime_evidence:
        evidence_path = Path(args.runtime_evidence).resolve()
        if not evidence_path.exists():
            failures.append(f"runtime evidence does not exist: {evidence_path}")
        else:
            evidence = load_json(evidence_path)
            failures.extend(validate_runtime_evidence(evidence))
    elif args.strict:
        failures.append("--runtime-evidence is required in --strict mode")

    if failures:
        print("FAIL: T-022 verification failed")
        for item in failures:
            print(f" - {item}")
        return 1

    print(
        "PASS: T-022 local-only model routing, runtime envelope, analysis/quality normalization, "
        "fallback policy, retry separation, skill preservation, and regression contracts passed"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
