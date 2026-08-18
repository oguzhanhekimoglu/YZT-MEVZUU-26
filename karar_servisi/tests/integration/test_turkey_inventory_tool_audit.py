"""Turkey Inventory Tool durable audit integration test."""

from pathlib import Path

import pytest

from operational_decision.contracts.common import PlatformStatus, ToolExecutionStatus
from operational_decision.contracts.inventory import TurkeyInventoryToolRequest
from operational_decision.memory.database import EventMemoryDatabase
from operational_decision.memory.event_service import EventService
from operational_decision.tools.turkey_inventory_tool import TurkeyInventoryTool

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.asyncio
async def test_inventory_tool_writes_audit_record(tmp_path: Path) -> None:
    """BaseTool audit stores execution and Inventory domain status."""
    database = EventMemoryDatabase(tmp_path / "event_memory.db")
    await database.initialize()
    service = EventService(database)
    created = await service.create_event(raw_request={"kind": "inventory-test"})
    event_id = str(created.event["event_id"])
    request_id = str(created.event["request_id"])
    tool = TurkeyInventoryTool.from_files(
        ROOT / "data/inventory/turkey_inventory.json",
        ROOT / "data/platforms/platform_registry.json",
        event_id=event_id,
        request_id=request_id,
        event_service=service,
    )
    response = await tool.execute(
        TurkeyInventoryToolRequest(
            platform_id="PLT_F16",
            platform_execution_status=ToolExecutionStatus.SUCCESS,
            platform_status=PlatformStatus.EXPECTED,
        ),
        timeout_seconds=0.2,
    )
    trace = await service.get_event_trace(event_id)
    attempts = trace["tool_executions"]
    assert response.execution_status is ToolExecutionStatus.SUCCESS
    assert len(attempts) == 1
    assert attempts[0]["tool_name"] == "turkey_inventory_tool"
    assert attempts[0]["execution_status"] == "SUCCESS"
    assert attempts[0]["domain_status"] == "CONFIRMED"
