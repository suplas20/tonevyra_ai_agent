from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tonevyra_agent.core.enums import ErrorCode
from tonevyra_agent.lightroom.schemas import LIGHTROOM_COMMAND_PING, LightroomRequestPayload, LightroomResponsePayload


TINY_JPEG_B64 = "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////2wBDAf//////////////////////////////////////////////////////////////////////////////////////wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAX/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIQAxAAAAH/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAEFAqf/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAEDAQE/ASP/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAECAQE/ASP/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAY/Al//xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAE/IV//2gAMAwEAAgADAAAAEP/EABQRAQAAAAAAAAAAAAAAAAAAABD/2gAIAQMBAT8QH//EABQRAQAAAAAAAAAAAAAAAAAAABD/2gAIAQIBAT8QH//EABQQAQAAAAAAAAAAAAAAAAAAABD/2gAIAQEAAT8QH//Z"


def bridge_dir_from_env() -> Path:
    configured_bridge = os.environ.get("TONEVYRA_BRIDGE_DIR")
    if configured_bridge:
        return _absolute_project_path(configured_bridge)

    configured_runtime = os.environ.get("TONEVYRA_RUNTIME_DIR")
    runtime_dir = _absolute_project_path(configured_runtime) if configured_runtime else PROJECT_ROOT / "runtime"
    return (runtime_dir / "bridge").resolve()


def request_dir(bridge_dir: Path) -> Path:
    return bridge_dir / "requests"


def processing_dir(bridge_dir: Path) -> Path:
    return bridge_dir / "processing"


def response_dir(bridge_dir: Path) -> Path:
    return bridge_dir / "responses"


def error_dir(bridge_dir: Path) -> Path:
    return bridge_dir / "errors"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
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


def create_fake_export(source_path: Path, export_path: Path) -> None:
    if not source_path.exists():
        raise FileNotFoundError(f"source_path does not exist: {source_path}")

    export_path.parent.mkdir(parents=True, exist_ok=True)
    if source_path.suffix.lower() in {".jpg", ".jpeg"}:
        shutil.copy2(source_path, export_path)
        return

    try:
        from PIL import Image, ImageDraw

        image = Image.new("RGB", (1024, 768), (18, 95, 125))
        draw = ImageDraw.Draw(image)
        draw.text((32, 32), "Tonevyra AI Fake Lightroom Export", fill=(240, 250, 255))
        image.save(export_path, quality=92)
    except Exception:
        export_path.write_bytes(base64.b64decode(TINY_JPEG_B64))


def build_response(
    *,
    request_id: str,
    task_id: str,
    status: str,
    export_path: str | None,
    error_code: ErrorCode | str | None = None,
    error_message: str | None = None,
    command: str | None = None,
) -> LightroomResponsePayload:
    return LightroomResponsePayload(
        request_id=request_id,
        task_id=task_id,
        command=command,
        status=status,
        export_path=export_path,
        error_code=error_code.value if isinstance(error_code, ErrorCode) else error_code,
        error_message=error_message,
    )


def process_request(path: Path, *, bridge_dir: Path | None = None, fail: bool = False) -> Path:
    bridge_root = (bridge_dir or bridge_dir_from_env()).resolve()
    processing = processing_dir(bridge_root)
    responses = response_dir(bridge_root)
    errors = error_dir(bridge_root)
    processing.mkdir(parents=True, exist_ok=True)
    responses.mkdir(parents=True, exist_ok=True)
    errors.mkdir(parents=True, exist_ok=True)

    processing_path = processing / path.name
    try:
        path.replace(processing_path)
        raw_request = read_json(processing_path)
        request = LightroomRequestPayload.model_validate(raw_request)
        response_path = responses / f"{request.request_id}.json"

        if request.command == LIGHTROOM_COMMAND_PING:
            response = build_response(
                request_id=request.request_id,
                task_id=request.task_id,
                command=request.command,
                status="success",
                export_path=None,
            )
            write_json_atomic(response_path, response.model_dump(mode="json", exclude_none=True))
            return response_path

        if fail:
            response = build_response(
                request_id=request.request_id,
                task_id=request.task_id,
                command=request.command,
                status="failed",
                export_path=None,
                error_code=ErrorCode.LIGHTROOM_EXPORT_FAILED,
                error_message="Forced fake Lightroom failure.",
            )
            write_json_atomic(response_path, response.model_dump(mode="json"))
            return response_path

        try:
            create_fake_export(Path(request.source_path or ""), Path(request.export_path or ""))
        except Exception as exc:
            response = build_response(
                request_id=request.request_id,
                task_id=request.task_id,
                command=request.command,
                status="failed",
                export_path=None,
                error_code=ErrorCode.LIGHTROOM_EXPORT_FAILED,
                error_message=f"Fake export failed: {exc}",
            )
            write_json_atomic(response_path, response.model_dump(mode="json"))
            return response_path

        response = build_response(
            request_id=request.request_id,
            task_id=request.task_id,
            command=request.command,
            status="success",
            export_path=request.export_path,
        )
        write_json_atomic(response_path, response.model_dump(mode="json"))
        return response_path
    except Exception as exc:
        fallback_id = processing_path.stem
        error_path = errors / f"{fallback_id}.error.json"
        payload = {
            "schema_version": "1.0",
            "request_id": fallback_id,
            "task_id": fallback_id,
            "status": "failed",
            "export_path": None,
            "error_code": ErrorCode.LIGHTROOM_REQUEST_FAILED.value,
            "error_message": str(exc),
        }
        write_json_atomic(error_path, payload)
        return error_path


def process_pending_requests(*, bridge_dir: Path | None = None, fail: bool = False) -> list[Path]:
    bridge_root = (bridge_dir or bridge_dir_from_env()).resolve()
    requests = request_dir(bridge_root)
    requests.mkdir(parents=True, exist_ok=True)
    return [process_request(path, bridge_dir=bridge_root, fail=fail) for path in sorted(requests.glob("*.json"))]


def _absolute_project_path(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate.resolve()


def main() -> int:
    parser = argparse.ArgumentParser(description="Fake Lightroom worker for the Tonevyra AI harness.")
    parser.add_argument("--once", action="store_true", help="Process current request files and exit.")
    parser.add_argument("--bridge-dir", type=Path, default=None, help="Bridge directory containing requests/responses.")
    parser.add_argument("--poll-interval", type=float, default=1.0, help="Polling interval in seconds.")
    parser.add_argument("--fail", action="store_true", help="Force failed responses for testing.")
    args = parser.parse_args()

    bridge_root = (args.bridge_dir or bridge_dir_from_env()).resolve()
    request_dir(bridge_root).mkdir(parents=True, exist_ok=True)
    print(f"Fake Lightroom watching: {request_dir(bridge_root)}")

    while True:
        for response_path in process_pending_requests(bridge_dir=bridge_root, fail=args.fail):
            print(f"processed -> {response_path}")

        if args.once:
            break
        time.sleep(args.poll_interval)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
