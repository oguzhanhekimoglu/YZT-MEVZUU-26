"""Unit tests for YAML risk rules and confidence formulas."""
# ruff: noqa: D103

from pathlib import Path

import pytest

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
    RiskLevel,
    ToolExecutionStatus,
    UncertaintyLevel,
    VerificationStatus,
    VisualClass,
    VisualEvidenceStatus,
    VlmOriginCategory,
)
from operational_decision.contracts.platform import UsageDomain
from operational_decision.contracts.verification import VerificationInput
from operational_decision.decision.risk_advisor import (
    RiskAdvisor,
    calculate_decision_confidence,
    calculate_evidence_quality,
    calculate_risk_assessment_confidence,
)
from operational_decision.decision.verification_checker import VerificationChecker

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


def advisor() -> RiskAdvisor:
    return RiskAdvisor.from_yaml(ROOT / "data/rules/risk_rules.yaml")


@pytest.mark.parametrize(
    ("changes", "expected_risk", "expected_rule"),
    [
        (
            {
                "notam_status": NotamStatus.ACTIVE_RELEVANT,
                "notam_operation_effect": NotamOperationEffect.PROHIBITS_OPERATION,
            },
            RiskLevel.CRITICAL,
            "RULE_NOTAM_PROHIBITS_OPERATION",
        ),
        (
            {
                "notam_status": NotamStatus.ACTIVE_RELEVANT,
                "notam_operation_effect": NotamOperationEffect.RESTRICTS_OPERATION,
            },
            RiskLevel.HIGH,
            "RULE_NOTAM_RESTRICTS_OPERATION",
        ),
        (
            {
                "notam_status": NotamStatus.CONFLICTING,
                "notam_operation_effect": NotamOperationEffect.CONFLICTS_WITH_PERMISSION,
            },
            RiskLevel.HIGH,
            "RULE_NOTAM_PERMISSION_CONFLICT",
        ),
        (
            {"platform_status": PlatformStatus.UNKNOWN},
            RiskLevel.UNKNOWN,
            "RULE_PLATFORM_UNRESOLVED",
        ),
    ],
)
def test_binding_risk_rules(
    changes: dict[str, object], expected_risk: RiskLevel, expected_rule: str
) -> None:
    value = facts(**changes)
    result = advisor().assess(value, VerificationChecker().check(value))
    assert result.risk_level is expected_risk
    assert expected_rule in result.matched_rule_ids
    assert result.human_review_required is True
    if expected_rule == "RULE_NOTAM_PROHIBITS_OPERATION":
        assert result.human_review_priority == "URGENT"


@pytest.mark.parametrize(
    "effect", [NotamOperationEffect.INFORMATIONAL, NotamOperationEffect.NO_EFFECT]
)
def test_non_restrictive_notam_does_not_raise_risk_automatically(
    effect: NotamOperationEffect,
) -> None:
    value = facts(
        notam_status=NotamStatus.ACTIVE_RELEVANT,
        notam_operation_effect=effect,
    )
    result = advisor().assess(value, VerificationChecker().check(value))
    assert result.risk_level is RiskLevel.LOW
    assert all("NOTAM" not in rule_id for rule_id in result.matched_rule_ids)


def test_highest_risk_and_priority_are_preserved() -> None:
    value = facts(
        permission_status=PermissionStatus.EXPIRED,
        notam_status=NotamStatus.ACTIVE_RELEVANT,
        notam_operation_effect=NotamOperationEffect.PROHIBITS_OPERATION,
    )
    result = advisor().assess(value, VerificationChecker().check(value))
    assert result.risk_level is RiskLevel.CRITICAL
    assert result.selected_rule_id == "RULE_NOTAM_PROHIBITS_OPERATION"


def test_low_risk_does_not_require_review_for_visual_flag_alone() -> None:
    value = facts(visual_human_review_required=True)
    result = advisor().assess(value, VerificationChecker().check(value))
    assert result.risk_level is RiskLevel.LOW
    assert result.human_review_required is False
    assert result.explanation
    assert isinstance(result.increasing_factors, list)
    assert result.reducing_factors
    assert result.uncertainties


def test_confidence_formulas_and_unknown_cap() -> None:
    evidence = calculate_evidence_quality(
        visual_confidence=0.8,
        tool_coverage_score=1.0,
        context_status=ContextStatus.COMPLETE,
        verification_status=VerificationStatus.PARTIALLY_VERIFIED,
    )
    assert evidence == 0.88
    assert calculate_risk_assessment_confidence(evidence, 0.85, RiskLevel.MEDIUM) == 0.748
    assert calculate_risk_assessment_confidence(0.9, 0.85, RiskLevel.UNKNOWN) == 0.5
    assert calculate_decision_confidence(0.88, 0.748) == 0.748


