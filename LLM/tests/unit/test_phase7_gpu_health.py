"""Phase 7 GPU coordination and health aggregation unit tests."""
# ruff: noqa: D103

import asyncio

import httpx
import pytest

from operational_decision.api.main import create_app
from operational_decision.app.container import ApplicationContainer
from operational_decision.app.health import (
    ComponentHealth,
    HealthService,
    HealthStatus,
)
from operational_decision.decision.gpu_handoff import BatchCoordinator
from tests._phase7_support import build_harness


@pytest.mark.asyncio
async def test_global_llm_inference_and_same_video_are_sequential() -> None:
    coordinator = BatchCoordinator()
    active = 0
    maximum = 0

    async def work(video_id: str) -> None:
        nonlocal active, maximum
        async with coordinator.video_batch(video_id):
            async with coordinator.llm_inference():
                active += 1
                maximum = max(maximum, active)
                await asyncio.sleep(0.02)
                active -= 1

    await asyncio.gather(work("VIDEO-A"), work("VIDEO-B"), work("VIDEO-A"))
    assert maximum == 1


@pytest.mark.asyncio
async def test_health_aggregation_deep_false_and_required_failure(tmp_path) -> None:  # type: ignore[no-untyped-def]
    deep_values: list[bool] = []

    async def healthy(deep: bool) -> ComponentHealth:
        deep_values.append(deep)
        return ComponentHealth(status=HealthStatus.HEALTHY)

    async def model_missing(deep: bool) -> ComponentHealth:
        deep_values.append(deep)
        return ComponentHealth(status=HealthStatus.DEGRADED, detail="CANONICAL_MODEL_MISSING")

    probes = {
        "operational_db": healthy,
        "event_memory_db": healthy,
        "rag_index": healthy,
        "decision_model": model_missing,
    }
    service = HealthService(probes, {"operational_db", "event_memory_db", "rag_index"})
    report = await service.check(deep=False)
    assert report.status is HealthStatus.DEGRADED
    assert deep_values == [False, False, False, False]

    async def failed_db(deep: bool) -> ComponentHealth:
        del deep
        return ComponentHealth(status=HealthStatus.FAILED, detail="DATABASE_UNAVAILABLE")

    failed_service = HealthService(
        {**probes, "operational_db": failed_db},
        {"operational_db", "event_memory_db", "rag_index"},
    )
    failed = await failed_service.check(deep=False)
    assert failed.status is HealthStatus.FAILED

    root = __import__("pathlib").Path(__file__).resolve().parents[2]
    harness = await build_harness(root, tmp_path)
    app = create_app(
        ApplicationContainer(
            orchestrator=harness.orchestrator,
            event_service=harness.event_service,
            health_service=failed_service,
            scenario_path=root / "data/seeds/demo_scenarios.json",
        )
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health")
    assert response.status_code == 503
    assert response.json()["status"] == "FAILED"
