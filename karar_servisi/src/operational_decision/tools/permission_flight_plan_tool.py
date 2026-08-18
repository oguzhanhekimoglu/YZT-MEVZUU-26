"""Permission and flight-plan tool with separate domain interpretations."""

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from operational_decision.contracts.common import (
    ContextStatus,
    FlightPlanStatus,
    PermissionStatus,
    PlatformStatus,
    RecordConsistency,
    ToolExecutionStatus,
)
from operational_decision.contracts.permission import (
    FlightPlanRecord,
    PermissionFlightPlanRequest,
    PermissionFlightPlanResult,
    PermissionRecord,
)
from operational_decision.memory.event_service import EventService
from operational_decision.operational.flight_plan_repository import FlightPlanRepository
from operational_decision.operational.permission_repository import PermissionRepository
from operational_decision.tools.base import BaseTool, ToolSkipped


def _overlaps(
    start: datetime, end: datetime, observation_start: datetime, observation_end: datetime
) -> bool:
    return start <= observation_end and end >= observation_start


def _permission_state(
    row: Mapping[str, Any], observation_start: datetime, observation_end: datetime
) -> PermissionStatus:
    stored = PermissionStatus(row["permission_status"])
    if stored is PermissionStatus.REVOKED:
        return PermissionStatus.REVOKED
    if row["valid_to_utc"] < observation_start:
        return PermissionStatus.EXPIRED
    if row["valid_from_utc"] > observation_end:
        return PermissionStatus.NOT_YET_VALID
    return stored if stored is not PermissionStatus.NOT_FOUND else PermissionStatus.NOT_FOUND


def _plan_state(
    row: Mapping[str, Any], observation_start: datetime, observation_end: datetime
) -> FlightPlanStatus:
    stored = FlightPlanStatus(row["flight_plan_status"])
    if stored is FlightPlanStatus.CANCELLED:
        return FlightPlanStatus.CANCELLED
    end = row["planned_arrival_utc"] or row["planned_departure_utc"]
    if end < observation_start:
        return FlightPlanStatus.EXPIRED
    if row["planned_departure_utc"] > observation_end:
        return FlightPlanStatus.NOT_YET_ACTIVE
    return stored


def _equivalent(rows: Sequence[Mapping[str, Any]], ignored_id: str) -> bool:
    signatures = {
        tuple(
            sorted(
                (key, str(value))
                for key, value in row.items()
                if key not in {ignored_id, "notes", "issued_at_utc"}
            )
        )
        for row in rows
    }
    return len(signatures) == 1


def _permission_status(
    rows: list[dict[str, Any]], start: datetime, end: datetime
) -> PermissionStatus:
    if not rows:
        return PermissionStatus.NOT_FOUND
    states = [_permission_state(row, start, end) for row in rows]
    if len(rows) > 1:
        return (
            PermissionStatus.AMBIGUOUS
            if len(set(states)) == 1 and _equivalent(rows, "permission_id")
            else PermissionStatus.CONFLICTING
        )
    return states[0]


def _flight_plan_status(
    rows: list[dict[str, Any]], start: datetime, end: datetime
) -> FlightPlanStatus:
    if not rows:
        return FlightPlanStatus.NOT_FOUND
    states = [_plan_state(row, start, end) for row in rows]
    if len(rows) > 1:
        return (
            FlightPlanStatus.AMBIGUOUS
            if len(set(states)) == 1 and _equivalent(rows, "flight_plan_id")
            else FlightPlanStatus.CONFLICTING
        )
    return states[0]


def resolve_record_consistency(
    permission: PermissionStatus, flight_plan: FlightPlanStatus
) -> RecordConsistency:
    """Apply the binding deterministic consistency rules."""
    if (
        permission is PermissionStatus.NOT_APPLICABLE
        and flight_plan is FlightPlanStatus.NOT_APPLICABLE
    ):
        return RecordConsistency.NOT_APPLICABLE
    if permission is PermissionStatus.CONFLICTING or flight_plan is FlightPlanStatus.CONFLICTING:
        return RecordConsistency.CONFLICTING
    if permission is PermissionStatus.VALID and flight_plan is FlightPlanStatus.FILED:
        return RecordConsistency.CONSISTENT
    if permission is PermissionStatus.VALID and flight_plan in {
        FlightPlanStatus.CANCELLED,
        FlightPlanStatus.EXPIRED,
    }:
        return RecordConsistency.CONFLICTING
    if (
        permission in {PermissionStatus.EXPIRED, PermissionStatus.REVOKED}
        and flight_plan is FlightPlanStatus.FILED
    ):
        return RecordConsistency.CONFLICTING
    if (permission is PermissionStatus.VALID and flight_plan is FlightPlanStatus.NOT_FOUND) or (
        permission is PermissionStatus.NOT_FOUND and flight_plan is FlightPlanStatus.FILED
    ):
        return RecordConsistency.PARTIAL
    if permission is PermissionStatus.NOT_FOUND and flight_plan is FlightPlanStatus.NOT_FOUND:
        return RecordConsistency.UNKNOWN
    return RecordConsistency.UNKNOWN


