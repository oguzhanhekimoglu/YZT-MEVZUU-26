"""Phase 8 coverage for controlled Base Tool failure paths."""
# ruff: noqa: D101, D102, D103, D107

import asyncio
import sqlite3

import pytest

from operational_decision.contracts.common import StrictContract, ToolExecutionStatus
from operational_decision.tools.base import BaseTool, ToolExecutionFailure


class Request(StrictContract):
    value: int


class Result(StrictContract):
    state: str


class FailurePathTool(BaseTool[Request, Result]):
    tool_name = "failure_path_tool"

    def __init__(self, mode: str) -> None:
        super().__init__(event_id="evt_phase8", request_id="req_phase8")
        self.mode = mode

    async def execute_internal(self, request: Request) -> Result:
        if self.mode == "controlled":
            raise ToolExecutionFailure(code="CONTROLLED", message="controlled failure")
        if self.mode == "timeout":
            await asyncio.sleep(0.05)
        if self.mode == "busy":
            raise sqlite3.OperationalError("database is busy")
        if self.mode == "sqlite":
            raise sqlite3.OperationalError("storage unavailable")
        if self.mode == "invalid":
            raise ValueError("invalid domain request")
        if self.mode == "unexpected":
            raise RuntimeError("private failure detail")
        return Result(state=str(request.value))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "timeout", "status", "code", "retryable"),
    [
        ("controlled", 1.0, ToolExecutionStatus.ERROR, "CONTROLLED", False),
        ("timeout", 0.001, ToolExecutionStatus.TIMEOUT, "TIMEOUT", False),
        ("busy", 1.0, ToolExecutionStatus.ERROR, "SQLITE_BUSY", False),
        ("sqlite", 1.0, ToolExecutionStatus.ERROR, "SQLITE_ERROR", False),
        ("invalid", 1.0, ToolExecutionStatus.INVALID_INPUT, "INVALID_INPUT", False),
        ("unexpected", 1.0, ToolExecutionStatus.ERROR, "TOOL_ERROR", False),
    ],
)
async def test_base_tool_failure_mapping(
    mode: str,
    timeout: float,
    status: ToolExecutionStatus,
    code: str,
    retryable: bool,
) -> None:
    response = await FailurePathTool(mode).execute(Request(value=1), timeout_seconds=timeout)
    assert response.execution_status is status
    assert response.error is not None
    assert response.error.code == code
    assert response.error.retryable is retryable
    if mode == "unexpected":
        assert "private failure detail" not in response.error.message