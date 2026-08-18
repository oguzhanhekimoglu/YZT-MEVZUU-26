"""Strict runnable demo-scenario response contract tests."""

import json
from pathlib import Path
from typing import Any, cast

import httpx
import pytest

from operational_decision.api.main import create_app
from operational_decision.app.container import ApplicationContainer
from operational_decision.contracts.request import AnalyzeEventRequest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.asyncio
async def test_demo_scenario_catalog_is_complete_strict_and_deterministic() -> None:
    """Expose 23 strict DEMO_MOCK requests without frontend synthesis."""
    container = ApplicationContainer(
        orchestrator=cast(Any, None),
        event_service=cast(Any, None),
        health_service=cast(Any, None),
        scenario_path=ROOT / "data/seeds/demo_scenarios.json",
    )
    app = create_app(container)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        first = await client.get("/api/v1/demo/scenarios")
        second = await client.get("/api/v1/demo/scenarios")

    assert first.status_code == 200
    assert first.json() == second.json()
    scenarios = first.json()
    assert [item["scenario_id"] for item in scenarios] == [
        f"SCN-{number:02d}" for number in range(1, 24)
    ]
    for scenario in scenarios:
        assert scenario["name"].strip()
        assert scenario["description"].strip()
        request = AnalyzeEventRequest.model_validate_json(
            json.dumps(scenario["request_payload"], ensure_ascii=False),
            strict=True,
        )
        assert request.request_metadata is not None
        assert request.request_metadata["scenario_id"] == scenario["scenario_id"]
        assert request.request_metadata["source_type"] == "DEMO_MOCK"
        assert scenario["source_type"] == "DEMO_MOCK"
