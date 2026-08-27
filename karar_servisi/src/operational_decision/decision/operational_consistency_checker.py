"""Deterministic operational consistency checks."""

from operational_decision.contracts.common import (
    ContextStatus,
    FlightPlanStatus,
    InventoryStatus,
    NotamOperationEffect,
    OperationalConsistencyFlag,
    OperationalConsistencyStatus,
    PermissionStatus,
    PlatformStatus,
    ToolExecutionStatus,
    VisualClass,
)
from operational_decision.contracts.operational_consistency import (
    OperationalConsistencyInput,
    OperationalConsistencyResult,
)

_UNAVAILABLE = frozenset({ToolExecutionStatus.ERROR, ToolExecutionStatus.TIMEOUT})
_INVALID_PERMISSIONS = frozenset(
    {PermissionStatus.EXPIRED, PermissionStatus.REVOKED, PermissionStatus.NOT_FOUND}
)
_INVALID_FLIGHT_PLANS = frozenset(
    {FlightPlanStatus.CANCELLED, FlightPlanStatus.EXPIRED, FlightPlanStatus.NOT_FOUND}
)
_FLAG_ORDER = tuple(OperationalConsistencyFlag)
_EVIDENCE = {
    OperationalConsistencyFlag.INVENTORY_SCOPE_CONFIRMED: "inventory.inventory_status",
    OperationalConsistencyFlag.INVENTORY_NOT_LISTED: "inventory.inventory_status",
    OperationalConsistencyFlag.INVENTORY_CHECK_UNAVAILABLE: "inventory.execution_status",
    OperationalConsistencyFlag.DOWNSTREAM_CHECKS_SKIPPED_INVENTORY_NOT_CONFIRMED: (
        "permission_flight_plan.execution_status,notam.execution_status"
    ),
    OperationalConsistencyFlag.VISUAL_AFFILIATION_INVENTORY_MISMATCH: (
        "visual_evidence.affiliation,inventory.country_code"
    ),
    OperationalConsistencyFlag.PLATFORM_NOT_EXPECTED_IN_CONTEXT: "platform.platform_status",
    OperationalConsistencyFlag.PLATFORM_CONTEXT_MISMATCH: (
        "context.record.expected_platform_id,platform.platform_id"
    ),
    OperationalConsistencyFlag.FLIGHT_PLAN_WITHOUT_VALID_PERMISSION: (
        "permission_flight_plan.permission_status,permission_flight_plan.flight_plan_status"
    ),
    OperationalConsistencyFlag.INVALID_PERMISSION_WITH_FILED_PLAN: (
        "permission_flight_plan.permission_status,permission_flight_plan.flight_plan_status"
    ),
    OperationalConsistencyFlag.VALID_PERMISSION_WITH_INVALID_FLIGHT_PLAN: (
        "permission_flight_plan.permission_status,permission_flight_plan.flight_plan_status"
    ),
    OperationalConsistencyFlag.NOTAM_CONFLICTS_WITH_PERMISSION: "notam.operation_effect",
    OperationalConsistencyFlag.NOTAM_RESTRICTS_OPERATION: "notam.operation_effect",
    OperationalConsistencyFlag.NOTAM_PROHIBITS_OPERATION: "notam.operation_effect",
    OperationalConsistencyFlag.REQUIRED_OPERATIONAL_CHECK_UNAVAILABLE: "tool_execution_status",
    OperationalConsistencyFlag.CONTEXT_UNAVAILABLE: "context.context_status",
}
_INFORMATIONAL_FLAGS = frozenset(
    {
        OperationalConsistencyFlag.INVENTORY_SCOPE_CONFIRMED,
        OperationalConsistencyFlag.INVENTORY_NOT_LISTED,
    }
)
_PROBLEM_FLAGS = frozenset(_FLAG_ORDER) - _INFORMATIONAL_FLAGS


