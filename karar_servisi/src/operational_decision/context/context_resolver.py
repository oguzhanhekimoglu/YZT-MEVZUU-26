"""Resolve stored video context and its complete observation interval."""

from datetime import datetime, timedelta
from math import isfinite

from pydantic import ValidationError

from operational_decision.context.context_repository import ContextRepository
from operational_decision.contracts.common import ContextStatus
from operational_decision.contracts.context import ContextResolution, VideoContextRecord


def _validate_offset(value: float, field_name: str) -> None:
    if not isfinite(value) or value < 0:
        raise ValueError(f"{field_name} must be a finite non-negative number")


def calculate_observation_time(
    video_start_time_utc: datetime, first_seen_offset_seconds: float
) -> datetime:
    """Calculate first observation time from the video clock."""
    if video_start_time_utc.utcoffset() is None:
        raise ValueError("video_start_time_utc must be timezone-aware")
    _validate_offset(first_seen_offset_seconds, "first_seen_offset_seconds")
    return video_start_time_utc + timedelta(seconds=first_seen_offset_seconds)


def calculate_observation_end_time(
    video_start_time_utc: datetime, last_seen_offset_seconds: float
) -> datetime:
    """Calculate last observation time from the video clock."""
    if video_start_time_utc.utcoffset() is None:
        raise ValueError("video_start_time_utc must be timezone-aware")
    _validate_offset(last_seen_offset_seconds, "last_seen_offset_seconds")
    return video_start_time_utc + timedelta(seconds=last_seen_offset_seconds)


def _has_required_basics(record: VideoContextRecord) -> bool:
    return bool(
        record.video_id.strip()
        and record.camera_id.strip()
        and record.context_id.strip()
        and record.environment.strip()
        and record.video_start_time_utc.utcoffset() is not None
    )


def _has_resolvable_scope(record: VideoContextRecord) -> bool:
    return bool(record.operational_area_id.strip() and record.scenario_id.strip())


class OperationalContextResolver:
    """Resolve context without manufacturing missing operational facts."""

    def __init__(self, repository: ContextRepository) -> None:
        """Bind the resolver to the context repository."""
        self.repository = repository

    async def resolve_context(
        self,
        video_id: str,
        first_seen_offset_seconds: float,
        last_seen_offset_seconds: float,
    ) -> ContextResolution:
        """Resolve status and the full first-seen/last-seen interval."""
        if not video_id.strip():
            return ContextResolution(
                context_status=ContextStatus.INVALID,
                warnings=["VIDEO_ID_INVALID"],
            )
        try:
            _validate_offset(first_seen_offset_seconds, "first_seen_offset_seconds")
            _validate_offset(last_seen_offset_seconds, "last_seen_offset_seconds")
        except (ValueError, OverflowError) as error:
            return ContextResolution(
                context_status=ContextStatus.INVALID,
                warnings=[str(error)],
            )
        if last_seen_offset_seconds < first_seen_offset_seconds:
            return ContextResolution(
                context_status=ContextStatus.INVALID,
                warnings=["OBSERVATION_INTERVAL_INVALID"],
            )

        try:
            record = await self.repository.get_video_context(video_id)
        except (ValidationError, ValueError, OverflowError) as error:
            return ContextResolution(
                context_status=ContextStatus.INVALID,
                warnings=[str(error)],
            )
        if record is None:
            return ContextResolution(context_status=ContextStatus.MISSING)
        if not _has_required_basics(record):
            return ContextResolution(
                context_status=ContextStatus.INVALID,
                record=record,
                warnings=["CONTEXT_BASIC_FIELDS_INVALID"],
            )
        try:
            observation_time = calculate_observation_time(
                record.video_start_time_utc, first_seen_offset_seconds
            )
            observation_end = calculate_observation_end_time(
                record.video_start_time_utc, last_seen_offset_seconds
            )
        except (ValueError, OverflowError) as error:
            return ContextResolution(
                context_status=ContextStatus.INVALID,
                record=record,
                warnings=[str(error)],
            )
        if record.status != "ACTIVE":
            return ContextResolution(
                context_status=ContextStatus.INACTIVE,
                record=record,
                observation_time_utc=observation_time,
                observation_end_time_utc=observation_end,
            )
        if not _has_resolvable_scope(record):
            return ContextResolution(
                context_status=ContextStatus.PARTIAL,
                record=record,
                observation_time_utc=observation_time,
                observation_end_time_utc=observation_end,
                warnings=["AREA_OR_SCENARIO_UNRESOLVED"],
            )
        return ContextResolution(
            context_status=ContextStatus.COMPLETE,
            record=record,
            observation_time_utc=observation_time,
            observation_end_time_utc=observation_end,
        )
