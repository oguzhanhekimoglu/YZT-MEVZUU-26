"""Turkey Inventory V1 and operational consistency contract tests."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from operational_decision.contracts.common import (
    DecisionCode,
    EventStatus,
    InventoryStatus,
    OperationalConsistencyFlag,
    OperationalConsistencyStatus,
    PlatformStatus,
    ToolExecutionStatus,
)
from operational_decision.contracts.inventory import (
    TurkeyInventoryDataset,
    TurkeyInventoryRecord,
    TurkeyInventoryResult,
    TurkeyInventoryToolRequest,
)
from operational_decision.contracts.operational_consistency import OperationalConsistencyResult


def inventory_record() -> TurkeyInventoryRecord:
    """Build one valid inventory record."""
    return TurkeyInventoryRecord(
        inventory_record_id="INV-001",
        platform_id="PLT-F16",
        country_code="TR",
        operator_name="Demo Operator",
        service_status="ACTIVE_SERVICE",
        active=True,
        source_type="DEMO_MOCK",
    )


def inventory_result(status: InventoryStatus) -> TurkeyInventoryResult:
    """Build one valid result for a controlled status."""
    confirmed = status is InventoryStatus.CONFIRMED
    return TurkeyInventoryResult(
        inventory_status=status,
        platform_id="PLT-F16",
        inventory_record_id="INV-001" if confirmed else None,
        country_code="TR" if confirmed else None,
        operator_name="Demo Operator" if confirmed else None,
        service_status="ACTIVE_SERVICE" if confirmed else None,
        dataset_id="TR-DEMO" if confirmed else None,
        dataset_version="1.0.0" if confirmed else None,
        source_type="DEMO_MOCK" if confirmed else None,
        reason_codes=[status.value],
        safe_message="Inventory scope lookup completed.",
        warnings=[],
    )


def test_valid_inventory_record_dataset_and_request() -> None:
    """Valid strict record, dataset, and request are accepted."""
    dataset = TurkeyInventoryDataset(
        schema_version="turkey-inventory/1.0",
        dataset_id="TR-DEMO",
        dataset_version="1.0.0",
        effective_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
        source_type="DEMO_MOCK",
        records=[inventory_record()],
    )
    request = TurkeyInventoryToolRequest(
        platform_id="PLT-F16",
        platform_execution_status=ToolExecutionStatus.SUCCESS,
        platform_status=PlatformStatus.EXPECTED,
    )
    assert dataset.records[0].platform_id == request.platform_id


def test_unknown_field_is_rejected() -> None:
    """Strict contracts reject undeclared input."""
    with pytest.raises(ValidationError):
        TurkeyInventoryRecord.model_validate(
            {**inventory_record().model_dump(), "threat": "HOSTILE"}
        )


def test_naive_effective_datetime_is_rejected() -> None:
    """Dataset effective time must be timezone-aware."""
    with pytest.raises(ValidationError):
        TurkeyInventoryDataset(
            schema_version="turkey-inventory/1.0",
            dataset_id="TR-DEMO",
            dataset_version="1.0.0",
            effective_at_utc=datetime(2026, 1, 1),
            source_type="DEMO_MOCK",
            records=[inventory_record()],
        )


@pytest.mark.parametrize("status", list(InventoryStatus))
def test_all_inventory_result_statuses(status: InventoryStatus) -> None:
    """Every controlled Inventory V1 domain status validates."""
    assert inventory_result(status).inventory_status is status


def test_valid_consistency_result() -> None:
    """A controlled consistency result validates."""
    result = OperationalConsistencyResult(
        status=OperationalConsistencyStatus.FLAGGED,
        flags=[OperationalConsistencyFlag.INVENTORY_NOT_LISTED],
        reason_codes=["INVENTORY_NOT_LISTED"],
        evidence_references=["turkey_inventory_result"],
        human_review_required=True,
    )
    assert result.status is OperationalConsistencyStatus.FLAGGED


def test_duplicate_consistency_flag_is_rejected() -> None:
    """Duplicate flags cannot create nondeterministic output."""
    flag = OperationalConsistencyFlag.CONTEXT_UNAVAILABLE
    with pytest.raises(ValidationError):
        OperationalConsistencyResult(
            status=OperationalConsistencyStatus.INDETERMINATE,
            flags=[flag, flag],
            reason_codes=["CONTEXT_UNAVAILABLE"],
            evidence_references=[],
            human_review_required=True,
        )


def test_rejected_out_of_scope_is_decision_only() -> None:
    """Out-of-scope is a decision code and never an event status."""
    assert DecisionCode("REJECTED_OUT_OF_SCOPE") is DecisionCode.REJECTED_OUT_OF_SCOPE
    assert "REJECTED_OUT_OF_SCOPE" not in {status.value for status in EventStatus}
