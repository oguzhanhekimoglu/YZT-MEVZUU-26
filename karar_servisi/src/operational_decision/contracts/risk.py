"""Deterministic risk and action-catalog contracts."""

from typing import Literal

from pydantic import Field

from operational_decision.contracts.common import RiskLevel, StrictContract


class RiskResult(StrictContract):
    """Risk Advisor output that constrains every later decision layer."""

    risk_level: RiskLevel
    minimum_risk_level: RiskLevel
    human_review_required: bool
    human_review_priority: Literal["NORMAL", "URGENT"] = "NORMAL"
    matched_rule_ids: list[str] = Field(default_factory=list)
    selected_rule_id: str = Field(min_length=1, max_length=150)
    rule_specificity: float = Field(ge=0.0, le=1.0)
    evidence_quality_score: float = Field(ge=0.0, le=1.0)
    risk_assessment_confidence: float = Field(ge=0.0, le=1.0)
    decision_confidence: float = Field(ge=0.0, le=1.0)
    explanation: str = Field(
        default="Risk gerekçesi mevcut doğrulanmış bulgulardan üretilemedi.",
        min_length=1,
        max_length=4000,
    )
    increasing_factors: list[str] = Field(default_factory=list, max_length=20)
    reducing_factors: list[str] = Field(default_factory=list, max_length=20)
    uncertainties: list[str] = Field(default_factory=list, max_length=20)


class ActionDefinition(StrictContract):
    """One deterministic action catalog entry."""

    code: str = Field(min_length=1, max_length=150)
    title_tr: str = Field(min_length=1, max_length=300)
    allowed_risks: list[RiskLevel] = Field(min_length=1)


class ActionCatalog(StrictContract):
    """Validated deterministic action catalog."""

    actions: list[ActionDefinition] = Field(min_length=1)
