"""Unit tests for deterministic verification and tool health."""
# ruff: noqa: D103

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
)
from operational_decision.contracts.platform import UsageDomain
from operational_decision.contracts.verification import (
    VerificationInput,
    VerificationReasonCode,
)
from operational_decision.decision.verification_checker import (
    VerificationChecker,
    calculate_tool_health,
    derive_required_tools,
    is_unregistered_military_policy,
)


def facts(**changes: object) -> VerificationInput:
    values: dict[str, object] = {
        "context_status": ContextStatus.COMPLETE,
        "platform_status": PlatformStatus.EXPECTED,
        "permission_status": PermissionStatus.VALID,
        "flight_plan_status": FlightPlanStatus.FILED,
        "record_consistency": RecordConsistency.CONSISTENT,
        "notam_status": NotamStatus.NONE_ACTIVE,
        "notam_operation_effect": NotamOperationEffect.NO_EFFECT,
        "visual_class": VisualClass.FIGHTER_JET,
        "visual_evidence_status": VisualEvidenceStatus.SUPPORTED,
        "visual_confidence": 0.9,
        "uncertainty_level": UncertaintyLevel.LOW,
        "visual_human_review_required": False,
        "platform_execution_status": ToolExecutionStatus.SUCCESS,
        "permission_execution_status": ToolExecutionStatus.SUCCESS,
        "notam_execution_status": ToolExecutionStatus.SUCCESS,
    }
    values.update(changes)
    return VerificationInput(**values)


def test_required_tool_matrix_follows_context_and_platform_gates() -> None:
    assert derive_required_tools(facts()) == (
        "platform_tool",
        "turkey_inventory_tool",
        "notam_tool",
        "permission_flight_plan_tool",
    )
    assert derive_required_tools(
        facts(context_status=ContextStatus.MISSING, platform_status=PlatformStatus.UNKNOWN)
    ) == ("platform_tool",)
    assert derive_required_tools(facts(platform_status=PlatformStatus.UNKNOWN)) == (
        "platform_tool",
    )


def test_tool_health_distinguishes_critical_and_auxiliary_failures() -> None:
    assert calculate_tool_health(facts()) is ToolHealthStatus.HEALTHY
    assert (
        calculate_tool_health(facts(notam_execution_status=ToolExecutionStatus.ERROR))
        is ToolHealthStatus.DEGRADED
    )
    assert (
        calculate_tool_health(facts(permission_execution_status=ToolExecutionStatus.ERROR))
        is ToolHealthStatus.FAILED
    )
    assert (
        calculate_tool_health(facts(context_status=ContextStatus.MISSING))
        is ToolHealthStatus.FAILED
    )


def test_permission_not_found_with_filed_plan_is_not_permission() -> None:
    result = VerificationChecker().check(
        facts(
            permission_status=PermissionStatus.NOT_FOUND,
            flight_plan_status=FlightPlanStatus.FILED,
            record_consistency=RecordConsistency.PARTIAL,
        )
    )
    assert result.verification_status is VerificationStatus.UNVERIFIED
    assert VerificationReasonCode.PERMISSION_NOT_FOUND in result.reason_codes
    assert VerificationReasonCode.FLIGHT_PLAN_WITHOUT_PERMISSION in result.reason_codes


def test_tool_error_and_domain_not_found_remain_separate() -> None:
    result = VerificationChecker().check(
        facts(
            permission_status=PermissionStatus.NOT_FOUND,
            permission_execution_status=ToolExecutionStatus.ERROR,
        )
    )
    assert result.verification_status is VerificationStatus.INDETERMINATE
    assert result.tool_health_status is ToolHealthStatus.FAILED
    assert VerificationReasonCode.PERMISSION_TOOL_ERROR in result.reason_codes
    assert VerificationReasonCode.PERMISSION_NOT_FOUND in result.reason_codes


