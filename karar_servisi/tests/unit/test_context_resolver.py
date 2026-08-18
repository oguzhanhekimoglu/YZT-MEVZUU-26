"""Unit tests for operational context resolution."""
# ruff: noqa: D102, D103, D107

from datetime import UTC, datetime
from typing import cast

import pytest

from operational_decision.context.context_repository import ContextRepository
from operational_decision.context.context_resolver import (
    OperationalContextResolver,
    calculate_observation_end_time,
    calculate_observation_time,
)
from operational_decision.contracts.common import ContextStatus
from operational_decision.contracts.context import VideoContextRecord


class StubContextRepository:
    """Return one controlled record without persistence."""

    def __init__(self, record: VideoContextRecord | None) -> None:
        self.record = record

    async def get_video_context(self, video_id: str) -> VideoContextRecord | None:
        return self.record


def make_record(**changes: object) -> VideoContextRecord:
    values: dict[str, object] = {
        "video_id": "VIDEO_001",
        "camera_id": "CAM_01",
        "context_id": "CTX_01",
        "operational_area_id": "AREA_01",
        "scenario_id": "SCN-01",
        "video_start_time_utc": datetime(2026, 8, 10, 11, 20, tzinfo=UTC),
        "environment": "DEMO",
        "status": "ACTIVE",
        "source_type": "DEMO_MOCK",
    }
    values.update(changes)
    return VideoContextRecord.model_construct(**values)


def resolver_for(record: VideoContextRecord | None) -> OperationalContextResolver:
    repository = cast(ContextRepository, StubContextRepository(record))
    return OperationalContextResolver(repository)


def test_observation_interval_uses_first_and_last_seen() -> None:
    start = datetime(2026, 8, 10, 11, 20, tzinfo=UTC)
    assert calculate_observation_time(start, 2.5).isoformat().endswith("20:02.500000+00:00")
    assert calculate_observation_end_time(start, 9.0).isoformat().endswith("20:09+00:00")


@pytest.mark.asyncio
async def test_context_complete_missing_partial_inactive_and_invalid() -> None:
    complete = await resolver_for(make_record()).resolve_context("VIDEO_001", 2.5, 9.0)
    assert complete.context_status is ContextStatus.COMPLETE
    assert complete.observation_end_time_utc is not None
    assert complete.observation_time_utc is not None
    assert complete.observation_end_time_utc > complete.observation_time_utc

    missing = await resolver_for(None).resolve_context("UNKNOWN", 0, 1)
    assert missing.context_status is ContextStatus.MISSING

    partial = await resolver_for(make_record(operational_area_id="")).resolve_context(
        "VIDEO_001", 0, 1
    )
    assert partial.context_status is ContextStatus.PARTIAL

    inactive = await resolver_for(make_record(status="INACTIVE")).resolve_context("VIDEO_001", 0, 1)
    assert inactive.context_status is ContextStatus.INACTIVE

    invalid = await resolver_for(make_record()).resolve_context("VIDEO_001", 5, 4)
    assert invalid.context_status is ContextStatus.INVALID