class OperationalConsistencyChecker:
    """Evaluate controlled domain facts without LLM inference."""

    def check(self, facts: OperationalConsistencyInput) -> OperationalConsistencyResult:
        """Return ordered, unique flags with one reason and evidence reference each."""
        if facts.visual_evidence.visual_class is VisualClass.NON_AIRCRAFT:
            return OperationalConsistencyResult(
                status=OperationalConsistencyStatus.NOT_APPLICABLE,
                flags=[],
                reason_codes=[],
                evidence_references=[],
                human_review_required=False,
            )

        emitted: set[OperationalConsistencyFlag] = set()
        context_complete = facts.context.context_status is ContextStatus.COMPLETE
        if not context_complete:
            emitted.add(OperationalConsistencyFlag.CONTEXT_UNAVAILABLE)

        inventory = facts.inventory
        inventory_unavailable = (
            facts.inventory_execution_status in _UNAVAILABLE
            or inventory is None
            or (inventory is not None and inventory.inventory_status is InventoryStatus.UNKNOWN)
        )
        if inventory_unavailable:
            emitted.add(OperationalConsistencyFlag.INVENTORY_CHECK_UNAVAILABLE)
        elif (
            inventory is not None
            and facts.inventory_execution_status is ToolExecutionStatus.SUCCESS
        ):
            if inventory.inventory_status is InventoryStatus.NOT_LISTED:
                emitted.add(OperationalConsistencyFlag.INVENTORY_NOT_LISTED)
            elif inventory.inventory_status is InventoryStatus.CONFIRMED:
                emitted.add(OperationalConsistencyFlag.INVENTORY_SCOPE_CONFIRMED)

        platform = facts.platform
        if (
            facts.platform_execution_status is ToolExecutionStatus.SUCCESS
            and platform is not None
            and platform.platform_status is PlatformStatus.NOT_EXPECTED
        ):
            emitted.add(OperationalConsistencyFlag.PLATFORM_NOT_EXPECTED_IN_CONTEXT)

        record = facts.context.record
        if (
            context_complete
            and record is not None
            and record.expected_platform_id is not None
            and facts.platform_execution_status is ToolExecutionStatus.SUCCESS
            and platform is not None
            and platform.platform_id is not None
            and platform.platform_id != record.expected_platform_id
        ):
            emitted.add(OperationalConsistencyFlag.PLATFORM_CONTEXT_MISMATCH)

        permission = facts.permission_flight_plan
        if facts.permission_execution_status is ToolExecutionStatus.SUCCESS and permission:
            permission_status = permission.permission_status
            plan_status = permission.flight_plan_status
            if (
                plan_status is FlightPlanStatus.FILED
                and permission_status is not PermissionStatus.VALID
            ):
                emitted.add(OperationalConsistencyFlag.FLIGHT_PLAN_WITHOUT_VALID_PERMISSION)
            if permission_status in _INVALID_PERMISSIONS and plan_status is FlightPlanStatus.FILED:
                emitted.add(OperationalConsistencyFlag.INVALID_PERMISSION_WITH_FILED_PLAN)
            if permission_status is PermissionStatus.VALID and plan_status in _INVALID_FLIGHT_PLANS:
                emitted.add(OperationalConsistencyFlag.VALID_PERMISSION_WITH_INVALID_FLIGHT_PLAN)

        notam = facts.notam
        if facts.notam_execution_status is ToolExecutionStatus.SUCCESS and notam:
            flag = {
                NotamOperationEffect.CONFLICTS_WITH_PERMISSION: (
                    OperationalConsistencyFlag.NOTAM_CONFLICTS_WITH_PERMISSION
                ),
                NotamOperationEffect.RESTRICTS_OPERATION: (
                    OperationalConsistencyFlag.NOTAM_RESTRICTS_OPERATION
                ),
                NotamOperationEffect.PROHIBITS_OPERATION: (
                    OperationalConsistencyFlag.NOTAM_PROHIBITS_OPERATION
                ),
            }.get(notam.operation_effect)
            if flag is not None:
                emitted.add(flag)

        if self._required_check_unavailable(facts, context_complete):
            emitted.add(OperationalConsistencyFlag.REQUIRED_OPERATIONAL_CHECK_UNAVAILABLE)

        flags = [flag for flag in _FLAG_ORDER if flag in emitted]
        # CONTEXT_UNAVAILABLE alone should not force INDETERMINATE when the
        # platform's identity is resolved (IDENTIFIED_CONTEXT_UNKNOWN) and
        # Inventory still ran successfully — only genuinely unavailable
        # identity-independent checks should block. CONTEXT_UNAVAILABLE
        # still appears in `flags` for the audit trail either way.
        identity_resolved_despite_missing_context = (
            facts.platform_execution_status is ToolExecutionStatus.SUCCESS
            and platform is not None
            and platform.platform_status is PlatformStatus.IDENTIFIED_CONTEXT_UNKNOWN
            and not inventory_unavailable
        )
        blocking_flags = {
            OperationalConsistencyFlag.INVENTORY_CHECK_UNAVAILABLE,
            OperationalConsistencyFlag.REQUIRED_OPERATIONAL_CHECK_UNAVAILABLE,
        }
        if not identity_resolved_despite_missing_context:
            blocking_flags = blocking_flags | {OperationalConsistencyFlag.CONTEXT_UNAVAILABLE}
        indeterminate = bool(blocking_flags & emitted)
        if indeterminate:
            status = OperationalConsistencyStatus.INDETERMINATE
        elif emitted & _PROBLEM_FLAGS:
            status = OperationalConsistencyStatus.FLAGGED
        else:
            status = OperationalConsistencyStatus.CONSISTENT
        return OperationalConsistencyResult(
            status=status,
            flags=flags,
            reason_codes=[flag.value for flag in flags],
            evidence_references=[_EVIDENCE[flag] for flag in flags],
            human_review_required=status
            in {
                OperationalConsistencyStatus.FLAGGED,
                OperationalConsistencyStatus.INDETERMINATE,
            },
        )

    @staticmethod
    def _required_check_unavailable(
        facts: OperationalConsistencyInput,
        context_complete: bool,
    ) -> bool:
        if facts.platform_execution_status in _UNAVAILABLE:
            return True
        platform_resolved = (
            facts.platform_execution_status is ToolExecutionStatus.SUCCESS
            and facts.platform is not None
            and facts.platform.platform_id is not None
            and facts.platform.platform_status
            in {PlatformStatus.EXPECTED, PlatformStatus.NOT_EXPECTED}
        )
        if platform_resolved and facts.inventory_execution_status in _UNAVAILABLE:
            return True
        if not (context_complete and platform_resolved):
            return False
        return (
            facts.permission_execution_status in _UNAVAILABLE
            or facts.notam_execution_status in _UNAVAILABLE
        )
