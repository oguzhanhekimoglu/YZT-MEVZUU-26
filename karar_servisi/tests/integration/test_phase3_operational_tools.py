"""Integration tests for Phase 3 operational tools and retry audit."""
# ruff: noqa: D102, D103, D107

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from operational_decision.contracts.common import (
    ContextStatus,
    NotamOperationEffect,
    NotamStatus,
    PermissionStatus,
    PlatformStatus,
    StrictContract,
    ToolExecutionStatus,
    VisualClass,
)
from operational_decision.contracts.notam import NotamToolRequest
from operational_decision.contracts.permission import PermissionFlightPlanRequest
from operational_decision.memory.database import EventMemoryDatabase
from operational_decision.memory.event_service import EventService
from operational_decision.operational.database import OperationalDatabase
from operational_decision.operational.flight_plan_repository import FlightPlanRepository
from operational_decision.operational.notam_repository import NotamRepository
from operational_decision.operational.permission_repository import PermissionRepository
from operational_decision.tools.base import BaseTool
from operational_decision.tools.notam_tool import NotamTool
from operational_decision.tools.permission_flight_plan_tool import PermissionFlightPlanTool

NOW = datetime(2026, 8, 10, 11, 20, tzinfo=UTC)


@pytest.fixture
async def operational_database(tmp_path: Path) -> OperationalDatabase:
    database = OperationalDatabase(tmp_path / "operational.db")
    await database.initialize()
    return database


@pytest.mark.asyncio
async def test_context_to_permission_gate_skips_partial_context(
    operational_database: OperationalDatabase,
) -> None:
    tool = PermissionFlightPlanTool(
        PermissionRepository(operational_database),
        FlightPlanRepository(operational_database),
        event_id="evt_1",
        request_id="req_1",
    )
    response = await tool.execute(
        PermissionFlightPlanRequest(
            platform_id="PLT_F16",
            context_id="CTX",
            operational_area_id="AREA",
            scenario_id="SCN",
            observation_time_utc=NOW,
            observation_end_time_utc=NOW,
            context_status=ContextStatus.PARTIAL,
            platform_execution_status=ToolExecutionStatus.SUCCESS,
            platform_status=PlatformStatus.EXPECTED,
        ),
        timeout_seconds=1,
    )
    assert response.execution_status is ToolExecutionStatus.SKIPPED
    assert response.data is not None
    assert response.data.skip_reason == "CONTEXT_NOT_COMPLETE"


@pytest.mark.asyncio
async def test_notam_metadata_relevance_strongest_effect_and_explicit_conflict(
    operational_database: OperationalDatabase,
) -> None:
    repository = NotamRepository(operational_database)
    base = {
        "operational_area_id": "AREA",
        "valid_from_utc": datetime(2026, 8, 10, 11, tzinfo=UTC),
        "valid_to_utc": datetime(2026, 8, 10, 12, tzinfo=UTC),
        "context_id": "CTX",
        "scenario_id": "SCN",
        "affected_platform_categories": ["FIGHTER_JET"],
        "affected_platform_ids": ["PLT_F16"],
        "summary_tr": "Controlled record.",
        "source_type": "DEMO_MOCK",
    }
    await repository.upsert(
        {
            **base,
            "notam_id": "N1",
            "notam_status": "ACTIVE_RELEVANT",
            "operation_effect": "RESTRICTS_OPERATION",
        }
    )
    await repository.upsert(
        {
            **base,
            "notam_id": "N2",
            "notam_status": "ACTIVE_RELEVANT",
            "operation_effect": "PROHIBITS_OPERATION",
        }
    )
    request = NotamToolRequest(
        context_id="CTX",
        operational_area_id="AREA",
        scenario_id="SCN",
        observation_time_utc=NOW,
        observation_end_time_utc=NOW,
        visual_class=VisualClass.FIGHTER_JET,
        platform_id="PLT_F16",
        context_status=ContextStatus.COMPLETE,
    )
    tool = NotamTool(repository, event_id="evt_1", request_id="req_1")
    result = await tool.execute(request, timeout_seconds=1)
    assert result.data is not None
    assert result.data.notam_status is NotamStatus.ACTIVE_RELEVANT
    assert result.data.operation_effect is NotamOperationEffect.PROHIBITS_OPERATION

    await repository.upsert(
        {
            **base,
            "notam_id": "N3",
            "notam_status": "CONFLICTING",
            "operation_effect": "INFORMATIONAL",
        }
    )
    conflicting = await tool.execute(request, timeout_seconds=1)
    assert conflicting.data is not None
    assert conflicting.data.notam_status is NotamStatus.CONFLICTING
    assert conflicting.data.operation_effect is NotamOperationEffect.PROHIBITS_OPERATION


