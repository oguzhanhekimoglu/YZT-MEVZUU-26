"""Unit tests for permission/plan consistency and NOTAM effect policy."""
# ruff: noqa: D102, D103, D107

from operational_decision.contracts.common import (
    FlightPlanStatus,
    PermissionStatus,
    RecordConsistency,
)
from operational_decision.tools.permission_flight_plan_tool import (
    resolve_record_consistency,
)


def test_record_consistency_binding_matrix() -> None:
    assert (
        resolve_record_consistency(PermissionStatus.VALID, FlightPlanStatus.FILED)
        is RecordConsistency.CONSISTENT
    )
    assert (
        resolve_record_consistency(PermissionStatus.VALID, FlightPlanStatus.NOT_FOUND)
        is RecordConsistency.PARTIAL
    )
    assert (
        resolve_record_consistency(PermissionStatus.NOT_FOUND, FlightPlanStatus.FILED)
        is RecordConsistency.PARTIAL
    )
    assert (
        resolve_record_consistency(PermissionStatus.NOT_FOUND, FlightPlanStatus.NOT_FOUND)
        is RecordConsistency.UNKNOWN
    )
    assert (
        resolve_record_consistency(PermissionStatus.REVOKED, FlightPlanStatus.FILED)
        is RecordConsistency.CONFLICTING
    )
    assert (
        resolve_record_consistency(PermissionStatus.VALID, FlightPlanStatus.EXPIRED)
        is RecordConsistency.CONFLICTING
    )
    assert (
        resolve_record_consistency(PermissionStatus.AMBIGUOUS, FlightPlanStatus.AMBIGUOUS)
        is RecordConsistency.UNKNOWN
    )
