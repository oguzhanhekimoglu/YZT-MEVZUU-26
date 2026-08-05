"""Integration tests for event lifecycle, idempotency, and audit."""

import asyncio
from pathlib import Path

import pytest

from operational_decision.contracts.common import EventStatus
from operational_decision.memory.database import EventMemoryDatabase
from operational_decision.memory.event_service import (
    DuplicateProcessingError,
    EventCreationKind,
    EventService,
    InvalidEventTransitionError,
)


@pytest.fixture
async def event_service(tmp_path: Path) -> EventService:
    """Create an isolated event-memory service."""
    database = EventMemoryDatabase(tmp_path / "event_memory.db")
    await database.initialize()
    return EventService(database)


@pytest.mark.asyncio
async def test_event_created_and_valid_transition(event_service: EventService) -> None:
    """New events start CREATED and accept declared lifecycle transitions."""
    result = await event_service.create_event(raw_request={"video_id": "VIDEO_001"})
    assert result.kind is EventCreationKind.CREATED
    assert result.event["event_status"] == EventStatus.CREATED
    await event_service.update_event_status(result.event["event_id"], EventStatus.INPUT_VALIDATED)
    event = await event_service.get_event(result.event["event_id"])
    assert event is not None and event["event_status"] == EventStatus.INPUT_VALIDATED


@pytest.mark.asyncio
async def test_invalid_transition_is_rejected(event_service: EventService) -> None:
    """Undeclared lifecycle jumps are rejected."""
    result = await event_service.create_event(raw_request={})
    with pytest.raises(InvalidEventTransitionError):
        await event_service.update_event_status(result.event["event_id"], EventStatus.FINALIZED)


@pytest.mark.asyncio
async def test_steps_final_output_and_trace(event_service: EventService) -> None:
    """Trace preserves ordered steps and the associated final output."""
    result = await event_service.create_event(raw_request={"video_id": "VIDEO_001"})
    event_id = result.event["event_id"]
    await event_service.record_event_step(event_id, "first", "SUCCESS", {"order": 1})
    await event_service.record_event_step(event_id, "second", "SUCCESS", {"order": 2})
    await event_service.store_final_output(
        event_id, "final-output/2.1", {"event_id": event_id, "decision": "INDETERMINATE"}
    )
    trace = await event_service.get_event_trace(event_id)
    assert [step["step_name"] for step in trace["steps"]] == ["first", "second"]
    assert trace["final_output"]["schema_version"] == "final-output/2.1"


@pytest.mark.asyncio
async def test_invalid_input_is_audited(event_service: EventService) -> None:
    """Invalid input remains auditable without a fingerprint."""
    result = await event_service.create_event(
        raw_request={"password": "secret", "path": "C:\\private\\crop.bin"}
    )
    await event_service.reject_invalid_input(result.event["event_id"], "INVALID_INPUT")
    trace = await event_service.get_event_trace(result.event["event_id"])
    assert trace["event"]["event_status"] == EventStatus.REJECTED_INVALID_INPUT
    assert trace["event"]["event_fingerprint"] is None
    assert "secret" not in trace["raw_input"]["sanitized_request_json"]
    assert "C:\\private" not in trace["raw_input"]["sanitized_request_json"]


@pytest.mark.asyncio
async def test_finalized_duplicate_returns_existing_output(event_service: EventService) -> None:
    """A finalized fingerprint returns its canonical event and output."""
    fingerprint = "a" * 64
    first = await event_service.create_event(raw_request={}, fingerprint=fingerprint)
    for status in (
        EventStatus.INPUT_VALIDATED,
        EventStatus.CONTEXT_RESOLVED,
        EventStatus.TOOLS_RUNNING,
        EventStatus.TOOLS_COMPLETED,
        EventStatus.VERIFICATION_COMPLETED,
        EventStatus.RISK_ASSESSED,
        EventStatus.LLM_COMPLETED,
    ):
        await event_service.update_event_status(first.event["event_id"], status)
    await event_service.finalize_event(
        first.event["event_id"],
        "final-output/2.1",
        {"event_id": first.event["event_id"], "decision": "INDETERMINATE"},
    )
    duplicate = await event_service.create_event(raw_request={}, fingerprint=fingerprint)
    assert duplicate.kind is EventCreationKind.FINALIZED_DUPLICATE
    assert duplicate.event["event_id"] == first.event["event_id"]
    assert duplicate.final_output is not None


@pytest.mark.asyncio
async def test_active_duplicate_raises_typed_error(event_service: EventService) -> None:
    """An active fingerprint produces a typed duplicate-processing result."""
    fingerprint = "b" * 64
    first = await event_service.create_event(raw_request={}, fingerprint=fingerprint)
    with pytest.raises(DuplicateProcessingError) as error:
        await event_service.create_event(raw_request={}, fingerprint=fingerprint)
    assert error.value.existing_event_id == first.event["event_id"]


