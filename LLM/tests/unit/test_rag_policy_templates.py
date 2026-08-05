# ruff: noqa: D103

"""Unit tests for deterministic Inventory-aware RAG policy."""

import pytest

from operational_decision.contracts.common import (
    ContextStatus,
    FlightPlanStatus,
    InventoryStatus,
    NotamOperationEffect,
    NotamStatus,
    OperationalConsistencyFlag,
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
from operational_decision.decision.rag_policy import (
    select_text_rag_query,
    should_call_text_rag,
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


def should_call(
    value: VerificationInput,
    *,
    verification: VerificationStatus = VerificationStatus.UNVERIFIED,
    risk: RiskLevel = RiskLevel.HIGH,
    health: ToolHealthStatus = ToolHealthStatus.HEALTHY,
    explanation: bool = False,
) -> bool:
    return should_call_text_rag(
        verification_status=verification,
        risk_level=risk,
        tool_health_status=health,
        facts=value,
        explanation_requested=explanation,
    )


def test_not_listed_alone_has_no_inventory_query_or_rag_call() -> None:
    value = facts(
        inventory_status=InventoryStatus.NOT_LISTED,
        permission_status=PermissionStatus.NOT_APPLICABLE,
        flight_plan_status=FlightPlanStatus.NOT_APPLICABLE,
        notam_operation_effect=NotamOperationEffect.UNKNOWN,
        permission_execution_status=ToolExecutionStatus.SKIPPED,
        notam_execution_status=ToolExecutionStatus.SKIPPED,
    )
    assert select_text_rag_query(value) is None
    assert (
        should_call(
            value,
            verification=VerificationStatus.INDETERMINATE,
            risk=RiskLevel.UNKNOWN,
            explanation=True,
        )
        is False
    )
    assert value.inventory_status is InventoryStatus.NOT_LISTED


def test_explanation_requested_calls_only_with_supported_template() -> None:
    supported = facts(permission_status=PermissionStatus.EXPIRED)
    assert (
        should_call(
            supported,
            verification=VerificationStatus.INDETERMINATE,
            risk=RiskLevel.UNKNOWN,
            explanation=True,
        )
        is True
    )
    unsupported = facts(platform_status=PlatformStatus.NOT_EXPECTED)
    assert select_text_rag_query(unsupported) is None
    assert should_call(unsupported, explanation=True) is False


def test_permission_missing_and_flight_plan_without_permission_templates() -> None:
    without_plan = facts(
        permission_status=PermissionStatus.NOT_FOUND,
        flight_plan_status=FlightPlanStatus.NOT_FOUND,
    )
    plan = select_text_rag_query(without_plan)
    assert plan is not None
    assert plan.query_template_id == "PERMISSION_NOT_FOUND"
    assert should_call(without_plan) is True

    filed = facts(permission_status=PermissionStatus.NOT_FOUND)
    distinction = select_text_rag_query(filed)
    assert distinction is not None
    assert distinction.query_template_id == "FLIGHT_PLAN_WITHOUT_PERMISSION"
    assert distinction.document_ids == ("LT_GEN_1_2", "LT_ENR_1_10")


def test_consistency_permission_plan_flag_selects_existing_distinction_template() -> None:
    value = facts(
        flight_plan_status=FlightPlanStatus.CANCELLED,
        operational_consistency_flags=[
            OperationalConsistencyFlag.INVENTORY_SCOPE_CONFIRMED,
            OperationalConsistencyFlag.VALID_PERMISSION_WITH_INVALID_FLIGHT_PLAN,
        ],
    )
    plan = select_text_rag_query(value)
    assert plan is not None
    assert plan.query_template_id == "FLIGHT_PLAN_WITHOUT_PERMISSION"
    assert should_call(value) is True


@pytest.mark.parametrize(
    "effect",
    [
        NotamOperationEffect.RESTRICTS_OPERATION,
        NotamOperationEffect.PROHIBITS_OPERATION,
        NotamOperationEffect.CONFLICTS_WITH_PERMISSION,
    ],
)
def test_binding_notam_effects_select_active_notam(effect: NotamOperationEffect) -> None:
    value = facts(
        notam_status=NotamStatus.ACTIVE_RELEVANT,
        notam_operation_effect=effect,
    )
    plan = select_text_rag_query(value)
    assert plan is not None
    assert plan.query_template_id == "ACTIVE_NOTAM"
    assert plan.document_ids == ("LT_GEN_3_1",)
    assert should_call(value) is True


def test_verified_low_healthy_skips_even_when_general_template_exists() -> None:
    value = facts(visual_class=VisualClass.UAV)
    assert select_text_rag_query(value) is not None
    assert (
        should_call(
            value,
            verification=VerificationStatus.VERIFIED,
            risk=RiskLevel.LOW,
            health=ToolHealthStatus.HEALTHY,
        )
        is False
    )


def test_non_aircraft_and_missing_template_are_safe_skips() -> None:
    non_aircraft = facts(visual_class=VisualClass.NON_AIRCRAFT)
    assert (
        should_call(
            non_aircraft,
            verification=VerificationStatus.NOT_APPLICABLE,
            risk=RiskLevel.LOW,
        )
        is False
    )

    no_template = facts(platform_status=PlatformStatus.UNKNOWN)
    assert select_text_rag_query(no_template) is None
    assert (
        should_call(
            no_template,
            verification=VerificationStatus.INDETERMINATE,
            risk=RiskLevel.UNKNOWN,
            health=ToolHealthStatus.FAILED,
        )
        is False
    )


def test_civil_uav_uses_existing_runtime_filter() -> None:
    plan = select_text_rag_query(facts(visual_class=VisualClass.UAV))
    assert plan is not None
    assert plan.query_template_id == "CIVIL_UAV"
    assert plan.document_ids == ("SHT_IHA_REV_05",)


def test_unregistered_military_airspace_context_template_is_exact_and_safe() -> None:
    value = facts(
        platform_usage_domain=UsageDomain.MILITARY,
        inventory_status=InventoryStatus.NOT_LISTED,
        inventory_execution_status=ToolExecutionStatus.SUCCESS,
        permission_status=PermissionStatus.NOT_APPLICABLE,
        flight_plan_status=FlightPlanStatus.NOT_APPLICABLE,
        notam_operation_effect=NotamOperationEffect.UNKNOWN,
        permission_execution_status=ToolExecutionStatus.SKIPPED,
        notam_execution_status=ToolExecutionStatus.SKIPPED,
    )
    plan = select_text_rag_query(value)

    assert plan is not None
    assert plan.query_template_id == "UNREGISTERED_MILITARY_AIRSPACE_CONTEXT"
    assert plan.document_ids == ("LT_GEN_1_2", "LT_GEN_1_6", "LT_GEN_3_3")
    assert should_call(value) is True
    normalized_query = plan.query.casefold()
    assert "envanter dışı askerî hava araçları" in normalized_query
    assert "uçuş izni" in normalized_query
    assert "koordinasyonu" in normalized_query
    assert all(term not in normalized_query for term in ("düşman", "kesin izinsiz"))


@pytest.mark.parametrize(
    "usage_domain", [UsageDomain.CIVIL, UsageDomain.DUAL_USE, UsageDomain.UNKNOWN]
)
def test_unregistered_military_template_does_not_apply_to_other_domains(
    usage_domain: UsageDomain,
) -> None:
    value = facts(
        platform_usage_domain=usage_domain,
        inventory_status=InventoryStatus.NOT_LISTED,
        inventory_execution_status=ToolExecutionStatus.SUCCESS,
        permission_status=PermissionStatus.NOT_APPLICABLE,
        flight_plan_status=FlightPlanStatus.NOT_APPLICABLE,
        notam_operation_effect=NotamOperationEffect.UNKNOWN,
        permission_execution_status=ToolExecutionStatus.SKIPPED,
        notam_execution_status=ToolExecutionStatus.SKIPPED,
    )
    assert select_text_rag_query(value) is None
    assert should_call(value) is False


def test_unregistered_military_template_requires_success_complete_and_resolved() -> None:
    base = facts(
        platform_usage_domain=UsageDomain.MILITARY,
        inventory_status=InventoryStatus.NOT_LISTED,
        permission_status=PermissionStatus.NOT_APPLICABLE,
        flight_plan_status=FlightPlanStatus.NOT_APPLICABLE,
        notam_operation_effect=NotamOperationEffect.UNKNOWN,
    )
    for changed in (
        base.model_copy(update={"inventory_execution_status": ToolExecutionStatus.ERROR}),
        base.model_copy(update={"context_status": ContextStatus.PARTIAL}),
        base.model_copy(update={"platform_status": PlatformStatus.UNKNOWN}),
    ):
        assert select_text_rag_query(changed) is None
        assert should_call(changed) is False
