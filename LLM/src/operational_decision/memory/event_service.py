"""Transactional event lifecycle, audit, and idempotency service."""

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import Any
from uuid import uuid4

from operational_decision.contracts.common import EventStatus
from operational_decision.memory.database import EventMemoryDatabase
from operational_decision.memory.event_repository import EventRepository, map_event_row
from operational_decision.persistence.sqlite_database import (
    decode_json,
    encode_json,
    parse_utc,
    row_to_dict,
    sanitize_raw_request,
    serialize_utc,
    utc_now,
)


class EventCreationKind(StrEnum):
    """Typed outcomes of transactional event registration."""

    CREATED = "CREATED"
    RETRY_CREATED = "RETRY_CREATED"
    FINALIZED_DUPLICATE = "FINALIZED_DUPLICATE"


@dataclass(frozen=True, slots=True)
class EventCreationResult:
    """Event registration result with optional existing final output."""

    kind: EventCreationKind
    event: dict[str, Any]
    final_output: dict[str, Any] | None = None


class DuplicateProcessingError(RuntimeError):
    """Signal that the same fingerprint is already being processed."""

    def __init__(self, existing_event_id: str) -> None:
        """Record the active event that caused the duplicate result."""
        self.existing_event_id = existing_event_id
        super().__init__(f"fingerprint is already active in event {existing_event_id}")


class InvalidEventTransitionError(RuntimeError):
    """Signal an undeclared event lifecycle transition."""


class EventNotFoundError(LookupError):
    """Signal that a requested event does not exist."""


class _FinalizedDuplicateRollback(RuntimeError):
    """Internal rollback carrier for a finalized duplicate."""

    def __init__(self, event: dict[str, Any]) -> None:
        self.event = event


_INTERRUPTED_RECOVERY_STATUSES = (
    EventStatus.CREATED,
    EventStatus.INPUT_VALIDATED,
    EventStatus.CONTEXT_RESOLVED,
    EventStatus.TOOLS_RUNNING,
    EventStatus.TOOLS_COMPLETED,
    EventStatus.VERIFICATION_COMPLETED,
    EventStatus.RISK_ASSESSED,
    EventStatus.RAG_COMPLETED,
    EventStatus.LLM_COMPLETED,
)

ALLOWED_TRANSITIONS: dict[EventStatus, frozenset[EventStatus]] = {
    EventStatus.CREATED: frozenset(
        {EventStatus.INPUT_VALIDATED, EventStatus.REJECTED_INVALID_INPUT, EventStatus.FAILED}
    ),
    EventStatus.INPUT_VALIDATED: frozenset(
        {
            EventStatus.CONTEXT_RESOLVED,
            EventStatus.WAITING_FOR_GPU_HANDOFF,
            EventStatus.FAILED,
        }
    ),
    EventStatus.CONTEXT_RESOLVED: frozenset(
        {EventStatus.WAITING_FOR_GPU_HANDOFF, EventStatus.TOOLS_RUNNING, EventStatus.FAILED}
    ),
    EventStatus.WAITING_FOR_GPU_HANDOFF: frozenset({EventStatus.TOOLS_RUNNING, EventStatus.FAILED}),
    EventStatus.TOOLS_RUNNING: frozenset({EventStatus.TOOLS_COMPLETED, EventStatus.FAILED}),
    EventStatus.TOOLS_COMPLETED: frozenset(
        {EventStatus.VERIFICATION_COMPLETED, EventStatus.FAILED}
    ),
    EventStatus.VERIFICATION_COMPLETED: frozenset({EventStatus.RISK_ASSESSED, EventStatus.FAILED}),
    EventStatus.RISK_ASSESSED: frozenset(
        {EventStatus.RAG_COMPLETED, EventStatus.LLM_COMPLETED, EventStatus.FAILED}
    ),
    EventStatus.RAG_COMPLETED: frozenset({EventStatus.LLM_COMPLETED, EventStatus.FAILED}),
    EventStatus.LLM_COMPLETED: frozenset({EventStatus.FINALIZED, EventStatus.FAILED}),
    EventStatus.FINALIZED: frozenset(),
    EventStatus.FAILED: frozenset(),
    EventStatus.REJECTED_INVALID_INPUT: frozenset(),
}


def generate_event_fingerprint(
    video_id: str, track_id: str, first_seen_offset_seconds: float
) -> str:
    """Generate the specification-defined stable event fingerprint."""
    canonical = f"{video_id}|{track_id}|{first_seen_offset_seconds:.3f}"
    return sha256(canonical.encode("utf-8")).hexdigest()


