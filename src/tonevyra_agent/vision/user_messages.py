"""User-facing local vision model error messages."""

from __future__ import annotations

from tonevyra_agent.core.enums import ErrorCode
from tonevyra_agent.core.errors import TonevyraError


MODEL_ERROR_CODES = {
    ErrorCode.MODEL_LOAD_FAILED,
    ErrorCode.MODEL_INFERENCE_FAILED,
    ErrorCode.MODEL_OUTPUT_INVALID,
}


def is_model_error(error: TonevyraError) -> bool:
    return error.code in MODEL_ERROR_CODES


def model_error_message(error: TonevyraError) -> str:
    if error.code == ErrorCode.MODEL_LOAD_FAILED:
        summary = "로컬 AI 모델을 불러오지 못했습니다."
        action = "모델 파일과 GPU 드라이버, 설치된 모델 런타임을 확인해 주세요."
    elif error.code == ErrorCode.MODEL_OUTPUT_INVALID:
        summary = "로컬 AI 모델의 분석 결과 형식이 올바르지 않습니다."
        action = "해당 사진을 다시 처리하고 같은 문제가 반복되면 로그를 확인해 주세요."
    else:
        summary = "로컬 AI 모델이 사진을 분석하지 못했습니다."
        action = "GPU 메모리와 모델 파일을 확인한 뒤 다시 처리해 주세요."

    return (
        f"{summary}\n\n"
        f"{action}\n\n"
        f"오류 코드: {error.code.value}\n"
        f"상세 정보: {error.message}\n\n"
        "로그: 설치 폴더\\runtime\\tonevyra_inference_worker.stderr.log"
    )
