"""TEKNOFEST analyze response presentation integration tests."""
# ruff: noqa: D103

from pathlib import Path

import httpx
import pytest

from operational_decision.api.main import create_app
from tests._phase7_support import build_harness, scenario_payload
from tests.integration.test_phase7_orchestrator_api import container_for

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("scenario_number", "expected_risk", "expected_event"),
    [
        (1, "Düşük", "F-16-like"),
        (6, "Bilinmiyor", "UNRESOLVED-PLATFORM"),
        (8, "Düşük", "NON_AIRCRAFT"),
        (11, "Kritik", "F-16-like"),
    ],
)
async def test_selected_scenarios_return_teknofest_spec_from_persisted_canonical(
    tmp_path: Path,
    scenario_number: int,
    expected_risk: str,
    expected_event: str,
) -> None:
    harness = await build_harness(ROOT, tmp_path)
    app = create_app(container_for(harness))
    payload = scenario_payload(ROOT, scenario_number)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/events/analyze",
            params={"response_format": "teknofest_spec"},
            json=payload,
        )
        canonical_response = await client.post("/api/v1/events/analyze", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"summary", "events", "risk", "actions"}
    assert body["summary"]
    assert body["events"] == [{"time": "00:08", "event": expected_event}]
    assert body["risk"] == expected_risk
    assert isinstance(body["actions"], list)
    assert all(isinstance(action, str) and action for action in body["actions"])

    assert canonical_response.status_code == 200
    event_id = canonical_response.json()["event_id"]
    persisted = await harness.event_service.get_final_output(event_id)
    assert persisted is not None
    canonical = persisted["output"]
    assert canonical["schema_version"] == "final-output/2.1"
    assert "risk_level" in canonical
    assert "risk" not in canonical
    assert "events" not in canonical


@pytest.mark.asyncio
async def test_default_and_explicit_canonical_responses_are_unchanged(tmp_path: Path) -> None:
    harness = await build_harness(ROOT, tmp_path)
    app = create_app(container_for(harness))
    payload = scenario_payload(ROOT, 1)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        default_response = await client.post("/api/v1/events/analyze", json=payload)
        explicit_response = await client.post(
            "/api/v1/events/analyze",
            params={"response_format": "canonical"},
            json=payload,
        )

    assert default_response.status_code == 200
    assert explicit_response.status_code == 200
    assert explicit_response.json() == default_response.json()
    assert default_response.json()["output"]["schema_version"] == "final-output/2.1"


@pytest.mark.asyncio
async def test_invalid_response_format_is_422_and_waiting_response_stays_canonical(
    tmp_path: Path,
) -> None:
    harness = await build_harness(ROOT, tmp_path)
    app = create_app(container_for(harness))
    payload = scenario_payload(ROOT, 1)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        invalid = await client.post(
            "/api/v1/events/analyze",
            params={"response_format": "invalid"},
            json=payload,
        )
        waiting = await client.post(
            "/api/v1/events/analyze",
            params={"response_format": "teknofest_spec"},
            json=scenario_payload(ROOT, 2, released=False),
        )

    assert invalid.status_code == 422
    assert waiting.status_code == 202
    assert set(waiting.json()) == {
        "event_id",
        "request_id",
        "event_status",
        "output",
        "detail",
    }
    assert waiting.json()["event_status"] == "WAITING_FOR_GPU_HANDOFF"
    assert waiting.json()["output"] is None
