"""SCN-01 through SCN-04 Phase 3 record and tool acceptance tests."""
# ruff: noqa: D102, D103, D107

from pathlib import Path

import pytest

from operational_decision.context.context_repository import ContextRepository
from operational_decision.context.context_resolver import OperationalContextResolver
from operational_decision.contracts.common import (
    ContextStatus,
    FlightPlanStatus,
    NotamOperationEffect,
    NotamStatus,
    PermissionStatus,
    PlatformStatus,
    ToolExecutionStatus,
    VisualClass,
)
from operational_decision.contracts.notam import NotamToolRequest
from operational_decision.contracts.permission import PermissionFlightPlanRequest
from operational_decision.contracts.platform import PlatformToolRequest
from operational_decision.operational.database import OperationalDatabase
from operational_decision.operational.flight_plan_repository import FlightPlanRepository
from operational_decision.operational.notam_repository import NotamRepository
from operational_decision.operational.permission_repository import PermissionRepository
from operational_decision.operational.seed_loader import seed_operational_database
from operational_decision.platform.platform_registry import (
    PlatformRegistryIndex,
    load_platform_aliases,
    load_platform_registry,
)
from operational_decision.tools.notam_tool import NotamTool
from operational_decision.tools.permission_flight_plan_tool import PermissionFlightPlanTool
from operational_decision.tools.platform_tool import PlatformTool

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
async def seeded_database(tmp_path: Path) -> OperationalDatabase:
    database = OperationalDatabase(tmp_path / "operational.db")
    await database.initialize()
    await seed_operational_database(database, ROOT / "data/seeds")
    return database


@pytest.mark.asyncio
@pytest.mark.parametrize(
    (
        "scenario_id",
        "video_id",
        "context_id",
        "expected_platform",
        "expected_permission",
        "expected_plan",
        "expected_notam",
    ),
    [
        (
            "SCN-01",
            "VIDEO_001",
            "DEMO_CONTEXT_A",
            PlatformStatus.EXPECTED,
            PermissionStatus.VALID,
            FlightPlanStatus.FILED,
            NotamStatus.NONE_ACTIVE,
        ),
        (
            "SCN-02",
            "VIDEO_002",
            "DEMO_CONTEXT_A",
            PlatformStatus.EXPECTED,
            PermissionStatus.NOT_FOUND,
            FlightPlanStatus.FILED,
            NotamStatus.NONE_ACTIVE,
        ),
        (
            "SCN-03",
            "VIDEO_003",
            "DEMO_CONTEXT_B",
            PlatformStatus.NOT_EXPECTED,
            PermissionStatus.NOT_FOUND,
            FlightPlanStatus.NOT_FOUND,
            NotamStatus.NONE_ACTIVE,
        ),
        (
            "SCN-04",
            "VIDEO_004",
            "DEMO_CONTEXT_A",
            PlatformStatus.EXPECTED,
            PermissionStatus.EXPIRED,
            FlightPlanStatus.FILED,
            NotamStatus.NONE_ACTIVE,
        ),
    ],
)
async def test_phase3_scenario_records(
    seeded_database: OperationalDatabase,
    scenario_id: str,
    video_id: str,
    context_id: str,
    expected_platform: PlatformStatus,
    expected_permission: PermissionStatus,
    expected_plan: FlightPlanStatus,
    expected_notam: NotamStatus,
) -> None:
    context = await OperationalContextResolver(ContextRepository(seeded_database)).resolve_context(
        video_id, 0, 10
    )
    assert context.context_status is ContextStatus.COMPLETE
    assert context.record is not None
    assert context.observation_time_utc is not None
    assert context.observation_end_time_utc is not None

    registry = load_platform_registry(ROOT / "data/platforms/platform_registry.json")
    aliases = load_platform_aliases(ROOT / "data/platforms/platform_aliases.json")
    platform = await PlatformTool(
        PlatformRegistryIndex(registry, aliases),
        event_id=f"evt_{scenario_id}",
        request_id=f"req_{scenario_id}",
    ).execute(
        PlatformToolRequest(
            visual_class=VisualClass.FIGHTER_JET,
            final_visual_hypothesis="F-16",
            context_id=context_id,
            context_status=context.context_status,
        ),
        timeout_seconds=1,
    )
    assert platform.execution_status is ToolExecutionStatus.SUCCESS
    assert platform.data is not None
    assert platform.data.platform_status is expected_platform
    assert platform.data.platform_id == "PLT_F16"

    records = await PermissionFlightPlanTool(
        PermissionRepository(seeded_database),
        FlightPlanRepository(seeded_database),
        event_id=f"evt_{scenario_id}",
        request_id=f"req_{scenario_id}",
    ).execute(
        PermissionFlightPlanRequest(
            platform_id=platform.data.platform_id,
            context_id=context_id,
            operational_area_id=context.record.operational_area_id,
            scenario_id=scenario_id,
            observation_time_utc=context.observation_time_utc,
            observation_end_time_utc=context.observation_end_time_utc,
            context_status=context.context_status,
            platform_execution_status=platform.execution_status,
            platform_status=platform.data.platform_status,
        ),
        timeout_seconds=1,
    )
    assert records.execution_status is ToolExecutionStatus.SUCCESS
    assert records.data is not None
    assert records.data.permission_status is expected_permission
    assert records.data.flight_plan_status is expected_plan

    notam = await NotamTool(
        NotamRepository(seeded_database),
        event_id=f"evt_{scenario_id}",
        request_id=f"req_{scenario_id}",
    ).execute(
        NotamToolRequest(
            context_id=context_id,
            operational_area_id=context.record.operational_area_id,
            scenario_id=scenario_id,
            observation_time_utc=context.observation_time_utc,
            observation_end_time_utc=context.observation_end_time_utc,
            visual_class=VisualClass.FIGHTER_JET,
            platform_id=platform.data.platform_id,
            context_status=context.context_status,
            relevance_tags=["DEMO"],
        ),
        timeout_seconds=1,
    )
    assert notam.execution_status is ToolExecutionStatus.SUCCESS
    assert notam.data is not None
    assert notam.data.notam_status is expected_notam
    assert notam.data.operation_effect is NotamOperationEffect.NO_EFFECT
