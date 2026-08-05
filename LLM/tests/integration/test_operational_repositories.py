"""Integration tests for operational persistence repositories."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from operational_decision.context.context_repository import ContextRepository
from operational_decision.contracts.context import VideoContextRecord
from operational_decision.operational.database import OperationalDatabase
from operational_decision.operational.flight_plan_repository import FlightPlanRepository
from operational_decision.operational.notam_repository import NotamRepository
from operational_decision.operational.permission_repository import PermissionRepository
from operational_decision.persistence.sqlite_database import parse_utc, serialize_utc

OBSERVATION = datetime(2026, 8, 10, 11, 20, 8, 200000, tzinfo=UTC)


@pytest.fixture
async def operational_database(tmp_path: Path) -> OperationalDatabase:
    """Create an isolated migrated operational database."""
    database = OperationalDatabase(tmp_path / "operational.db")
    await database.initialize()
    return database


@pytest.mark.asyncio
async def test_context_insert_and_read(operational_database: OperationalDatabase) -> None:
    """Video context records round-trip through their repository."""
    repository = ContextRepository(operational_database)
    record = VideoContextRecord(
        video_id="VIDEO_001",
        camera_id="CAM_01",
        context_id="CTX_01",
        operational_area_id="AREA_01",
        scenario_id="SCN_01",
        video_start_time_utc=OBSERVATION,
        description="Demo",
        environment="DEMO",
        status="ACTIVE",
        source_type="DEMO_MOCK",
    )
    await repository.upsert(record)
    loaded = await repository.get_video_context("VIDEO_001")
    assert loaded == record
    assert await repository.get_video_context("UNKNOWN") is None


@pytest.mark.asyncio
async def test_permission_lookup_by_platform_and_time(
    operational_database: OperationalDatabase,
) -> None:
    """Permission rows are filtered only by persistence lookup fields."""
    repository = PermissionRepository(operational_database)
    await repository.upsert(
        {
            "permission_id": "PERM_01",
            "platform_id": "PLT_F16",
            "context_id": "CTX_01",
            "valid_from_utc": datetime(2026, 8, 10, 10, tzinfo=UTC),
            "valid_to_utc": datetime(2026, 8, 10, 12, tzinfo=UTC),
            "permission_status": "VALID",
            "source_type": "DEMO_MOCK",
        }
    )
    rows = await repository.find_by_platform_and_time("PLT_F16", OBSERVATION)
    assert [row["permission_id"] for row in rows] == ["PERM_01"]
    assert await repository.find_by_platform_and_time("UNKNOWN", OBSERVATION) == []


@pytest.mark.asyncio
async def test_flight_plan_lookup(operational_database: OperationalDatabase) -> None:
    """Flight plans are read without interpreting them as permissions."""
    repository = FlightPlanRepository(operational_database)
    await repository.upsert(
        {
            "flight_plan_id": "PLAN_01",
            "platform_id": "PLT_F16",
            "context_id": "CTX_01",
            "planned_departure_utc": datetime(2026, 8, 10, 11, tzinfo=UTC),
            "planned_arrival_utc": datetime(2026, 8, 10, 13, tzinfo=UTC),
            "flight_plan_status": "FILED",
            "source_type": "DEMO_MOCK",
        }
    )
    rows = await repository.find_by_platform("PLT_F16")
    assert rows[0]["flight_plan_status"] == "FILED"
    assert await repository.find_by_platform("UNKNOWN") == []


@pytest.mark.asyncio
async def test_notam_lookup_by_area_and_time(
    operational_database: OperationalDatabase,
) -> None:
    """NOTAM rows are filtered by area and validity interval only."""
    repository = NotamRepository(operational_database)
    await repository.upsert(
        {
            "notam_id": "NOTAM_01",
            "operational_area_id": "AREA_01",
            "valid_from_utc": datetime(2026, 8, 10, 10, tzinfo=UTC),
            "valid_to_utc": datetime(2026, 8, 10, 12, tzinfo=UTC),
            "notam_status": "ACTIVE_RELEVANT",
            "operation_effect": "RESTRICTS_OPERATION",
            "summary_tr": "Demo kısıtlama kaydı.",
            "source_type": "DEMO_MOCK",
        }
    )
    rows = await repository.find_by_area_and_time("AREA_01", OBSERVATION)
    assert rows[0]["notam_id"] == "NOTAM_01"
    assert await repository.find_by_area_and_time("UNKNOWN", OBSERVATION) == []


def test_utc_round_trip_and_naive_rejection() -> None:
    """UTC serialization is canonical and rejects naive values."""
    serialized = serialize_utc(OBSERVATION)
    assert serialized == "2026-08-10T11:20:08.200Z"
    assert parse_utc(serialized) == OBSERVATION
    with pytest.raises(ValueError, match="timezone-aware"):
        serialize_utc(datetime(2026, 8, 10, 11, 20, 8))
