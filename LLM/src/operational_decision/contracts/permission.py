"""Permission and flight-plan domain contracts."""

from datetime import datetime

from pydantic import Field, field_validator

from operational_decision.contracts.common import (
    ContextStatus,
    FlightPlanStatus,
    PermissionStatus,
    PlatformStatus,
    RecordConsistency,
    StrictContract,
    ToolExecutionStatus,
)
from operational_decision.contracts.visual import _require_aware_datetime


class PermissionRecord(StrictContract):
    """One operational flight-permission record."""

    permission_id: str = Field(min_length=1, max_length=150)
    platform_id: str = Field(min_length=1, max_length=150)
    context_id: str = Field(min_length=1, max_length=150)
    registration_mark: str | None = Field(default=None, max_length=50)
    operator_name: str | None = Field(default=None, max_length=200)
    operational_area_id: str | None = Field(default=None, max_length=150)
    flight_purpose: str | None = Field(default=None, max_length=200)
    flight_type: str | None = Field(default=None, max_length=100)
    altitude_ft_msl: int | None = Field(default=None, ge=0, le=100_000)
    departure_aerodrome: str | None = Field(default=None, max_length=20)
    arrival_aerodrome: str | None = Field(default=None, max_length=20)
    valid_from_utc: datetime
    valid_to_utc: datetime
    permission_status: PermissionStatus
    source_type: str = Field(min_length=1, max_length=50)

    _aware_times = field_validator("valid_from_utc", "valid_to_utc")(_require_aware_datetime)


class FlightPlanRecord(StrictContract):
    """One operational flight-plan record kept distinct from permission."""

    flight_plan_id: str = Field(min_length=1, max_length=150)
    platform_id: str = Field(min_length=1, max_length=150)
    context_id: str = Field(min_length=1, max_length=150)
    registration_mark: str | None = Field(default=None, max_length=50)
    callsign: str | None = Field(default=None, max_length=50)
    operational_area_id: str | None = Field(default=None, max_length=150)
    departure_aerodrome: str | None = Field(default=None, max_length=20)
    arrival_aerodrome: str | None = Field(default=None, max_length=20)
    route_or_area: str | None = Field(default=None, max_length=1000)
    planned_departure_utc: datetime
    planned_arrival_utc: datetime | None = None
    flight_plan_status: FlightPlanStatus
    source_type: str = Field(min_length=1, max_length=50)

    _aware_times = field_validator("planned_departure_utc", "planned_arrival_utc")(
        _require_aware_datetime
    )


class PermissionFlightPlanRequest(StrictContract):
    """Resolved platform and context facts needed for record lookup."""

    platform_id: str | None = Field(default=None, min_length=1, max_length=150)
    context_id: str | None = Field(default=None, min_length=1, max_length=150)
    operational_area_id: str | None = Field(default=None, min_length=1, max_length=150)
    scenario_id: str | None = Field(default=None, min_length=1, max_length=150)
    observation_time_utc: datetime
    observation_end_time_utc: datetime
    context_status: ContextStatus
    platform_execution_status: ToolExecutionStatus
    platform_status: PlatformStatus

    _aware_times = field_validator("observation_time_utc", "observation_end_time_utc")(
        _require_aware_datetime
    )


class PermissionFlightPlanResult(StrictContract):
    """Separate permission and flight-plan states plus their consistency."""

    permission_status: PermissionStatus
    flight_plan_status: FlightPlanStatus
    record_consistency: RecordConsistency
    permission_records: list[PermissionRecord] = Field(default_factory=list)
    flight_plan_records: list[FlightPlanRecord] = Field(default_factory=list)
    skip_reason: str | None = Field(default=None, max_length=150)