def test_undefined_risk_uses_unknown_fallback(tmp_path: Path) -> None:
    path = tmp_path / "empty_rules.yaml"
    path.write_text("rules: []\n", encoding="utf-8")
    value = facts(
        platform_status=PlatformStatus.EXPECTED,
        permission_status=PermissionStatus.VALID,
        flight_plan_status=FlightPlanStatus.NOT_FOUND,
    )
    result = RiskAdvisor.from_yaml(path).assess(value, VerificationChecker().check(value))
    assert result.risk_level is RiskLevel.UNKNOWN
    assert result.human_review_required is True
    assert result.rule_specificity == 0.5


def test_not_listed_verified_operation_uses_normal_low_risk_rule() -> None:
    not_listed = facts(inventory_status=InventoryStatus.NOT_LISTED)
    not_listed_result = advisor().assess(not_listed, VerificationChecker().check(not_listed))
    assert not_listed_result.risk_level is RiskLevel.LOW
    assert not_listed_result.selected_rule_id == "RULE_VERIFIED_OPERATION"
    assert not_listed_result.human_review_required is False
    assert "RULE_INVENTORY_NOT_LISTED" not in not_listed_result.matched_rule_ids


def test_not_listed_missing_permission_uses_normal_medium_risk_rule() -> None:
    not_listed = facts(
        inventory_status=InventoryStatus.NOT_LISTED,
        permission_status=PermissionStatus.NOT_FOUND,
        flight_plan_status=FlightPlanStatus.NOT_FOUND,
        record_consistency=RecordConsistency.UNKNOWN,
    )
    result = advisor().assess(not_listed, VerificationChecker().check(not_listed))
    assert result.risk_level is RiskLevel.MEDIUM
    assert result.selected_rule_id == "RULE_EXPECTED_NO_PERMISSION"
    assert result.human_review_required is True


def test_filed_plan_with_expired_permission_is_not_a_reducing_factor() -> None:
    value = facts(
        permission_status=PermissionStatus.EXPIRED,
        flight_plan_status=FlightPlanStatus.FILED,
        record_consistency=RecordConsistency.CONFLICTING,
    )
    result = advisor().assess(value, VerificationChecker().check(value))

    assert result.risk_level is RiskLevel.HIGH
    assert all("Uyumlu Flight Plan" not in item for item in result.reducing_factors)
    assert any(
        "geçerli uçuş izniyle birlikte doğrulanamamıştır" in item
        for item in result.increasing_factors
    )


def test_inventory_and_required_check_unknown_rules() -> None:
    unavailable = facts(
        inventory_status=InventoryStatus.UNKNOWN,
        inventory_execution_status=ToolExecutionStatus.ERROR,
        operational_consistency_status=OperationalConsistencyStatus.INDETERMINATE,
        operational_consistency_flags=[
            OperationalConsistencyFlag.INVENTORY_CHECK_UNAVAILABLE,
            OperationalConsistencyFlag.REQUIRED_OPERATIONAL_CHECK_UNAVAILABLE,
        ],
    )
    unavailable_result = advisor().assess(unavailable, VerificationChecker().check(unavailable))
    assert unavailable_result.risk_level is RiskLevel.UNKNOWN
    assert "RULE_INVENTORY_UNAVAILABLE" in unavailable_result.matched_rule_ids
    assert "RULE_REQUIRED_OPERATIONAL_CHECK_UNAVAILABLE" in unavailable_result.matched_rule_ids


def test_origin_and_taxonomy_are_not_risk_inputs() -> None:
    assert {"platform_origin", "manufacturer_country_code", "taxonomy"}.isdisjoint(
        VerificationInput.model_fields
    )


def test_valid_permission_cancelled_plan_is_high() -> None:
    value = facts(
        permission_status=PermissionStatus.VALID,
        flight_plan_status=FlightPlanStatus.CANCELLED,
    )
    result = advisor().assess(value, VerificationChecker().check(value))
    assert result.risk_level is RiskLevel.HIGH
    assert "RULE_FLIGHT_PLAN_CANCELLED" in result.matched_rule_ids


