"""Persistence-only repository for event-memory tables."""

from datetime import datetime
from typing import Any

import aiosqlite

from operational_decision.contracts.common import EventStatus
from operational_decision.memory.database import EventMemoryDatabase
from operational_decision.persistence.sqlite_database import (
    decode_json,
    parse_utc,
    row_to_dict,
    serialize_utc,
)

ACTIVE_EVENT_STATUSES = (
    EventStatus.CREATED,
    EventStatus.INPUT_VALIDATED,
    EventStatus.CONTEXT_RESOLVED,
    EventStatus.WAITING_FOR_GPU_HANDOFF,
    EventStatus.TOOLS_RUNNING,
    EventStatus.TOOLS_COMPLETED,
    EventStatus.VERIFICATION_COMPLETED,
    EventStatus.RISK_ASSESSED,
    EventStatus.RAG_COMPLETED,
    EventStatus.LLM_COMPLETED,
)


def map_event_row(row: aiosqlite.Row | None) -> dict[str, Any] | None:
    """Map a persisted event row to typed status and datetime values."""
    mapped = row_to_dict(row)
    if mapped is None:
        return None
    mapped["event_status"] = EventStatus(mapped["event_status"])
    for field in ("observation_time_utc", "created_at_utc", "updated_at_utc", "completed_at_utc"):
        if mapped[field] is not None:
            mapped[field] = parse_utc(mapped[field])
    return mapped


class EventRepository:
    """Read and write event-memory rows without lifecycle decisions."""

    def __init__(self, database: EventMemoryDatabase) -> None:
        """Bind the repository to an event-memory database."""
        self.database = database

    async def insert_event(
        self,
        connection: aiosqlite.Connection,
        *,
        event_id: str,
        request_id: str,
        created_at_utc: datetime,
        video_id: str | None,
        track_id: str | None,
    ) -> None:
        """Insert a minimal CREATED event inside the caller transaction."""
        timestamp = serialize_utc(created_at_utc)
        await connection.execute(
            """INSERT INTO events (
                event_id, request_id, video_id, track_id, event_status,
                created_at_utc, updated_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                event_id,
                request_id,
                video_id,
                track_id,
                EventStatus.CREATED.value,
                timestamp,
                timestamp,
            ),
        )

    async def assign_fingerprint(
        self,
        connection: aiosqlite.Connection,
        *,
        event_id: str,
        fingerprint: str,
        retry_of_event_id: str | None,
        updated_at_utc: datetime,
    ) -> None:
        """Attach canonical fingerprint and optional retry relationship."""
        await connection.execute(
            """UPDATE events
            SET event_fingerprint = ?, retry_of_event_id = ?, updated_at_utc = ?
            WHERE event_id = ?""",
            (
                fingerprint,
                retry_of_event_id,
                serialize_utc(updated_at_utc),
                event_id,
            ),
        )

    async def insert_raw_input(
        self,
        connection: aiosqlite.Connection,
        *,
        event_id: str,
        sanitized_request_json: str,
        created_at_utc: datetime,
    ) -> None:
        """Persist one sanitized raw request inside the event transaction."""
        await connection.execute(
            """INSERT INTO raw_inputs
            (event_id, sanitized_request_json, created_at_utc) VALUES (?, ?, ?)""",
            (event_id, sanitized_request_json, serialize_utc(created_at_utc)),
        )

    async def find_finalized_by_fingerprint(
        self, connection: aiosqlite.Connection, fingerprint: str
    ) -> dict[str, Any] | None:
        """Find the canonical finalized event for a fingerprint."""
        cursor = await connection.execute(
            """SELECT * FROM events
            WHERE event_fingerprint = ? AND event_status = ?
            ORDER BY created_at_utc DESC LIMIT 1""",
            (fingerprint, EventStatus.FINALIZED.value),
        )
        return map_event_row(await cursor.fetchone())

    async def find_active_by_fingerprint(
        self, connection: aiosqlite.Connection, fingerprint: str
    ) -> dict[str, Any] | None:
        """Find an active event for a fingerprint within the locked transaction."""
        cursor = await connection.execute(
            """SELECT * FROM events
            WHERE event_fingerprint = ?
              AND event_status IN (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ORDER BY created_at_utc DESC LIMIT 1""",
            (fingerprint, *(status.value for status in ACTIVE_EVENT_STATUSES)),
        )
        return map_event_row(await cursor.fetchone())

    async def find_latest_failed_by_fingerprint(
        self, connection: aiosqlite.Connection, fingerprint: str
    ) -> dict[str, Any] | None:
        """Find the newest failed event eligible as a retry parent."""
        cursor = await connection.execute(
            """SELECT * FROM events
            WHERE event_fingerprint = ? AND event_status = ?
            ORDER BY created_at_utc DESC LIMIT 1""",
            (fingerprint, EventStatus.FAILED.value),
        )
        return map_event_row(await cursor.fetchone())

    async def get_event(self, event_id: str) -> dict[str, Any] | None:
        """Read one event by ID or return None."""
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                "SELECT * FROM events WHERE event_id = ?", (event_id,)
            )
            return map_event_row(await cursor.fetchone())

    async def get_final_output(self, event_id: str) -> dict[str, Any] | None:
        """Read and decode one final output row."""
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                "SELECT * FROM final_outputs WHERE event_id = ?", (event_id,)
            )
            row = row_to_dict(await cursor.fetchone())
        if row is None:
            return None
        row["output"] = decode_json(row.pop("output_json"))
        row["created_at_utc"] = parse_utc(row["created_at_utc"])
        return row

    async def list_finalized_outputs_for_video(self, video_id: str) -> list[dict[str, Any]]:
        """Read and decode every finalized event's output for one video, oldest first.

        get_final_output(event_id)'nin toplu hâli — video-geneli özet (bkz.
        decision/video_summary.py) o videoya ait tüm hedef-bazlı nihai kararları
        tek seferde okumak için kullanır.
        """
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                """SELECT final_outputs.* FROM final_outputs
                JOIN events ON events.event_id = final_outputs.event_id
                WHERE events.video_id = ? AND events.event_status = ?
                ORDER BY final_outputs.created_at_utc ASC""",
                (video_id, EventStatus.FINALIZED.value),
            )
            rows = [row_to_dict(row) for row in await cursor.fetchall()]
        outputs: list[dict[str, Any]] = []
        for row in rows:
            if row is None:
                continue
            row["output"] = decode_json(row.pop("output_json"))
            row["created_at_utc"] = parse_utc(row["created_at_utc"])
            outputs.append(row)
        return outputs

    async def count_for_fingerprint(self, fingerprint: str) -> int:
        """Count persisted events for integration verification."""
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                "SELECT COUNT(*) FROM events WHERE event_fingerprint = ?", (fingerprint,)
            )
            row = await cursor.fetchone()
        if row is None:
            raise RuntimeError("COUNT query returned no row")
        return int(row[0])
