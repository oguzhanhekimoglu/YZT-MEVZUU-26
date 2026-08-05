"""Deterministic operational verification, tool health, and early exit."""

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
    ToolExecutionStatus,
    ToolHealthStatus,
    UncertaintyLevel,
    VerificationStatus,
    VisualClass,
    VisualEvidenceStatus,
    VlmOriginCategory,
)
from operational_decision.contracts.platform import UsageDomain
from operational_decision.contracts.verification import (
    VerificationInput,
    VerificationReasonCode,
    VerificationResult,
)
from operational_decision.contracts.visual import FinalVisualEvidencePackage

PLATFORM_TOOL = "platform_tool"
INVENTORY_TOOL = "turkey_inventory_tool"
NOTAM_TOOL = "notam_tool"
PERMISSION_TOOL = "permission_flight_plan_tool"
_FAILED_EXECUTIONS = {
    ToolExecutionStatus.ERROR,
    ToolExecutionStatus.TIMEOUT,
    ToolExecutionStatus.INVALID_INPUT,
}


def should_early_exit_non_aircraft(visual: FinalVisualEvidencePackage, threshold: float) -> bool:
    """Return true only for strong, supported, low-uncertainty non-aircraft evidence."""
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("non-aircraft threshold must be between 0 and 1")
    return (
        visual.visual_class is VisualClass.NON_AIRCRAFT
        and visual.visual_evidence_status is VisualEvidenceStatus.SUPPORTED
        and visual.uncertainty_level is UncertaintyLevel.LOW
        and visual.visual_confidence >= threshold
    )


def is_unregistered_military_policy(
    *,
    platform_usage_domain: UsageDomain,
    inventory_execution_status: ToolExecutionStatus,
    inventory_status: InventoryStatus,
) -> bool:
    """Return whether the exact policy gate excludes downstream operational tools."""
    return (
        platform_usage_domain is UsageDomain.MILITARY
        and inventory_execution_status is ToolExecutionStatus.SUCCESS
        and inventory_status is InventoryStatus.NOT_LISTED
    )


def is_unregistered_military_turkey_claim(facts: VerificationInput) -> bool:
    """Return whether an unregistered military platform is claimed as Turkish-origin by the VLM."""
    return (
        is_unregistered_military_policy(
            platform_usage_domain=facts.platform_usage_domain,
            inventory_execution_status=facts.inventory_execution_status,
            inventory_status=facts.inventory_status,
        )
        and facts.vlm_origin_category is VlmOriginCategory.TURKEY
    )


def is_military_listed_foreign_origin(facts: VerificationInput) -> bool:
    """Return whether a MILITARY, Inventory-listed platform reports a FOREIGN VLM origin."""
    return (
        facts.platform_usage_domain is UsageDomain.MILITARY
        and facts.inventory_execution_status is ToolExecutionStatus.SUCCESS
        and facts.inventory_status is InventoryStatus.CONFIRMED
        and facts.vlm_origin_category is VlmOriginCategory.FOREIGN
    )


def is_military_listed_unknown_origin(facts: VerificationInput) -> bool:
    """Return whether a MILITARY, Inventory-listed platform reports an UNKNOWN VLM origin."""
    return (
        facts.platform_usage_domain is UsageDomain.MILITARY
        and facts.inventory_execution_status is ToolExecutionStatus.SUCCESS
        and facts.inventory_status is InventoryStatus.CONFIRMED
        and facts.vlm_origin_category is VlmOriginCategory.UNKNOWN
    )


def derive_required_tools(
    facts: VerificationInput, *, strong_non_aircraft: bool = False
) -> tuple[str, ...]:
    """Derive required tools from resolved Platform and complete context."""
    if strong_non_aircraft:
        return ()
    required = [PLATFORM_TOOL]
    platform_resolved = (
        facts.platform_execution_status is ToolExecutionStatus.SUCCESS
        and facts.platform_status in {PlatformStatus.EXPECTED, PlatformStatus.NOT_EXPECTED}
    )
    if not platform_resolved:
        return tuple(required)
    required.append(INVENTORY_TOOL)
    if (
        facts.context_status is ContextStatus.COMPLETE
        and not is_unregistered_military_policy(
            platform_usage_domain=facts.platform_usage_domain,
            inventory_execution_status=facts.inventory_execution_status,
            inventory_status=facts.inventory_status,
        )
    ):
        required.extend((NOTAM_TOOL, PERMISSION_TOOL))
    return tuple(required)


