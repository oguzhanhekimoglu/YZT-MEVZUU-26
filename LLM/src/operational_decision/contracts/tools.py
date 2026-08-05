"""Shared controlled-tool envelopes."""

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import Field, field_validator

from operational_decision.contracts.common import StrictContract, ToolExecutionStatus
from operational_decision.contracts.visual import _require_aware_datetime

DataT = TypeVar("DataT")


class ToolError(StrictContract):
    """Sanitized structured tool failure detail."""

    code: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=1000)
    retryable: bool = False


class ToolResponseEnvelope(StrictContract, Generic[DataT]):
    """Separate infrastructure execution status from domain result data."""

    tool_name: str = Field(min_length=1, max_length=150)
    tool_version: str = Field(min_length=1, max_length=50)
    event_id: str = Field(min_length=1, max_length=100)
    request_id: str = Field(min_length=1, max_length=100)
    execution_status: ToolExecutionStatus
    started_at_utc: datetime
    finished_at_utc: datetime
    latency_ms: int = Field(ge=0)
    data: DataT | None = None
    warnings: list[str] = Field(default_factory=list)
    error: ToolError | None = None
    source_refs: list[str] = Field(default_factory=list)

    _aware_times = field_validator("started_at_utc", "finished_at_utc")(_require_aware_datetime)