def test_verification_precedence_for_context_notam_and_platform() -> None:
    checker = VerificationChecker()
    missing = checker.check(facts(context_status=ContextStatus.MISSING))
    assert missing.verification_status is VerificationStatus.INDETERMINATE

    restricts = checker.check(
        facts(
            notam_status=NotamStatus.ACTIVE_RELEVANT,
            notam_operation_effect=NotamOperationEffect.RESTRICTS_OPERATION,
        )
    )
    assert restricts.verification_status is VerificationStatus.UNVERIFIED
    assert VerificationReasonCode.NOTAM_RESTRICTS_OPERATION in restricts.reason_codes

    unresolved = checker.check(facts(platform_status=PlatformStatus.UNKNOWN))
    assert unresolved.verification_status is VerificationStatus.INDETERMINATE


def test_strong_non_aircraft_precedes_operational_tools() -> None:
    result = VerificationChecker().check(
        facts(
            visual_class=VisualClass.NON_AIRCRAFT,
            platform_status=PlatformStatus.NON_AIRCRAFT,
            permission_status=PermissionStatus.NOT_APPLICABLE,
            flight_plan_status=FlightPlanStatus.NOT_APPLICABLE,
            record_consistency=RecordConsistency.NOT_APPLICABLE,
            platform_execution_status=ToolExecutionStatus.SKIPPED,
            permission_execution_status=ToolExecutionStatus.SKIPPED,
            notam_execution_status=ToolExecutionStatus.SKIPPED,
        ),
        strong_non_aircraft=True,
    )
    assert result.verification_status is VerificationStatus.NOT_APPLICABLE
    assert result.tool_health_status is ToolHealthStatus.HEALTHY
    assert result.required_tools == []


def test_unregistered_military_policy_skip_is_healthy_and_unverified() -> None:
    current = facts(
        platform_usage_domain=UsageDomain.MILITARY,
        inventory_status=InventoryStatus.NOT_LISTED,
        inventory_execution_status=ToolExecutionStatus.SUCCESS,
        permission_status=PermissionStatus.NOT_APPLICABLE,
        flight_plan_status=FlightPlanStatus.NOT_APPLICABLE,
        record_consistency=RecordConsistency.NOT_APPLICABLE,
        notam_operation_effect=NotamOperationEffect.UNKNOWN,
        permission_execution_status=ToolExecutionStatus.SKIPPED,
        notam_execution_status=ToolExecutionStatus.SKIPPED,
    )
    result = VerificationChecker().check(current)
    assert result.required_tools == ["platform_tool", "turkey_inventory_tool"]
    assert result.successful_required_tools == ["platform_tool", "turkey_inventory_tool"]
    assert result.tool_health_status is ToolHealthStatus.HEALTHY
    assert result.verification_status is VerificationStatus.UNVERIFIED


def test_unregistered_military_policy_condition_is_exact() -> None:
    assert is_unregistered_military_policy(
        platform_usage_domain=UsageDomain.MILITARY,
        inventory_execution_status=ToolExecutionStatus.SUCCESS,
        inventory_status=InventoryStatus.NOT_LISTED,
    )
    for usage_domain in (UsageDomain.CIVIL, UsageDomain.DUAL_USE, UsageDomain.UNKNOWN):
        assert not is_unregistered_military_policy(
            platform_usage_domain=usage_domain,
            inventory_execution_status=ToolExecutionStatus.SUCCESS,
            inventory_status=InventoryStatus.NOT_LISTED,
        )
    for execution_status in (
        ToolExecutionStatus.ERROR,
        ToolExecutionStatus.TIMEOUT,
        ToolExecutionStatus.SKIPPED,
    ):
        assert not is_unregistered_military_policy(
            platform_usage_domain=UsageDomain.MILITARY,
            inventory_execution_status=execution_status,
            inventory_status=InventoryStatus.NOT_LISTED,
        )
    assert not is_unregistered_military_policy(
        platform_usage_domain=UsageDomain.MILITARY,
        inventory_execution_status=ToolExecutionStatus.SUCCESS,
        inventory_status=InventoryStatus.CONFIRMED,
    )

