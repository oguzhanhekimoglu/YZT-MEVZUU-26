"""Single adapter point for current and future video event payloads."""

from collections.abc import Iterable
from decimal import Decimal, InvalidOperation

from operational_decision.contracts.video_events import (
    EventExtractionStatus,
    RawVideoEvent,
    TimestampedVideoEvent,
    UntimestampedVisualAssessment,
    VideoEventProjection,
    VideoTimestamp,
)


def _timestamp_sort_key(value: VideoTimestamp) -> tuple[int, Decimal | str]:
    """Order producer timestamps without rewriting their stored values."""
    if isinstance(value, (int, float)):
        return (0, Decimal(str(value)))
    try:
        return (0, Decimal(value))
    except InvalidOperation:
        return (1, value)


def map_video_event_projection(
    events: Iterable[RawVideoEvent] | None,
    *,
    visual_assessment_tr: str | None = None,
) -> VideoEventProjection:
    """Map producer events verbatim; never derive time from other domain records."""
    timestamped_events = sorted(
        (TimestampedVideoEvent.model_validate(event.model_dump()) for event in events or ()),
        key=lambda event: _timestamp_sort_key(event.first_seen),
    )
    if timestamped_events:
        return VideoEventProjection(
            timestamped_events=timestamped_events,
            timestamps_available=True,
            event_extraction_status=EventExtractionStatus.AVAILABLE,
        )
    assessment = (
        UntimestampedVisualAssessment(description_tr=visual_assessment_tr)
        if visual_assessment_tr
        else None
    )
    return VideoEventProjection(untimestamped_visual_assessment=assessment)
