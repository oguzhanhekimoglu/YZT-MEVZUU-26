"""Presentation-only contracts for future video event extraction."""

from enum import StrEnum
from typing import Literal, Self, TypeAlias

from pydantic import Field, model_validator

from operational_decision.contracts.common import StrictContract

VideoTimestamp: TypeAlias = int | float | str


class EventExtractionStatus(StrEnum):
    """Availability state of the external video event extractor."""

    PENDING_VIDEO_EVENT_INTEGRATION = "PENDING_VIDEO_EVENT_INTEGRATION"
    AVAILABLE = "AVAILABLE"


class RawVideoEvent(StrictContract):
    """One timestamped event supplied by the future video module."""

    event_id: str = Field(min_length=1, max_length=150)
    event_type: str = Field(min_length=1, max_length=150)
    first_seen: VideoTimestamp
    last_seen: VideoTimestamp | None = None
    critical_moment: bool = False
    description_tr: str = Field(min_length=1, max_length=2000)
    confidence: float = Field(ge=0.0, le=1.0)
    track_id: str | None = Field(default=None, min_length=1, max_length=150)
    source: str = Field(min_length=1, max_length=100)


class TimestampedVideoEvent(RawVideoEvent):
    """Validated event whose producer timestamps are retained verbatim."""


class UntimestampedVisualAssessment(StrictContract):
    """Raw visual assessment kept separate from timestamped events."""

    type: Literal["VISUAL_PLATFORM_ASSESSMENT"] = "VISUAL_PLATFORM_ASSESSMENT"
    timestamp: None = None
    source: Literal["RAW_VLM"] = "RAW_VLM"
    critical: Literal[False] = False
    description_tr: str = Field(min_length=1, max_length=4000)


class VideoEventProjection(StrictContract):
    """UI projection isolated from operational decision facts."""

    timestamped_events: list[TimestampedVideoEvent] = Field(default_factory=list)
    timestamps_available: bool = False
    event_extraction_status: EventExtractionStatus = (
        EventExtractionStatus.PENDING_VIDEO_EVENT_INTEGRATION
    )
    untimestamped_visual_assessment: UntimestampedVisualAssessment | None = None

    @model_validator(mode="after")
    def validate_availability(self) -> Self:
        """Keep event presence, availability, and extraction status aligned."""
        if self.timestamped_events:
            if not self.timestamps_available:
                raise ValueError("timestamped events require timestamps_available=true")
            if self.event_extraction_status is not EventExtractionStatus.AVAILABLE:
                raise ValueError("timestamped events require AVAILABLE extraction status")
        elif self.timestamps_available:
            raise ValueError("timestamps_available requires timestamped events")
        elif (
            self.event_extraction_status
            is not EventExtractionStatus.PENDING_VIDEO_EVENT_INTEGRATION
        ):
            raise ValueError("empty events require pending video integration status")
        return self
