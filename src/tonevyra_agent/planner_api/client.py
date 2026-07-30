"""Bounded HTTPS client for the T-032 Planner API."""

from __future__ import annotations

import json
import socket
import ssl
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPSHandler, OpenerDirector, Request, build_opener

from tonevyra_agent.core.config import Settings, get_settings
from tonevyra_agent.core.enums import ErrorCode, Stage
from tonevyra_agent.core.errors import TonevyraError
from tonevyra_agent.planner_api.contracts import (
    REQUEST_SCHEMA_VERSION,
    PlannerRequest,
    canonical_json_bytes,
)


RETRYABLE_HTTP_STATUS = {408, 429, 500, 502, 503, 504}
NON_RETRYABLE_HTTP_STATUS = {400, 401, 403, 404, 409, 413, 422}


@dataclass(frozen=True)
class PlannerApiAttempt:
    attempt: int
    outcome: str
    http_status: int | None = None
    error_code: str | None = None
    message: str | None = None
    retryable: bool = False
    retry_after_seconds: float | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "attempt": self.attempt,
            "outcome": self.outcome,
            "http_status": self.http_status,
            "error_code": self.error_code,
            "message": self.message,
            "retryable": self.retryable,
            "retry_after_seconds": self.retry_after_seconds,
        }


@dataclass(frozen=True)
class PlannerApiResult:
    response_payload: dict[str, Any]
    attempts: list[PlannerApiAttempt]


class NoRedirectHttpsHandler(HTTPSHandler):
    def http_error_301(self, req, fp, code, msg, headers):  # type: ignore[no-untyped-def]
        raise HTTPError(req.full_url, code, msg, headers, fp)

    http_error_302 = http_error_303 = http_error_307 = http_error_308 = http_error_301


