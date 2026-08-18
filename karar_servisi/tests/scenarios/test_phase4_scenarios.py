"""Deterministic Phase 4 acceptance matrix for SCN-01 through SCN-12."""
# ruff: noqa: D103

from pathlib import Path

import pytest

from operational_decision.contracts.common import (
    ContextStatus,
    FlightPlanStatus,
    NotamOperationEffect,
    NotamStatus,
    PermissionStatus,
    PlatformStatus,
    RecordConsistency,
    RiskLevel,
    ToolExecutionStatus,
    UncertaintyLevel,
    VerificationStatus,
    VisualClass,
    VisualEvidenceStatus,
)
from operational_decision.contracts.verification import VerificationInput
from operational_decision.decision.risk_advisor import RiskAdvisor
from operational_decision.decision.verification_checker import VerificationChecker

ROOT = Path(__file__).resolve().parents[2]


def scenario_facts(scenario_id: str) -> tuple[VerificationInput, bool]:
    base: dict[str, object] = {
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
    changes: dict[str, dict[str, object]] = {
        "SCN-01": {},
        "SCN-02": {
            "permission_status": PermissionStatus.NOT_FOUND,
            "record_consistency": RecordConsistency.PARTIAL,
        },
        "SCN-03": {
            "platform_status": PlatformStatus.NOT_EXPECTED,
            "permission_status": PermissionStatus.NOT_FOUND,
            "flight_plan_status": FlightPlanStatus.NOT_FOUND,
            "record_consistency": RecordConsistency.UNKNOWN,
        },
        "SCN-04": {
            "permission_status": PermissionStatus.EXPIRED,
            "record_consistency": RecordConsistency.CONFLICTING,
        },
        "SCN-05": {
            "notam_status": NotamStatus.ACTIVE_RELEVANT,
            "notam_operation_effect": NotamOperationEffect.RESTRICTS_OPERATION,
        },
        "SCN-06": {
            "platform_status": PlatformStatus.UNKNOWN,
            "permission_status": PermissionStatus.NOT_APPLICABLE,
            "flight_plan_status": FlightPlanStatus.NOT_APPLICABLE,
            "record_consistency": RecordConsistency.NOT_APPLICABLE,
            "permission_execution_status": ToolExecutionStatus.SKIPPED,
            "visual_class": VisualClass.UNKNOWN_AIRCRAFT,
            "uncertainty_level": UncertaintyLevel.HIGH,
        },
        "SCN-07": {
            "permission_status": PermissionStatus.NOT_FOUND,
            "flight_plan_status": FlightPlanStatus.NOT_FOUND,
            "record_consistency": RecordConsistency.UNKNOWN,
            "permission_execution_status": ToolExecutionStatus.ERROR,
        },
        "SCN-08": {
            "platform_status": PlatformStatus.NON_AIRCRAFT,
            "permission_status": PermissionStatus.NOT_APPLICABLE,
            "flight_plan_status": FlightPlanStatus.NOT_APPLICABLE,
            "record_consistency": RecordConsistency.NOT_APPLICABLE,
            "visual_class": VisualClass.NON_AIRCRAFT,
            "platform_execution_status": ToolExecutionStatus.SKIPPED,
            "permission_execution_status": ToolExecutionStatus.SKIPPED,
            "notam_execution_status": ToolExecutionStatus.SKIPPED,
        },
        "SCN-09": {
            "flight_plan_status": FlightPlanStatus.CANCELLED,
            "record_consistency": RecordConsistency.CONFLICTING,
        },
        "SCN-10": {
            "context_status": ContextStatus.INACTIVE,
            "platform_status": PlatformStatus.UNKNOWN,
            "permission_status": PermissionStatus.NOT_APPLICABLE,
            "flight_plan_status": FlightPlanStatus.NOT_APPLICABLE,
            "record_consistency": RecordConsistency.NOT_APPLICABLE,
            "permission_execution_status": ToolExecutionStatus.SKIPPED,
            "notam_execution_status": ToolExecutionStatus.SKIPPED,
        },
        "SCN-11": {
            "notam_status": NotamStatus.ACTIVE_RELEVANT,
            "notam_operation_effect": NotamOperationEffect.PROHIBITS_OPERATION,
        },
        "SCN-12": {
            "platform_status": PlatformStatus.NOT_EXPECTED,
        },
    }
    base.update(changes[scenario_id])
    return VerificationInput(**base), scenario_id == "SCN-08"


@pytest.mark.parametrize(
    ("scenario_id", "verification_status", "risk_level", "selected_rule"),
    [
        ("SCN-01", VerificationStatus.VERIFIED, RiskLevel.LOW, "RULE_VERIFIED_OPERATION"),
        (
            "SCN-02",
            VerificationStatus.UNVERIFIED,
            RiskLevel.MEDIUM,
            "RULE_EXPECTED_NO_PERMISSION",
        ),
        (
            "SCN-03",
            VerificationStatus.UNVERIFIED,
            RiskLevel.HIGH,
            "RULE_NOT_EXPECTED_NO_PERMISSION",
        ),
        (
            "SCN-04",
            VerificationStatus.UNVERIFIED,
            RiskLevel.HIGH,
            "RULE_CONFLICTING_RECORDS",
        ),
        (
            "SCN-05",
            VerificationStatus.UNVERIFIED,
            RiskLevel.HIGH,
            "RULE_NOTAM_RESTRICTS_OPERATION",
        ),
        (
            "SCN-06",
            VerificationStatus.INDETERMINATE,
            RiskLevel.UNKNOWN,
            "RULE_PLATFORM_UNRESOLVED",
        ),
        (
            "SCN-07",
            VerificationStatus.INDETERMINATE,
            RiskLevel.UNKNOWN,
            "RULE_CRITICAL_TOOL_FAILURE",
        ),
        (
            "SCN-08",
            VerificationStatus.NOT_APPLICABLE,
            RiskLevel.LOW,
            "RULE_NON_AIRCRAFT",
        ),
        (
            "SCN-09",
            VerificationStatus.UNVERIFIED,
            RiskLevel.HIGH,
            "RULE_CONFLICTING_RECORDS",
        ),
        (
            "SCN-10",
            VerificationStatus.INDETERMINATE,
            RiskLevel.UNKNOWN,
            "RULE_CONTEXT_UNAVAILABLE",
        ),
        (
            "SCN-11",
            VerificationStatus.UNVERIFIED,
            RiskLevel.CRITICAL,
            "RULE_NOTAM_PROHIBITS_OPERATION",
        ),
        (
            "SCN-12",
            VerificationStatus.PARTIALLY_VERIFIED,
            RiskLevel.MEDIUM,
            "RULE_NOT_EXPECTED_VALID_PERMISSION",
        ),
    ],
)
def test_phase4_scenario_matrix(
    scenario_id: str,
    verification_status: VerificationStatus,
    risk_level: RiskLevel,
    selected_rule: str,
) -> None:
    facts, strong_non_aircraft = scenario_facts(scenario_id)
    verification = VerificationChecker().check(facts, strong_non_aircraft=strong_non_aircraft)
    risk = RiskAdvisor.from_yaml(ROOT / "data/rules/risk_rules.yaml").assess(facts, verification)
    assert verification.verification_status is verification_status
    assert risk.risk_level is risk_level
    assert risk.selected_rule_id == selected_rule
    if risk_level is RiskLevel.UNKNOWN:
        assert risk.human_review_required is True