def _execution_status(facts: VerificationInput, tool_name: str) -> ToolExecutionStatus:
    return {
        PLATFORM_TOOL: facts.platform_execution_status,
        INVENTORY_TOOL: facts.inventory_execution_status,
        NOTAM_TOOL: facts.notam_execution_status,
        PERMISSION_TOOL: facts.permission_execution_status,
    }[tool_name]


def calculate_tool_health(
    facts: VerificationInput, *, strong_non_aircraft: bool = False
) -> ToolHealthStatus:
    """Calculate health without treating successful NOT_LISTED as a tool failure."""
    if strong_non_aircraft:
        return ToolHealthStatus.HEALTHY
    if facts.context_status is not ContextStatus.COMPLETE:
        return ToolHealthStatus.FAILED
    required = derive_required_tools(facts)
    if facts.platform_execution_status is not ToolExecutionStatus.SUCCESS:
        return ToolHealthStatus.FAILED
    if (
        facts.inventory_status is InventoryStatus.UNKNOWN
        or facts.inventory_execution_status in _FAILED_EXECUTIONS
    ):
        return ToolHealthStatus.FAILED
    if (
        INVENTORY_TOOL in required
        and facts.inventory_execution_status is not ToolExecutionStatus.SUCCESS
    ):
        return ToolHealthStatus.FAILED
    if (
        PERMISSION_TOOL in required
        and facts.permission_execution_status is not ToolExecutionStatus.SUCCESS
    ):
        return ToolHealthStatus.FAILED
    if NOTAM_TOOL in required and facts.notam_execution_status is not ToolExecutionStatus.SUCCESS:
        return ToolHealthStatus.DEGRADED
    return ToolHealthStatus.HEALTHY


