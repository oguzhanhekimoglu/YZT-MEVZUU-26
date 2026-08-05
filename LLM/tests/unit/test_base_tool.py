"""Unit tests for base tool retry and status separation."""
# ruff: noqa: D102, D103, D107

import sqlite3

import pytest

from operational_decision.contracts.common import StrictContract, ToolExecutionStatus
from operational_decision.tools.base import BaseTool


class DemoRequest(StrictContract):
    """Minimal strict test request."""

    value: int


class DemoResult(StrictContract):
    """Minimal domain result."""

    domain_status: str


class FlakyTool(BaseTool[DemoRequest, DemoResult]):
    """Fail once with transient SQLite locking."""

    tool_name = "flaky_tool"

    def __init__(self) -> None:
        super().__init__(event_id="evt_1", request_id="req_1")
        self.calls = 0

    async def execute_internal(self, request: DemoRequest) -> DemoResult:
        self.calls += 1
        if self.calls == 1:
            raise sqlite3.OperationalError("database is locked")
        return DemoResult(domain_status="NOT_FOUND")


@pytest.mark.asyncio
async def test_transient_sqlite_failure_retries_once() -> None:
    tool = FlakyTool()
    response = await tool.execute(DemoRequest(value=1), timeout_seconds=1)
    assert tool.calls == 2
    assert response.execution_status is ToolExecutionStatus.SUCCESS
    assert response.data is not None and response.data.domain_status == "NOT_FOUND"


@pytest.mark.asyncio
async def test_invalid_timeout_is_not_retried() -> None:
    tool = FlakyTool()
    response = await tool.execute(DemoRequest(value=1), timeout_seconds=0)
    assert tool.calls == 0
    assert response.execution_status is ToolExecutionStatus.INVALID_INPUT
