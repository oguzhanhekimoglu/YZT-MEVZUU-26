"""Unit tests for deterministic operational consistency rules."""

# ruff: noqa: D103

from pathlib import Path

import pytest

from operational_decision.app.demo_scenarios import build_demo_request
from operational_decision.contracts.common import (
    ContextStatus,
    FlightPlanStatus,
    InventoryStatus,
    NotamOperationEffect,
    NotamStatus,
    PermissionStatus,
    PlatformStatus,
    RecordConsistency,
    ToolExecutionStatus,
)
from operational_decision.contracts.common import (
    OperationalConsistencyFlag as Flag,
)
from operational_decision.contracts.common import (
    OperationalConsistencyStatus as Status,
)
from operational_decision.contracts.context import ContextResolution
from operational_decision.contracts.inventory import TurkeyInventoryResult
from operational_decision.contracts.notam import NotamResult
from operational_decision.contracts.operational_consistency import OperationalConsistencyInput
from operational_decision.contracts.permission import PermissionFlightPlanResult
from operational_decision.contracts.platform import PlatformResult
from operational_decision.decision.operational_consistency_checker import (
    OperationalConsistencyChecker,
)

ROOT = Path(__file__).resolve().parents[2]
SUCCESS = ToolExecutionStatus.SUCCESS


def inventory(status: InventoryStatus = InventoryStatus.CONFIRMED) -> TurkeyInventoryResult:
    return TurkeyInventoryResult(
        inventory_status=status,
        platform_id="PLT_F16",
        reason_codes=[status.value],
        safe_message="Controlled inventory result.",
        warnings=[],
    )


def permission(
    permission_status: PermissionStatus = PermissionStatus.VALID,
    flight_plan_status: FlightPlanStatus = FlightPlanStatus.FILED,
) -> PermissionFlightPlanResult:
    return PermissionFlightPlanResult(
        permission_status=permission_status,
        flight_plan_status=flight_plan_status,
        record_consistency=RecordConsistency.CONSISTENT,
    )


def notam(effect: NotamOperationEffect = NotamOperationEffect.NO_EFFECT) -> NotamResult:
    return NotamResult(notam_status=NotamStatus.NONE_ACTIVE, operation_effect=effect)


def facts(scenario: int = 1, **updates: object) -> OperationalConsistencyInput:
    base = OperationalConsistencyInput(
        context=ContextResolution(context_status=ContextStatus.COMPLETE),
        platform=PlatformResult(platform_status=PlatformStatus.EXPECTED, platform_id="PLT_F16"),
        inventory=inventory(),
        permission_flight_plan=permission(),
        notam=notam(),
        visual_evidence=build_demo_request(ROOT, f"SCN-{scenario:02d}").visual_evidence,
        platform_execution_status=SUCCESS,
        inventory_execution_status=SUCCESS,
        permission_execution_status=SUCCESS,
        notam_execution_status=SUCCESS,
    )
    return base.model_copy(update=updates)


def check(value: OperationalConsistencyInput):
    return OperationalConsistencyChecker().check(value)


def test_normal_operation_is_consistent() -> None:
    result = check(facts())
    assert result.status is Status.CONSISTENT
    assert result.flags == [Flag.INVENTORY_SCOPE_CONFIRMED]
    assert result.human_review_required is False
    assert len(result.flags) == len(result.reason_codes) == len(result.evidence_references)


def test_inventory_not_listed_is_informational_when_downstream_succeeds() -> None:
    result = check(
        facts(
            inventory=inventory(InventoryStatus.NOT_LISTED),
        )
    )
    assert result.status is Status.CONSISTENT
    assert result.flags == [Flag.INVENTORY_NOT_LISTED]
    assert Flag.DOWNSTREAM_CHECKS_SKIPPED_INVENTORY_NOT_CONFIRMED not in result.flags
    assert result.human_review_required is False


def test_inventory_not_listed_does_not_hide_downstream_consistency_flags() -> None:
    result = check(
        facts(
            inventory=inventory(InventoryStatus.NOT_LISTED),
            permission_flight_plan=permission(
                PermissionStatus.NOT_FOUND,
                FlightPlanStatus.FILED,
            ),
        )
    )
    assert result.status is Status.FLAGGED
    assert result.flags == [
        Flag.INVENTORY_NOT_LISTED,
        Flag.FLIGHT_PLAN_WITHOUT_VALID_PERMISSION,
        Flag.INVALID_PERMISSION_WITH_FILED_PLAN,
    ]
    assert Flag.DOWNSTREAM_CHECKS_SKIPPED_INVENTORY_NOT_CONFIRMED not in result.flags