def _reason_codes(facts: VerificationInput) -> list[VerificationReasonCode]:
    reasons: list[VerificationReasonCode] = []
    reasons.append(
        {
            ContextStatus.COMPLETE: VerificationReasonCode.CONTEXT_COMPLETE,
            ContextStatus.PARTIAL: VerificationReasonCode.CONTEXT_PARTIAL,
            ContextStatus.MISSING: VerificationReasonCode.CONTEXT_MISSING,
            ContextStatus.INVALID: VerificationReasonCode.CONTEXT_INVALID,
            ContextStatus.INACTIVE: VerificationReasonCode.CONTEXT_INACTIVE,
        }[facts.context_status]
    )

    inventory_reason = {
        InventoryStatus.CONFIRMED: VerificationReasonCode.INVENTORY_CONFIRMED,
        InventoryStatus.NOT_LISTED: VerificationReasonCode.INVENTORY_NOT_LISTED,
        InventoryStatus.UNKNOWN: VerificationReasonCode.INVENTORY_UNKNOWN,
    }.get(facts.inventory_status)
    if inventory_reason is not None:
        reasons.append(inventory_reason)
    if facts.inventory_execution_status in _FAILED_EXECUTIONS:
        reasons.append(VerificationReasonCode.INVENTORY_TOOL_ERROR)

    platform_reason = {
        PlatformStatus.EXPECTED: VerificationReasonCode.PLATFORM_EXPECTED,
        PlatformStatus.NOT_EXPECTED: VerificationReasonCode.PLATFORM_NOT_EXPECTED,
        PlatformStatus.UNKNOWN: VerificationReasonCode.PLATFORM_UNKNOWN,
        PlatformStatus.AMBIGUOUS: VerificationReasonCode.PLATFORM_AMBIGUOUS,
    }.get(facts.platform_status)
    if platform_reason is not None:
        reasons.append(platform_reason)

    permission_reason = {
        PermissionStatus.VALID: VerificationReasonCode.PERMISSION_VALID,
        PermissionStatus.NOT_FOUND: VerificationReasonCode.PERMISSION_NOT_FOUND,
        PermissionStatus.EXPIRED: VerificationReasonCode.PERMISSION_EXPIRED,
        PermissionStatus.NOT_YET_VALID: VerificationReasonCode.PERMISSION_NOT_YET_VALID,
        PermissionStatus.REVOKED: VerificationReasonCode.PERMISSION_REVOKED,
        PermissionStatus.CONFLICTING: VerificationReasonCode.PERMISSION_CONFLICTING,
    }.get(facts.permission_status)
    if permission_reason is not None:
        reasons.append(permission_reason)

    plan_reason = {
        FlightPlanStatus.FILED: VerificationReasonCode.FLIGHT_PLAN_FILED,
        FlightPlanStatus.NOT_FOUND: VerificationReasonCode.FLIGHT_PLAN_NOT_FOUND,
        FlightPlanStatus.EXPIRED: VerificationReasonCode.FLIGHT_PLAN_EXPIRED,
        FlightPlanStatus.NOT_YET_ACTIVE: VerificationReasonCode.FLIGHT_PLAN_NOT_YET_ACTIVE,
        FlightPlanStatus.CANCELLED: VerificationReasonCode.FLIGHT_PLAN_CANCELLED,
        FlightPlanStatus.CONFLICTING: VerificationReasonCode.FLIGHT_PLAN_CONFLICTING,
    }.get(facts.flight_plan_status)
    if plan_reason is not None:
        reasons.append(plan_reason)
    if (
        facts.flight_plan_status is FlightPlanStatus.FILED
        and facts.permission_status is not PermissionStatus.VALID
    ):
        reasons.append(VerificationReasonCode.FLIGHT_PLAN_WITHOUT_PERMISSION)

    if facts.notam_status is NotamStatus.ACTIVE_RELEVANT:
        reasons.append(VerificationReasonCode.NOTAM_ACTIVE_RELEVANT)
    elif facts.notam_status is NotamStatus.NONE_ACTIVE:
        reasons.append(VerificationReasonCode.NOTAM_NONE_ACTIVE)
    elif facts.notam_status is NotamStatus.CONFLICTING:
        reasons.append(VerificationReasonCode.NOTAM_CONFLICTING)
    effect_reason = {
        NotamOperationEffect.RESTRICTS_OPERATION: VerificationReasonCode.NOTAM_RESTRICTS_OPERATION,
        NotamOperationEffect.PROHIBITS_OPERATION: VerificationReasonCode.NOTAM_PROHIBITS_OPERATION,
        NotamOperationEffect.CONFLICTS_WITH_PERMISSION: (
            VerificationReasonCode.NOTAM_CONFLICTS_WITH_PERMISSION
        ),
    }.get(facts.notam_operation_effect)
    if effect_reason is not None:
        reasons.append(effect_reason)

    if facts.operational_consistency_status is OperationalConsistencyStatus.INDETERMINATE:
        reasons.append(VerificationReasonCode.OPERATIONAL_CONSISTENCY_INDETERMINATE)
    if (
        OperationalConsistencyFlag.REQUIRED_OPERATIONAL_CHECK_UNAVAILABLE
        in facts.operational_consistency_flags
    ):
        reasons.append(VerificationReasonCode.REQUIRED_OPERATIONAL_CHECK_UNAVAILABLE)
    if facts.visual_evidence_status is VisualEvidenceStatus.CONFLICTING:
        reasons.append(VerificationReasonCode.VISUAL_EVIDENCE_CONFLICTING)
    if facts.uncertainty_level is UncertaintyLevel.HIGH:
        reasons.append(VerificationReasonCode.VISUAL_UNCERTAINTY_HIGH)

    statuses = (
        facts.platform_execution_status,
        facts.inventory_execution_status,
        facts.permission_execution_status,
        facts.notam_execution_status,
    )
    if ToolExecutionStatus.TIMEOUT in statuses:
        reasons.append(VerificationReasonCode.TOOL_TIMEOUT)
    if facts.platform_execution_status in _FAILED_EXECUTIONS:
        reasons.append(VerificationReasonCode.PLATFORM_TOOL_ERROR)
    if facts.permission_execution_status in _FAILED_EXECUTIONS:
        reasons.append(VerificationReasonCode.PERMISSION_TOOL_ERROR)
    if facts.notam_execution_status in _FAILED_EXECUTIONS:
        reasons.append(VerificationReasonCode.NOTAM_TOOL_ERROR)
    return list(dict.fromkeys(reasons))


