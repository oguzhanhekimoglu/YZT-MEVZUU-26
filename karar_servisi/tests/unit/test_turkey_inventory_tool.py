"""Turkey Inventory V1 controlled tool behavior tests."""

from pathlib import Path

import pytest

from operational_decision.contracts.common import (
    InventoryStatus,
    PlatformStatus,
    ToolExecutionStatus,
)
from operational_decision.contracts.inventory import TurkeyInventoryToolRequest
from operational_decision.tools.turkey_inventory_tool import TurkeyInventoryTool

ROOT = Path(__file__).resolve().parents[2]
INVENTORY_PATH = ROOT / "data/inventory/turkey_inventory.json"
PLATFORM_PATH = ROOT / "data/platforms/platform_registry.json"


def request(
    *,
    platform_id: str | None = "PLT_F16",
    execution: ToolExecutionStatus = ToolExecutionStatus.SUCCESS,
    status: PlatformStatus = PlatformStatus.EXPECTED,
) -> TurkeyInventoryToolRequest:
    """Build controlled Platform Tool facts."""
    return TurkeyInventoryToolRequest(
        platform_id=platform_id,
        platform_execution_status=execution,
        platform_status=status,
    )


def tool(
    inventory_path: Path = INVENTORY_PATH,
    platform_path: Path = PLATFORM_PATH,
) -> TurkeyInventoryTool:
    """Build a file-backed tool without runtime wiring."""
    return TurkeyInventoryTool.from_files(
        inventory_path,
        platform_path,
        event_id="evt_inventory",
        request_id="req_inventory",
    )


@pytest.mark.asyncio
async def test_confirmed_result() -> None:
    """An exact active Inventory record produces SUCCESS plus CONFIRMED."""
    response = await tool().execute(request(), timeout_seconds=0.2)
    assert response.execution_status is ToolExecutionStatus.SUCCESS
    assert response.data is not None
    assert response.data.inventory_status is InventoryStatus.CONFIRMED
    assert response.data.inventory_record_id == "TR-DEMO-F16-001"
    assert response.source_refs == ["TR-INVENTORY-DEMO@1.0.0"]
    assert "uçuş izni anlamına gelmez" in response.data.safe_message


@pytest.mark.asyncio
async def test_boeing_747_not_listed_is_success_not_error() -> None:
    """Resolved Boeing 747 absent from Inventory is a domain result, not failure."""
    response = await tool().execute(
        request(platform_id="PLT_BOEING_747"),
        timeout_seconds=0.2,
    )
    assert response.execution_status is ToolExecutionStatus.SUCCESS
    assert response.error is None
    assert response.data is not None
    assert response.data.inventory_status is InventoryStatus.NOT_LISTED
    assert response.data.inventory_record_id is None
    assert response.data.safe_message == (
        "Platform mevcut Türkiye envanter veri setinde bulunamadı."
    )


@pytest.mark.asyncio
async def test_unresolved_platform_is_skipped_unknown() -> None:
    """Unavailable Platform Tool facts produce SKIPPED plus UNKNOWN."""
    response = await tool().execute(
        request(
            platform_id=None,
            execution=ToolExecutionStatus.ERROR,
            status=PlatformStatus.UNKNOWN,
        ),
        timeout_seconds=0.2,
    )
    assert response.execution_status is ToolExecutionStatus.SKIPPED
    assert response.data is not None
    assert response.data.inventory_status is InventoryStatus.UNKNOWN


@pytest.mark.asyncio
async def test_non_aircraft_is_skipped_not_applicable() -> None:
    """Non-aircraft input produces SKIPPED plus NOT_APPLICABLE."""
    response = await tool().execute(
        request(platform_id=None, status=PlatformStatus.NON_AIRCRAFT),
        timeout_seconds=0.2,
    )
    assert response.execution_status is ToolExecutionStatus.SKIPPED
    assert response.data is not None
    assert response.data.inventory_status is InventoryStatus.NOT_APPLICABLE


@pytest.mark.asyncio
async def test_registry_load_error_is_error_unknown(tmp_path: Path) -> None:
    """Registry validation failure remains distinct from NOT_LISTED."""
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{}", encoding="utf-8")
    response = await tool(inventory_path=invalid).execute(request(), timeout_seconds=0.2)
    assert response.execution_status is ToolExecutionStatus.ERROR
    assert response.error is not None
    assert response.error.code == "INVENTORY_REGISTRY_UNAVAILABLE"
    assert response.data is not None
    assert response.data.inventory_status is InventoryStatus.UNKNOWN
