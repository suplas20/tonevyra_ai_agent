from tonevyra_agent.core.enums import ErrorCode
from tonevyra_agent.core.errors import TonevyraError
from tonevyra_agent.vision.user_messages import model_error_message


def test_model_load_error_has_clear_korean_user_message() -> None:
    error = TonevyraError(
        code=ErrorCode.MODEL_LOAD_FAILED,
        message="torch runtime is missing",
        failed_stage="vision",
    )

    message = model_error_message(error)

    assert "로컬 AI 모델을 불러오지 못했습니다" in message
    assert "MODEL_LOAD_FAILED" in message
    assert "torch runtime is missing" in message
    assert "tonevyra_inference_worker.stderr.log" in message