def test_unregistered_military_platform_is_high_and_urgent() -> None:
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
    result = advisor().assess(value, VerificationChecker().check(value))

    assert result.risk_level is RiskLevel.HIGH
    assert result.selected_rule_id == "RULE_UNREGISTERED_MILITARY_PLATFORM"
    assert result.human_review_required is True
    assert result.human_review_priority == "URGENT"
    assert result.explanation == (
        "Platform askerî kullanım alanında olup Türkiye Inventory veri setinde kayıtlı değildir."
    )
    assert result.increasing_factors[0] == (
        "Askerî kullanım alanındaki platform Türkiye Inventory veri setinde kayıtlı değildir."
    )
    forbidden = ("Permission kaydı bulunamadı", "Flight Plan kaydı bulunamadı", "NOTAM")
    assert all(token not in " ".join(result.increasing_factors) for token in forbidden)


@pytest.mark.parametrize(
    "usage_domain", [UsageDomain.CIVIL, UsageDomain.DUAL_USE, UsageDomain.UNKNOWN]
)
def test_unregistered_military_rule_does_not_apply_to_other_domains(
    usage_domain: UsageDomain,
) -> None:
    value = facts(
        platform_usage_domain=usage_domain,
        inventory_status=InventoryStatus.NOT_LISTED,
    )
    result = advisor().assess(value, VerificationChecker().check(value))
    assert "RULE_UNREGISTERED_MILITARY_PLATFORM" not in result.matched_rule_ids
    assert result.risk_level is RiskLevel.LOW


def test_unregistered_military_rule_does_not_override_inventory_error() -> None:
    value = facts(
        platform_usage_domain=UsageDomain.MILITARY,
        inventory_status=InventoryStatus.NOT_LISTED,
        inventory_execution_status=ToolExecutionStatus.ERROR,
    )
    result = advisor().assess(value, VerificationChecker().check(value))
    assert result.risk_level is RiskLevel.UNKNOWN
    assert result.selected_rule_id == "RULE_INVENTORY_EXECUTION_FAILURE"


# Regression coverage for the VLM ulke_orjini origin policy. This must apply
# uniformly to every MILITARY, Inventory-LISTED (CONFIRMED) platform, so each
# case is parametrized across visual classes standing in for real inventory
# platforms: FIGHTER_JET (F-16, F-4E), UCAV (Bayraktar TB2, AKINCI), UAV
# (TUSAŞ ANKA), and HELICOPTER (T129 ATAK) -- proving the policy is generic
# and never keyed off a platform name.
_MILITARY_PLATFORM_VISUAL_CLASSES = [
    VisualClass.FIGHTER_JET,  # e.g. F-16, F-4E
    VisualClass.UCAV,  # e.g. Bayraktar TB2, AKINCI
    VisualClass.UAV,  # e.g. TUSAŞ ANKA
    VisualClass.HELICOPTER,  # e.g. T129 ATAK
]


@pytest.mark.parametrize("visual_class", _MILITARY_PLATFORM_VISUAL_CLASSES)
def test_military_listed_turkey_origin_allows_low_with_positive_tools(
    visual_class: VisualClass,
) -> None:
    """Turkey origin alone must not force a floor; LOW stays reachable with clean tools."""
    value = facts(
        visual_class=visual_class,
        platform_usage_domain=UsageDomain.MILITARY,
        inventory_status=InventoryStatus.CONFIRMED,
        vlm_origin_category=VlmOriginCategory.TURKEY,
    )
    result = advisor().assess(value, VerificationChecker().check(value))
    assert result.risk_level is RiskLevel.LOW
    assert result.human_review_required is False
    assert result.human_review_priority == "NORMAL"


@pytest.mark.parametrize("visual_class", _MILITARY_PLATFORM_VISUAL_CLASSES)
def test_military_listed_turkey_origin_alone_does_not_guarantee_low(
    visual_class: VisualClass,
) -> None:
    """Turkey origin must not single-handedly produce a safe decision."""
    value = facts(
        visual_class=visual_class,
        platform_usage_domain=UsageDomain.MILITARY,
        inventory_status=InventoryStatus.CONFIRMED,
        vlm_origin_category=VlmOriginCategory.TURKEY,
        permission_status=PermissionStatus.NOT_FOUND,
        flight_plan_status=FlightPlanStatus.NOT_FOUND,
        record_consistency=RecordConsistency.UNKNOWN,
    )
    result = advisor().assess(value, VerificationChecker().check(value))
    assert result.risk_level is not RiskLevel.LOW
    assert result.human_review_required is True


