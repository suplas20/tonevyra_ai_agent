from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from tonevyra_agent.core.config import Settings
from tonevyra_agent.core.enums import ErrorCode
from tonevyra_agent.core.errors import TonevyraError
from tonevyra_agent.planner_api.client import PlannerApiClient
from tonevyra_agent.planner_api.contracts import (
    PlannerRequest,
    attach_input_digest,
    response_to_correction_plan,
)
from tonevyra_planner_service.app import create_app
from tonevyra_planner_service.config import PlannerServerConfig


FIXTURE = Path("harness/fixtures/t032_planner_api/valid_request.json")


def _request_payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _headers(payload: dict, *, key: str = "secret-key", idempotency_key: str = "test:one") -> dict[str, str]:
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "X-Request-ID": payload["request_id"],
        "Idempotency-Key": idempotency_key,
        "X-Tonevyra-Schema-Version": "t032.planner.request.v1",
    }


def test_local_planner_server_health_and_authenticated_plan(tmp_path: Path) -> None:
    config = PlannerServerConfig(data_dir=tmp_path, api_key="secret-key")
    client = TestClient(create_app(config))
    payload = _request_payload()

    assert client.get("/health/live").status_code == 200
    ready = client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json()["ready"] is True
    assert client.get("/api/v1/version").json()["planner_version"] == "rule-planner-v1"
    assert client.post("/api/v1/plans", json=payload, headers=_headers(payload, key="wrong")).status_code == 401

    response = client.post("/api/v1/plans", json=payload, headers=_headers(payload))

    assert response.status_code == 200
    body = response.json()
    request = PlannerRequest.model_validate(payload)
    plan = response_to_correction_plan(
        request=request,
        response_payload=body,
        supported_planner_versions={"rule-planner-v1"},
        supported_policy_versions={"local-reference"},
    )
    assert plan.adjustments_json
    assert body["replayed"] is False


def test_local_planner_server_persists_replay_and_rejects_conflict(tmp_path: Path) -> None:
    config = PlannerServerConfig(data_dir=tmp_path, api_key="secret-key")
    payload = _request_payload()
    headers = _headers(payload, idempotency_key="test:durable")

    first_client = TestClient(create_app(config))
    first = first_client.post("/api/v1/plans", json=payload, headers=headers)
    assert first.status_code == 200

    second_client = TestClient(create_app(config))
    replay = second_client.post("/api/v1/plans", json=payload, headers=headers)
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert replay.json()["plan_digest"] == first.json()["plan_digest"]

    changed = json.loads(json.dumps(payload))
    changed["preferences"]["correction_strength"] = "aggressive"
    changed = attach_input_digest(changed)
    conflict = second_client.post("/api/v1/plans", json=changed, headers=headers)
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_client_allows_http_only_for_loopback_local_server_mode() -> None:
    local = PlannerApiClient(
        Settings(
            planner_api_mode="local_server",
            planner_api_base_url="http://127.0.0.1:8000",
            planner_api_key="secret-key",
            planner_api_allowed_host="127.0.0.1",
        )
    )
    local._validate_config()

    remote = PlannerApiClient(
        Settings(
            planner_api_mode="local_server",
            planner_api_base_url="http://planner.example.test:8000",
            planner_api_key="secret-key",
            planner_api_allowed_host="planner.example.test",
        )
    )
    with pytest.raises(TonevyraError) as exc:
        remote._validate_config()
    assert exc.value.code == ErrorCode.SECURITY_NETWORK_ACCESS_BLOCKED


def test_planner_server_build_script_targets_port_8000_executable() -> None:
    source = Path("harness/scripts/build_tonevyra_planner_server_exe.py").read_text(encoding="utf-8")

    assert '"TonevyraPlannerServer"' in source
    assert '"--onefile"' in source
    assert '"--console"' in source
    assert '"port": 8000' in source
