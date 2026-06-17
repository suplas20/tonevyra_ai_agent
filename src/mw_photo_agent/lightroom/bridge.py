"""File-based JSON bridge for Lightroom Classic."""

from pathlib import Path

from mw_photo_agent.lightroom.schemas import LightroomRequest


class LightroomBridge:
    def __init__(self, bridge_dir: Path) -> None:
        self.bridge_dir = bridge_dir

    def write_request(self, request: LightroomRequest) -> Path:
        raise NotImplementedError("Lightroom request writing is not implemented yet.")

    def wait_for_response(self, request_id: str, timeout_seconds: int):
        raise NotImplementedError("Lightroom response waiting is not implemented yet.")

