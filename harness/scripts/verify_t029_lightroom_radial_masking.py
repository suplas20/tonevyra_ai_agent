#!/usr/bin/env python3
"""Static, runtime, and strict live-evidence verifier for T-029 native masking."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

TICKET = "T029"
RUNTIME_SCHEMA = "t029.runtime.evidence.v1"
LIVE_SCHEMA = "t029.live.evidence.v1"
BASELINE_SKILL_COUNT = 41
EXPECTED_SKILL_COUNT = 43
REQUIRED_SKILLS = {"lightroom-radial-mask-execution", "radial-mask-template-library"}
REQUIRED_FILES = [
    ".docs/t029/T-029_Lightroom_Native_Mask_and_Radial_Fallback_Work_Order.md",
    ".docs/t029/T-029_Implementation_Specification.md",
    ".docs/t029/T-029_Codex_Prompt.md",
    ".docs/t029/T-029_Lightroom_Live_Test_Checklist.md",
    ".docs/t029/T-029_Seed_Radial_Preset_Preparation_Guide.md",
    ".docs/reports/T029_DOCUMENT_HARNESS_SKILL_UPDATE_REPORT.md",
    "harness/CONTRACT_T029_LIGHTROOM_RADIAL_MASKING.md",
    "harness/HARNESS_ENV_T029_LIGHTROOM_RADIAL_MASKING.example",
    "harness/T029_RADIAL_MASKING_UPDATE_MANIFEST.json",
    "harness/schemas/t029_mask_apply_request.schema.json",
    "harness/schemas/t029_mask_apply_result.schema.json",
    "harness/schemas/t029_runtime_evidence.schema.json",
    "harness/schemas/t029_live_evidence.schema.json",
    "skills/T029_SKILL_INVENTORY.json",
    "harness/scripts/run_t029_radial_masking_runtime.py",
    "harness/fixtures/images/t029_background_person_red_recovery.jpg",
]
FORBIDDEN_PROVIDER_KEYS = {
    "plugin_command",
    "preset_path",
    "template_path",
    "lightroom_mask_payload",
    "final_develop_settings",
    "execute_mask",
    "mouse_coordinates",
}
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_forbidden(value: Any, prefix: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            path = f"{prefix}.{key}"
            if key in FORBIDDEN_PROVIDER_KEYS:
                found.append(path)
            found.extend(find_forbidden(nested, path))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            found.extend(find_forbidden(nested, f"{prefix}[{index}]"))
    return found


def validate_geometry(g: Any, label: str) -> list[str]:
    failures: list[str] = []
    if not isinstance(g, dict):
        return [f"{label} must be an object"]
    if g.get("coordinate_space") != "oriented_normalized_image":
        failures.append(f"{label}.coordinate_space invalid")
    for key in ("center_x", "center_y"):
        value = g.get(key)
        if not isinstance(value, (int, float)) or not 0 <= value <= 1:
            failures.append(f"{label}.{key} must be in 0..1")
    for key in ("width", "height"):
        value = g.get(key)
        if not isinstance(value, (int, float)) or not 0 < value <= 1:
            failures.append(f"{label}.{key} must be in (0,1]")
    rotation = g.get("rotation_deg")
    if not isinstance(rotation, (int, float)) or not -180 <= rotation <= 180:
        failures.append(f"{label}.rotation_deg invalid")
    return failures


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if manifest.get("schema_version") != "t029.radial_template_manifest.v1":
        failures.append("manifest schema_version invalid")
    library_version = manifest.get("library_version")
    if not SHA256_RE.match(str(manifest.get("seed_signature", ""))):
        failures.append("manifest seed_signature must be SHA-256")
    templates = manifest.get("templates")
    if not isinstance(templates, list) or not templates:
        return failures + ["manifest templates missing"]
    ids: set[str] = set()
    for index, template in enumerate(templates):
        tid = template.get("template_id")
        if not isinstance(tid, str) or not tid:
            failures.append(f"manifest template[{index}] missing template_id")
            continue
        if tid in ids:
            failures.append(f"duplicate template_id: {tid}")
        ids.add(tid)
        if template.get("library_version") != library_version:
            failures.append(f"template {tid} library_version mismatch")
        rel = str(template.get("relative_path", ""))
        if not rel or Path(rel).is_absolute() or ".." in Path(rel).parts:
            failures.append(f"template {tid} relative_path unsafe")
        if not SHA256_RE.match(str(template.get("sha256", ""))):
            failures.append(f"template {tid} sha256 invalid")
        failures.extend(validate_geometry(template.get("geometry"), f"template[{tid}].geometry"))
        feather = template.get("feather")
        if not isinstance(feather, (int, float)) or not 0 <= feather <= 1:
            failures.append(f"template {tid} feather invalid")
    return failures


def validate_adjustments(adjustments: Any, label: str) -> list[str]:
    bounds = {
        "Exposure2012": (-1.0, 1.0),
        "Shadows2012": (-40.0, 40.0),
        "Temperature": (-20.0, 20.0),
        "Tint": (-20.0, 20.0),
        "Saturation": (-35.0, 35.0),
        "Vibrance": (-30.0, 30.0),
        "Texture": (-20.0, 20.0),
        "Clarity2012": (-20.0, 20.0),
        "Dehaze": (-15.0, 15.0),
    }
    failures: list[str] = []
    if not isinstance(adjustments, dict) or not adjustments:
        return [f"{label} missing"]
    for key, value in adjustments.items():
        if key not in bounds:
            failures.append(f"{label}.{key} unsupported")
        elif not isinstance(value, (int, float)) or not bounds[key][0] <= value <= bounds[key][1]:
            failures.append(f"{label}.{key} outside bounds {bounds[key]}")
    return failures


def validate_request(request: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if request.get("schema_version") != "t029.mask_apply.request.v1":
        failures.append("request schema_version invalid")
    if request.get("command") != "APPLY_LIGHTROOM_MASK_PLAN":
        failures.append("request command invalid")
    if not request.get("source_path"):
        failures.append("request source_path missing")
    if len(str(request.get("idempotency_key", ""))) < 8:
        failures.append("request idempotency_key invalid")
    plan = request.get("mask_plan", {})
    if plan.get("schema_version") != "t029.mask_plan.v1":
        failures.append("mask plan schema invalid")
    operations = plan.get("operations")
    if not isinstance(operations, list) or not operations:
        return failures + ["mask plan operations missing"]
    for index, operation in enumerate(operations):
        label = f"operation[{index}]"
        strategy = operation.get("strategy")
        if strategy not in {"native_ai", "skip_local", "review_required"}:
            failures.append(f"{label}.strategy invalid")
        if "template_ref" in operation or "fit_evidence" in operation:
            failures.append(f"{label} must not contain radial template fields")
        if not str(operation.get("mask_name", "")).startswith("Tonevyra::T029::"):
            failures.append(f"{label}.mask_name namespace invalid")
        failures.extend(validate_geometry(operation.get("predicted_geometry"), f"{label}.predicted_geometry"))
        failures.extend(validate_adjustments(operation.get("local_adjustments"), f"{label}.local_adjustments"))
        safety = operation.get("safety", {})
        if safety.get("preserve_user_masks") is not True or safety.get("non_destructive_required") is not True:
            failures.append(f"{label}.safety must preserve user masks and be non-destructive")
        native = operation.get("native_assessment", {})
        if strategy == "native_ai" and native.get("target_detected") is not True:
            failures.append(f"{label} native_ai requires target_detected=true")
        if strategy in {"skip_local", "review_required"} and native.get("target_detected") is not False:
            failures.append(f"{label} skip/review fallback requires target_detected=false")
    return failures


def validate_result(result: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if result.get("schema_version") != "t029.mask_apply.result.v1":
        failures.append("result schema_version invalid")
    if result.get("status") not in {"applied", "partial", "skipped", "failed"}:
        failures.append("result status invalid")
    capability = result.get("capability_snapshot", {})
    if capability.get("native_mask_command_supported") is not True:
        failures.append("result capability requires native_mask_command_supported=true")
    if not result.get("pre_apply_snapshot_ref") or not result.get("post_apply_snapshot_ref"):
        failures.append("result pre/post snapshot refs required")
    operations = result.get("operation_results")
    if not isinstance(operations, list) or not operations:
        return failures + ["result operation_results missing"]
    for index, operation in enumerate(operations):
        label = f"result.operation[{index}]"
        if not str(operation.get("mask_name", "")).startswith("Tonevyra::T029::"):
            failures.append(f"{label}.mask_name invalid")
        if operation.get("strategy") == "radial_template":
            failures.append(f"{label} radial_template is excluded from T-029")
    return failures


def validate_static(root: Path) -> list[str]:
    failures: list[str] = []
    for rel in REQUIRED_FILES:
        if not (root / rel).is_file():
            failures.append(f"missing required file: {rel}")
    skill_dirs = {path.parent.name for path in (root / "skills").glob("*/SKILL.md")}
    if len(skill_dirs) < BASELINE_SKILL_COUNT:
        failures.append(f"baseline skill count too small: {len(skill_dirs)} < {BASELINE_SKILL_COUNT}")
    missing_skills = sorted(REQUIRED_SKILLS - skill_dirs)
    if missing_skills:
        failures.append(f"missing T-029 skills: {missing_skills}")
    if len(skill_dirs) < EXPECTED_SKILL_COUNT:
        failures.append(f"expected at least {EXPECTED_SKILL_COUNT} cumulative skills, found {len(skill_dirs)}")

    try:
        inventory = load_json(root / "skills" / "T029_SKILL_INVENTORY.json")
        if inventory.get("baseline_skill_count") != BASELINE_SKILL_COUNT:
            failures.append("T-029 inventory baseline skill count mismatch")
        if inventory.get("expected_total_skill_count") != EXPECTED_SKILL_COUNT:
            failures.append("T-029 inventory total skill count mismatch")
        inventory_skills = set(inventory.get("all_skills", []))
        if len(inventory_skills) != EXPECTED_SKILL_COUNT or not inventory_skills.issubset(skill_dirs):
            failures.append("T-029 inventory snapshot is not preserved in current SKILL.md directories")
    except Exception as exc:
        failures.append(f"invalid T-029 skill inventory: {exc}")

    try:
        update_manifest = load_json(root / "harness" / "T029_RADIAL_MASKING_UPDATE_MANIFEST.json")
        preservation = update_manifest.get("preservation_result", {})
        if preservation.get("baseline_preserved") is not True or preservation.get("removed_file_count") != 0:
            failures.append("T-029 update manifest reports removed baseline files")
        if update_manifest.get("skill_inventory", {}).get("total") != EXPECTED_SKILL_COUNT:
            failures.append("T-029 update manifest skill total mismatch")
        for rel, expected_hash in update_manifest.get("core_file_sha256", {}).items():
            candidate = root / rel
            if not candidate.is_file():
                failures.append(f"T-029 manifest core file missing: {rel}")
            elif sha256_file(candidate) != expected_hash:
                failures.append(f"T-029 manifest core checksum mismatch: {rel}")
    except Exception as exc:
        failures.append(f"invalid T-029 update manifest: {exc}")

    for rel in (
        "harness/schemas/t029_mask_apply_request.schema.json",
        "harness/schemas/t029_mask_apply_result.schema.json",
        "harness/schemas/t029_runtime_evidence.schema.json",
        "harness/schemas/t029_live_evidence.schema.json",
    ):
        try:
            schema = load_json(root / rel)
            if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
                failures.append(f"schema draft mismatch: {rel}")
        except Exception as exc:
            failures.append(f"invalid schema JSON {rel}: {exc}")

    fixture_root = root / "harness" / "fixtures" / "t029_radial_masking"
    if not fixture_root.is_dir():
        return failures + ["missing T-029 fixture directory"]
    for path in sorted(fixture_root.glob("*.json")):
        try:
            data = load_json(path)
        except Exception as exc:
            failures.append(f"invalid JSON {path.name}: {exc}")
            continue
        if path.name == "invalid_model_direct_plugin_command.json":
            if not find_forbidden(data.get("provider_output", {})):
                failures.append("direct-provider-command negative fixture has no forbidden keys")

    try:
        request = load_json(fixture_root / "valid_mask_apply_request.json")
        failures.extend(validate_request(request))
        result = load_json(fixture_root / "valid_mask_apply_result.json")
        failures.extend(validate_result(result))
        case = load_json(fixture_root / "background_person_red_recovery_case.json")
        if case.get("native_assessment", {}).get("target_detected") is not False:
            failures.append("background-person fixture must prove native target detection failure")
        if case.get("expected_strategy") not in {"skip_local", "review_required"}:
            failures.append("background-person fixture must expect safe skip_local/review_required")
        if case.get("expected_template_id") is not None:
            failures.append("background-person fixture must not expect a radial template")
    except Exception as exc:
        failures.append(f"fixture validation failed: {exc}")

    invalid_geometry = load_json(fixture_root / "invalid_out_of_bounds_geometry.json")
    if not validate_geometry(invalid_geometry.get("geometry"), "invalid_geometry"):
        failures.append("out-of-bounds geometry fixture is not invalid")
    invalid_adjustments = load_json(fixture_root / "invalid_unbounded_adjustment.json")
    if not validate_adjustments(invalid_adjustments.get("local_adjustments"), "invalid_adjustments"):
        failures.append("unbounded adjustment fixture is not invalid")
    unknown = load_json(fixture_root / "invalid_unknown_template_id.json")
    if "template_ref" not in unknown:
        failures.append("template negative fixture must retain a forbidden template_ref marker")

    image = root / "harness" / "fixtures" / "images" / "t029_background_person_red_recovery.jpg"
    if image.is_file() and image.stat().st_size <= 0:
        failures.append("T-029 source image fixture is empty")
    return failures


def validate_runtime(path: Path) -> list[str]:
    data = load_json(path)
    failures: list[str] = []
    if data.get("schema_version") != RUNTIME_SCHEMA:
        failures.append(f"runtime schema must be {RUNTIME_SCHEMA}")
    if data.get("ticket") != TICKET:
        failures.append("runtime ticket must be T029")
    if data.get("completed") is not True:
        failures.append("runtime completed must be true")
    for field in (
        "planning_harness_passed",
        "clamps_valid",
        "idempotent_replay",
        "user_masks_preserved",
        "regressions_passed",
    ):
        if data.get(field) is not True:
            failures.append(f"runtime {field} must be true")
    if data.get("selected_strategy") not in {"native_ai", "skip_local", "review_required"}:
        failures.append("runtime selected_strategy must be native_ai/skip_local/review_required")
    if data.get("selected_strategy") in {"skip_local", "review_required"}:
        if data.get("native_target_detected") is not False:
            failures.append("runtime skip/review requires native_target_detected=false")
        if data.get("native_detection_failed_safely") is not True:
            failures.append("runtime native_detection_failed_safely must be true")
    if data.get("selected_strategy") == "native_ai" and data.get("native_target_detected") is not True:
        failures.append("runtime native_ai requires native_target_detected=true")
    if data.get("selected_template_id") is not None or data.get("expected_template_id") is not None:
        failures.append("runtime must not contain selected/expected radial template IDs")
    if not SHA256_RE.match(str(data.get("source_sha256", ""))):
        failures.append("runtime source_sha256 missing/invalid")
    return failures


def validate_live(path: Path, root: Path) -> list[str]:
    data = load_json(path)
    failures: list[str] = []
    if data.get("schema_version") != LIVE_SCHEMA:
        failures.append(f"live schema must be {LIVE_SCHEMA}")
    if data.get("ticket") != TICKET:
        failures.append("live ticket must be T029")
    required_true = (
        "phase0_passed",
        "native_mask_command_supported",
        "native_target_detected",
        "mask_applied_without_ui_drawing",
        "target_alignment_passed",
        "red_recovery_passed",
        "background_spill_passed",
        "idempotent_replay_passed",
        "user_masks_preserved",
        "rollback_verified",
        "export_file_exists",
        "quality_evidence_present",
        "regressions_passed",
    )
    for field in required_true:
        if data.get(field) is not True:
            failures.append(f"live {field} must be true")
    for field in ("lightroom_version", "plugin_version"):
        if not data.get(field):
            failures.append(f"live {field} required")
    export_path = data.get("export_path")
    if export_path:
        candidate = Path(export_path)
        if not candidate.is_absolute():
            candidate = root / candidate
        if not candidate.is_file() or candidate.stat().st_size <= 0:
            failures.append(f"live export_path missing or empty: {candidate}")
    else:
        failures.append("live export_path required")
    evidence_paths = data.get("evidence_paths")
    if not isinstance(evidence_paths, list) or not evidence_paths:
        failures.append("live evidence_paths required")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify T-029 radial masking contract and evidence.")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--runtime-evidence", type=Path)
    parser.add_argument("--live-evidence", type=Path)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    root = args.project_root.resolve()
    failures = validate_static(root)
    if args.runtime_evidence:
        failures.extend(validate_runtime(args.runtime_evidence))
    elif args.strict:
        failures.append("--strict requires --runtime-evidence")
    if args.live_evidence:
        failures.extend(validate_live(args.live_evidence, root))
    elif args.strict:
        failures.append("--strict requires --live-evidence from a real Lightroom run")

    if failures:
        print(f"FAIL: {TICKET}")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(f"PASS: {TICKET} static contract and fixtures")
    if args.runtime_evidence:
        print(f"PASS: {TICKET} deterministic runtime evidence")
    if args.live_evidence:
        print(f"PASS: {TICKET} real Lightroom live evidence")
    return 0


if __name__ == "__main__":
    sys.exit(main())
