# ruff: noqa: D103

"""Operational consistency orchestration integration tests."""

from pathlib import Path

import pytest

from tests._phase7_support import build_harness, scenario_payload

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.asyncio
async def test_consistency_trace_precedes_verification(tmp_path: Path) -> None:
    harness = await build_harness(ROOT, tmp_path)
    outcome = await harness.orchestrator.analyze(scenario_payload(ROOT, 1))
    trace = await harness.event_service.get_event_trace(outcome.event_id)
    steps = trace["steps"]
    names = [step["step_name"] for step in steps]
    index = names.index("OPERATIONAL_CONSISTENCY")
    assert index < names.index("VERIFICATION")
    step = steps[index]
    assert step["step_status"] == "CONSISTENT"
    assert step["payload"]["status"] == "CONSISTENT"
    assert step["payload"]["flags"] == ["INVENTORY_SCOPE_CONFIRMED"]
    assert step["payload"]["human_review_required"] is False


@pytest.mark.asyncio
async def test_non_aircraft_consistency_is_not_applicable(tmp_path: Path) -> None:
    harness = await build_harness(ROOT, tmp_path)
    outcome = await harness.orchestrator.analyze(scenario_payload(ROOT, 8))
    trace = await harness.event_service.get_event_trace(outcome.event_id)
    step = next(item for item in trace["steps"] if item["step_name"] == "OPERATIONAL_CONSISTENCY")
    assert step["step_status"] == "NOT_APPLICABLE"
    assert step["payload"]["flags"] == []
    assert step["payload"]["human_review_required"] is False
