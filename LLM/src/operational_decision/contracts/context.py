"""Operational context contracts."""

from datetime import datetime

from pydantic import Field, field_validator

from operational_decision.contracts.common import ContextStatus, StrictContract
from operational_decision.contracts.visual import _require_aware_datetime


class VideoContextRecord(StrictContract):
    """Stored context record keyed by a video identifier."""

    video_id: str = Field(min_length=1, max_length=150)
    camera_id: str = Field(min_length=1, max_length=150)
    context_id: str = Field(min_length=1, max_length=150)
    operational_area_id: str = Field(min_length=1, max_length=150)
    scenario_id: str = Field(min_length=1, max_length=150)
    expected_platform_id: str | None = Field(default=None, min_length=1, max_length=150)
    video_start_time_utc: datetime
    description: str | None = Field(default=None, max_length=1000)
    fir_code: str | None = Field(default=None, min_length=2, max_length=12)
    aerodrome_code: str | None = Field(default=None, min_length=3, max_length=12)
    operation_lower_limit: int | None = Field(default=None, ge=0, le=100_000)
    operation_upper_limit: int | None = Field(default=None, ge=0, le=100_000)
    environment: str = Field(min_length=1, max_length=50)
    status: str = Field(min_length=1, max_length=50)
    source_type: str = Field(default="DEMO_MOCK", min_length=1, max_length=50)

    _aware_start = field_validator("video_start_time_utc")(_require_aware_datetime)


class ContextResolution(StrictContract):
    """Resolved context and calculated observation interval."""

    context_status: ContextStatus
    record: VideoContextRecord | None = None
    observation_time_utc: datetime | None = None
    observation_end_time_utc: datetime | None = None
    warnings: list[str] = Field(default_factory=list)

    _aware_times = field_validator("observation_time_utc", "observation_end_time_utc")(
        _require_aware_datetime
    )
