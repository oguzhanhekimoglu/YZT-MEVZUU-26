"""Integration tests for deterministic demo seed loading."""

from pathlib import Path

import pytest

from operational_decision.operational.database import OperationalDatabase
from operational_decision.operational.seed_loader import seed_operational_database


@pytest.mark.asyncio
async def test_seed_is_idempotent_and_demo_only(tmp_path: Path) -> None:
    """Repeated seed loading creates no duplicates and only DEMO_MOCK rows."""
    database = OperationalDatabase(tmp_path / "operational.db")
    await database.initialize()
    first = await seed_operational_database(database, Path("data/seeds"))
    second = await seed_operational_database(database, Path("data/seeds"))
    assert first.total_inserted > 0
    assert second.total_inserted == 0
    async with database.connection() as connection:
        for table in ("video_contexts", "permissions", "flight_plans", "notams"):
            row = await (
                await connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE source_type != ?",  # noqa: S608
                    ("DEMO_MOCK",),
                )
            ).fetchone()
            assert row[0] == 0
