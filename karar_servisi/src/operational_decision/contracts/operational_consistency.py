"""Strict deterministic operational consistency contracts."""

from typing import Self

from pydantic import model_validator

from operational_decision.contracts.common import (
    OperationalConsistencyFlag,
    OperationalConsistencyStatus,
    StrictContract,
    ToolExecutionStatus,
)
from operational_decision.contracts.context import ContextResolution
from operational_decision.contracts.inventory import TurkeyInventoryResult
from operational_decision.contracts.notam import NotamResult
from operational_decision.contracts.permission import PermissionFlightPlanResult
from operational_decision.contracts.platform import PlatformResult
from operational_decision.contracts.visual import FinalVisualEvidencePackage


class OperationalConsistencyInput(StrictContract):
    """Deterministic facts and execution states consumed by the checker."""

    context: ContextResolution
    platform: PlatformResult | None
    inventory: TurkeyInventoryResult | None
    permission_flight_plan: PermissionFlightPlanResult | None
    notam: NotamResult | None
    visual_evidence: FinalVisualEvidencePackage
    platform_execution_status: ToolExecutionStatus
    inventory_execution_status: ToolExecutionStatus
    permission_execution_status: ToolExecutionStatus
    notam_execution_status: ToolExecutionStatus


class OperationalConsistencyResult(StrictContract):
    """Consistency result produced before operational verification."""

    status: OperationalConsistencyStatus
    flags: list[OperationalConsistencyFlag]
    reason_codes: list[str]
    evidence_references: list[str]
    human_review_required: bool

    @model_validator(mode="after")
    def validate_deterministic_evidence(self) -> Self:
        """Require unique flags and one reason/evidence reference per flag."""
        if len(self.flags) != len(set(self.flags)):
            raise ValueError("flags must be unique")
        if not len(self.flags) == len(self.reason_codes) == len(self.evidence_references):
            raise ValueError("flags, reason_codes, and evidence_references must have equal lengths")
        return self