class VerificationChecker:
    """Apply binding precedence without producing a risk level."""

    def check(
        self, facts: VerificationInput, *, strong_non_aircraft: bool = False
    ) -> VerificationResult:
        """Return deterministic status, reasons, health, and tool coverage facts."""
        required = derive_required_tools(facts, strong_non_aircraft=strong_non_aircraft)
        health = calculate_tool_health(facts, strong_non_aircraft=strong_non_aircraft)
        reasons = _reason_codes(facts)
        if strong_non_aircraft:
            reasons = [VerificationReasonCode.NON_AIRCRAFT]
            status = VerificationStatus.NOT_APPLICABLE
        elif (
            facts.inventory_status is InventoryStatus.UNKNOWN
            or facts.inventory_execution_status in _FAILED_EXECUTIONS
            or facts.operational_consistency_status is OperationalConsistencyStatus.INDETERMINATE
        ):
            status = VerificationStatus.INDETERMINATE
        elif facts.context_status in {
            ContextStatus.MISSING,
            ContextStatus.INVALID,
            ContextStatus.INACTIVE,
        }:
            status = VerificationStatus.INDETERMINATE
        elif health is ToolHealthStatus.FAILED:
            status = VerificationStatus.INDETERMINATE
        elif facts.platform_status in {PlatformStatus.UNKNOWN, PlatformStatus.AMBIGUOUS}:
            status = VerificationStatus.INDETERMINATE
        elif is_unregistered_military_policy(
            platform_usage_domain=facts.platform_usage_domain,
            inventory_execution_status=facts.inventory_execution_status,
            inventory_status=facts.inventory_status,
        ):
            status = VerificationStatus.UNVERIFIED
        elif (
            facts.permission_status is PermissionStatus.CONFLICTING
            or facts.flight_plan_status is FlightPlanStatus.CONFLICTING
            or facts.record_consistency is RecordConsistency.CONFLICTING
            or facts.notam_operation_effect
            in {
                NotamOperationEffect.CONFLICTS_WITH_PERMISSION,
                NotamOperationEffect.PROHIBITS_OPERATION,
                NotamOperationEffect.RESTRICTS_OPERATION,
            }
            or (
                facts.flight_plan_status is FlightPlanStatus.FILED
                and facts.permission_status is not PermissionStatus.VALID
            )
            or (
                facts.permission_status is PermissionStatus.VALID
                and facts.flight_plan_status
                in {
                    FlightPlanStatus.CANCELLED,
                    FlightPlanStatus.EXPIRED,
                    FlightPlanStatus.NOT_FOUND,
                }
            )
            or facts.permission_status
            in {
                PermissionStatus.EXPIRED,
                PermissionStatus.REVOKED,
                PermissionStatus.NOT_YET_VALID,
                PermissionStatus.NOT_FOUND,
            }
        ):
            status = VerificationStatus.UNVERIFIED
        elif (
            facts.platform_status is PlatformStatus.EXPECTED
            and facts.permission_status is PermissionStatus.VALID
            and facts.flight_plan_status is FlightPlanStatus.FILED
        ):
            status = VerificationStatus.VERIFIED
        elif (
            facts.platform_status in {PlatformStatus.EXPECTED, PlatformStatus.NOT_EXPECTED}
            and facts.permission_status is PermissionStatus.VALID
            and facts.flight_plan_status is FlightPlanStatus.FILED
        ) or facts.context_status is ContextStatus.PARTIAL:
            status = VerificationStatus.PARTIALLY_VERIFIED
        else:
            status = VerificationStatus.INDETERMINATE

        successful = [
            name
            for name in required
            if _execution_status(facts, name) is ToolExecutionStatus.SUCCESS
        ]
        return VerificationResult(
            verification_status=status,
            reason_codes=reasons,
            tool_health_status=health,
            required_tools=list(required),
            successful_required_tools=successful,
        )
