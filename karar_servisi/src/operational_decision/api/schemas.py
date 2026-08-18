"""Small API-only response envelopes."""

from typing import Any, Literal

from pydantic import Field

from operational_decision.contracts.common import (
    EventStatus,
    RiskLevel,
    StrictContract,
    VerificationStatus,
)
from operational_decision.contracts.request import AnalyzeEventRequest


class AnalyzeResponse(StrictContract):
    """HTTP analyze response independent from decision core logic."""

    event_id: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    event_status: EventStatus
    output: dict[str, Any] | None = None
    detail: str | None = None


class DemoScenarioResponse(StrictContract):
    """Runnable deterministic demo scenario returned by the catalog endpoint."""

    scenario_id: str = Field(pattern=r"^SCN-(0[1-9]|1[0-9]|2[0-3])$")
    name: str = Field(min_length=1, max_length=150)
    description: str = Field(min_length=1, max_length=1000)
    expected_verification_status: VerificationStatus
    expected_risk_level: RiskLevel
    request_payload: AnalyzeEventRequest
    source_type: Literal["DEMO_MOCK"] = "DEMO_MOCK"
