"""Final decision output contracts shared by success and safe failures."""

from datetime import date, datetime
from typing import Literal

from pydantic import Field, field_validator

from operational_decision.contracts.common import (
    ContextStatus,
    DecisionCode,
    EventStatus,
    FlightPlanStatus,
    InventoryStatus,
    NotamOperationEffect,
    NotamStatus,
    OperationalConsistencyFlag,
    OperationalConsistencyStatus,
    PermissionStatus,
    PlatformStatus,
    RecordConsistency,
    RiskLevel,
    StrictContract,
    ToolExecutionStatus,
    ToolHealthStatus,
    UncertaintyLevel,
    VerificationStatus,
    VisualClass,
    VisualEvidenceStatus,
    VlmOriginCategory,
)
from operational_decision.contracts.llm import RecommendedAction
from operational_decision.contracts.platform import PlatformTaxonomy, UsageDomain
from operational_decision.contracts.video_events import (
    EventExtractionStatus,
    TimestampedVideoEvent,
    UntimestampedVisualAssessment,
)
from operational_decision.contracts.visual import _require_aware_datetime


class SourceReference(StrictContract):
    """Compact authoritative provenance exposed in final output."""

    source_id: str = Field(min_length=1, max_length=200)
    document_id: str = Field(min_length=1, max_length=200)
    filename: str = Field(min_length=1, max_length=300)
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    section_title: str | None = Field(default=None, max_length=500)
    revision_date: date | None = None
    effective_date: date | None = None


class NotamEvidence(StrictContract):
    """Compact active NOTAM evidence exposed for user and audit presentation."""

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
    summary_tr: str = Field(min_length=1, max_length=1000)
    source_type: str = Field(min_length=1, max_length=50)
    source_reference: str | None = Field(default=None, max_length=500)

    _aware_times = field_validator("valid_from_utc", "valid_to_utc")(_require_aware_datetime)


class PermissionEvidence(StrictContract):
    """Selected permission record facts exposed without changing its status."""

    permission_id: str = Field(min_length=1, max_length=150)
    valid_from_utc: datetime
    valid_to_utc: datetime
    permission_status: PermissionStatus
    operator_name: str | None = Field(default=None, max_length=200)
    flight_purpose: str | None = Field(default=None, max_length=200)
    altitude_ft_msl: int | None = Field(default=None, ge=0, le=100_000)
    departure_aerodrome: str | None = Field(default=None, max_length=20)
    arrival_aerodrome: str | None = Field(default=None, max_length=20)
    source_type: str = Field(min_length=1, max_length=50)

    _aware_times = field_validator("valid_from_utc", "valid_to_utc")(_require_aware_datetime)


class FlightPlanEvidence(StrictContract):
    """Selected flight-plan record facts kept independent from permission and NOTAM."""

    flight_plan_id: str = Field(min_length=1, max_length=150)
    planned_departure_utc: datetime
    planned_arrival_utc: datetime | None = None
    flight_plan_status: FlightPlanStatus
    callsign: str | None = Field(default=None, max_length=50)
    departure_aerodrome: str | None = Field(default=None, max_length=20)
    arrival_aerodrome: str | None = Field(default=None, max_length=20)
    route_or_area: str | None = Field(default=None, max_length=1000)
    source_type: str = Field(min_length=1, max_length=50)

    _aware_times = field_validator("planned_departure_utc", "planned_arrival_utc")(
        _require_aware_datetime
    )


class ToolExecutionSummaryItem(StrictContract):
    """Compact final-output summary of one tool execution."""

    execution_status: ToolExecutionStatus
    latency_ms: int | None = Field(default=None, ge=0)
    domain_status: str | None = Field(default=None, max_length=100)
    error_code: str | None = Field(default=None, max_length=100)
    warnings: list[str] = Field(default_factory=list)


class GuardCorrection(StrictContract):
    """Auditable deterministic correction applied to an LLM field."""

    field: str = Field(min_length=1, max_length=100)
    llm_value: object | None = None
    final_value: object | None = None
    reason: str = Field(min_length=1, max_length=200)


class ModelVersions(StrictContract):
    """Runtime model identifiers recorded with a final output."""

    decision_llm: str | None = Field(default=None, max_length=200)
    text_embedding: str | None = Field(default=None, max_length=200)
    visual_pipeline: str | None = Field(default=None, max_length=200)