@pytest.mark.asyncio
async def test_failed_event_allows_linked_retry(event_service: EventService) -> None:
    """A failed fingerprint permits a new event linked to the failure."""
    fingerprint = "c" * 64
    first = await event_service.create_event(raw_request={}, fingerprint=fingerprint)
    await event_service.mark_event_failed(first.event["event_id"], "TEST_FAILURE", "failed")
    retry = await event_service.create_event(raw_request={}, fingerprint=fingerprint)
    assert retry.kind is EventCreationKind.RETRY_CREATED
    assert retry.event["retry_of_event_id"] == first.event["event_id"]


@pytest.mark.asyncio
async def test_concurrent_fingerprint_allows_one_active_event(
    event_service: EventService,
) -> None:
    """Transactional fingerprint registration permits only one active event."""
    fingerprint = "d" * 64
    results = await asyncio.gather(
        *(event_service.create_event(raw_request={}, fingerprint=fingerprint) for _ in range(5)),
        return_exceptions=True,
    )
    created = [item for item in results if not isinstance(item, Exception)]
    duplicates = [item for item in results if isinstance(item, DuplicateProcessingError)]
    assert len(created) == 1
    assert len(duplicates) == 4
    assert await event_service.count_events_for_fingerprint(fingerprint) == 1


@pytest.mark.asyncio
async def test_tool_execution_cardinality_and_retry(event_service: EventService) -> None:
    """Different tools and retry attempts coexist under one API request."""
    result = await event_service.create_event(raw_request={})
    event_id = result.event["event_id"]
    request_id = result.event["request_id"]
    await event_service.record_tool_execution(
        event_id=event_id,
        request_id=request_id,
        tool_name="platform_tool",
        attempt_number=1,
        execution_status="SUCCESS",
        domain_status="NOT_FOUND",
        response={"platform_status": "UNKNOWN"},
    )
    await event_service.record_tool_execution(
        event_id=event_id,
        request_id=request_id,
        tool_name="notam_tool",
        attempt_number=1,
        execution_status="ERROR",
        domain_status=None,
        error_code="SQLITE_BUSY",
    )
    await event_service.record_tool_execution(
        event_id=event_id,
        request_id=request_id,
        tool_name="notam_tool",
        attempt_number=2,
        execution_status="SUCCESS",
        domain_status="NONE_ACTIVE",
    )
    trace = await event_service.get_event_trace(event_id)
    assert len(trace["tool_executions"]) == 3
    assert trace["tool_executions"][0]["domain_status"] == "NOT_FOUND"
    assert trace["tool_executions"][1]["execution_status"] == "ERROR"
    assert trace["tool_executions"][1]["domain_status"] is None


@pytest.mark.asyncio
async def test_duplicate_tool_attempt_is_rejected(event_service: EventService) -> None:
    """The same event, tool, and attempt number cannot be inserted twice."""
    result = await event_service.create_event(raw_request={})
    arguments = {
        "event_id": result.event["event_id"],
        "request_id": result.event["request_id"],
        "tool_name": "platform_tool",
        "attempt_number": 1,
        "execution_status": "SUCCESS",
    }
    await event_service.record_tool_execution(**arguments)
    with pytest.raises(Exception, match="UNIQUE"):
        await event_service.record_tool_execution(**arguments)


@pytest.mark.asyncio
async def test_startup_recovery_fails_interrupted_events_but_preserves_gpu_waiting(
    event_service: EventService,
) -> None:
    """Process-restart recovery releases stale fingerprints without breaking GPU resume."""
    interrupted_fingerprint = "e" * 64
    interrupted = await event_service.create_event(
        raw_request={}, fingerprint=interrupted_fingerprint
    )
    for status in (
        EventStatus.INPUT_VALIDATED,
        EventStatus.CONTEXT_RESOLVED,
        EventStatus.TOOLS_RUNNING,
        EventStatus.TOOLS_COMPLETED,
        EventStatus.VERIFICATION_COMPLETED,
        EventStatus.RISK_ASSESSED,
    ):
        await event_service.update_event_status(interrupted.event["event_id"], status)

    waiting_fingerprint = "f" * 64
    waiting = await event_service.create_event(raw_request={}, fingerprint=waiting_fingerprint)
    for status in (
        EventStatus.INPUT_VALIDATED,
        EventStatus.CONTEXT_RESOLVED,
        EventStatus.WAITING_FOR_GPU_HANDOFF,
    ):
        await event_service.update_event_status(waiting.event["event_id"], status)

    assert await event_service.recover_interrupted_events() == 1

    interrupted_row = await event_service.get_event(interrupted.event["event_id"])
    waiting_row = await event_service.get_event(waiting.event["event_id"])
    assert interrupted_row is not None
    assert interrupted_row["event_status"] is EventStatus.FAILED
    assert interrupted_row["error_code"] == "PROCESS_RESTARTED"
    assert waiting_row is not None
    assert waiting_row["event_status"] is EventStatus.WAITING_FOR_GPU_HANDOFF

    retry = await event_service.create_event(raw_request={}, fingerprint=interrupted_fingerprint)
    assert retry.kind is EventCreationKind.RETRY_CREATED
    assert retry.event["retry_of_event_id"] == interrupted.event["event_id"]