def test_inventory_error_is_indeterminate() -> None:
    result = check(
        facts(
            inventory=inventory(InventoryStatus.UNKNOWN),
            inventory_execution_status=ToolExecutionStatus.ERROR,
        )
    )
    assert result.status is Status.INDETERMINATE
    assert Flag.INVENTORY_CHECK_UNAVAILABLE in result.flags
    assert Flag.REQUIRED_OPERATIONAL_CHECK_UNAVAILABLE in result.flags
    assert Flag.DOWNSTREAM_CHECKS_SKIPPED_INVENTORY_NOT_CONFIRMED not in result.flags


def test_context_unavailable_is_indeterminate() -> None:
    result = check(facts(context=ContextResolution(context_status=ContextStatus.MISSING)))
    assert result.status is Status.INDETERMINATE
    assert Flag.CONTEXT_UNAVAILABLE in result.flags


def test_platform_not_expected_is_flagged() -> None:
    result = check(
        facts(
            platform=PlatformResult(
                platform_status=PlatformStatus.NOT_EXPECTED, platform_id="PLT_F16"
            )
        )
    )
    assert result.status is Status.FLAGGED
    assert Flag.PLATFORM_NOT_EXPECTED_IN_CONTEXT in result.flags


def test_filed_plan_without_valid_permission_emits_both_specific_flags() -> None:
    result = check(facts(permission_flight_plan=permission(PermissionStatus.EXPIRED)))
    assert Flag.FLIGHT_PLAN_WITHOUT_VALID_PERMISSION in result.flags
    assert Flag.INVALID_PERMISSION_WITH_FILED_PLAN in result.flags


def test_valid_permission_with_cancelled_plan() -> None:
    result = check(
        facts(permission_flight_plan=permission(PermissionStatus.VALID, FlightPlanStatus.CANCELLED))
    )
    assert result.status is Status.FLAGGED
    assert Flag.VALID_PERMISSION_WITH_INVALID_FLIGHT_PLAN in result.flags


@pytest.mark.parametrize(
    ("effect", "expected"),
    [
        (NotamOperationEffect.RESTRICTS_OPERATION, Flag.NOTAM_RESTRICTS_OPERATION),
        (NotamOperationEffect.PROHIBITS_OPERATION, Flag.NOTAM_PROHIBITS_OPERATION),
        (NotamOperationEffect.CONFLICTS_WITH_PERMISSION, Flag.NOTAM_CONFLICTS_WITH_PERMISSION),
    ],
)
def test_notam_effect_flags(effect: NotamOperationEffect, expected: Flag) -> None:
    result = check(facts(notam=notam(effect)))
    assert result.status is Status.FLAGGED
    assert expected in result.flags


def test_required_tool_error_is_indeterminate_without_domain_inference() -> None:
    result = check(
        facts(permission_flight_plan=None, permission_execution_status=ToolExecutionStatus.ERROR)
    )
    assert result.status is Status.INDETERMINATE
    assert result.flags == [
        Flag.INVENTORY_SCOPE_CONFIRMED,
        Flag.REQUIRED_OPERATIONAL_CHECK_UNAVAILABLE,
    ]


def test_non_aircraft_is_not_applicable() -> None:
    result = check(facts(8))
    assert result.status is Status.NOT_APPLICABLE
    assert result.flags == []
    assert result.human_review_required is False


def test_flags_are_unique_and_in_deterministic_enum_order() -> None:
    result = check(
        facts(
            platform=PlatformResult(
                platform_status=PlatformStatus.NOT_EXPECTED, platform_id="PLT_F16"
            ),
            permission_flight_plan=permission(PermissionStatus.EXPIRED),
            notam=notam(NotamOperationEffect.PROHIBITS_OPERATION),
        )
    )
    assert len(result.flags) == len(set(result.flags))
    assert result.flags == [flag for flag in Flag if flag in set(result.flags)]