def _permission_record(row: Mapping[str, Any]) -> PermissionRecord:
    return PermissionRecord(
        permission_id=row["permission_id"],
        platform_id=row["platform_id"],
        context_id=row["context_id"],
        registration_mark=row.get("registration_mark"),
        operator_name=row.get("operator_name"),
        operational_area_id=row.get("operational_area_id"),
        flight_purpose=row.get("flight_purpose"),
        flight_type=row.get("flight_type"),
        altitude_ft_msl=row.get("altitude_ft_msl"),
        departure_aerodrome=row.get("departure_aerodrome"),
        arrival_aerodrome=row.get("arrival_aerodrome"),
        valid_from_utc=row["valid_from_utc"],
        valid_to_utc=row["valid_to_utc"],
        permission_status=PermissionStatus(row["permission_status"]),
        source_type=row["source_type"],
    )


def _plan_record(row: Mapping[str, Any]) -> FlightPlanRecord:
    return FlightPlanRecord(
        flight_plan_id=row["flight_plan_id"],
        platform_id=row["platform_id"],
        context_id=row["context_id"],
        registration_mark=row.get("registration_mark"),
        callsign=row.get("callsign"),
        operational_area_id=row.get("operational_area_id"),
        departure_aerodrome=row.get("departure_aerodrome"),
        arrival_aerodrome=row.get("arrival_aerodrome"),
        route_or_area=row.get("route_or_area"),
        planned_departure_utc=row["planned_departure_utc"],
        planned_arrival_utc=row["planned_arrival_utc"],
        flight_plan_status=FlightPlanStatus(row["flight_plan_status"]),
        source_type=row["source_type"],
    )


class PermissionFlightPlanTool(BaseTool[PermissionFlightPlanRequest, PermissionFlightPlanResult]):
    """Query two repositories without treating a flight plan as permission."""

    tool_name = "permission_flight_plan_tool"

    def __init__(
        self,
        permission_repository: PermissionRepository,
        flight_plan_repository: FlightPlanRepository,
        *,
        event_id: str,
        request_id: str,
        event_service: EventService | None = None,
    ) -> None:
        """Bind independent permission and flight-plan repositories."""
        super().__init__(event_id=event_id, request_id=request_id, event_service=event_service)
        self.permission_repository = permission_repository
        self.flight_plan_repository = flight_plan_repository

    def validate_request(self, request: PermissionFlightPlanRequest) -> None:
        """Reject inverted observation intervals."""
        if request.observation_end_time_utc < request.observation_time_utc:
            raise ValueError("observation interval is inverted")

    async def execute_internal(
        self, request: PermissionFlightPlanRequest
    ) -> PermissionFlightPlanResult:
        """Gate execution then classify records over the complete interval."""
        if request.context_status is not ContextStatus.COMPLETE:
            raise self._skipped("CONTEXT_NOT_COMPLETE")
        if request.platform_execution_status is not ToolExecutionStatus.SUCCESS:
            raise self._skipped("PLATFORM_EXECUTION_NOT_SUCCESS")
        if request.platform_id is None:
            raise self._skipped("PLATFORM_UNRESOLVED")
        if request.platform_status not in {
            PlatformStatus.EXPECTED,
            PlatformStatus.NOT_EXPECTED,
        }:
            raise self._skipped("PLATFORM_UNRESOLVED")
        if (
            request.context_id is None
            or request.operational_area_id is None
            or request.scenario_id is None
        ):
            raise ValueError("complete context requires context, area, and scenario identifiers")

        permissions = await self.permission_repository.find_by_platform_and_context(
            request.platform_id, request.context_id
        )
        plans = await self.flight_plan_repository.find_by_platform_and_context(
            request.platform_id, request.context_id
        )
        permissions = [
            row
            for row in permissions
            if row["scenario_id"] == request.scenario_id
            and row["operational_area_id"] == request.operational_area_id
        ]
        plans = [
            row
            for row in plans
            if row["scenario_id"] == request.scenario_id
            and row["operational_area_id"] == request.operational_area_id
        ]
        permission_status = _permission_status(
            permissions, request.observation_time_utc, request.observation_end_time_utc
        )
        plan_status = _flight_plan_status(
            plans, request.observation_time_utc, request.observation_end_time_utc
        )
        return PermissionFlightPlanResult(
            permission_status=permission_status,
            flight_plan_status=plan_status,
            record_consistency=resolve_record_consistency(permission_status, plan_status),
            permission_records=[_permission_record(row) for row in permissions],
            flight_plan_records=[_plan_record(row) for row in plans],
        )

    @staticmethod
    def _skipped(reason: str) -> ToolSkipped:
        data = PermissionFlightPlanResult(
            permission_status=PermissionStatus.NOT_APPLICABLE,
            flight_plan_status=FlightPlanStatus.NOT_APPLICABLE,
            record_consistency=RecordConsistency.NOT_APPLICABLE,
            skip_reason=reason,
        )
        return ToolSkipped(data, reason)
