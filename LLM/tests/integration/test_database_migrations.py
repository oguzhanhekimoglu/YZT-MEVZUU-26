"""Integration tests for SQLite migration and connection guarantees."""

from pathlib import Path

import pytest

from operational_decision.memory.database import EventMemoryDatabase
from operational_decision.operational.database import OperationalDatabase


@pytest.mark.asyncio
async def test_operational_migration_creates_required_tables(tmp_path: Path) -> None:
    """A clean operational database receives every required table."""
    database = OperationalDatabase(tmp_path / "operational.db")
    await database.initialize()
    assert set(await database.list_tables()) >= {
        "schema_migrations",
        "video_contexts",
        "permissions",
        "flight_plans",
        "notams",
    }


@pytest.mark.asyncio
async def test_event_memory_migration_creates_required_tables(tmp_path: Path) -> None:
    """A clean event-memory database receives every required table."""
    database = EventMemoryDatabase(tmp_path / "event_memory.db")
    await database.initialize()
    assert set(await database.list_tables()) >= {
        "schema_migrations",
        "events",
        "event_steps",
        "tool_executions",
        "final_outputs",
        "raw_inputs",
    }


@pytest.mark.asyncio
async def test_migration_rerun_preserves_existing_data(tmp_path: Path) -> None:
    """Reapplying migrations never deletes existing rows."""
    database = OperationalDatabase(tmp_path / "operational.db")
    await database.initialize()
    async with database.transaction() as connection:
        await connection.execute(
            """INSERT INTO video_contexts (
                video_id, camera_id, context_id, operational_area_id, scenario_id,
                video_start_time_utc, environment, status, source_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "VIDEO_KEEP",
                "CAM_01",
                "CTX_01",
                "AREA_01",
                "SCN_01",
                "2026-08-10T11:20:00.000Z",
                "DEMO",
                "ACTIVE",
                "DEMO_MOCK",
            ),
        )
    assert await database.initialize() == []
    async with database.connection() as connection:
        cursor = await connection.execute(
            "SELECT COUNT(*) AS count FROM video_contexts WHERE video_id = ?",
            ("VIDEO_KEEP",),
        )
        row = await cursor.fetchone()
    assert row is not None and row["count"] == 1


@pytest.mark.asyncio
async def test_connection_pragmas_are_applied(tmp_path: Path) -> None:
    """Every connection enables foreign keys, WAL, and the required busy timeout."""
    database = EventMemoryDatabase(tmp_path / "event_memory.db")
    await database.initialize()
    async with database.connection() as connection:
        foreign_keys = await (await connection.execute("PRAGMA foreign_keys")).fetchone()
        journal_mode = await (await connection.execute("PRAGMA journal_mode")).fetchone()
        busy_timeout = await (await connection.execute("PRAGMA busy_timeout")).fetchone()
    assert foreign_keys[0] == 1
    assert journal_mode[0].lower() == "wal"
    assert busy_timeout[0] == 3000


@pytest.mark.asyncio
async def test_foreign_key_violation_is_rejected(tmp_path: Path) -> None:
    """Foreign-key enforcement rejects orphan event steps."""
    database = EventMemoryDatabase(tmp_path / "event_memory.db")
    await database.initialize()
    with pytest.raises(Exception, match="FOREIGN KEY"):
        async with database.transaction() as connection:
            await connection.execute(
                """INSERT INTO event_steps
                (event_id, step_name, step_status, payload_json, created_at_utc)
                VALUES (?, ?, ?, ?, ?)""",
                ("missing", "test", "SUCCESS", None, "2026-08-10T11:20:00.000Z"),
            )
