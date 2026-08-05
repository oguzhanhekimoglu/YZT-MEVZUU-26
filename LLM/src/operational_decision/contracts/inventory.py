"""Strict, versioned Turkey Inventory V1 contracts."""

from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from operational_decision.contracts.common import (
    InventoryStatus,
    PlatformStatus,
    StrictContract,
    ToolExecutionStatus,
)


def _require_aware_datetime(value: datetime) -> datetime:
    """Reject timestamps without a usable UTC offset."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value


class TurkeyInventoryRecord(StrictContract):
    """One explicitly listed Turkey inventory record."""

    inventory_record_id: str = Field(min_length=1, max_length=150)
    platform_id: str = Field(min_length=1, max_length=150)
    country_code: str = Field(min_length=2, max_length=3)
    operator_name: str = Field(min_length=1, max_length=200)
    service_status: str = Field(min_length=1, max_length=100)
    active: bool
    source_type: Literal["DEMO_MOCK"]


class TurkeyInventoryDataset(StrictContract):
    """A strict, versioned Turkey inventory dataset."""

    schema_version: str = Field(min_length=1, max_length=100)
    dataset_id: str = Field(min_length=1, max_length=150)
    dataset_version: str = Field(min_length=1, max_length=100)
    effective_at_utc: datetime
    source_type: Literal["DEMO_MOCK"]
    records: list[TurkeyInventoryRecord]

    _aware_effective_at = field_validator("effective_at_utc")(_require_aware_datetime)


class TurkeyInventoryToolRequest(StrictContract):
    """Platform Tool facts used for an inventory lookup."""

    platform_id: str | None = Field(min_length=1, max_length=150)
    platform_execution_status: ToolExecutionStatus
    platform_status: PlatformStatus


class TurkeyInventoryResult(StrictContract):
    """Domain result carried inside the existing tool response envelope."""

    inventory_status: InventoryStatus
    platform_id: str = Field(min_length=1, max_length=150)
    inventory_record_id: str | None = Field(default=None, min_length=1, max_length=150)
    country_code: str | None = Field(default=None, min_length=2, max_length=3)
    operator_name: str | None = Field(default=None, min_length=1, max_length=200)
    service_status: str | None = Field(default=None, min_length=1, max_length=100)
    dataset_id: str | None = Field(default=None, min_length=1, max_length=150)
    dataset_version: str | None = Field(default=None, min_length=1, max_length=100)
    source_type: Literal["DEMO_MOCK"] | None = None
    reason_codes: list[str]
    safe_message: str = Field(min_length=1, max_length=1000)
    warnings: list[str]
