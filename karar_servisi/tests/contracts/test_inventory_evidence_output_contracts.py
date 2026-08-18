# ruff: noqa: D103

"""Inventory and consistency evidence/final-output 2.1 contract tests."""

import json

from operational_decision.contracts.common import (
    DecisionCode,
    EventStatus,
    InventoryStatus,
    OperationalConsistencyFlag,
    OperationalConsistencyStatus,
    RiskLevel,
)
from operational_decision.contracts.final_output import FinalDecisionOutput
from operational_decision.contracts.llm import (
    EvidenceConstraints,
    EvidenceEvent,
    LLMEvidencePackage,
)


def test_llm_evidence_21_contract_contains_deterministic_inventory() -> None:
    package = LLMEvidencePackage(
        inventory_status=InventoryStatus.CONFIRMED,
        inventory_record_id="INV_TR_F16_DEMO",
        inventory_country_code="TR",
        inventory_operator_name="Demo Operator",
        inventory_service_status="ACTIVE",
        inventory_dataset_id="TR_INVENTORY_DEMO",
        inventory_dataset_version="1.0.0",
        inventory_source_type="DEMO_MOCK",
        inventory_reason_codes=["INVENTORY_RECORD_MATCHED"],
        operational_consistency_status=OperationalConsistencyStatus.CONSISTENT,
        operational_consistency_flags=[OperationalConsistencyFlag.INVENTORY_SCOPE_CONFIRMED],
        event=EvidenceEvent(event_id="EV-1", track_id="TRK-1", observation_time_utc=None),
        visual_evidence=[],
        operational_context={},
        platform_result=[],
        permission_flight_plan_result=[],
        notam_result=[],
        verification_result=[],
        risk_result=[],
        constraints=EvidenceConstraints(
            minimum_risk_level="LOW",
            human_review_required=False,
            allowed_decision_codes=[DecisionCode.AUTHORIZED_OPERATIONAL_MATCH],
        ),
    )
    assert package.schema_version == "llm-evidence/2.1"
    assert package.inventory_dataset_version == "1.0.0"
    assert package.operational_consistency_flags == [
        OperationalConsistencyFlag.INVENTORY_SCOPE_CONFIRMED
    ]


def final_output() -> FinalDecisionOutput:
    return FinalDecisionOutput(
        event_id="EV-1",
        request_id="REQ-1",
        event_status=EventStatus.FINALIZED,
        inventory_status=InventoryStatus.NOT_LISTED,
        inventory_dataset_id="TR_INVENTORY_DEMO",
        inventory_dataset_version="1.0.0",
        inventory_source_type="DEMO_MOCK",
        inventory_reason_codes=["INVENTORY_RECORD_NOT_FOUND"],
        operational_consistency_status=OperationalConsistencyStatus.FLAGGED,
        operational_consistency_flags=[
            OperationalConsistencyFlag.INVENTORY_NOT_LISTED,
            OperationalConsistencyFlag.DOWNSTREAM_CHECKS_SKIPPED_INVENTORY_NOT_CONFIRMED,
        ],
        decision=DecisionCode.REJECTED_OUT_OF_SCOPE,
        risk_level=RiskLevel.UNKNOWN,
        minimum_risk_level=RiskLevel.UNKNOWN,
        summary_tr="Platform mevcut Türkiye envanter veri setinde bulunamadı.",
        operational_report_tr="Kontrollü operasyonel rapor.",
        human_approval_required=True,
    )


def test_final_output_21_contract() -> None:
    output = final_output()
    assert output.schema_version == "final-output/2.1"
    assert output.inventory_status is InventoryStatus.NOT_LISTED
    assert output.operational_consistency_status is OperationalConsistencyStatus.FLAGGED
    assert output.operational_report_tr == "Kontrollü operasyonel rapor."


def test_final_output_20_record_remains_readable() -> None:
    payload = final_output().model_dump(mode="json")
    payload["schema_version"] = "final-output/2.0"
    for field in (
        "inventory_record_id",
        "inventory_country_code",
        "inventory_operator_name",
        "inventory_service_status",
        "inventory_dataset_id",
        "inventory_dataset_version",
        "inventory_source_type",
        "inventory_reason_codes",
        "operational_consistency_status",
        "operational_consistency_flags",
        "operational_report_tr",
    ):
        payload.pop(field)
    restored = FinalDecisionOutput.model_validate_json(json.dumps(payload), strict=True)
    assert restored.schema_version == "final-output/2.0"
    assert restored.inventory_dataset_version is None
    assert restored.operational_consistency_status is None
