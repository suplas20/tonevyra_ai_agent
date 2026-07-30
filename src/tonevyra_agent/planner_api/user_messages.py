"""User-facing Planner API error classification and messages."""

from __future__ import annotations

from tonevyra_agent.core.enums import ErrorCode
from tonevyra_agent.core.errors import TonevyraError


PLANNER_API_ERROR_CODES = {
    ErrorCode.SECURITY_NETWORK_ACCESS_BLOCKED,
    ErrorCode.PLANNER_API_UNAVAILABLE,
    ErrorCode.PLANNER_API_TIMEOUT,
    ErrorCode.PLANNER_API_AUTH_FAILED,
    ErrorCode.PLANNER_API_FORBIDDEN,
    ErrorCode.PLANNER_API_RATE_LIMITED,
    ErrorCode.PLANNER_API_SCHEMA_MISMATCH,
    ErrorCode.PLANNER_API_RESPONSE_INVALID,
    ErrorCode.PLANNER_API_RESPONSE_DIGEST_MISMATCH,
    ErrorCode.PLANNER_API_VERSION_UNSUPPORTED,
    ErrorCode.PLANNER_API_RETRY_EXHAUSTED,
    ErrorCode.PLANNER_SERVICE_NOT_READY,
    ErrorCode.PLANNER_EXECUTION_FAILED,
}


def is_planner_api_error(error: TonevyraError) -> bool:
    return error.code in PLANNER_API_ERROR_CODES


def planner_error_message(error: TonevyraError) -> str:
    if error.code == ErrorCode.PLANNER_API_AUTH_FAILED:
        summary = "플래너 서버 인증에 실패했습니다."
        action = "플래너 API 키 설정을 확인한 후 다시 시도하세요."
    elif error.code == ErrorCode.PLANNER_API_FORBIDDEN:
        summary = "플래너 서버가 이 요청을 허용하지 않았습니다."
        action = "플래너 서버의 계정 권한을 확인하세요."
    elif error.code == ErrorCode.PLANNER_SERVICE_NOT_READY:
        summary = "플래너 서버가 아직 요청을 처리할 준비가 되지 않았습니다."
        action = "잠시 후 다시 시도하거나 서버 상태를 확인하세요."
    elif error.code in {
        ErrorCode.PLANNER_API_UNAVAILABLE,
        ErrorCode.PLANNER_API_TIMEOUT,
        ErrorCode.PLANNER_API_RETRY_EXHAUSTED,
    }:
        summary = "플래너 서버에 연결할 수 없습니다."
        action = "서버 주소와 네트워크 연결을 확인한 후 다시 시도하세요."
    elif error.code == ErrorCode.SECURITY_NETWORK_ACCESS_BLOCKED:
        summary = "플래너 서버 연결 설정이 보안 정책과 일치하지 않습니다."
        action = "HTTPS 주소와 허용된 서버 호스트 설정을 확인하세요."
    else:
        summary = "플래너 서버 응답을 처리할 수 없습니다."
        action = "플래너 서버의 상태와 버전을 확인하세요."

    return (
        f"{summary}\n\n"
        "사진 보정 계획을 생성하지 못했습니다.\n"
        f"{action}\n\n"
        f"오류 코드: {error.code.value}\n"
        f"세부 정보: {error.message}"
    )