def test_inventory_not_listed_with_valid_operation_is_verified() -> None:
    result = VerificationChecker().check(
        facts(inventory_status=InventoryStatus.NOT_LISTED)
    )
    assert result.verification_status is VerificationStatus.VERIFIED
    assert result.tool_health_status is ToolHealthStatus.HEALTHY
    assert result.required_tools == [
        "platform_tool",
        "turkey_inventory_tool",
        "notam_tool",
        "permission_flight_plan_tool",
    ]
    assert VerificationReasonCode.INVENTORY_NOT_LISTED in result.reason_codes
    assert VerificationReasonCode.PERMISSION_VALID in result.reason_codes
    assert VerificationReasonCode.FLIGHT_PLAN_FILED in result.reason_codes
    assert len(result.reason_codes) == len(set(result.reason_codes))


def test_inventory_not_listed_with_missing_records_is_unverified() -> None:
    result = VerificationChecker().check(
        facts(
            inventory_status=InventoryStatus.NOT_LISTED,
            permission_status=PermissionStatus.NOT_FOUND,
            flight_plan_status=FlightPlanStatus.NOT_FOUND,
            record_consistency=RecordConsistency.UNKNOWN,
        )
    )
    assert result.verification_status is VerificationStatus.UNVERIFIED
    assert result.tool_health_status is ToolHealthStatus.HEALTHY
    assert VerificationReasonCode.INVENTORY_NOT_LISTED in result.reason_codes
    assert VerificationReasonCode.PERMISSION_NOT_FOUND in result.reason_codes
    assert VerificationReasonCode.FLIGHT_PLAN_NOT_FOUND in result.reason_codes


def test_inventory_error_is_indeterminate_and_failed() -> None:
    result = VerificationChecker().check(
        facts(
            inventory_status=InventoryStatus.UNKNOWN,
            inventory_execution_status=ToolExecutionStatus.ERROR,
            operational_consistency_status=OperationalConsistencyStatus.INDETERMINATE,
            operational_consistency_flags=[
                OperationalConsistencyFlag.INVENTORY_CHECK_UNAVAILABLE,
                OperationalConsistencyFlag.REQUIRED_OPERATIONAL_CHECK_UNAVAILABLE,
            ],
        )
    )
    assert result.verification_status is VerificationStatus.INDETERMINATE
    assert result.tool_health_status is ToolHealthStatus.FAILED
    assert VerificationReasonCode.INVENTORY_UNKNOWN in result.reason_codes
    assert VerificationReasonCode.INVENTORY_TOOL_ERROR in result.reason_codes


def test_cancelled_plan_and_consistency_indeterminate_precedence() -> None:
    cancelled = VerificationChecker().check(facts(flight_plan_status=FlightPlanStatus.CANCELLED))
    assert cancelled.verification_status is VerificationStatus.UNVERIFIED
    indeterminate = VerificationChecker().check(
        facts(
            operational_consistency_status=OperationalConsistencyStatus.INDETERMINATE,
            operational_consistency_flags=[
                OperationalConsistencyFlag.REQUIRED_OPERATIONAL_CHECK_UNAVAILABLE
            ],
        )
    )
    assert indeterminate.verification_status is VerificationStatus.INDETERMINATE
    assert (
        VerificationReasonCode.OPERATIONAL_CONSISTENCY_INDETERMINATE in indeterminate.reason_codes
    )


def test_inventory_unknown_is_failed_even_without_technical_error() -> None:
    result = VerificationChecker().check(
        facts(
            inventory_status=InventoryStatus.UNKNOWN,
            inventory_execution_status=ToolExecutionStatus.SKIPPED,
            platform_status=PlatformStatus.UNKNOWN,
            permission_execution_status=ToolExecutionStatus.SKIPPED,
            notam_execution_status=ToolExecutionStatus.SKIPPED,
        )
    )
    assert result.verification_status is VerificationStatus.INDETERMINATE
    assert result.tool_health_status is ToolHealthStatus.FAILED
