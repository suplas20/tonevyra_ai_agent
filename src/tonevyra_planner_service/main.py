"""Console entry point for Tonevyra Planner Server."""

from __future__ import annotations

import uvicorn

from tonevyra_planner_service.app import create_app
from tonevyra_planner_service.config import PlannerServerConfig


def main() -> None:
    config = PlannerServerConfig.from_env()
    print(f"Tonevyra Planner Server starting at http://{config.host}:{config.port}")
    print("Keep this window open while Tonevyra AI is running. Press Ctrl+C to stop.")
    uvicorn.run(
        create_app(config),
        host=config.host,
        port=config.port,
        workers=1,
        log_level="info",
        access_log=True,
    )


if __name__ == "__main__":
    main()
