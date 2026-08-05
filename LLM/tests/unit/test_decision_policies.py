"""Unit tests for early exit, decision policy, action catalog, and RAG policy."""
# ruff: noqa: D103

from pathlib import Path

import pytest

from operational_decision.contracts.common import (
    ContextStatus,
    DecisionCode,
    FlightPlanStatus,
    InventoryStatus,
    NotamOperationEffect,
    NotamStatus,
    PermissionStatus,
    PlatformStatus,
    RecordConsistency,
    RiskLevel,
    ToolExecutionStatus,
    ToolHealthStatus,
    UncertaintyLevel,
    VerificationStatus,
    VisualClass,
    VisualEvidenceStatus,
)
from operational_decision.contracts.platform import UsageDomain
from operational_decision.contracts.verification import VerificationInput
from operational_decision.contracts.visual import FinalVisualEvidencePackage
from operational_decision.decision.decision_policy import (
    allowed_decision_codes,
    load_action_catalog,
)
from operational_decision.decision.rag_policy import should_call_text_rag
from operational_decision.decision.verification_checker import (
    VerificationChecker,
    should_early_exit_non_aircraft,
)

ROOT = Path(__file__).resolve().parents[2]


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


def test_strong_non_aircraft_early_exit_requires_every_guard() -> None:
    visual = FinalVisualEvidencePackage.model_construct(
        visual_class=VisualClass.NON_AIRCRAFT,
        visual_evidence_status=VisualEvidenceStatus.SUPPORTED,
        uncertainty_level=UncertaintyLevel.LOW,
        visual_confidence=0.9,
    )
    assert should_early_exit_non_aircraft(visual, 0.85) is True
    weak = visual.model_copy(update={"uncertainty_level": UncertaintyLevel.HIGH})
    assert should_early_exit_non_aircraft(weak, 0.85) is False


def test_allowed_decision_policy_is_deterministic() -> None:
    verified_facts = facts()
    verified = VerificationChecker().check(verified_facts)
    assert allowed_decision_codes(verified, verified_facts) == [
        DecisionCode.AUTHORIZED_OPERATIONAL_MATCH
    ]

    unresolved_facts = facts(platform_status=PlatformStatus.UNKNOWN)
    unresolved = VerificationChecker().check(unresolved_facts)
    assert allowed_decision_codes(unresolved, unresolved_facts) == [
        DecisionCode.PLATFORM_UNRESOLVED
    ]


def test_rag_call_policy_without_implementing_rag() -> None:
    assert (
        should_call_text_rag(
            verification_status=VerificationStatus.VERIFIED,
            risk_level=RiskLevel.LOW,
            tool_health_status=ToolHealthStatus.HEALTHY,
            facts=facts(),
            explanation_requested=False,
        )
        is False
    )
    assert (
        should_call_text_rag(
            verification_status=VerificationStatus.UNVERIFIED,
            risk_level=RiskLevel.HIGH,
            tool_health_status=ToolHealthStatus.HEALTHY,
            facts=facts(permission_status=PermissionStatus.NOT_FOUND),
            explanation_requested=False,
        )
        is True
    )
    assert (
        should_call_text_rag(
            verification_status=VerificationStatus.NOT_APPLICABLE,
            risk_level=RiskLevel.LOW,
            tool_health_status=ToolHealthStatus.HEALTHY,
            facts=facts(visual_class=VisualClass.NON_AIRCRAFT),
            explanation_requested=False,
            strong_non_aircraft=True,
        )
        is False
    )


def test_action_catalog_is_validated() -> None:
    catalog = load_action_catalog(ROOT / "data/rules/action_catalog.yaml")
    assert catalog.actions[0].code == "CONTINUE_TRACKING"
    assert all(action.allowed_risks for action in catalog.actions)


def test_inventory_not_listed_verified_uses_authorized_operational_match() -> None:
    value = facts(inventory_status=InventoryStatus.NOT_LISTED)
    verification = VerificationChecker().check(value)
    assert verification.verification_status is VerificationStatus.VERIFIED
    assert allowed_decision_codes(verification, value) == [
        DecisionCode.AUTHORIZED_OPERATIONAL_MATCH
    ]


def test_resolved_platform_permission_missing_uses_authorization_unverified() -> None:
    value = facts(
        inventory_status=InventoryStatus.NOT_LISTED,
        permission_status=PermissionStatus.NOT_FOUND,
        flight_plan_status=FlightPlanStatus.NOT_FOUND,
        record_consistency=RecordConsistency.UNKNOWN,
    )
    verification = VerificationChecker().check(value)
    assert verification.verification_status is VerificationStatus.UNVERIFIED
    assert allowed_decision_codes(verification, value) == [
        DecisionCode.OPERATIONAL_AUTHORIZATION_UNVERIFIED
    ]


def test_inventory_error_uses_existing_safe_review_decision() -> None:
    value = facts(
        inventory_status=InventoryStatus.UNKNOWN,
        inventory_execution_status=ToolExecutionStatus.ERROR,
    )
    verification = VerificationChecker().check(value)
    assert allowed_decision_codes(verification, value) == [DecisionCode.INDETERMINATE]


def test_origin_and_taxonomy_are_not_decision_inputs() -> None:
    assert {"platform_origin", "manufacturer_country_code", "taxonomy"}.isdisjoint(
        VerificationInput.model_fields
    )


def test_unregistered_military_unverified_uses_dedicated_decision() -> None:
    value = facts(
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
    verification = VerificationChecker().check(value)
    assert verification.verification_status is VerificationStatus.UNVERIFIED
    assert allowed_decision_codes(verification, value) == [
        DecisionCode.UNREGISTERED_MILITARY_AIRCRAFT
    ]


@pytest.mark.parametrize(
    "usage_domain", [UsageDomain.CIVIL, UsageDomain.DUAL_USE, UsageDomain.UNKNOWN]
)
def test_dedicated_military_decision_does_not_apply_to_other_domains(
    usage_domain: UsageDomain,
) -> None:
    value = facts(
        platform_usage_domain=usage_domain,
        inventory_status=InventoryStatus.NOT_LISTED,
        permission_status=PermissionStatus.NOT_FOUND,
        flight_plan_status=FlightPlanStatus.NOT_FOUND,
        record_consistency=RecordConsistency.UNKNOWN,
    )
    verification = VerificationChecker().check(value)
    assert allowed_decision_codes(verification, value) == [
        DecisionCode.OPERATIONAL_AUTHORIZATION_UNVERIFIED
    ]


@pytest.mark.parametrize(
    "permission_status",
    [PermissionStatus.EXPIRED, PermissionStatus.REVOKED],
)
def test_invalid_permission_precedes_generic_record_conflict(
    permission_status: PermissionStatus,
) -> None:
    value = facts(
        permission_status=permission_status,
        flight_plan_status=FlightPlanStatus.FILED,
        record_consistency=RecordConsistency.CONFLICTING,
    )
    verification = VerificationChecker().check(value)

    assert verification.verification_status is VerificationStatus.UNVERIFIED
    assert allowed_decision_codes(verification, value) == [
        DecisionCode.EXPIRED_OR_INVALID_PERMISSION
    ]


def test_active_notam_prohibition_uses_dedicated_decision() -> None:
    value = facts(
        notam_status=NotamStatus.ACTIVE_RELEVANT,
        notam_operation_effect=NotamOperationEffect.PROHIBITS_OPERATION,
    )
    verification = VerificationChecker().check(value)

    assert verification.verification_status is VerificationStatus.UNVERIFIED
    assert allowed_decision_codes(verification, value) == [DecisionCode.ACTIVE_NOTAM_PROHIBITION]