@pytest.mark.parametrize("visual_class", _MILITARY_PLATFORM_VISUAL_CLASSES)
def test_military_listed_unknown_origin_cannot_be_low_and_requires_review(
    visual_class: VisualClass,
) -> None:
    value = facts(
        visual_class=visual_class,
        platform_usage_domain=UsageDomain.MILITARY,
        inventory_status=InventoryStatus.CONFIRMED,
        vlm_origin_category=VlmOriginCategory.UNKNOWN,
    )
    result = advisor().assess(value, VerificationChecker().check(value))
    assert result.risk_level is RiskLevel.MEDIUM
    assert result.human_review_required is True
    assert "RULE_MILITARY_LISTED_UNKNOWN_ORIGIN" in result.matched_rule_ids
    assert any("belirlenememiştir" in item for item in result.increasing_factors)


@pytest.mark.parametrize("visual_class", _MILITARY_PLATFORM_VISUAL_CLASSES)
def test_military_listed_foreign_origin_is_high_and_urgent_despite_clean_tools(
    visual_class: VisualClass,
) -> None:
    """Foreign origin must stay HIGH/URGENT even when every downstream tool is positive."""
    value = facts(
        visual_class=visual_class,
        platform_usage_domain=UsageDomain.MILITARY,
        inventory_status=InventoryStatus.CONFIRMED,
        vlm_origin_category=VlmOriginCategory.FOREIGN,
    )
    result = advisor().assess(value, VerificationChecker().check(value))
    assert result.risk_level is RiskLevel.HIGH
    assert result.human_review_required is True
    assert result.human_review_priority == "URGENT"
    assert "RULE_MILITARY_LISTED_FOREIGN_ORIGIN" in result.matched_rule_ids
    assert any("yabancı askerî aidiyet şüphesi" in item for item in result.increasing_factors)


@pytest.mark.parametrize("visual_class", _MILITARY_PLATFORM_VISUAL_CLASSES)
def test_military_listed_foreign_origin_does_not_cap_worse_rules(
    visual_class: VisualClass,
) -> None:
    """A prohibiting NOTAM must still escalate above the FOREIGN-origin HIGH floor."""
    value = facts(
        visual_class=visual_class,
        platform_usage_domain=UsageDomain.MILITARY,
        inventory_status=InventoryStatus.CONFIRMED,
        vlm_origin_category=VlmOriginCategory.FOREIGN,
        notam_status=NotamStatus.ACTIVE_RELEVANT,
        notam_operation_effect=NotamOperationEffect.PROHIBITS_OPERATION,
    )
    result = advisor().assess(value, VerificationChecker().check(value))
    assert result.risk_level is RiskLevel.CRITICAL
    assert result.selected_rule_id == "RULE_NOTAM_PROHIBITS_OPERATION"


@pytest.mark.parametrize(
    "usage_domain", [UsageDomain.CIVIL, UsageDomain.DUAL_USE, UsageDomain.UNKNOWN]
)
@pytest.mark.parametrize(
    "origin_category",
    [VlmOriginCategory.TURKEY, VlmOriginCategory.UNKNOWN, VlmOriginCategory.FOREIGN],
)
def test_origin_policy_does_not_apply_to_non_military_domains(
    usage_domain: UsageDomain, origin_category: VlmOriginCategory
) -> None:
    """Civil platform behavior must stay unchanged by the VLM origin category."""
    value = facts(
        platform_usage_domain=usage_domain,
        inventory_status=InventoryStatus.CONFIRMED,
        vlm_origin_category=origin_category,
    )
    result = advisor().assess(value, VerificationChecker().check(value))
    assert result.risk_level is RiskLevel.LOW
    assert result.human_review_required is False
    assert "RULE_MILITARY_LISTED_FOREIGN_ORIGIN" not in result.matched_rule_ids
    assert "RULE_MILITARY_LISTED_UNKNOWN_ORIGIN" not in result.matched_rule_ids


@pytest.mark.parametrize(
    "origin_category",
    [VlmOriginCategory.TURKEY, VlmOriginCategory.UNKNOWN, VlmOriginCategory.FOREIGN],
)
def test_origin_policy_does_not_apply_to_unregistered_military_platform(
    origin_category: VlmOriginCategory,
) -> None:
    """A NOT_LISTED military platform keeps its existing gate regardless of VLM origin."""
    value = facts(
        platform_usage_domain=UsageDomain.MILITARY,
        inventory_status=InventoryStatus.NOT_LISTED,
        inventory_execution_status=ToolExecutionStatus.SUCCESS,
        vlm_origin_category=origin_category,
        permission_status=PermissionStatus.NOT_APPLICABLE,
        flight_plan_status=FlightPlanStatus.NOT_APPLICABLE,
        record_consistency=RecordConsistency.NOT_APPLICABLE,
        notam_operation_effect=NotamOperationEffect.UNKNOWN,
        permission_execution_status=ToolExecutionStatus.SKIPPED,
        notam_execution_status=ToolExecutionStatus.SKIPPED,
    )
    result = advisor().assess(value, VerificationChecker().check(value))
    assert result.risk_level is RiskLevel.HIGH
    assert result.selected_rule_id == "RULE_UNREGISTERED_MILITARY_PLATFORM"
    assert result.human_review_priority == "URGENT"


