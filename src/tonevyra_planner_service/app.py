"""FastAPI application for the separate local Planner Service."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from tonevyra_agent.core.enums import ErrorCode
from tonevyra_agent.core.errors import TonevyraError
from tonevyra_agent.planner_api.contracts import (
    ERROR_SCHEMA_VERSION,
    REQUEST_SCHEMA_VERSION,
    RESPONSE_SCHEMA_VERSION,
    PlannerRequest,
    assert_privacy_safe,
    sha256_digest,
    validate_request_digest,
)
from tonevyra_planner_service.config import PlannerServerConfig
from tonevyra_planner_service.engine import PlannerEngine
from tonevyra_planner_service.store import IdempotencyConflictError, IdempotencyStore


class ServiceError(Exception):
    def __init__(self, status_code: int, code: ErrorCode, message: str, *, retryable: bool = False) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.retryable = retryable


def create_app(
    config: PlannerServerConfig | None = None,
    *,
    engine: PlannerEngine | None = None,
) -> FastAPI:
    service_config = config or PlannerServerConfig.from_env()
    planner = engine or PlannerEngine()
    store = IdempotencyStore(service_config.data_dir / "idempotency.json")
    evidence_log = service_config.data_dir / "requests.jsonl"
    semaphore = asyncio.Semaphore(1)
    app = FastAPI(title="Tonevyra Planner Service", version="0.1.0", docs_url=None, redoc_url=None)

    @app.exception_handler(ServiceError)
    async def handle_service_error(request: Request, exc: ServiceError) -> JSONResponse:
        request_id = request.headers.get("X-Request-ID")
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(exc.code, exc.message, request_id=request_id, retryable=exc.retryable),
        )

    @app.get("/health/live")
    async def health_live() -> dict[str, object]:
        return {"status": "live", "service": "tonevyra-planner"}

    @app.get("/health/ready")
    async def health_ready() -> JSONResponse:
        ready = store.ready()
        return JSONResponse(
            status_code=200 if ready else 503,
            content={
                "ready": ready,
                "status": "ready" if ready else "not_ready",
                "planner_version": service_config.planner_version,
                "policy_version": service_config.policy_version,
                "idempotency_store_ready": ready,
            },
        )

    @app.get("/api/v1/version")
    async def version() -> dict[str, str]:
        return {
            "service_version": "0.1.0",
            "planner_version": service_config.planner_version,
            "policy_version": service_config.policy_version,
            "request_schema": REQUEST_SCHEMA_VERSION,
            "response_schema": RESPONSE_SCHEMA_VERSION,
        }

    @app.post("/api/v1/plans")
    async def create_plan(request: Request) -> JSONResponse:
        started = time.monotonic()
        server_request_id = f"srv-{uuid4()}"
        principal_hash = _authenticate(request, service_config.api_key)
        if request.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
            raise ServiceError(415, ErrorCode.PLANNER_API_SCHEMA_MISMATCH, "Content-Type must be application/json.")
        raw = await request.body()
        if len(raw) > service_config.max_request_body_bytes:
            raise ServiceError(413, ErrorCode.PLANNER_REQUEST_TOO_LARGE, "Planner request body is too large.")
        try:
            payload = json.loads(raw.decode("utf-8"))
            planner_request = PlannerRequest.model_validate(payload)
            assert_privacy_safe(payload)
            validate_request_digest(payload)
        except (json.JSONDecodeError, UnicodeDecodeError, ValidationError) as exc:
            raise ServiceError(422, ErrorCode.PLANNER_API_SCHEMA_MISMATCH, "Planner request schema is invalid.") from exc
        except TonevyraError as exc:
            raise ServiceError(422, exc.code, exc.message) from exc

        if request.headers.get("X-Tonevyra-Schema-Version") != REQUEST_SCHEMA_VERSION:
            raise ServiceError(422, ErrorCode.PLANNER_API_SCHEMA_MISMATCH, "Planner schema header is invalid.")
        if request.headers.get("X-Request-ID") != planner_request.request_id:
            raise ServiceError(422, ErrorCode.PLANNER_API_SCHEMA_MISMATCH, "Request ID header does not match the body.")
        idempotency_key = request.headers.get("Idempotency-Key", "").strip()
        if not idempotency_key:
            raise ServiceError(422, ErrorCode.PLANNER_API_SCHEMA_MISMATCH, "Idempotency-Key is required.")

        async with semaphore:
            try:
                response, replayed = store.execute(
                    principal_hash=principal_hash,
                    idempotency_key=idempotency_key,
                    input_digest=planner_request.input_digest,
                    create_response=lambda: _success_payload(
                        planner_request,
                        server_request_id=server_request_id,
                        planner_version=service_config.planner_version,
                        policy_version=service_config.policy_version,
                        create_plan=planner.create_plan,
                    ),
                )
            except IdempotencyConflictError as exc:
                raise ServiceError(409, ErrorCode.IDEMPOTENCY_CONFLICT, "Idempotency key was reused with different input.") from exc
            except Exception as exc:
                raise ServiceError(500, ErrorCode.PLANNER_EXECUTION_FAILED, "Planner execution failed.") from exc

        _append_evidence(
            evidence_log,
            {
                "server_request_id": server_request_id,
                "request_id": planner_request.request_id,
                "principal_hash_prefix": principal_hash[:12],
                "status": "success",
                "replayed": replayed,
                "latency_ms": round((time.monotonic() - started) * 1000, 2),
                "planner_version": service_config.planner_version,
                "policy_version": service_config.policy_version,
            },
        )
        return JSONResponse(status_code=200, content=response)

    return app


def _authenticate(request: Request, expected_key: str) -> str:
    value = request.headers.get("Authorization", "")
    supplied = value[7:] if value.startswith("Bearer ") else ""
    if not supplied or not hmac.compare_digest(supplied, expected_key):
        raise ServiceError(401, ErrorCode.PLANNER_API_AUTH_FAILED, "Planner API authentication failed.")
    return hashlib.sha256(supplied.encode("utf-8")).hexdigest()


def _success_payload(
    request: PlannerRequest,
    *,
    server_request_id: str,
    planner_version: str,
    policy_version: str,
    create_plan: Callable[[PlannerRequest], dict[str, Any]],
) -> dict[str, Any]:
    plan = create_plan(request)
    assert_privacy_safe(plan, response=True)
    return {
        "schema_version": RESPONSE_SCHEMA_VERSION,
        "status": "success",
        "request_id": request.request_id,
        "server_request_id": server_request_id,
        "planner_version": planner_version,
        "policy_version": policy_version,
        "input_digest": request.input_digest,
        "replayed": False,
        "plan": plan,
        "plan_digest": sha256_digest(plan),
    }


def _error_payload(
    code: ErrorCode,
    message: str,
    *,
    request_id: str | None,
    retryable: bool,
) -> dict[str, Any]:
    return {
        "schema_version": ERROR_SCHEMA_VERSION,
        "status": "error",
        "request_id": request_id,
        "server_request_id": None,
        "error": {
            "code": code.value,
            "message": message,
            "retryable": retryable,
            "retry_after_seconds": None,
        },
    }


def _append_evidence(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


app = create_app()
