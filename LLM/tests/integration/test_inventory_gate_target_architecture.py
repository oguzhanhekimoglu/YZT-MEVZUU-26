"""Target architecture tests for decoupling Inventory from downstream eligibility."""
# ruff: noqa: D103

import json
from dataclasses import replace
from pathlib import Path

import pytest

from operational_decision.decision.orchestrator import DecisionOrchestrator
from operational_decision.inventory.turkey_inventory_registry import (
    load_turkey_inventory_registry,
)
from operational_decision.tools.turkey_inventory_tool import TurkeyInventoryTool
from tests._phase7_support import Phase7Harness, build_harness, scenario_payload

ROOT = Path(__file__).resolve().parents[2]
PLATFORM_PATH = ROOT / "data/platforms/platform_registry.json"
INVENTORY_PATH = ROOT / "data/inventory/turkey_inventory.json"
DOWNSTREAM_TOOLS = ("permission_flight_plan_tool", "notam_tool")


def _tool_rows(trace: dict[str, object]) -> dict[str, dict[str, object]]:
    rows = trace["tool_executions"]
    assert isinstance(rows, list)
    return {str(row["tool_name"]): row for row in rows}


def _replace_inventory_factory(
    harness: Phase7Harness,
    inventory_path: Path,
) -> None:
    try:
        registry = load_turkey_inventory_registry(inventory_path, PLATFORM_PATH)
    except ValueError:
        registry = None

    def factory(event_id: str, request_id: str) -> TurkeyInventoryTool:
        if registry is not None:
            return TurkeyInventoryTool(
                registry,
                event_id=event_id,
                request_id=request_id,
                event_service=harness.event_service,
            )
        return TurkeyInventoryTool.from_files(
            inventory_path,
            PLATFORM_PATH,
            event_id=event_id,
            request_id=request_id,
            event_service=harness.event_service,
        )

    harness.orchestrator = DecisionOrchestrator(
        replace(harness.orchestrator.deps, inventory_factory=factory)
    )


async def _rows_for_scenario(
    harness: Phase7Harness,
    scenario_number: int,
) -> dict[str, dict[str, object]]:
    outcome = await harness.orchestrator.analyze(scenario_payload(ROOT, scenario_number))
    return _tool_rows(await harness.event_service.get_event_trace(outcome.event_id))


def _assert_downstream_executed(rows: dict[str, dict[str, object]]) -> None:
    for tool_name in DOWNSTREAM_TOOLS:
        assert rows[tool_name]["execution_status"] == "SUCCESS"


def _assert_downstream_skipped_without_domain_data(
    rows: dict[str, dict[str, object]],
) -> None:
    for tool_name in DOWNSTREAM_TOOLS:
        row = rows[tool_name]
        assert row["execution_status"] == "SKIPPED"
        assert row["domain_status"] is None
        response = row["response"]
        assert isinstance(response, dict)
        assert response["data"] is None


@pytest.mark.asyncio
async def test_target_unregistered_military_not_listed_gates_downstream(
    tmp_path: Path,
) -> None:
    harness = await build_harness(ROOT, tmp_path)
    payload = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    payload["records"] = [
        record for record in payload["records"] if record["platform_id"] != "PLT_F16"
    ]
    inventory_path = tmp_path / "not_listed_inventory.json"
    inventory_path.write_text(json.dumps(payload), encoding="utf-8")
    _replace_inventory_factory(harness, inventory_path)

    rows = await _rows_for_scenario(harness, 1)

    assert rows["platform_tool"]["execution_status"] == "SUCCESS"
    assert rows["turkey_inventory_tool"]["domain_status"] == "NOT_LISTED"
    _assert_downstream_skipped_without_domain_data(rows)
    for tool_name in DOWNSTREAM_TOOLS:
        assert rows[tool_name]["response"]["warnings"] == [
            "UNREGISTERED_MILITARY_POLICY"
        ]


@pytest.mark.asyncio
async def test_target_inventory_error_does_not_gate_resolved_complete_downstream(
    tmp_path: Path,
) -> None:
    harness = await build_harness(ROOT, tmp_path)
    invalid_inventory = tmp_path / "invalid_inventory.json"
    invalid_inventory.write_text("{}", encoding="utf-8")
    _replace_inventory_factory(harness, invalid_inventory)

    rows = await _rows_for_scenario(harness, 1)

    assert rows["platform_tool"]["execution_status"] == "SUCCESS"
    assert rows["turkey_inventory_tool"]["execution_status"] == "ERROR"
    _assert_downstream_executed(rows)


@pytest.mark.asyncio
async def test_target_incomplete_context_skips_without_domain_results(tmp_path: Path) -> None:
    harness = await build_harness(ROOT, tmp_path)

    rows = await _rows_for_scenario(harness, 10)

    _assert_downstream_skipped_without_domain_data(rows)


@pytest.mark.asyncio
async def test_target_unresolved_platform_skips_downstream(tmp_path: Path) -> None:
    harness = await build_harness(ROOT, tmp_path)

    rows = await _rows_for_scenario(harness, 6)

    assert rows["platform_tool"]["domain_status"] == "UNKNOWN"
    _assert_downstream_skipped_without_domain_data(rows)


@pytest.mark.asyncio
async def test_target_non_aircraft_skips_downstream(tmp_path: Path) -> None:
    harness = await build_harness(ROOT, tmp_path)

    rows = await _rows_for_scenario(harness, 8)

    assert rows["platform_tool"]["domain_status"] == "NON_AIRCRAFT"
    _assert_downstream_skipped_without_domain_data(rows)


@pytest.mark.asyncio
async def test_target_confirmed_complete_still_runs_downstream(tmp_path: Path) -> None:
    harness = await build_harness(ROOT, tmp_path)

    rows = await _rows_for_scenario(harness, 1)

    assert rows["turkey_inventory_tool"]["domain_status"] == "CONFIRMED"
    _assert_downstream_executed(rows)
