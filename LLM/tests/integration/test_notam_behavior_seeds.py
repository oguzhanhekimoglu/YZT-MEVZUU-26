"""Seed-backed NOTAM behavior fixtures isolated from canonical demo scenarios."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from operational_decision.contracts.common import (
    ContextStatus,
    NotamOperationEffect,
    NotamStatus,
    VisualClass,
)
from operational_decision.contracts.notam import NotamToolRequest
from operational_decision.operational.database import OperationalDatabase
from operational_decision.operational.notam_repository import NotamRepository
from operational_decision.operational.seed_loader import seed_operational_database
from operational_decision.tools.notam_tool import NotamTool

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 8, 12, 10, 30, tzinfo=UTC)
_BEHAVIOR_SCOPES = {
    "INFO": "INFORMATIONAL",
    "NO_EFFECT": "NO-EFFECT",
    "TIME": "TIME-OUTSIDE",
    "FIR": "FIR-MISMATCH",
    "ALTITUDE": "ALTITUDE-MISMATCH",
    "PLATFORM": "PLATFORM-MISMATCH",
}


@pytest.fixture
async def seeded_database(tmp_path: Path) -> OperationalDatabase:
    """Load the shared DEMO_MOCK seeds into an isolated database."""
    database = OperationalDatabase(tmp_path / "operational.db")
    await database.initialize()
    await seed_operational_database(database, ROOT / "data/seeds")
    return database


async def execute_behavior(
    database: OperationalDatabase,
    behavior: str,
    *,
    observation_time: datetime = NOW,
    fir_code: str = "LTAA",
    lower_limit: int = 0,
    upper_limit: int = 10000,
    platform_id: str = "PLT_OPERATIONAL_SCOPE_ALPHA",
) -> tuple[NotamStatus, NotamOperationEffect, list[str], list[str]]:
    """Run one isolated behavior request and return its observable selection facts."""
    response = await NotamTool(
        NotamRepository(database),
        event_id=f"evt_{behavior}",
        request_id=f"req_{behavior}",
    ).execute(
        NotamToolRequest(
            context_id=f"CONTEXT_NOTAM_{behavior}",
            operational_area_id=f"AREA_NOTAM_{behavior}",
            scenario_id=f"NOTAM-BEHAVIOR-{_BEHAVIOR_SCOPES[behavior]}",
            observation_time_utc=observation_time,
            observation_end_time_utc=observation_time,
            visual_class=VisualClass.FIGHTER_JET,
            platform_id=platform_id,
            context_status=ContextStatus.COMPLETE,
            fir_code=fir_code,
            operation_lower_limit=lower_limit,
            operation_upper_limit=upper_limit,
        ),
        timeout_seconds=1,
    )
    assert response.data is not None
    return (
        response.data.notam_status,
        response.data.operation_effect,
        response.data.matched_notam_ids,
        [record.notam_id for record in response.data.active_notams],
    )


@pytest.mark.asyncio
async def test_active_informational_seed_matches_without_operational_restriction(
    seeded_database: OperationalDatabase,
) -> None:
    """An active informational seed must match without restricting the operation."""
    status, effect, matched, active = await execute_behavior(seeded_database, "INFO")
    assert status is NotamStatus.ACTIVE_RELEVANT
    assert effect is NotamOperationEffect.INFORMATIONAL
    assert matched == ["DEMO_NOTAM_BEHAVIOR_INFORMATIONAL"]
    assert active == matched


@pytest.mark.asyncio
async def test_active_no_effect_seed_matches_without_operational_restriction(
    seeded_database: OperationalDatabase,
) -> None:
    """An active no-effect seed must match without restricting the operation."""
    status, effect, matched, active = await execute_behavior(seeded_database, "NO_EFFECT")
    assert status is NotamStatus.ACTIVE_RELEVANT
    assert effect is NotamOperationEffect.NO_EFFECT
    assert matched == ["DEMO_NOTAM_BEHAVIOR_NO_EFFECT"]
    assert active == matched


@pytest.mark.asyncio
async def test_time_outside_seed_is_rejected_only_by_validity_interval(
    seeded_database: OperationalDatabase,
) -> None:
    """A temporally disjoint seed must be rejected by its validity interval."""
    status, effect, matched, active = await execute_behavior(seeded_database, "TIME")
    assert status is NotamStatus.EXPIRED_ONLY
    assert effect is NotamOperationEffect.NO_EFFECT
    assert matched == []
    assert active == []


@pytest.mark.asyncio
async def test_fir_mismatch_seed_is_active_but_not_relevant(
    seeded_database: OperationalDatabase,
) -> None:
    """An active seed with a different FIR must not be relevant."""
    status, effect, matched, active = await execute_behavior(
        seeded_database, "FIR", fir_code="LTBB"
    )
    assert status is NotamStatus.ACTIVE_NOT_RELEVANT
    assert effect is NotamOperationEffect.NO_EFFECT
    assert matched == []
    assert active == ["DEMO_NOTAM_BEHAVIOR_FIR_MISMATCH"]


@pytest.mark.asyncio
async def test_altitude_mismatch_seed_is_active_but_not_relevant(
    seeded_database: OperationalDatabase,
) -> None:
    """An active seed with a disjoint altitude band must not be relevant."""
    status, effect, matched, active = await execute_behavior(
        seeded_database, "ALTITUDE", lower_limit=0, upper_limit=10000
    )
    assert status is NotamStatus.ACTIVE_NOT_RELEVANT
    assert effect is NotamOperationEffect.NO_EFFECT
    assert matched == []
    assert active == ["DEMO_NOTAM_BEHAVIOR_ALTITUDE_MISMATCH"]


@pytest.mark.asyncio
async def test_platform_id_mismatch_seed_is_active_but_not_relevant(
    seeded_database: OperationalDatabase,
) -> None:
    """An active seed for another platform ID must not be relevant."""
    status, effect, matched, active = await execute_behavior(
        seeded_database, "PLATFORM", platform_id="PLT_OPERATIONAL_SCOPE_BETA"
    )
    assert status is NotamStatus.ACTIVE_NOT_RELEVANT
    assert effect is NotamOperationEffect.NO_EFFECT
    assert matched == []
    assert active == ["DEMO_NOTAM_BEHAVIOR_PLATFORM_MISMATCH"]
