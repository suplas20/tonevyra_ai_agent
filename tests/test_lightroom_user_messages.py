from tonevyra_agent.core.enums import ErrorCode
from tonevyra_agent.core.errors import TonevyraError
from tonevyra_agent.lightroom.user_messages import is_lightroom_error, lightroom_error_message


def test_lightroom_timeout_message_explains_restart_and_log_location() -> None:
    error = TonevyraError(
        code=ErrorCode.LIGHTROOM_RESPONSE_TIMEOUT,
        message="No apply result was produced.",
    )

    assert is_lightroom_error(error)
    message = lightroom_error_message(error)
    assert "Lightroom" not in message
    assert "LIGHTROOM_RESPONSE_TIMEOUT" in message
    assert "Tonevyra AI" in message
    assert r"runtime\bridge\lightroom_worker_status.txt" in message
    assert "No apply result was produced." in message


def test_non_lightroom_error_is_not_classified_as_lightroom_failure() -> None:
    error = TonevyraError(
        code=ErrorCode.MODEL_LOAD_FAILED,
        message="model missing",
    )

    assert not is_lightroom_error(error)