class PlannerApiClient:
    """Call the remote Planner API with bounded retry and no local fallback."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.base_url = self.settings.planner_api_base_url.rstrip("/")
        self._opener = self._build_opener()
        self.last_attempts: list[PlannerApiAttempt] = []

    def create_plan(self, *, request: PlannerRequest, idempotency_key: str) -> PlannerApiResult:
        self._validate_config()
        self.last_attempts = []
        body = request.model_dump(mode="json")
        encoded = canonical_json_bytes(body)
        if len(encoded) > self.settings.planner_api_max_request_body_bytes:
            raise TonevyraError(
                code=ErrorCode.PLANNER_REQUEST_TOO_LARGE,
                message="Planner API request exceeds configured body limit.",
                failed_stage=Stage.CORRECTION_PLAN.value,
            )

        attempts: list[PlannerApiAttempt] = []
        total_attempts = max(1, int(self.settings.planner_api_total_attempts))
        for attempt_number in range(1, total_attempts + 1):
            try:
                payload = self._send_once(body=encoded, request=request, idempotency_key=idempotency_key)
                attempts.append(PlannerApiAttempt(attempt=attempt_number, outcome="success", http_status=200))
                self.last_attempts = attempts
                return PlannerApiResult(response_payload=payload, attempts=attempts)
            except _PlannerHttpFailure as failure:
                attempts.append(failure.to_attempt(attempt_number))
                if not failure.retryable or attempt_number >= total_attempts:
                    self._raise_failure(failure, attempts=attempts)
                self._sleep_before_retry(failure, attempt_number)
            except (TimeoutError, socket.timeout) as exc:
                failure = _PlannerHttpFailure(
                    error_code=ErrorCode.PLANNER_API_TIMEOUT,
                    message=f"Planner API request timed out: {exc}",
                    retryable=True,
                )
                attempts.append(failure.to_attempt(attempt_number))
                if attempt_number >= total_attempts:
                    self._raise_failure(failure, attempts=attempts)
                self._sleep_before_retry(failure, attempt_number)
            except URLError as exc:
                failure = _PlannerHttpFailure(
                    error_code=ErrorCode.PLANNER_API_UNAVAILABLE,
                    message=f"Planner API is unavailable: {exc.reason}",
                    retryable=True,
                )
                attempts.append(failure.to_attempt(attempt_number))
                if attempt_number >= total_attempts:
                    self._raise_failure(failure, attempts=attempts)
                self._sleep_before_retry(failure, attempt_number)

        raise TonevyraError(
            code=ErrorCode.PLANNER_API_RETRY_EXHAUSTED,
            message="Planner API retry budget exhausted.",
            failed_stage=Stage.CORRECTION_PLAN.value,
        )

    def check_readiness(self) -> dict[str, Any]:
        """Verify the configured Planner Service readiness endpoint once."""

        self._validate_config()
        request = Request(
            f"{self.base_url}/health/ready",
            method="GET",
            headers={
                "Authorization": f"Bearer {self.settings.planner_api_key}",
                "Accept": "application/json",
            },
        )
        timeout = max(0.5, float(self.settings.planner_api_connect_timeout_seconds))
        try:
            with self._opener.open(request, timeout=timeout) as response:
                content_type = response.headers.get("Content-Type", "")
                raw = response.read(self.settings.planner_api_max_request_body_bytes + 1)
                if "application/json" not in content_type.lower():
                    raise TonevyraError(
                        code=ErrorCode.PLANNER_API_RESPONSE_INVALID,
                        message=f"Planner readiness endpoint returned non-JSON content type: {content_type}",
                        failed_stage=Stage.CORRECTION_PLAN.value,
                    )
                payload = json.loads(raw.decode("utf-8"))
                if not isinstance(payload, dict):
                    raise TonevyraError(
                        code=ErrorCode.PLANNER_API_RESPONSE_INVALID,
                        message="Planner readiness endpoint returned an invalid response body.",
                        failed_stage=Stage.CORRECTION_PLAN.value,
                    )
                if payload.get("ready") is False or str(payload.get("status", "")).lower() in {
                    "not_ready",
                    "unavailable",
                }:
                    raise TonevyraError(
                        code=ErrorCode.PLANNER_SERVICE_NOT_READY,
                        message="Planner readiness endpoint reported that the service is not ready.",
                        failed_stage=Stage.CORRECTION_PLAN.value,
                    )
                return payload
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise TonevyraError(
                code=ErrorCode.PLANNER_API_RESPONSE_INVALID,
                message="Planner readiness endpoint returned invalid JSON.",
                failed_stage=Stage.CORRECTION_PLAN.value,
            ) from exc
        except HTTPError as exc:
            failure = self._http_failure(exc)
            code = ErrorCode.PLANNER_SERVICE_NOT_READY if exc.code == 503 else failure.error_code
            raise TonevyraError(
                code=code,
                message=failure.message,
                failed_stage=Stage.CORRECTION_PLAN.value,
            ) from exc
        except (TimeoutError, socket.timeout) as exc:
            raise TonevyraError(
                code=ErrorCode.PLANNER_API_TIMEOUT,
                message=f"Planner readiness check timed out: {exc}",
                failed_stage=Stage.CORRECTION_PLAN.value,
            ) from exc
        except URLError as exc:
            raise TonevyraError(
                code=ErrorCode.PLANNER_API_UNAVAILABLE,
                message=f"Planner API is unavailable: {exc.reason}",
                failed_stage=Stage.CORRECTION_PLAN.value,
            ) from exc

    def _send_once(self, *, body: bytes, request: PlannerRequest, idempotency_key: str) -> dict[str, Any]:
        http_request = Request(
            f"{self.base_url}/api/v1/plans",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.settings.planner_api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-Request-ID": request.request_id,
                "Idempotency-Key": idempotency_key,
                "X-Tonevyra-Schema-Version": REQUEST_SCHEMA_VERSION,
            },
        )
        try:
            with self._opener.open(http_request, timeout=float(self.settings.planner_api_read_timeout_seconds)) as response:
                content_type = response.headers.get("Content-Type", "")
                raw = response.read(self.settings.planner_api_max_request_body_bytes + 1)
                if len(raw) > self.settings.planner_api_max_request_body_bytes:
                    raise _PlannerHttpFailure(
                        error_code=ErrorCode.PLANNER_REQUEST_TOO_LARGE,
                        message="Planner API response exceeded configured body limit.",
                        retryable=False,
                        http_status=response.status,
                    )
                if "application/json" not in content_type.lower():
                    raise _PlannerHttpFailure(
                        error_code=ErrorCode.PLANNER_API_RESPONSE_INVALID,
                        message=f"Planner API returned non-JSON content type: {content_type}",
                        retryable=False,
                        http_status=response.status,
                    )
                return json.loads(raw.decode("utf-8"))
        except HTTPError as exc:
            raise self._http_failure(exc) from exc

    def _http_failure(self, exc: HTTPError) -> _PlannerHttpFailure:
        retryable = exc.code in RETRYABLE_HTTP_STATUS
        error_code = _error_code_for_status(exc.code)
        retry_after = _retry_after_seconds(exc.headers.get("Retry-After"), self.settings.planner_api_max_retry_after_seconds)
        message = f"Planner API returned HTTP {exc.code}."
        try:
            payload = json.loads(exc.read().decode("utf-8"))
            detail = payload.get("error", {}) if isinstance(payload, dict) else {}
            if isinstance(detail, dict):
                message = str(detail.get("message") or message)
                code = str(detail.get("code") or "")
                if code and code in ErrorCode.__members__:
                    error_code = ErrorCode[code]
                retryable = bool(detail.get("retryable", retryable))
                retry_after = _retry_after_seconds(
                    detail.get("retry_after_seconds", retry_after),
                    self.settings.planner_api_max_retry_after_seconds,
                )
        except Exception:
            pass
        if exc.code in NON_RETRYABLE_HTTP_STATUS:
            retryable = False
        return _PlannerHttpFailure(
            error_code=error_code,
            message=message,
            retryable=retryable,
            http_status=exc.code,
            retry_after_seconds=retry_after,
        )

    def _validate_config(self) -> None:
        if not self.base_url:
            raise TonevyraError(
                code=ErrorCode.PLANNER_API_UNAVAILABLE,
                message="TONEVYRA_PLANNER_API_BASE_URL is required for T-032 Planner API mode.",
                failed_stage=Stage.CORRECTION_PLAN.value,
            )
        if not self.settings.planner_api_key:
            raise TonevyraError(
                code=ErrorCode.PLANNER_API_AUTH_FAILED,
                message="TONEVYRA_PLANNER_API_KEY is required for T-032 Planner API mode.",
                failed_stage=Stage.CORRECTION_PLAN.value,
            )
        parsed = urlparse(self.base_url)
        local_server_mode = (self.settings.planner_api_mode or "api").lower() == "local_server"
        loopback_http = parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        if parsed.scheme != "https" and not (local_server_mode and loopback_http):
            raise TonevyraError(
                code=ErrorCode.SECURITY_NETWORK_ACCESS_BLOCKED,
                message="Planner API base URL must use HTTPS; local_server mode permits loopback HTTP only.",
                failed_stage=Stage.CORRECTION_PLAN.value,
            )
        allowed_hosts = {
            item.strip()
            for item in (self.settings.planner_api_allowed_host or str(parsed.hostname or "")).split(",")
            if item.strip()
        }
        if parsed.hostname not in allowed_hosts:
            raise TonevyraError(
                code=ErrorCode.SECURITY_NETWORK_ACCESS_BLOCKED,
                message="Planner API host is not the configured allowlisted host.",
                failed_stage=Stage.CORRECTION_PLAN.value,
            )

    def _build_opener(self) -> OpenerDirector:
        cafile = None
        parsed = urlparse(self.base_url)
        if parsed.scheme == "https" and self.settings.planner_api_ca_bundle is not None:
            cafile = str(self.settings.project_path(self.settings.planner_api_ca_bundle).resolve())
        context = ssl.create_default_context(cafile=cafile)
        return build_opener(NoRedirectHttpsHandler(context=context))

    def _sleep_before_retry(self, failure: _PlannerHttpFailure, attempt_number: int) -> None:
        retry_after = failure.retry_after_seconds
        if retry_after is None:
            retry_after = min(2 ** (attempt_number - 1), self.settings.planner_api_max_retry_after_seconds)
        time.sleep(max(0.0, float(retry_after)))

    def _raise_failure(self, failure: _PlannerHttpFailure, *, attempts: list[PlannerApiAttempt]) -> None:
        self.last_attempts = attempts
        if failure.retryable:
            raise TonevyraError(
                code=ErrorCode.PLANNER_API_RETRY_EXHAUSTED,
                message=f"Planner API retry budget exhausted after {len(attempts)} attempt(s): {failure.message}",
                failed_stage=Stage.CORRECTION_PLAN.value,
            )
        raise TonevyraError(
            code=failure.error_code,
            message=failure.message,
            failed_stage=Stage.CORRECTION_PLAN.value,
        )


@dataclass(frozen=True)
class _PlannerHttpFailure(Exception):
    error_code: ErrorCode
    message: str
    retryable: bool
    http_status: int | None = None
    retry_after_seconds: float | None = None

    def to_attempt(self, attempt_number: int) -> PlannerApiAttempt:
        return PlannerApiAttempt(
            attempt=attempt_number,
            outcome="failure",
            http_status=self.http_status,
            error_code=self.error_code.value,
            message=self.message,
            retryable=self.retryable,
            retry_after_seconds=self.retry_after_seconds,
        )


def _error_code_for_status(status: int) -> ErrorCode:
    return {
        401: ErrorCode.PLANNER_API_AUTH_FAILED,
        403: ErrorCode.PLANNER_API_FORBIDDEN,
        409: ErrorCode.IDEMPOTENCY_CONFLICT,
        413: ErrorCode.PLANNER_REQUEST_TOO_LARGE,
        422: ErrorCode.PLANNER_API_SCHEMA_MISMATCH,
        429: ErrorCode.PLANNER_API_RATE_LIMITED,
        503: ErrorCode.PLANNER_SERVICE_NOT_READY,
    }.get(status, ErrorCode.PLANNER_API_UNAVAILABLE if status >= 500 else ErrorCode.PLANNER_API_RESPONSE_INVALID)


def _retry_after_seconds(value: Any, cap: float) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(parsed, float(cap)))
