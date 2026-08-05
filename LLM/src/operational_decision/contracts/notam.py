"""NOTAM lookup and result contracts."""

from datetime import datetime

from pydantic import Field, field_validator

from operational_decision.contracts.common import (
    ContextStatus,
    NotamOperationEffect,
    NotamStatus,
    StrictContract,
    VisualClass,
)
from operational_decision.contracts.visual import _require_aware_datetime


class NotamRecord(StrictContract):
    """One controlled local NOTAM record."""

    notam_id: str = Field(min_length=1, max_length=150)
    operational_area_id: str = Field(min_length=1, max_length=150)
    valid_from_utc: datetime
    valid_to_utc: datetime
    notam_status: NotamStatus
    operation_effect: NotamOperationEffect
    display_number: str | None = Field(default=None, max_length=30)
    series: str | None = Field(default=None, max_length=10)
    number: int | None = Field(default=None, ge=1)
    year: int | None = Field(default=None, ge=2000, le=2100)
    q_code: str | None = Field(default=None, max_length=20)
    item_e: str | None = Field(default=None, max_length=2000)
    estimated_end: bool = False
    permanent: bool = False
    lower_limit: int | None = Field(default=None, ge=0, le=100_000)
    upper_limit: int | None = Field(default=None, ge=0, le=100_000)
    fir_code: str | None = Field(default=None, max_length=12)
    aerodrome_code: str | None = Field(default=None, max_length=12)
    operational_reason_tr: str | None = Field(default=None, max_length=2000)
    conflict_with_permission: bool = False
    conflict_with_flight_plan: bool = False
    context_id: str | None = Field(default=None, max_length=150)
    scenario_id: str | None = Field(default=None, max_length=150)
    relevance_tags: list[str] = Field(default_factory=list)
    affected_platform_categories: list[VisualClass] = Field(default_factory=list)
    affected_platform_ids: list[str] = Field(default_factory=list)
    summary_tr: str = Field(min_length=1, max_length=1000)
    source_reference: str | None = Field(default=None, max_length=500)
    source_type: str = Field(min_length=1, max_length=50)

    _aware_times = field_validator("valid_from_utc", "valid_to_utc")(_require_aware_datetime)


class NotamToolRequest(StrictContract):
    """Context and visual facts used for deterministic NOTAM relevance."""

    context_id: str | None = Field(default=None, min_length=1, max_length=150)
    operational_area_id: str | None = Field(default=None, min_length=1, max_length=150)
    scenario_id: str | None = Field(default=None, min_length=1, max_length=150)
    observation_time_utc: datetime
    observation_end_time_utc: datetime
    visual_class: VisualClass
    platform_id: str | None = Field(default=None, max_length=150)
    context_status: ContextStatus
    relevance_tags: list[str] = Field(default_factory=list)
    fir_code: str | None = Field(default=None, max_length=12)
    aerodrome_code: str | None = Field(default=None, max_length=12)
    operation_lower_limit: int | None = Field(default=None, ge=0, le=100_000)
    operation_upper_limit: int | None = Field(default=None, ge=0, le=100_000)

    _aware_observation = field_validator("observation_time_utc", "observation_end_time_utc")(
        _require_aware_datetime
    )


class NotamResult(StrictContract):
    """Deterministically selected active NOTAM result."""

    notam_status: NotamStatus
    operation_effect: NotamOperationEffect
    active_notams: list[NotamRecord] = Field(default_factory=list)
    matched_notam_ids: list[str] = Field(default_factory=list)
    primary_notam_number: str | None = Field(default=None, max_length=30)
    reason_tr: str | None = Field(default=None, max_length=2000)
    matched_by: list[str] = Field(default_factory=list)
    conflict_with_permission: bool = False
    conflict_with_flight_plan: bool = False
    skip_reason: str | None = Field(default=None, max_length=150)
