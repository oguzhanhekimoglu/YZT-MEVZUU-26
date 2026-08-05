"""Contracts for context-free raw-VLM platform assessment."""

from enum import StrEnum
from typing import Literal

from pydantic import Field

from operational_decision.contracts.common import (
    DecisionCode,
    InventoryStatus,
    RiskLevel,
    StrictContract,
    VerificationStatus,
    VlmOriginCategory,
)
from operational_decision.contracts.platform import PlatformOrigin
from operational_decision.contracts.raw_vlm import RawVLMOutput
from operational_decision.contracts.video_events import (
    EventExtractionStatus,
    TimestampedVideoEvent,
    UntimestampedVisualAssessment,
)


class OriginComparisonStatus(StrEnum):
    """Relationship between the visual origin hypothesis and Registry evidence."""

    MANUFACTURER_COUNTRY_COMPATIBLE = "MANUFACTURER_COUNTRY_COMPATIBLE"
    TURKEY_INVENTORY_COMPATIBLE = "TURKEY_INVENTORY_COMPATIBLE"
    MISMATCH = "MISMATCH"
    UNKNOWN_HYPOTHESIS = "UNKNOWN_HYPOTHESIS"
    OPERATOR_AFFILIATION_UNVERIFIED = "OPERATOR_AFFILIATION_UNVERIFIED"
    REGISTRY_ORIGIN_UNKNOWN = "REGISTRY_ORIGIN_UNKNOWN"
    PLATFORM_UNRESOLVED = "PLATFORM_UNRESOLVED"


class ContextFreeCheckStatus(StrEnum):
    """Explicit state for checks that require time and operational scope."""

    NOT_EVALUATED = "NOT_EVALUATED"


class RawVLMAssessmentResult(StrictContract):
    """Safe VLM-only result without synthetic video or operational context."""

    schema_version: Literal["raw-vlm-assessment/1.0"] = "raw-vlm-assessment/1.0"
    raw_vlm: RawVLMOutput
    normalized_model_hypothesis: str | None = None
    platform_resolved: bool
    platform_id: str | None = None
    matched_platform: str | None = None
    registry_platform_origin: PlatformOrigin = PlatformOrigin.UNKNOWN
    registry_country_code: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    vlm_origin_hypothesis: str | None = None
    vlm_origin_category: VlmOriginCategory = VlmOriginCategory.UNKNOWN
    origin_comparison: OriginComparisonStatus
    origin_explanation_tr: str
    inventory_status: InventoryStatus
    inventory_operator_name: str | None = None
    inventory_service_status: str | None = None
    permission_status: ContextFreeCheckStatus = ContextFreeCheckStatus.NOT_EVALUATED
    flight_plan_status: ContextFreeCheckStatus = ContextFreeCheckStatus.NOT_EVALUATED
    notam_status: ContextFreeCheckStatus = ContextFreeCheckStatus.NOT_EVALUATED
    verification_status: VerificationStatus = VerificationStatus.INDETERMINATE
    risk_level: RiskLevel
    decision: DecisionCode
    human_review_required: bool = True
    rag_called: bool = False
    rag_reason: str = "OPERATIONAL_CONTEXT_NOT_AVAILABLE"
    summary_tr: str
    recommended_actions: list[str]
    timestamped_events: list[TimestampedVideoEvent] = Field(default_factory=list)
    timestamps_available: bool = False
    event_extraction_status: EventExtractionStatus = (
        EventExtractionStatus.PENDING_VIDEO_EVENT_INTEGRATION
    )
    untimestamped_visual_assessment: UntimestampedVisualAssessment | None = None
