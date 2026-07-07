"""Lightroom bridge package for Tonevyra AI."""

from __future__ import annotations

from importlib import import_module
from typing import Any

_LAZY_EXPORTS = {
    "LightroomBridge": ("tonevyra_agent.lightroom.bridge", "LightroomBridge"),
    "ingest_lightroom_response": ("tonevyra_agent.lightroom.bridge", "ingest_lightroom_response"),
    "write_lightroom_request": ("tonevyra_agent.lightroom.bridge", "write_lightroom_request"),
    "LightroomRequestPayload": ("tonevyra_agent.lightroom.schemas", "LightroomRequestPayload"),
    "LightroomResponsePayload": ("tonevyra_agent.lightroom.schemas", "LightroomResponsePayload"),
}

__all__ = sorted(_LAZY_EXPORTS)


def __getattr__(name: str) -> Any:
    if name not in _LAZY_EXPORTS:
        raise AttributeError(name)
    module_name, attr_name = _LAZY_EXPORTS[name]
    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value