class FinalDecisionOutput(StrictContract):
    """Versioned final output used for finalized and rejected events."""

    schema_version: Literal["final-output/2.0", "final-output/2.1"] = "final-output/2.1"
    event_id: str = Field(min_length=1, max_length=100)
    request_id: str = Field(min_length=1, max_length=100)
    event_status: EventStatus
    video_id: str | None = Field(default=None, max_length=150)
    camera_id: str | None = Field(default=None, max_length=150)
    context_id: str | None = Field(default=None, max_length=150)
    operational_area_id: str | None = Field(default=None, max_length=150)
    scenario_id: str | None = Field(default=None, max_length=150)
    track_id: str | None = Field(default=None, max_length=150)
    observation_time_utc: datetime | None = None
    observation_end_time_utc: datetime | None = None
    visual_class: VisualClass | None = None
    visual_hypothesis: str | None = Field(default=None, max_length=200)
    visual_analysis_tr: str | None = Field(default=None, max_length=4000)
    timestamped_events: list[TimestampedVideoEvent] = Field(default_factory=list)
    timestamps_available: bool = False
    event_extraction_status: EventExtractionStatus = (
        EventExtractionStatus.PENDING_VIDEO_EVENT_INTEGRATION
    )
    untimestamped_visual_assessment: UntimestampedVisualAssessment | None = None
    visual_evidence_status: VisualEvidenceStatus | None = None
    visual_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    uncertainty_level: UncertaintyLevel | None = None
    uncertainty_flags: list[str] = Field(default_factory=list)
    platform_status: PlatformStatus | None = None
    platform_id: str | None = Field(default=None, max_length=150)
    matched_platform: str | None = Field(default=None, max_length=200)
    canonical_name: str | None = Field(default=None, max_length=200)
    platform_category: VisualClass | None = None
    platform_taxonomy: PlatformTaxonomy | None = None
    platform_usage_domain: UsageDomain = UsageDomain.UNKNOWN
    platform_origin: str | None = Field(default=None, max_length=50)
    manufacturer_country_code: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    platform_identity_scope: str | None = Field(default=None, max_length=50)
    platform_variant_policy: str | None = Field(default=None, max_length=50)
    vlm_origin_hypothesis: str | None = Field(default=None, max_length=500)
    vlm_origin_category: VlmOriginCategory | None = None
    inventory_status: InventoryStatus | None = None
    inventory_registry_version: str | None = Field(default=None, max_length=50)
    inventory_record_id: str | None = Field(default=None, max_length=150)
    inventory_country_code: str | None = Field(default=None, max_length=3)
    inventory_operator_name: str | None = Field(default=None, max_length=200)
    inventory_service_status: str | None = Field(default=None, max_length=100)
    inventory_dataset_id: str | None = Field(default=None, max_length=150)
    inventory_dataset_version: str | None = Field(default=None, max_length=100)
    inventory_source_type: str | None = Field(default=None, max_length=50)
    inventory_reason_codes: list[str] = Field(default_factory=list)
    operational_consistency_status: OperationalConsistencyStatus | None = None
    operational_consistency_flags: list[OperationalConsistencyFlag] = Field(default_factory=list)
    permission_status: PermissionStatus | None = None
    permission_details: list[PermissionEvidence] = Field(default_factory=list, max_length=10)
    flight_plan_status: FlightPlanStatus | None = None
    flight_plan_details: list[FlightPlanEvidence] = Field(default_factory=list, max_length=10)
    record_consistency: RecordConsistency | None = None
    notam_status: NotamStatus | None = None
    notam_operation_effect: NotamOperationEffect | None = None
    notam_details: list[NotamEvidence] = Field(default_factory=list, max_length=10)
    matched_notam_ids: list[str] = Field(default_factory=list, max_length=10)
    primary_notam_number: str | None = Field(default=None, max_length=30)
    notam_reason_tr: str | None = Field(default=None, max_length=2000)
    notam_matched_by: list[str] = Field(default_factory=list, max_length=20)
    notam_conflict_with_permission: bool = False
    notam_conflict_with_flight_plan: bool = False
    context_status: ContextStatus | None = None
    verification_status: VerificationStatus | None = None
    verification_reason_codes: list[str] = Field(default_factory=list)
    tool_health_status: ToolHealthStatus | None = None
    decision: DecisionCode
    decision_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    risk_level: RiskLevel
    minimum_risk_level: RiskLevel
    risk_assessment_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence_quality_score: float | None = Field(default=None, ge=0.0, le=1.0)
    matched_rule_ids: list[str] = Field(default_factory=list)
    risk_explanation: str | None = Field(default=None, min_length=1, max_length=4000)
    risk_increasing_factors: list[str] = Field(default_factory=list, max_length=20)
    risk_reducing_factors: list[str] = Field(default_factory=list, max_length=20)
    rag_summary: str | None = Field(default=None, min_length=1, max_length=4000)
    rag_sources: list[SourceReference] = Field(default_factory=list, max_length=4)
    rag_decision_effect: str | None = Field(default=None, min_length=1, max_length=2000)
    human_review_reasons: list[str] = Field(default_factory=list, max_length=20)
    human_review_priority: Literal["NORMAL", "URGENT"] = "NORMAL"
    hostile_target_confirmed: bool = False
    legal_violation_confirmed: bool = False
    summary_tr: str = Field(min_length=1, max_length=4000)
    operational_report_tr: str | None = Field(default=None, min_length=1, max_length=12000)
    turkish_report: str | None = Field(default=None, min_length=1, max_length=12000)
    evidence_summary: list[str] = Field(default_factory=list)
    recommended_actions: list[RecommendedAction] = Field(default_factory=list)
    human_approval_required: bool
    uncertainty_notes: list[str] = Field(default_factory=list)
    sources: list[SourceReference] = Field(default_factory=list)
    tool_execution_summary: dict[str, ToolExecutionSummaryItem] = Field(default_factory=dict)
    guard_corrections: list[GuardCorrection] = Field(default_factory=list)
    processing_latency_ms: int | None = Field(default=None, ge=0)
    model_versions: ModelVersions = Field(default_factory=ModelVersions)

    @field_validator("observation_time_utc", "observation_end_time_utc")
    @classmethod
    def _aware_times(cls, value: datetime | None) -> datetime | None:
        return _require_aware_datetime(value) if value is not None else None
