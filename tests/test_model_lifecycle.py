from __future__ import annotations

from tonevyra_agent.agent.worker import AgentWorker
from tonevyra_agent.vision.analyzer import VisionAnalyzer


def test_agent_worker_does_not_load_vision_backend_on_init(monkeypatch) -> None:
    def fail_if_constructed(*_args, **_kwargs):
        raise AssertionError("VisionAnalyzer should be lazy")

    monkeypatch.setattr("tonevyra_agent.agent.worker.VisionAnalyzer", fail_if_constructed)

    AgentWorker()


def test_vision_analyzer_close_delegates_to_backend() -> None:
    class Backend:
        backend_name = "test"
        model_name = "test"

        def __init__(self) -> None:
            self.closed = False

        def analyze(self, **_kwargs):
            return {}

        def close(self) -> None:
            self.closed = True

    backend = Backend()
    analyzer = VisionAnalyzer(backend=backend)

    analyzer.close()

    assert backend.closed is True
