"""Operational verification contracts."""

from enum import StrEnum

from pydantic import Field

from operational_decision.contracts.common import (
    ContextStatus,
    FlightPlanStatus,
    InventoryStatus,
    NotamOperationEffect,
    NotamStatus,
    OperationalConsistencyFlag,
    OperationalConsistencyStatus,
    PermissionStatus,
    PlatformStatus,
    RecordConsistency,
    StrictContract,
    ToolExecutionStatus,
    ToolHealthStatus,
    UncertaintyLevel,
    VerificationStatus,
    VisualClass,
    VisualEvidenceStatus,
    VlmOriginCategory,
)
from operational_decision.contracts.platform import UsageDomain


class VerificationReasonCode(StrEnum):
    """Controlled reasons emitted by deterministic verification."""

    INVENTORY_CONFIRMED = "INVENTORY_CONFIRMED"
    INVENTORY_NOT_LISTED = "INVENTORY_NOT_LISTED"
    INVENTORY_UNKNOWN = "INVENTORY_UNKNOWN"
    INVENTORY_TOOL_ERROR = "INVENTORY_TOOL_ERROR"
    OPERATIONAL_CONSISTENCY_INDETERMINATE = "OPERATIONAL_CONSISTENCY_INDETERMINATE"
    REQUIRED_OPERATIONAL_CHECK_UNAVAILABLE = "REQUIRED_OPERATIONAL_CHECK_UNAVAILABLE"
    PLATFORM_EXPECTED = "PLATFORM_EXPECTED"
    PLATFORM_NOT_EXPECTED = "PLATFORM_NOT_EXPECTED"
    PLATFORM_UNKNOWN = "PLATFORM_UNKNOWN"
    PLATFORM_AMBIGUOUS = "PLATFORM_AMBIGUOUS"
    PLATFORM_IDENTIFIED_CONTEXT_UNKNOWN = "PLATFORM_IDENTIFIED_CONTEXT_UNKNOWN"
    PERMISSION_VALID = "PERMISSION_VALID"
    PERMISSION_NOT_FOUND = "PERMISSION_NOT_FOUND"
    PERMISSION_EXPIRED = "PERMISSION_EXPIRED"
    PERMISSION_NOT_YET_VALID = "PERMISSION_NOT_YET_VALID"
    PERMISSION_REVOKED = "PERMISSION_REVOKED"
    PERMISSION_CONFLICTING = "PERMISSION_CONFLICTING"
    FLIGHT_PLAN_FILED = "FLIGHT_PLAN_FILED"
    FLIGHT_PLAN_NOT_FOUND = "FLIGHT_PLAN_NOT_FOUND"
    FLIGHT_PLAN_EXPIRED = "FLIGHT_PLAN_EXPIRED"
    FLIGHT_PLAN_NOT_YET_ACTIVE = "FLIGHT_PLAN_NOT_YET_ACTIVE"
    FLIGHT_PLAN_CANCELLED = "FLIGHT_PLAN_CANCELLED"
    FLIGHT_PLAN_CONFLICTING = "FLIGHT_PLAN_CONFLICTING"
    FLIGHT_PLAN_WITHOUT_PERMISSION = "FLIGHT_PLAN_WITHOUT_PERMISSION"
    NOTAM_ACTIVE_RELEVANT = "NOTAM_ACTIVE_RELEVANT"
    NOTAM_RESTRICTS_OPERATION = "NOTAM_RESTRICTS_OPERATION"
    NOTAM_PROHIBITS_OPERATION = "NOTAM_PROHIBITS_OPERATION"
    NOTAM_CONFLICTS_WITH_PERMISSION = "NOTAM_CONFLICTS_WITH_PERMISSION"
    NOTAM_NONE_ACTIVE = "NOTAM_NONE_ACTIVE"
    NOTAM_CONFLICTING = "NOTAM_CONFLICTING"
    CONTEXT_COMPLETE = "CONTEXT_COMPLETE"
    CONTEXT_PARTIAL = "CONTEXT_PARTIAL"
    CONTEXT_MISSING = "CONTEXT_MISSING"
    CONTEXT_INVALID = "CONTEXT_INVALID"
    CONTEXT_INACTIVE = "CONTEXT_INACTIVE"
    PLATFORM_TOOL_ERROR = "PLATFORM_TOOL_ERROR"
    PERMISSION_TOOL_ERROR = "PERMISSION_TOOL_ERROR"
    NOTAM_TOOL_ERROR = "NOTAM_TOOL_ERROR"
    TOOL_TIMEOUT = "TOOL_TIMEOUT"
    VISUAL_EVIDENCE_CONFLICTING = "VISUAL_EVIDENCE_CONFLICTING"
    VISUAL_UNCERTAINTY_HIGH = "VISUAL_UNCERTAINTY_HIGH"
    NON_AIRCRAFT = "NON_AIRCRAFT"


class VerificationInput(StrictContract):
    """Canonical Phase 1â€“3 facts consumed by deterministic verification."""

    context_status: ContextStatus
    platform_status: PlatformStatus
    platform_usage_domain: UsageDomain = UsageDomain.UNKNOWN
    vlm_origin_category: VlmOriginCategory = VlmOriginCategory.UNKNOWN
    inventory_status: InventoryStatus = InventoryStatus.CONFIRMED
    operational_consistency_status: OperationalConsistencyStatus = (
        OperationalConsistencyStatus.CONSISTENT
    )
    operational_consistency_flags: list[OperationalConsistencyFlag] = Field(
        default_factory=lambda: [OperationalConsistencyFlag.INVENTORY_SCOPE_CONFIRMED]
    )
    permission_status: PermissionStatus
    flight_plan_status: FlightPlanStatus
    record_consistency: RecordConsistency
    notam_status: NotamStatus
    notam_operation_effect: NotamOperationEffect
    visual_class: VisualClass
    visual_evidence_status: VisualEvidenceStatus
    visual_confidence: float = Field(ge=0.0, le=1.0)
    uncertainty_level: UncertaintyLevel
    visual_human_review_required: bool
    platform_execution_status: ToolExecutionStatus
    inventory_execution_status: ToolExecutionStatus = ToolExecutionStatus.SUCCESS
    permission_execution_status: ToolExecutionStatus
    notam_execution_status: ToolExecutionStatus


class VerificationResult(StrictContract):
    """Deterministic verification result without risk selection."""

    verification_status: VerificationStatus
    reason_codes: list[VerificationReasonCode] = Field(default_factory=list)
    tool_health_status: ToolHealthStatus
    required_tools: list[str] = Field(default_factory=list)
    successful_required_tools: list[str] = Field(default_factory=list)
