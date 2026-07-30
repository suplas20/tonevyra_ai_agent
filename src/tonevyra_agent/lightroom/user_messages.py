"""User-facing Lightroom bridge error messages."""

from __future__ import annotations

from tonevyra_agent.core.enums import ErrorCode
from tonevyra_agent.core.errors import TonevyraError


LIGHTROOM_ERROR_CODES = {
    ErrorCode.LIGHTROOM_REQUEST_FAILED,
    ErrorCode.LIGHTROOM_RESPONSE_TIMEOUT,
    ErrorCode.LIGHTROOM_EXPORT_FAILED,
    ErrorCode.EXPORT_FILE_MISSING,
}


def is_lightroom_error(error: TonevyraError) -> bool:
    return error.code in LIGHTROOM_ERROR_CODES


def lightroom_error_message(error: TonevyraError) -> str:
    if error.code == ErrorCode.LIGHTROOM_RESPONSE_TIMEOUT:
        summary = "\ub77c\uc774\ud2b8\ub8f8 \ud50c\ub7ec\uadf8\uc778\uc774 \ubcf4\uc815 \uc694\uccad\uc5d0 \uc751\ub2f5\ud558\uc9c0 \uc54a\uc558\uc2b5\ub2c8\ub2e4."
        action = (
            "\ub77c\uc774\ud2b8\ub8f8 \ud074\ub798\uc2dd\uc744 \uc644\uc804\ud788 \uc885\ub8cc\ud55c \ub4a4 \ub2e4\uc2dc \uc2e4\ud589\ud558\uace0, "
            "\ud50c\ub7ec\uadf8\uc778 \uad00\ub9ac\uc790\uc5d0\uc11c Tonevyra AI\uac00 \ud65c\uc131\ud654\ub418\uc5c8\ub294\uc9c0 \ud655\uc778\ud574 \uc8fc\uc138\uc694."
        )
    elif error.code == ErrorCode.EXPORT_FILE_MISSING:
        summary = "\ub77c\uc774\ud2b8\ub8f8\uc758 \ubcf4\uc815 \uacb0\uacfc \ud30c\uc77c\uc744 \ucc3e\uc744 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4."
        action = "\ub0b4\ubcf4\ub0b4\uae30 \ud3f4\ub354 \uad8c\ud55c\uacfc \ub514\uc2a4\ud06c \uc6a9\ub7c9\uc744 \ud655\uc778\ud55c \ub4a4 \ub2e4\uc2dc \ucc98\ub9ac\ud574 \uc8fc\uc138\uc694."
    elif error.code == ErrorCode.LIGHTROOM_EXPORT_FAILED:
        summary = "\ub77c\uc774\ud2b8\ub8f8\uc774 \ubcf4\uc815\ub41c \uc0ac\uc9c4\uc744 \ub0b4\ubcf4\ub0b4\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4."
        action = "\ub77c\uc774\ud2b8\ub8f8 \uce74\ud0c8\ub85c\uadf8\uc640 \uc6d0\ubcf8 \ud30c\uc77c, \ucd9c\ub825 \ud3f4\ub354\uc758 \uc0c1\ud0dc\ub97c \ud655\uc778\ud574 \uc8fc\uc138\uc694."
    else:
        summary = "\ub77c\uc774\ud2b8\ub8f8\uc5d0 \ubcf4\uc815 \uc694\uccad\uc744 \uc804\ub2ec\ud558\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4."
        action = "\ub77c\uc774\ud2b8\ub8f8 \ud074\ub798\uc2dd\uacfc Tonevyra AI \ud50c\ub7ec\uadf8\uc778\uc758 \uc2e4\ud589 \uc0c1\ud0dc\ub97c \ud655\uc778\ud574 \uc8fc\uc138\uc694."

    return (
        f"{summary}\n\n"
        f"{action}\n\n"
        f"\uc624\ub958 \ucf54\ub4dc: {error.code.value}\n"
        f"\uc0c1\uc138 \uc815\ubcf4: {error.message}\n\n"
        "\uc0c1\ud0dc \ub85c\uadf8: \uc124\uce58 \ud3f4\ub354\\runtime\\bridge\\lightroom_worker_status.txt\n"
        "\uc624\ub958 \ud3f4\ub354: \uc124\uce58 \ud3f4\ub354\\runtime\\bridge\\lightroom_apply_errors"
    )
