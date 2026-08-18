"""Structured local LLM evidence and decision contracts."""

from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from operational_decision.contracts.common import (
    DecisionCode,
    InventoryStatus,
    OperationalConsistencyFlag,
    OperationalConsistencyStatus,
    StrictContract,
)
from operational_decision.contracts.rag import RAGSource
from operational_decision.contracts.visual import _require_aware_datetime


class RecommendedAction(StrictContract):
    """One catalog-constrained action proposed by the decision model."""

    action_code: str = Field(min_length=1, max_length=100)
    priority: int = Field(ge=1)
    reason_tr: str = Field(min_length=1, max_length=1000)


class LLMDecision(StrictContract):
    """Fields the local LLM may produce under deterministic constraints."""

    decision_code: DecisionCode
    summary_tr: str = Field(min_length=1, max_length=4000)
    evidence_summary: list[str] = Field(default_factory=list, max_length=20)
    recommended_actions: list[RecommendedAction] = Field(default_factory=list, max_length=20)
    uncertainty_notes: list[str] = Field(default_factory=list, max_length=20)
    source_ids: list[str] = Field(default_factory=list, max_length=20)


def ollama_decision_json_schema() -> dict[str, object]:
    """Return the Pydantic decision contract in Ollama grammar-compatible form."""
    action_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "action_code": {"type": "string"},
            "priority": {"type": "integer"},
            "reason_tr": {"type": "string"},
        },
        "required": ["action_code", "priority", "reason_tr"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "decision_code": {
                "type": "string",
                "enum": [value.value for value in DecisionCode],
            },
            "summary_tr": {"type": "string"},
            "evidence_summary": {"type": "array", "items": {"type": "string"}},
            "recommended_actions": {"type": "array", "items": action_schema},
            "uncertainty_notes": {"type": "array", "items": {"type": "string"}},
            "source_ids": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "decision_code",
            "summary_tr",
            "evidence_summary",
            "recommended_actions",
            "uncertainty_notes",
            "source_ids",
        ],
        "additionalProperties": False,
    }


class EvidenceEvent(StrictContract):
    """Minimal event identity admitted to the LLM evidence package."""

    event_id: str = Field(min_length=1, max_length=100)
    track_id: str = Field(min_length=1, max_length=150)
    observation_time_utc: datetime | None

    @field_validator("observation_time_utc")
    @classmethod
    def _aware_time(cls, value: datetime | None) -> datetime | None:
        return _require_aware_datetime(value) if value is not None else None


class EvidenceConstraints(StrictContract):
    """Deterministic choices and identifiers the LLM may use."""

    minimum_risk_level: str = Field(min_length=1, max_length=20)
    human_review_required: bool
    visual_identity_is_hypothesis: Literal[True] = True
    hostile_target_confirmed: Literal[False] = False
    legal_violation_confirmed: Literal[False] = False
    allowed_decision_codes: list[DecisionCode] = Field(min_length=1, max_length=5)
    allowed_action_codes: list[str] = Field(default_factory=list, max_length=30)
    allowed_source_ids: list[str] = Field(default_factory=list, max_length=20)


class LLMEvidencePackage(StrictContract):
    """Bounded structured evidence supplied to the local decision model."""

    schema_version: Literal["llm-evidence/2.1"] = "llm-evidence/2.1"
    inventory_status: InventoryStatus
    inventory_record_id: str | None = Field(default=None, max_length=150)
    inventory_country_code: str | None = Field(default=None, max_length=3)
    inventory_operator_name: str | None = Field(default=None, max_length=200)
    inventory_service_status: str | None = Field(default=None, max_length=100)
    inventory_dataset_id: str | None = Field(default=None, max_length=150)
    inventory_dataset_version: str | None = Field(default=None, max_length=100)
    inventory_source_type: str | None = Field(default=None, max_length=50)
    inventory_reason_codes: list[str] = Field(default_factory=list)
    operational_consistency_status: OperationalConsistencyStatus
    operational_consistency_flags: list[OperationalConsistencyFlag] = Field(default_factory=list)
    event: EvidenceEvent
    visual_evidence: list[str] = Field(default_factory=list, max_length=30)
    operational_context: dict[str, object]
    platform_result: list[str] = Field(default_factory=list, max_length=30)
    permission_flight_plan_result: list[str] = Field(default_factory=list, max_length=30)
    notam_result: list[str] = Field(default_factory=list, max_length=30)
    verification_result: list[str] = Field(default_factory=list, max_length=30)
    risk_result: list[str] = Field(default_factory=list, max_length=30)
    rag_context: list[RAGSource] = Field(default_factory=list, max_length=4)
    rag_called: bool = False
    rag_role: Literal["EXPLANATION_ONLY"] = "EXPLANATION_ONLY"
    rag_decision_effect: Literal["NONE"] = "NONE"
    constraints: EvidenceConstraints