@pytest.mark.asyncio
async def test_notam_matching_audits_time_area_aerodrome_and_altitude_overlap(
    operational_database: OperationalDatabase,
) -> None:
    repository = NotamRepository(operational_database)
    base = {
        "operational_area_id": "AREA_ALT",
        "valid_from_utc": datetime(2026, 8, 10, 11, tzinfo=UTC),
        "valid_to_utc": datetime(2026, 8, 10, 12, tzinfo=UTC),
        "context_id": "CTX_ALT",
        "scenario_id": "SCN_ALT",
        "fir_code": "LTAA",
        "aerodrome_code": "LTBA",
        "notam_status": "ACTIVE_RELEVANT",
        "operation_effect": "RESTRICTS_OPERATION",
        "summary_tr": "Controlled altitude record.",
        "source_type": "DEMO_MOCK",
    }
    await repository.upsert(
        {**base, "notam_id": "ALT_MATCH", "lower_limit": 0, "upper_limit": 12000}
    )
    await repository.upsert(
        {**base, "notam_id": "ALT_OUT", "lower_limit": 20000, "upper_limit": 30000}
    )
    response = await NotamTool(repository, event_id="evt_alt", request_id="req_alt").execute(
        NotamToolRequest(
            context_id="CTX_ALT",
            operational_area_id="AREA_ALT",
            scenario_id="SCN_ALT",
            observation_time_utc=NOW,
            observation_end_time_utc=NOW,
            visual_class=VisualClass.CIVILIAN_AIRCRAFT,
            context_status=ContextStatus.COMPLETE,
            fir_code="LTAA",
            aerodrome_code="LTBA",
            operation_lower_limit=5000,
            operation_upper_limit=10000,
        ),
        timeout_seconds=1,
    )
    assert response.data is not None
    assert response.data.matched_notam_ids == ["ALT_MATCH"]
    assert {
        "TIME_OVERLAP",
        "AREA_MATCH",
        "FIR_MATCH",
        "AERODROME_MATCH",
        "ALTITUDE_OVERLAP",
    }.issubset(set(response.data.matched_by))

    missing_altitude = await NotamTool(
        repository, event_id="evt_no_alt", request_id="req_no_alt"
    ).execute(
        NotamToolRequest(
            context_id="CTX_ALT",
            operational_area_id="AREA_ALT",
            scenario_id="SCN_ALT",
            observation_time_utc=NOW,
            observation_end_time_utc=NOW,
            visual_class=VisualClass.CIVILIAN_AIRCRAFT,
            context_status=ContextStatus.COMPLETE,
            fir_code="LTAA",
            aerodrome_code="LTBA",
        ),
        timeout_seconds=1,
    )
    assert missing_altitude.data is not None
    assert missing_altitude.data.notam_status is NotamStatus.ACTIVE_NOT_RELEVANT
    assert missing_altitude.data.matched_notam_ids == []