class EventService:
    """Coordinate event persistence under explicit SQLite transactions."""

    def __init__(self, database: EventMemoryDatabase) -> None:
        """Bind lifecycle operations to one event-memory database."""
        self.database = database
        self.repository = EventRepository(database)

    async def recover_interrupted_events(self) -> int:
        """Fail non-waiting events left active by a previous local process."""
        placeholders = ",".join("?" for _ in _INTERRUPTED_RECOVERY_STATUSES)
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                f"""SELECT event_id FROM events
                WHERE event_status IN ({placeholders})""",  # noqa: S608
                tuple(status.value for status in _INTERRUPTED_RECOVERY_STATUSES),
            )
            event_ids = [str(row["event_id"]) for row in await cursor.fetchall()]
        for event_id in event_ids:
            await self.mark_event_failed(
                event_id,
                "PROCESS_RESTARTED",
                "Previous local process ended before event finalization.",
            )
        return len(event_ids)

    async def create_event(
        self,
        *,
        raw_request: object,
        fingerprint: str | None = None,
        video_id: str | None = None,
        track_id: str | None = None,
        event_id: str | None = None,
        request_id: str | None = None,
    ) -> EventCreationResult:
        """Create, audit, and transactionally register an optional fingerprint."""
        resolved_event_id = event_id or f"evt_{uuid4().hex}"
        resolved_request_id = request_id or f"req_{uuid4().hex}"
        now = utc_now()
        retry_of_event_id: str | None = None
        try:
            async with self.database.transaction() as connection:
                await self.repository.insert_event(
                    connection,
                    event_id=resolved_event_id,
                    request_id=resolved_request_id,
                    created_at_utc=now,
                    video_id=video_id,
                    track_id=track_id,
                )
                await self.repository.insert_raw_input(
                    connection,
                    event_id=resolved_event_id,
                    sanitized_request_json=sanitize_raw_request(raw_request),
                    created_at_utc=now,
                )
                if fingerprint is not None:
                    finalized = await self.repository.find_finalized_by_fingerprint(
                        connection, fingerprint
                    )
                    if finalized is not None:
                        raise _FinalizedDuplicateRollback(finalized)
                    active = await self.repository.find_active_by_fingerprint(
                        connection, fingerprint
                    )
                    if active is not None:
                        raise DuplicateProcessingError(active["event_id"])
                    failed = await self.repository.find_latest_failed_by_fingerprint(
                        connection, fingerprint
                    )
                    retry_of_event_id = None if failed is None else failed["event_id"]
                    await self.repository.assign_fingerprint(
                        connection,
                        event_id=resolved_event_id,
                        fingerprint=fingerprint,
                        retry_of_event_id=retry_of_event_id,
                        updated_at_utc=now,
                    )
        except _FinalizedDuplicateRollback as duplicate:
            final_output = await self.repository.get_final_output(duplicate.event["event_id"])
            return EventCreationResult(
                kind=EventCreationKind.FINALIZED_DUPLICATE,
                event=duplicate.event,
                final_output=final_output,
            )
        event = await self.get_event(resolved_event_id)
        if event is None:
            raise RuntimeError("created event could not be read back")
        kind = (
            EventCreationKind.RETRY_CREATED
            if retry_of_event_id is not None
            else EventCreationKind.CREATED
        )
        return EventCreationResult(kind=kind, event=event)

    async def get_event(self, event_id: str) -> dict[str, Any] | None:
        """Read one event without manufacturing a missing value."""
        return await self.repository.get_event(event_id)

    async def update_event_status(self, event_id: str, status: EventStatus) -> None:
        """Validate and persist one lifecycle transition with an audit step."""
        now = utc_now()
        async with self.database.transaction() as connection:
            cursor = await connection.execute(
                "SELECT * FROM events WHERE event_id = ?", (event_id,)
            )
            event = map_event_row(await cursor.fetchone())
            if event is None:
                raise EventNotFoundError(event_id)
            current = event["event_status"]
            if status not in ALLOWED_TRANSITIONS[current]:
                raise InvalidEventTransitionError(f"invalid transition {current} -> {status}")
            completed_at = (
                now
                if status
                in {
                    EventStatus.FINALIZED,
                    EventStatus.FAILED,
                    EventStatus.REJECTED_INVALID_INPUT,
                }
                else None
            )
            await connection.execute(
                """UPDATE events SET event_status = ?, updated_at_utc = ?, completed_at_utc = ?
                WHERE event_id = ?""",
                (
                    status.value,
                    serialize_utc(now),
                    serialize_utc(completed_at) if completed_at is not None else None,
                    event_id,
                ),
            )
            await connection.execute(
                """INSERT INTO event_steps
                (event_id, step_name, step_status, payload_json, created_at_utc)
                VALUES (?, ?, ?, ?, ?)""",
                (event_id, "EVENT_STATUS", status.value, None, serialize_utc(now)),
            )

    async def record_event_step(
        self,
        event_id: str,
        step_name: str,
        step_status: str,
        payload: object | None = None,
    ) -> None:
        """Append one ordered event trace step."""
        async with self.database.transaction() as connection:
            await connection.execute(
                """INSERT INTO event_steps
                (event_id, step_name, step_status, payload_json, created_at_utc)
                VALUES (?, ?, ?, ?, ?)""",
                (
                    event_id,
                    step_name,
                    step_status,
                    encode_json(payload) if payload is not None else None,
                    serialize_utc(utc_now()),
                ),
            )

    async def record_tool_execution(
        self,
        *,
        event_id: str,
        request_id: str,
        tool_name: str,
        attempt_number: int,
        execution_status: str,
        domain_status: str | None = None,
        request: object | None = None,
        response: object | None = None,
        latency_ms: int | None = None,
        error_code: str | None = None,
    ) -> str:
        """Persist one tool attempt under its own generated primary key."""
        if attempt_number < 1:
            raise ValueError("attempt_number must start at 1")
        tool_execution_id = f"tool_{uuid4().hex}"
        async with self.database.transaction() as connection:
            await connection.execute(
                """INSERT INTO tool_executions (
                    tool_execution_id, request_id, event_id, tool_name, attempt_number,
                    execution_status, domain_status, request_json, response_json,
                    latency_ms, error_code, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    tool_execution_id,
                    request_id,
                    event_id,
                    tool_name,
                    attempt_number,
                    execution_status,
                    domain_status,
                    encode_json(request) if request is not None else None,
                    encode_json(response) if response is not None else None,
                    latency_ms,
                    error_code,
                    serialize_utc(utc_now()),
                ),
            )
        return tool_execution_id

    async def store_final_output(self, event_id: str, schema_version: str, output: object) -> None:
        """Persist one final output without changing lifecycle status."""
        async with self.database.transaction() as connection:
            await connection.execute(
                """INSERT INTO final_outputs
                (event_id, schema_version, output_json, created_at_utc)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(event_id) DO UPDATE SET
                    schema_version = excluded.schema_version,
                    output_json = excluded.output_json,
                    created_at_utc = excluded.created_at_utc""",
                (
                    event_id,
                    schema_version,
                    encode_json(output),
                    serialize_utc(utc_now()),
                ),
            )

    async def finalize_event(self, event_id: str, schema_version: str, output: object) -> None:
        """Store final output and transition an LLM-completed event atomically."""
        now = serialize_utc(utc_now())
        async with self.database.transaction() as connection:
            cursor = await connection.execute(
                "SELECT event_status FROM events WHERE event_id = ?", (event_id,)
            )
            row = await cursor.fetchone()
            if row is None:
                raise EventNotFoundError(event_id)
            if EventStatus(row[0]) is not EventStatus.LLM_COMPLETED:
                raise InvalidEventTransitionError("only LLM_COMPLETED events may be finalized")
            await connection.execute(
                """INSERT INTO final_outputs
                (event_id, schema_version, output_json, created_at_utc)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(event_id) DO UPDATE SET
                    schema_version = excluded.schema_version,
                    output_json = excluded.output_json,
                    created_at_utc = excluded.created_at_utc""",
                (event_id, schema_version, encode_json(output), now),
            )
            await connection.execute(
                """UPDATE events SET event_status = ?, updated_at_utc = ?,
                completed_at_utc = ? WHERE event_id = ?""",
                (EventStatus.FINALIZED.value, now, now, event_id),
            )
            await connection.execute(
                """INSERT INTO event_steps
                (event_id, step_name, step_status, payload_json, created_at_utc)
                VALUES (?, ?, ?, ?, ?)""",
                (event_id, "EVENT_STATUS", EventStatus.FINALIZED.value, None, now),
            )

    async def reject_invalid_input(self, event_id: str, error_code: str) -> None:
        """Mark an audited fingerprint-free event as rejected invalid input."""
        async with self.database.transaction() as connection:
            cursor = await connection.execute(
                "SELECT event_status FROM events WHERE event_id = ?", (event_id,)
            )
            row = await cursor.fetchone()
            if row is None:
                raise EventNotFoundError(event_id)
            if EventStatus(row[0]) is not EventStatus.CREATED:
                raise InvalidEventTransitionError("only CREATED events may reject invalid input")
            now = serialize_utc(utc_now())
            await connection.execute(
                """UPDATE events SET event_status = ?, error_code = ?, updated_at_utc = ?,
                completed_at_utc = ? WHERE event_id = ?""",
                (EventStatus.REJECTED_INVALID_INPUT.value, error_code, now, now, event_id),
            )

    async def mark_event_failed(self, event_id: str, error_code: str, error_message: str) -> None:
        """Mark a nonterminal event failed while preserving its fingerprint."""
        event = await self.get_event(event_id)
        if event is None:
            raise EventNotFoundError(event_id)
        if EventStatus.FAILED not in ALLOWED_TRANSITIONS[event["event_status"]]:
            raise InvalidEventTransitionError("terminal event cannot be marked failed")
        now = serialize_utc(utc_now())
        async with self.database.transaction() as connection:
            await connection.execute(
                """UPDATE events SET event_status = ?, error_code = ?, error_message = ?,
                updated_at_utc = ?, completed_at_utc = ? WHERE event_id = ?""",
                (
                    EventStatus.FAILED.value,
                    error_code,
                    error_message,
                    now,
                    now,
                    event_id,
                ),
            )

    async def get_event_trace(self, event_id: str) -> dict[str, Any]:
        """Read event, ordered steps, tool attempts, final output, and raw audit."""
        async with self.database.connection() as connection:
            event_cursor = await connection.execute(
                "SELECT * FROM events WHERE event_id = ?", (event_id,)
            )
            event = map_event_row(await event_cursor.fetchone())
            if event is None:
                raise EventNotFoundError(event_id)
            steps_cursor = await connection.execute(
                "SELECT * FROM event_steps WHERE event_id = ? ORDER BY id", (event_id,)
            )
            tools_cursor = await connection.execute(
                """SELECT * FROM tool_executions WHERE event_id = ?
                ORDER BY created_at_utc, tool_name, attempt_number""",
                (event_id,),
            )
            final_cursor = await connection.execute(
                "SELECT * FROM final_outputs WHERE event_id = ?", (event_id,)
            )
            raw_cursor = await connection.execute(
                "SELECT * FROM raw_inputs WHERE event_id = ?", (event_id,)
            )
            step_rows = await steps_cursor.fetchall()
            tool_rows = await tools_cursor.fetchall()
            final_row = row_to_dict(await final_cursor.fetchone())
            raw_row = row_to_dict(await raw_cursor.fetchone())
        steps: list[dict[str, Any]] = []
        for row in step_rows:
            mapped = dict(row)
            mapped["payload"] = decode_json(mapped.pop("payload_json"))
            mapped["created_at_utc"] = parse_utc(mapped["created_at_utc"])
            steps.append(mapped)
        tools: list[dict[str, Any]] = []
        for row in tool_rows:
            mapped = dict(row)
            mapped["request"] = decode_json(mapped.pop("request_json"))
            mapped["response"] = decode_json(mapped.pop("response_json"))
            mapped["created_at_utc"] = parse_utc(mapped["created_at_utc"])
            tools.append(mapped)
        if final_row is not None:
            final_row["output"] = decode_json(final_row.pop("output_json"))
            final_row["created_at_utc"] = parse_utc(final_row["created_at_utc"])
        if raw_row is not None:
            raw_row["created_at_utc"] = parse_utc(raw_row["created_at_utc"])
        return {
            "event": event,
            "steps": steps,
            "tool_executions": tools,
            "final_output": final_row,
            "raw_input": raw_row,
        }

    async def get_final_output(self, event_id: str) -> dict[str, Any] | None:
        """Read one persisted final output for API delivery."""
        return await self.repository.get_final_output(event_id)

    async def get_active_by_fingerprint(self, fingerprint: str) -> dict[str, Any] | None:
        """Read an active event for resume checks without creating a duplicate."""
        async with self.database.connection() as connection:
            return await self.repository.find_active_by_fingerprint(connection, fingerprint)

    async def has_other_active_video_event(self, video_id: str, event_id: str) -> bool:
        """Check whether another nonterminal event belongs to the same video."""
        statuses = tuple(
            status.value
            for status in ALLOWED_TRANSITIONS
            if status
            not in {
                EventStatus.FINALIZED,
                EventStatus.FAILED,
                EventStatus.REJECTED_INVALID_INPUT,
            }
        )
        placeholders = ", ".join("?" for _ in statuses)
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                f"""SELECT 1 FROM events
                WHERE video_id = ? AND event_id != ?
                  AND event_status IN ({placeholders}) LIMIT 1""",
                (video_id, event_id, *statuses),
            )
            return await cursor.fetchone() is not None

    async def count_events_for_fingerprint(self, fingerprint: str) -> int:
        """Count fingerprint history for concurrency verification."""
        return await self.repository.count_for_fingerprint(fingerprint)
