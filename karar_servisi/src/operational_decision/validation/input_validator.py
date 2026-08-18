"""Canonical input validation and safe invalid-output construction."""

from pydantic import Field

from operational_decision.contracts.common import (
    DecisionCode,
    EventStatus,
    RiskLevel,
    StrictContract,
)
from operational_decision.contracts.final_output import FinalDecisionOutput


class ValidationIssue(StrictContract):
    """Sanitized machine-readable input validation issue."""

    code: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=1000)
    field: str | None = Field(default=None, max_length=300)


def build_invalid_input_output(
    event_id: str,
    request_id: str,
    errors: list[ValidationIssue],
) -> FinalDecisionOutput:
    """Build the mandatory safe final contract for rejected input."""
    notes = [f"{issue.code}: {issue.message}" for issue in errors]
    return FinalDecisionOutput(
        event_id=event_id,
        request_id=request_id,
        event_status=EventStatus.REJECTED_INVALID_INPUT,
        decision=DecisionCode.INDETERMINATE,
        risk_level=RiskLevel.UNKNOWN,
        minimum_risk_level=RiskLevel.UNKNOWN,
        summary_tr="Girdi sözleşme doğrulamasından geçemedi; olay operatör incelemesine ayrıldı.",
        human_approval_required=True,
        uncertainty_notes=notes,
    )