@pytest.mark.asyncio
async def test_notam_inactive_temporal_states(
    operational_database: OperationalDatabase,
) -> None:
    repository = NotamRepository(operational_database)
    tool = NotamTool(repository, event_id="evt_1", request_id="req_1")

    def request(area: str) -> NotamToolRequest:
        return NotamToolRequest(
            context_id="CTX",
            operational_area_id=area,
            scenario_id="SCN",
            observation_time_utc=NOW,
            observation_end_time_utc=NOW,
            visual_class=VisualClass.FIGHTER_JET,
            context_status=ContextStatus.COMPLETE,
        )

    common = {
        "notam_status": "ACTIVE_RELEVANT",
        "operation_effect": "INFORMATIONAL",
        "summary_tr": "Temporal record.",
        "source_type": "DEMO_MOCK",
    }
    await repository.upsert(
        {
            **common,
            "notam_id": "PAST",
            "operational_area_id": "PAST_AREA",
            "valid_from_utc": datetime(2026, 8, 10, 9, tzinfo=UTC),
            "valid_to_utc": datetime(2026, 8, 10, 10, tzinfo=UTC),
        }
    )
    await repository.upsert(
        {
            **common,
            "notam_id": "FUTURE",
            "operational_area_id": "FUTURE_AREA",
            "valid_from_utc": datetime(2026, 8, 10, 13, tzinfo=UTC),
            "valid_to_utc": datetime(2026, 8, 10, 14, tzinfo=UTC),
        }
    )
    past = await tool.execute(request("PAST_AREA"), timeout_seconds=1)
    future = await tool.execute(request("FUTURE_AREA"), timeout_seconds=1)
    none = await tool.execute(request("EMPTY_AREA"), timeout_seconds=1)
    assert past.data is not None and past.data.notam_status is NotamStatus.EXPIRED_ONLY
    assert future.data is not None and future.data.notam_status is NotamStatus.NOT_YET_ACTIVE
    assert none.data is not None and none.data.notam_status is NotamStatus.NONE_ACTIVE


class AuditRequest(StrictContract):
    """Minimal retry-audit request."""

    value: int


class AuditResult(StrictContract):
    """Minimal retry-audit result."""

    permission_status: PermissionStatus


class AuditedFlakyTool(BaseTool[AuditRequest, AuditResult]):
    """Raise one SQLite lock then return domain NOT_FOUND."""

    tool_name = "audited_flaky_tool"

    def __init__(self, event_service: EventService, event_id: str, request_id: str) -> None:
        super().__init__(
            event_id=event_id,
            request_id=request_id,
            event_service=event_service,
        )
        self.calls = 0

    async def execute_internal(self, request: AuditRequest) -> AuditResult:
        self.calls += 1
        if self.calls == 1:
            raise sqlite3.OperationalError("database is locked")
        return AuditResult(permission_status=PermissionStatus.NOT_FOUND)


@pytest.mark.asyncio
async def test_each_sqlite_retry_is_a_separate_audit_record(tmp_path: Path) -> None:
    database = EventMemoryDatabase(tmp_path / "event_memory.db")
    await database.initialize()
    service = EventService(database)
    event = await service.create_event(raw_request={})
    tool = AuditedFlakyTool(service, event.event["event_id"], event.event["request_id"])
    response = await tool.execute(AuditRequest(value=1), timeout_seconds=1)
    trace = await service.get_event_trace(event.event["event_id"])
    attempts = trace["tool_executions"]
    assert response.execution_status is ToolExecutionStatus.SUCCESS
    assert len(attempts) == 2
    assert attempts[0]["execution_status"] == "ERROR"
    assert attempts[0]["error_code"] == "SQLITE_LOCKED"
    assert attempts[1]["execution_status"] == "SUCCESS"
    assert attempts[1]["domain_status"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_unresolved_platform_and_incomplete_notam_are_reasoned_skips(
    operational_database: OperationalDatabase,
) -> None:
    permission = await PermissionFlightPlanTool(
        PermissionRepository(operational_database),
        FlightPlanRepository(operational_database),
        event_id="evt_skip",
        request_id="req_skip",
    ).execute(
        PermissionFlightPlanRequest(
            observation_time_utc=NOW,
            observation_end_time_utc=NOW,
            context_status=ContextStatus.COMPLETE,
            platform_execution_status=ToolExecutionStatus.SUCCESS,
            platform_status=PlatformStatus.UNKNOWN,
        ),
        timeout_seconds=1,
    )
    assert permission.execution_status is ToolExecutionStatus.SKIPPED
    assert permission.data is not None
    assert permission.data.skip_reason == "PLATFORM_UNRESOLVED"

    notam = await NotamTool(
        NotamRepository(operational_database),
        event_id="evt_skip",
        request_id="req_skip",
    ).execute(
        NotamToolRequest(
            observation_time_utc=NOW,
            observation_end_time_utc=NOW,
            visual_class=VisualClass.FIGHTER_JET,
            context_status=ContextStatus.MISSING,
        ),
        timeout_seconds=1,
    )
    assert notam.execution_status is ToolExecutionStatus.SKIPPED
    assert notam.data is not None
    assert notam.data.skip_reason == "CONTEXT_NOT_COMPLETE"
