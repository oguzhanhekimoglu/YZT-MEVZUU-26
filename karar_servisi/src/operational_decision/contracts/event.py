"""Event identity and trace contracts."""

from datetime import datetime

from pydantic import Field

from operational_decision.contracts.common import EventStatus, StrictContract


class EventRecord(StrictContract):
    """Persisted lifecycle record for one decision event."""

    event_id: str = Field(min_length=1, max_length=100)
    request_id: str = Field(min_length=1, max_length=100)
    event_fingerprint: str | None = Field(default=None, min_length=64, max_length=64)
    retry_of_event_id: str | None = Field(default=None, min_length=1, max_length=100)
    event_status: EventStatus
    created_at_utc: datetime
    updated_at_utc: datetime
    completed_at_utc: datetime | None = None


class EventStep(StrictContract):
    """Audited state transition within an event trace."""

    step_name: str = Field(min_length=1, max_length=100)
    step_status: str = Field(min_length=1, max_length=100)
    payload: dict[str, object] | None = None
    created_at_utc: datetime
