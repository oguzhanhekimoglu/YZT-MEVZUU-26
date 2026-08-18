"""Deterministic allowed-decision and action-catalog policies."""

from pathlib import Path
from typing import cast

import yaml

from operational_decision.contracts.common import (
    ContextStatus,
    DecisionCode,
    FlightPlanStatus,
    NotamOperationEffect,
    NotamStatus,
    PermissionStatus,
    PlatformStatus,
    RecordConsistency,
    RiskLevel,
    VerificationStatus,
)
from operational_decision.contracts.risk import (
    ActionCatalog,
    ActionDefinition,
    RiskResult,
)
from operational_decision.contracts.verification import VerificationInput, VerificationResult
from operational_decision.decision.verification_checker import is_unregistered_military_policy


def allowed_decision_codes(
    verification: VerificationResult, facts: VerificationInput
) -> list[DecisionCode]:
    """Return every decision code allowed by the binding policy table."""
    status = verification.verification_status
    if status is VerificationStatus.NOT_APPLICABLE:
        return [DecisionCode.NON_AIRCRAFT]
    if status is VerificationStatus.VERIFIED:
        return [DecisionCode.AUTHORIZED_OPERATIONAL_MATCH]
    if status is VerificationStatus.PARTIALLY_VERIFIED:
        return [DecisionCode.PARTIALLY_VERIFIED_OPERATION]
    if status is VerificationStatus.INDETERMINATE:
        if facts.platform_status in {PlatformStatus.UNKNOWN, PlatformStatus.AMBIGUOUS}:
            return [DecisionCode.PLATFORM_UNRESOLVED]
        return [DecisionCode.INDETERMINATE]

    if (
        status is VerificationStatus.UNVERIFIED
        and facts.context_status is ContextStatus.COMPLETE
        and facts.platform_status in {PlatformStatus.EXPECTED, PlatformStatus.NOT_EXPECTED}
        and is_unregistered_military_policy(
            platform_usage_domain=facts.platform_usage_domain,
            inventory_execution_status=facts.inventory_execution_status,
            inventory_status=facts.inventory_status,
        )
    ):
        return [DecisionCode.UNREGISTERED_MILITARY_AIRCRAFT]

    if facts.notam_operation_effect is NotamOperationEffect.PROHIBITS_OPERATION:
        return [DecisionCode.ACTIVE_NOTAM_PROHIBITION]
    if facts.permission_status in {
        PermissionStatus.EXPIRED,
        PermissionStatus.REVOKED,
    }:
        return [DecisionCode.EXPIRED_OR_INVALID_PERMISSION]
    if (
        facts.record_consistency is RecordConsistency.CONFLICTING
        or facts.permission_status is PermissionStatus.CONFLICTING
        or facts.flight_plan_status is FlightPlanStatus.CONFLICTING
        or facts.notam_status is NotamStatus.CONFLICTING
        or facts.notam_operation_effect is NotamOperationEffect.CONFLICTS_WITH_PERMISSION
    ):
        return [DecisionCode.CONFLICTING_OPERATIONAL_RECORDS]
    if facts.platform_status is PlatformStatus.NOT_EXPECTED:
        return [DecisionCode.UNEXPECTED_PLATFORM]
    if facts.permission_status is PermissionStatus.NOT_FOUND:
        return [DecisionCode.OPERATIONAL_AUTHORIZATION_UNVERIFIED]
    return [DecisionCode.UNVERIFIED_AIRCRAFT]


def allowed_action_codes(
    action_catalog: ActionCatalog,
    risk: RiskResult,
    facts: VerificationInput,
    verification: VerificationResult,
) -> list[str]:
    """Return the evidence-compatible action pool exposed to the LLM."""
    codes = [
        action.code
        for action in action_catalog.actions
        if risk.risk_level in action.allowed_risks
    ]
    if allowed_decision_codes(verification, facts) == [
        DecisionCode.UNREGISTERED_MILITARY_AIRCRAFT
    ]:
        policy_codes = {
            "CONTINUE_TRACKING",
            "REQUEST_OPERATOR_REVIEW",
            "VERIFY_PLATFORM_MANUALLY",
            "ESCALATE_TO_AUTHORIZED_UNIT",
        }
        return [code for code in codes if code in policy_codes]
    return codes

def load_action_catalog(path: Path) -> ActionCatalog:
    """Load the controlled action catalog and validate unique codes."""
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("action catalog YAML must be an object")
    raw_actions = cast(dict[object, object], payload).get("actions")
    if not isinstance(raw_actions, list) or not raw_actions:
        raise ValueError("action catalog must contain actions")
    actions: list[ActionDefinition] = []
    seen_codes: set[str] = set()
    for raw_action in raw_actions:
        if not isinstance(raw_action, dict):
            raise ValueError("each action must be an object")
        item = cast(dict[object, object], raw_action)
        code = item.get("code")
        title = item.get("title_tr")
        raw_risks = item.get("allowed_risks")
        if not isinstance(code, str) or not isinstance(title, str):
            raise ValueError("action code and title_tr must be strings")
        if code in seen_codes:
            raise ValueError(f"duplicate action code: {code}")
        if not isinstance(raw_risks, list) or not all(isinstance(risk, str) for risk in raw_risks):
            raise ValueError(f"allowed_risks must be a string list: {code}")
        actions.append(
            ActionDefinition(
                code=code,
                title_tr=title,
                allowed_risks=[RiskLevel(risk) for risk in raw_risks],
            )
        )
        seen_codes.add(code)
    return ActionCatalog(actions=actions)