@pytest.mark.parametrize("visual_class", _MILITARY_PLATFORM_VISUAL_CLASSES)
def test_unregistered_military_turkey_claim_is_flagged_as_suspicious(
    visual_class: VisualClass,
) -> None:
    """A NOT_LISTED military platform claiming Turkish origin must be called out as suspicious."""
    value = facts(
        visual_class=visual_class,
        platform_usage_domain=UsageDomain.MILITARY,
        inventory_status=InventoryStatus.NOT_LISTED,
        inventory_execution_status=ToolExecutionStatus.SUCCESS,
        vlm_origin_category=VlmOriginCategory.TURKEY,
        permission_status=PermissionStatus.NOT_APPLICABLE,
        flight_plan_status=FlightPlanStatus.NOT_APPLICABLE,
        record_consistency=RecordConsistency.NOT_APPLICABLE,
        notam_operation_effect=NotamOperationEffect.UNKNOWN,
        permission_execution_status=ToolExecutionStatus.SKIPPED,
        notam_execution_status=ToolExecutionStatus.SKIPPED,
    )
    result = advisor().assess(value, VerificationChecker().check(value))
    assert result.risk_level is RiskLevel.HIGH
    assert result.selected_rule_id == "RULE_UNREGISTERED_MILITARY_PLATFORM"
    assert result.human_review_priority == "URGENT"
    assert any("şüpheli kabul edilmeli" in item for item in result.increasing_factors)
    assert "şüpheli kabul edilmeli" in result.explanation


@pytest.mark.parametrize("visual_class", _MILITARY_PLATFORM_VISUAL_CLASSES)
def test_unregistered_military_foreign_or_unknown_origin_is_not_flagged_as_turkey_claim(
    visual_class: VisualClass,
) -> None:
    """Non-Turkey origins on a NOT_LISTED military platform keep the generic explanation."""
    for origin_category in (VlmOriginCategory.FOREIGN, VlmOriginCategory.UNKNOWN):
        value = facts(
            visual_class=visual_class,
            platform_usage_domain=UsageDomain.MILITARY,
            inventory_status=InventoryStatus.NOT_LISTED,
            inventory_execution_status=ToolExecutionStatus.SUCCESS,
            vlm_origin_category=origin_category,
            permission_status=PermissionStatus.NOT_APPLICABLE,
            flight_plan_status=FlightPlanStatus.NOT_APPLICABLE,
            record_consistency=RecordConsistency.NOT_APPLICABLE,
            notam_operation_effect=NotamOperationEffect.UNKNOWN,
            permission_execution_status=ToolExecutionStatus.SKIPPED,
            notam_execution_status=ToolExecutionStatus.SKIPPED,
        )
        result = advisor().assess(value, VerificationChecker().check(value))
        assert result.risk_level is RiskLevel.HIGH
        assert "şüpheli kabul edilmeli" not in result.explanation
        assert all("şüpheli kabul edilmeli" not in item for item in result.increasing_factors)


def test_that_turkey_unknown_and_foreign_origin_no_longer_share_the_same_low_output() -> None:
    """Regression check: identical tools, different origin, no longer the same LOW output."""
    base = {
        "platform_usage_domain": UsageDomain.MILITARY,
        "inventory_status": InventoryStatus.CONFIRMED,
    }
    turkey_result = advisor().assess(
        facts(vlm_origin_category=VlmOriginCategory.TURKEY, **base),
        VerificationChecker().check(facts(vlm_origin_category=VlmOriginCategory.TURKEY, **base)),
    )
    unknown_result = advisor().assess(
        facts(vlm_origin_category=VlmOriginCategory.UNKNOWN, **base),
        VerificationChecker().check(facts(vlm_origin_category=VlmOriginCategory.UNKNOWN, **base)),
    )
    foreign_result = advisor().assess(
        facts(vlm_origin_category=VlmOriginCategory.FOREIGN, **base),
        VerificationChecker().check(facts(vlm_origin_category=VlmOriginCategory.FOREIGN, **base)),
    )
    outcomes = {turkey_result.risk_level, unknown_result.risk_level, foreign_result.risk_level}
    assert turkey_result.risk_level is RiskLevel.LOW
    assert len(outcomes) == 3
