"""Phase 6 decision policy, guard, repair, fallback, and evidence tests."""
# ruff: noqa: D103

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest

from operational_decision.contracts.common import (
    ContextStatus,
    DecisionCode,
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
    ToolHealthStatus,
    UncertaintyLevel,
    VerificationStatus,
    VisualClass,
    VisualEvidenceStatus,
)
from operational_decision.contracts.context import ContextResolution
from operational_decision.contracts.final_output import ModelVersions
from operational_decision.contracts.inventory import TurkeyInventoryResult
from operational_decision.contracts.llm import EvidenceConstraints, LLMDecision, RecommendedAction
from operational_decision.contracts.notam import NotamResult
from operational_decision.contracts.operational_consistency import OperationalConsistencyResult
from operational_decision.contracts.permission import PermissionFlightPlanResult
from operational_decision.contracts.platform import PlatformResult, UsageDomain
from operational_decision.contracts.rag import RAGResult, RAGSource
from operational_decision.contracts.risk import RiskResult
from operational_decision.contracts.verification import (
    VerificationInput,
    VerificationReasonCode,
    VerificationResult,
)
from operational_decision.contracts.visual import FinalVisualEvidencePackage
from operational_decision.decision.decision_policy import (
    allowed_decision_codes,
    load_action_catalog,
)
from operational_decision.decision.evidence_builder import (
    EvidenceBudgetError,
    EvidencePackageBuilder,
)
from operational_decision.finalizer.output_finalizer import (
    FinalizationMetadata,
    OutputFinalizer,
    _deterministic_fallback_decision,
    _rag_summary,
)
from operational_decision.finalizer.output_guard import OutputGuard, normalize_guard_text
from operational_decision.finalizer.turkish_report import _rag_sentence
from operational_decision.llm.base_client import BaseLLMClient, LocalLLMError
from operational_decision.llm.prompt_builder import PromptBuilder
from operational_decision.llm.response_parser import (
    LLMResponseParseError,
    StructuredDecisionRunner,
    parse_llm_decision,
)

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2025, 1, 1, tzinfo=UTC)


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


def verification(
    status: VerificationStatus = VerificationStatus.UNVERIFIED,
    reasons: list[VerificationReasonCode] | None = None,
) -> VerificationResult:
    return VerificationResult(
        verification_status=status,
        reason_codes=reasons or [VerificationReasonCode.PERMISSION_NOT_FOUND],
        tool_health_status=ToolHealthStatus.HEALTHY,
        required_tools=["platform", "permission", "notam"],
        successful_required_tools=["platform", "permission", "notam"],
    )


def risk(level: RiskLevel = RiskLevel.HIGH) -> RiskResult:
    return RiskResult(
        risk_level=level,
        minimum_risk_level=level,
        human_review_required=level is not RiskLevel.LOW,
        matched_rule_ids=["RULE_TEST"],
        selected_rule_id="RULE_TEST",
        rule_specificity=1.0,
        evidence_quality_score=0.8,
        risk_assessment_confidence=0.8,
        decision_confidence=0.8,
    )


def constraints(
    decision: DecisionCode = DecisionCode.UNVERIFIED_AIRCRAFT,
) -> EvidenceConstraints:
    return EvidenceConstraints(
        minimum_risk_level="HIGH",
        human_review_required=True,
        allowed_decision_codes=[decision],
        allowed_action_codes=[
            "REQUEST_OPERATOR_REVIEW",
            "VERIFY_PLATFORM_MANUALLY",
            "CHECK_PERMISSION_RECORDS",
            "CHECK_FLIGHT_PLAN_RECORDS",
            "REVIEW_ACTIVE_NOTAM",
            "REQUEST_ADDITIONAL_VISUAL_EVIDENCE",
            "ESCALATE_TO_AUTHORIZED_UNIT",
        ],
        allowed_source_ids=["SRC-1"],
    )


@pytest.mark.parametrize("decision_code", list(DecisionCode))
def test_every_canonical_decision_code_survives_llm_fallback(
    decision_code: DecisionCode,
) -> None:
    candidate = _deterministic_fallback_decision(
        constraints(decision_code), ["LOCAL_LLM_UNAVAILABLE"]
    )
    assert candidate.decision_code is decision_code
    assert candidate.uncertainty_notes == ["LOCAL_LLM_UNAVAILABLE"]


def test_allowed_decision_precedence_invalid_permission_before_conflict() -> None:
    current = facts(
        platform_status=PlatformStatus.NOT_EXPECTED,
        permission_status=PermissionStatus.EXPIRED,
        record_consistency=RecordConsistency.CONFLICTING,
    )
    assert allowed_decision_codes(verification(), current) == [
        DecisionCode.EXPIRED_OR_INVALID_PERMISSION
    ]
    expired = current.model_copy(update={"record_consistency": RecordConsistency.PARTIAL})
    assert allowed_decision_codes(verification(), expired) == [
        DecisionCode.EXPIRED_OR_INVALID_PERMISSION
    ]


def test_guard_corrects_permission_claim_sources_actions_and_minimums() -> None:
    catalog = load_action_catalog(ROOT / "data/rules/action_catalog.yaml")
    current = facts(permission_status=PermissionStatus.NOT_FOUND)
    result = OutputGuard().guard(
        LLMDecision(
            decision_code=DecisionCode.AUTHORIZED_OPERATIONAL_MATCH,
            summary_tr="Bu uçuş için izin var.",
            recommended_actions=[
                RecommendedAction(action_code="FAKE_ACTION", priority=1, reason_tr="uydurma")
            ],
            source_ids=["SRC-1", "SRC-NOT-REAL"],
        ),
        constraints=constraints(),
        facts=current,
        verification=verification(),
        risk=risk(),
        action_catalog=catalog,
    )
    assert result.decision.decision_code is DecisionCode.UNVERIFIED_AIRCRAFT
    assert "doğrulanamamıştır" in result.decision.summary_tr
    assert result.decision.source_ids == ["SRC-1"]
    codes = [item.action_code for item in result.decision.recommended_actions]
    assert codes[:2] == ["REQUEST_OPERATOR_REVIEW", "CHECK_PERMISSION_RECORDS"]
    assert "FAKE_ACTION" not in codes
    assert {item.reason for item in result.corrections} >= {
        "DECISION_NOT_ALLOWED",
        "UNKNOWN_SOURCE_ID_REMOVED",
        "TOOL_CONTRADICTION_OR_VISUAL_OVERCLAIM",
    }


def test_guard_removes_untraceable_absolute_regulatory_evidence_claims() -> None:
    catalog = load_action_catalog(ROOT / "data/rules/action_catalog.yaml")
    result = OutputGuard().guard(
        LLMDecision(
            decision_code=DecisionCode.UNVERIFIED_AIRCRAFT,
            summary_tr="İnsan incelemesi gereklidir.",
            evidence_summary=[
                "Tescil ve uçuş amacı bilgisi mutlak olarak gereklidir.",
                "Askeri uçuşlarda uçuş izni zorunludur.",
                "Uçuş planı kaydı tek başına izin sağlamaz.",
            ],
        ),
        constraints=constraints(),
        facts=facts(),
        verification=verification(),
        risk=risk(),
        action_catalog=catalog,
    )

    assert result.decision.evidence_summary == ["Uçuş planı kaydı tek başına izin sağlamaz."]
    assert any(
        correction.reason == "UNSUPPORTED_OR_CONTRADICTORY_EVIDENCE_REMOVED"
        for correction in result.corrections
    )


def test_guard_removes_non_aircraft_action_for_aircraft_class() -> None:
    catalog = load_action_catalog(ROOT / "data/rules/action_catalog.yaml")
    allowed = EvidenceConstraints(
        minimum_risk_level="LOW",
        human_review_required=False,
        allowed_decision_codes=[DecisionCode.AUTHORIZED_OPERATIONAL_MATCH],
        allowed_action_codes=["MARK_AS_NON_AIRCRAFT", "CONTINUE_TRACKING"],
    )
    result = OutputGuard().guard(
        LLMDecision(
            decision_code=DecisionCode.AUTHORIZED_OPERATIONAL_MATCH,
            summary_tr="Operasyonel kayıtlar doğrulandı.",
            recommended_actions=[
                RecommendedAction(
                    action_code="MARK_AS_NON_AIRCRAFT",
                    priority=1,
                    reason_tr="Hedefi hava aracı olmayan unsur olarak işaretle.",
                ),
                RecommendedAction(
                    action_code="CONTINUE_TRACKING",
                    priority=2,
                    reason_tr="Takibi sürdür.",
                ),
            ],
        ),
        constraints=allowed,
        facts=facts(visual_class=VisualClass.UCAV),
        verification=verification(VerificationStatus.VERIFIED, []),
        risk=risk(RiskLevel.LOW),
        action_catalog=catalog,
    )
    assert [item.action_code for item in result.decision.recommended_actions] == [
        "CONTINUE_TRACKING"
    ]


def test_guard_unresolved_platform_keeps_only_safe_deterministic_actions() -> None:
    catalog = load_action_catalog(ROOT / "data/rules/action_catalog.yaml")
    current = facts(
        platform_status=PlatformStatus.UNKNOWN,
        permission_status=PermissionStatus.NOT_APPLICABLE,
        flight_plan_status=FlightPlanStatus.NOT_APPLICABLE,
        notam_operation_effect=NotamOperationEffect.UNKNOWN,
        permission_execution_status=ToolExecutionStatus.SKIPPED,
        notam_execution_status=ToolExecutionStatus.SKIPPED,
    )
    result = OutputGuard().guard(
        LLMDecision(
            decision_code=DecisionCode.PLATFORM_UNRESOLVED,
            summary_tr="Bu hedef doğrulanmış F-16'dır.",
            recommended_actions=[
                RecommendedAction(
                    action_code="CHECK_PERMISSION_RECORDS",
                    priority=1,
                    reason_tr="Permission NOT_APPLICABLE",
                ),
                RecommendedAction(
                    action_code="REVIEW_ACTIVE_NOTAM",
                    priority=2,
                    reason_tr="NOTAM NONE_ACTIVE",
                ),
                RecommendedAction(
                    action_code="VERIFY_PLATFORM_MANUALLY",
                    priority=3,
                    reason_tr="Permission ve NOTAM sonucu belirle",
                ),
                RecommendedAction(
                    action_code="VERIFY_PLATFORM_MANUALLY",
                    priority=4,
                    reason_tr="Tekrar eden öneri",
                ),
            ],
        ),
        constraints=constraints(DecisionCode.PLATFORM_UNRESOLVED),
        facts=current,
        verification=verification(
            VerificationStatus.INDETERMINATE,
            [VerificationReasonCode.PLATFORM_UNKNOWN],
        ),
        risk=risk(RiskLevel.UNKNOWN),
        action_catalog=catalog,
    )
    assert "yalnız hipotezdir" in result.decision.summary_tr
    assert [item.action_code for item in result.decision.recommended_actions] == [
        "VERIFY_PLATFORM_MANUALLY",
        "REQUEST_ADDITIONAL_VISUAL_EVIDENCE",
        "REQUEST_OPERATOR_REVIEW",
    ]
    reasons = [item.reason_tr for item in result.decision.recommended_actions]
    assert reasons == [
        "Platform kimliğini manuel doğrula",
        "Daha kaliteli veya farklı açılardan görsel kanıt sağla",
        "Operasyonel karar için insan incelemesi yap",
    ]
    assert all("NOT_APPLICABLE" not in reason and "NONE_ACTIVE" not in reason for reason in reasons)


class _StubClient(BaseLLMClient):
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = outputs
        self.messages: list[Sequence[dict[str, str]]] = []

    async def generate(self, messages: Sequence[dict[str, str]]) -> str:
        self.messages.append(messages)
        return self.outputs.pop(0)

    async def unload(self) -> None:
        return None


class _FixedCounter:
    def __init__(self, count: int) -> None:
        self._count = count

    def encode(self, text: str) -> list[int]:
        return list(range(self._count))


def evidence(  # type: ignore[no-untyped-def]
    counter: _FixedCounter | None = None,
    rag: RAGResult | None = None,
    overrides: dict | None = None,
):
    kwargs = {
        "event_id": "event-1",
        "track_id": "track-1",
        "observation_time_utc": NOW,
        "visual_evidence": {
            "visual_class": "FIGHTER_JET",
            "upstream_vlm_output": {"raw": "excluded"},
            "crop_evidence_summary": {"refs": ["excluded"]},
        },
        "operational_context": {
            "context_status": "COMPLETE",
            "record": {"context_id": "CTX-1", "environment": "DEMO", "description": "raw"},
        },
        "platform_result": {
            "platform_status": "EXPECTED",
            "platform_origin": "FOREIGN_ORIGIN",
            "manufacturer_country_code": "US",
            "identity_scope": "MODEL_FAMILY",
            "variant_policy": "EXPLICIT_CHILD_RECORDS",
        },
        "inventory_result": TurkeyInventoryResult(
            inventory_status=InventoryStatus.CONFIRMED,
            platform_id="PLT_F16",
            inventory_record_id="INV_TR_F16_DEMO",
            country_code="TR",
            operator_name="Demo Operator",
            service_status="ACTIVE",
            dataset_id="TR_INVENTORY_DEMO",
            dataset_version="1.0.0",
            source_type="DEMO_MOCK",
            reason_codes=["INVENTORY_RECORD_MATCHED"],
            safe_message="Inventory kaydı doğrulandı.",
            warnings=[],
        ),
        "permission_flight_plan_result": {
            "permission_status": "VALID",
            "permission_records": [{"permission_id": "raw"}],
        },
        "operational_consistency": OperationalConsistencyResult(
            status=OperationalConsistencyStatus.CONSISTENT,
            flags=[OperationalConsistencyFlag.INVENTORY_SCOPE_CONFIRMED],
            reason_codes=["INVENTORY_SCOPE_CONFIRMED"],
            evidence_references=["inventory.inventory_status"],
            human_review_required=False,
        ),
        "notam_result": {
            "notam_status": "NONE_ACTIVE",
            "active_notams": [{"notam_id": "N-1", "source_reference": "SRC-N"}],
        },
        "verification": verification(VerificationStatus.VERIFIED, []),
        "facts": facts(),
        "risk": risk(RiskLevel.LOW),
        "rag": rag or RAGResult(called=False),
        "action_catalog": load_action_catalog(ROOT / "data/rules/action_catalog.yaml"),
    }
    kwargs.update(overrides or {})
    return EvidencePackageBuilder(counter or _FixedCounter(100)).build(**kwargs)


@pytest.mark.asyncio
async def test_one_malformed_json_is_repaired_with_same_evidence() -> None:
    valid = LLMDecision(
        decision_code=DecisionCode.AUTHORIZED_OPERATIONAL_MATCH,
        summary_tr="Kayıtlar uyumludur.",
    ).model_dump_json()
    client = _StubClient(["not-json", valid])
    result = await StructuredDecisionRunner(client).run(evidence())
    assert result.repair_attempted is True
    assert result.fallback_required is False
    assert result.decision is not None
    assert len(client.messages) == 2
    assert client.messages[0][1]["content"] == client.messages[1][1]["content"]


@pytest.mark.asyncio
async def test_second_malformed_json_requires_safe_fallback() -> None:
    result = await StructuredDecisionRunner(_StubClient(["bad", "still bad"])).run(evidence())
    assert result.repair_attempted is True
    assert result.fallback_required is True
    assert result.decision is None


def test_evidence_carries_rag_as_explanation_only_with_real_source_allowlist() -> None:
    source = RAGSource(
        source_id="LT_GEN_1_2_P1_C1",
        chunk_id="LT_GEN_1_2_P1_C1",
        document_id="LT_GEN_1_2",
        filename="LT_GEN_1_2_en.pdf",
        page_start=1,
        page_end=1,
        section_title="Entry, transit and departure of aircraft",
        content="All flights using Turkish airspace follow applicable procedures.",
        source_priority=100,
        authoritative=True,
        similarity=0.91,
    )
    package = evidence(
        rag=RAGResult(
            called=True,
            query_template_id="UNREGISTERED_MILITARY_AIRSPACE_CONTEXT",
            sources=[source],
        )
    )

    assert package.rag_called is True
    assert package.rag_role == "EXPLANATION_ONLY"
    assert package.rag_decision_effect == "NONE"
    assert package.rag_context == [source]
    assert package.constraints.allowed_source_ids == ["LT_GEN_1_2_P1_C1"]

    summary = _rag_summary(
        RAGResult(called=True, sources=[source]),
        unregistered_military_policy=True,
    )
    assert "envanter dışı askerî hava araçlarının" in summary
    assert "mevcut risk ve kararı değiştirmemektedir" in summary
    report_sentence = _rag_sentence(
        {
            "decision": "UNREGISTERED_MILITARY_AIRCRAFT",
            "rag_sources": [source.model_dump(mode="json")],
        }
    )
    assert "özel izin ve koordinasyon" in report_sentence
    assert "risk ve kararı değiştirmemektedir" in report_sentence


def test_unregistered_military_empty_rag_has_no_invented_source() -> None:
    result = RAGResult(
        called=True,
        query_template_id="UNREGISTERED_MILITARY_AIRSPACE_CONTEXT",
    )
    package = evidence(rag=result)
    assert package.rag_called is True
    assert package.rag_context == []
    assert package.constraints.allowed_source_ids == []
    assert "ilgili mevzuat kaynağı getirilememiştir" in _rag_summary(
        result,
        unregistered_military_policy=True,
    )


def test_evidence_budget_uses_canonical_counter() -> None:
    with pytest.raises(EvidenceBudgetError):
        evidence(_FixedCounter(5001))


def test_finalizer_exposes_real_rag_sources_as_explanation_only() -> None:
    current = facts()
    verified = verification(VerificationStatus.VERIFIED, [])
    allowed = constraints(DecisionCode.AUTHORIZED_OPERATIONAL_MATCH).model_copy(
        update={"minimum_risk_level": "LOW", "human_review_required": False}
    )
    source = RAGSource(
        source_id="SRC-1",
        chunk_id="CHUNK-1",
        document_id="DOC-1",
        filename="mevzuat.pdf",
        page_start=3,
        page_end=3,
        content="Doğrulanmış örnek mevzuat içeriği.",
        source_priority=1,
        authoritative=True,
        similarity=0.91,
    )
    final = OutputFinalizer().finalize(
        metadata=FinalizationMetadata(event_id="event-rag", request_id="request-rag"),
        visual=FinalVisualEvidencePackage.model_construct(
            track_id="track-rag",
            visual_class=VisualClass.FIGHTER_JET,
            final_visual_hypothesis="F-16",
            visual_evidence_status=VisualEvidenceStatus.SUPPORTED,
            visual_confidence=0.9,
            uncertainty_level=UncertaintyLevel.LOW,
            uncertainty_flags=[],
            human_visual_review_required=False,
        ),
        context=ContextResolution(context_status=ContextStatus.COMPLETE),
        platform=PlatformResult(platform_status=PlatformStatus.EXPECTED),
        permission=PermissionFlightPlanResult(
            permission_status=PermissionStatus.VALID,
            flight_plan_status=FlightPlanStatus.FILED,
            record_consistency=RecordConsistency.CONSISTENT,
        ),
        notam=NotamResult(
            notam_status=NotamStatus.NONE_ACTIVE,
            operation_effect=NotamOperationEffect.NO_EFFECT,
        ),
        facts=current,
        verification=verified,
        risk=risk(RiskLevel.LOW),
        rag=RAGResult(called=True, query_template_id="QUERY-1", sources=[source]),
        constraints=allowed,
        action_catalog=load_action_catalog(ROOT / "data/rules/action_catalog.yaml"),
        tool_execution_summary={},
        model_versions=ModelVersions(decision_llm="stub"),
        llm_decision=LLMDecision(
            decision_code=DecisionCode.AUTHORIZED_OPERATIONAL_MATCH,
            summary_tr="Operasyonel kayıtlar doğrulandı.",
            source_ids=["SRC-1"],
        ),
    )

    assert [item.source_id for item in final.rag_sources] == ["SRC-1"]
    assert [item.source_id for item in final.sources] == ["SRC-1"]
    assert "1 doğrulanabilir kaynak" in final.rag_summary
    assert "yalnız mevzuat açıklaması" in final.rag_decision_effect
    assert "risk seviyesi veya izin durumunu değiştirmedi" in final.rag_decision_effect
    assert final.turkish_report is None
    assert final.operational_report_tr is not None
    assert "Text RAG 1 doğrulanabilir kaynak döndürdü" in final.operational_report_tr
    assert final.rag_decision_effect not in final.operational_report_tr


def test_finalizer_fallback_keeps_critical_risk_and_review() -> None:
    current = facts(
        notam_status=NotamStatus.ACTIVE_RELEVANT,
        notam_operation_effect=NotamOperationEffect.PROHIBITS_OPERATION,
    )
    verify = verification(reasons=[VerificationReasonCode.NOTAM_PROHIBITS_OPERATION])
    final = OutputFinalizer().finalize(
        metadata=FinalizationMetadata(
            event_id="event-1",
            request_id="request-1",
            video_id="video-1",
            observation_time_utc=NOW,
            observation_end_time_utc=NOW,
        ),
        visual=FinalVisualEvidencePackage.model_construct(
            track_id="track-1",
            visual_class=VisualClass.FIGHTER_JET,
            final_visual_hypothesis="F-16",
            visual_evidence_status=VisualEvidenceStatus.SUPPORTED,
            visual_confidence=0.9,
            uncertainty_level=UncertaintyLevel.LOW,
            uncertainty_flags=[],
        ),
        context=ContextResolution(context_status=ContextStatus.MISSING),
        platform=PlatformResult(platform_status=PlatformStatus.EXPECTED),
        permission=PermissionFlightPlanResult(
            permission_status=PermissionStatus.VALID,
            flight_plan_status=FlightPlanStatus.FILED,
            record_consistency=RecordConsistency.CONSISTENT,
        ),
        notam=NotamResult(
            notam_status=NotamStatus.ACTIVE_RELEVANT,
            operation_effect=NotamOperationEffect.PROHIBITS_OPERATION,
        ),
        facts=current,
        verification=verify,
        risk=risk(RiskLevel.CRITICAL),
        rag=RAGResult(called=False),
        constraints=constraints(DecisionCode.ACTIVE_NOTAM_PROHIBITION),
        action_catalog=load_action_catalog(ROOT / "data/rules/action_catalog.yaml"),
        tool_execution_summary={},
        model_versions=ModelVersions(decision_llm="stub"),
        llm_decision=None,
        failure_notes=["SECOND_INVALID_OUTPUT"],
    )
    assert final.decision is DecisionCode.ACTIVE_NOTAM_PROHIBITION
    assert final.risk_level is RiskLevel.CRITICAL
    assert final.minimum_risk_level is RiskLevel.CRITICAL
    assert final.human_approval_required is True
    assert "ESCALATE_TO_AUTHORIZED_UNIT" in {item.action_code for item in final.recommended_actions}
    assert final.operational_report_tr is not None
    assert "operasyonu açıkça yasaklamaktadır" in final.operational_report_tr
    assert "İnsan incelemesi zorunludur" in final.operational_report_tr


def test_finalizer_fallback_keeps_notam_permission_conflict_and_review() -> None:
    current = facts(
        notam_status=NotamStatus.CONFLICTING,
        notam_operation_effect=NotamOperationEffect.CONFLICTS_WITH_PERMISSION,
    )
    verify = verification(
        reasons=[
            VerificationReasonCode.NOTAM_CONFLICTING,
            VerificationReasonCode.NOTAM_CONFLICTS_WITH_PERMISSION,
        ]
    )
    final = OutputFinalizer().finalize(
        metadata=FinalizationMetadata(
            event_id="event-notam-conflict-fallback",
            request_id="request-notam-conflict-fallback",
            video_id="video-notam-conflict-fallback",
            observation_time_utc=NOW,
            observation_end_time_utc=NOW,
        ),
        visual=FinalVisualEvidencePackage.model_construct(
            track_id="track-notam-conflict-fallback",
            visual_class=VisualClass.UAV,
            final_visual_hypothesis="Operational UAV hypothesis",
            visual_evidence_status=VisualEvidenceStatus.SUPPORTED,
            visual_confidence=0.9,
            uncertainty_level=UncertaintyLevel.LOW,
            uncertainty_flags=[],
        ),
        context=ContextResolution(context_status=ContextStatus.MISSING),
        platform=PlatformResult(platform_status=PlatformStatus.EXPECTED),
        permission=PermissionFlightPlanResult(
            permission_status=PermissionStatus.VALID,
            flight_plan_status=FlightPlanStatus.FILED,
            record_consistency=RecordConsistency.CONSISTENT,
        ),
        notam=NotamResult(
            notam_status=NotamStatus.CONFLICTING,
            operation_effect=NotamOperationEffect.CONFLICTS_WITH_PERMISSION,
            conflict_with_permission=True,
        ),
        facts=current,
        verification=verify,
        risk=risk(RiskLevel.HIGH),
        rag=RAGResult(called=False),
        constraints=constraints(DecisionCode.CONFLICTING_OPERATIONAL_RECORDS),
        action_catalog=load_action_catalog(ROOT / "data/rules/action_catalog.yaml"),
        tool_execution_summary={},
        model_versions=ModelVersions(decision_llm="stub"),
        llm_decision=None,
        failure_notes=["SECOND_INVALID_OUTPUT"],
        inventory=inventory_result(InventoryStatus.CONFIRMED),
        consistency=consistency_result(
            OperationalConsistencyFlag.NOTAM_CONFLICTS_WITH_PERMISSION
        ),
    )
    assert final.decision is DecisionCode.CONFLICTING_OPERATIONAL_RECORDS
    assert final.risk_level is RiskLevel.HIGH
    assert final.minimum_risk_level is RiskLevel.HIGH
    assert final.notam_status is NotamStatus.CONFLICTING
    assert final.notam_operation_effect is NotamOperationEffect.CONFLICTS_WITH_PERMISSION
    assert final.notam_conflict_with_permission is True
    assert final.human_approval_required is True
    assert {item.action_code for item in final.recommended_actions}.issuperset(
        {"REQUEST_OPERATOR_REVIEW", "REVIEW_ACTIVE_NOTAM"}
    )
    assert final.operational_report_tr is not None
    assert "permission kayd\u0131yla \u00e7eli\u015fmektedir" in final.operational_report_tr
    assert "g\u00fcvenli fallback uyguland\u0131" in " ".join(final.human_review_reasons)


class _FailClient(BaseLLMClient):
    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, messages: Sequence[dict[str, str]]) -> str:
        self.calls += 1
        raise LocalLLMError("network unavailable")

    async def unload(self) -> None:
        return None


@pytest.mark.asyncio
async def test_network_failure_has_no_automatic_retry() -> None:
    client = _FailClient()
    result = await StructuredDecisionRunner(client).run(evidence())
    assert result.fallback_required is True
    assert result.repair_attempted is False
    assert client.calls == 1


def test_llm_cannot_emit_or_lower_deterministic_risk() -> None:
    raw = '{"decision_code":"UNVERIFIED_AIRCRAFT","summary_tr":"inceleme","risk_level":"LOW"}'
    with pytest.raises(LLMResponseParseError):
        parse_llm_decision(raw)


@pytest.mark.parametrize("level", [RiskLevel.MEDIUM, RiskLevel.UNKNOWN])
def test_medium_and_unknown_require_operator_review(level: RiskLevel) -> None:
    catalog = load_action_catalog(ROOT / "data/rules/action_catalog.yaml")
    result = OutputGuard().guard(
        LLMDecision(
            decision_code=DecisionCode.UNVERIFIED_AIRCRAFT,
            summary_tr="Operasyon kaydı inceleme gerektirir.",
        ),
        constraints=constraints(),
        facts=facts(permission_status=PermissionStatus.NOT_FOUND),
        verification=verification(),
        risk=risk(level),
        action_catalog=catalog,
    )
    assert result.decision.recommended_actions[0].action_code == "REQUEST_OPERATOR_REVIEW"


def test_evidence_excludes_raw_rows_crops_and_vlm_payload() -> None:
    package = evidence()
    assert package.schema_version == "llm-evidence/2.1"
    assert package.inventory_status is InventoryStatus.CONFIRMED
    assert package.inventory_record_id == "INV_TR_F16_DEMO"
    assert package.inventory_dataset_version == "1.0.0"
    assert package.operational_consistency_flags == [
        OperationalConsistencyFlag.INVENTORY_SCOPE_CONFIRMED
    ]
    assert "records" not in package.model_dump(mode="json")
    visual_joined = " ".join(package.visual_evidence)
    assert "upstream_vlm_output" not in visual_joined
    assert "crop_evidence_summary" not in visual_joined
    assert package.permission_flight_plan_result == ["İzin: geçerli."]
    platform_joined = " ".join(package.platform_result)
    assert "platform_origin" not in platform_joined
    assert "manufacturer_country_code" not in platform_joined
    assert "identity_scope" not in platform_joined
    assert "variant_policy" not in platform_joined
    assert "Üretici ülke bilgisi operatör kimliğini belirlemez." in platform_joined
    assert "record" not in package.operational_context
    assert package.operational_context["context_id"] == "CTX-1"
    assert package.notam_result == ["Aktif NOTAM yok."]


def test_notam_rendering_uses_tool_reason_text_without_leaking_source_refs() -> None:
    package = evidence(
        overrides={
            "notam_result": {
                "notam_status": "ACTIVE_RELEVANT",
                "operation_effect": "RESTRICTS_OPERATION",
                "primary_notam_number": "A1234/26",
                "active_notams": [
                    {
                        "notam_id": "DEMO_NOTAM_SCN_23",
                        "source_reference": "RAW_SOURCE_SHOULD_NOT_LEAK",
                        "operational_reason_tr": "Operasyonun ilgili bölümünü kısıtlamaktadır.",
                    }
                ],
            }
        }
    )
    joined = " ".join(package.notam_result)
    assert "A1234/26" in joined
    assert "Operasyonun ilgili bölümünü kısıtlamaktadır." in joined
    assert "RAW_SOURCE_SHOULD_NOT_LEAK" not in joined


def test_permission_flight_plan_rendering_includes_record_dates() -> None:
    package = evidence(
        overrides={
            "permission_flight_plan_result": {
                "permission_status": "NOT_FOUND",
                "flight_plan_status": "FILED",
                "record_consistency": "PARTIAL",
                "flight_plan_records": [
                    {
                        "flight_plan_id": "PLAN-1",
                        "planned_departure_utc": "2026-08-11T01:10:00Z",
                        "planned_arrival_utc": "2026-08-11T01:50:00Z",
                        "route_or_area": "AREA_007",
                    }
                ],
            }
        }
    )
    joined = " ".join(package.permission_flight_plan_result)
    assert "İzin: bulunamadı." in joined
    assert "2026-08-11T01:10:00Z" in joined
    assert "AREA_007" in joined
    assert "Kayıt tutarlılığı: kısmi." in joined


def inventory_result(
    status: InventoryStatus = InventoryStatus.CONFIRMED,
) -> TurkeyInventoryResult:
    return TurkeyInventoryResult(
        inventory_status=status,
        platform_id="PLT_F16",
        inventory_record_id=("INV_TR_F16_DEMO" if status is InventoryStatus.CONFIRMED else None),
        country_code=("TR" if status is InventoryStatus.CONFIRMED else None),
        operator_name=("Demo Operator" if status is InventoryStatus.CONFIRMED else None),
        service_status=("ACTIVE" if status is InventoryStatus.CONFIRMED else None),
        dataset_id="TR_INVENTORY_DEMO",
        dataset_version="1.0.0",
        source_type="DEMO_MOCK",
        reason_codes=[status.value],
        safe_message="Platform mevcut T\u00fcrkiye envanter veri setinde bulunamad\u0131.",
        warnings=[],
    )


def consistency_result(
    *flags: OperationalConsistencyFlag,
) -> OperationalConsistencyResult:
    selected = list(flags) or [OperationalConsistencyFlag.INVENTORY_SCOPE_CONFIRMED]
    status = (
        OperationalConsistencyStatus.FLAGGED if flags else OperationalConsistencyStatus.CONSISTENT
    )
    return OperationalConsistencyResult(
        status=status,
        flags=selected,
        reason_codes=[flag.value for flag in selected],
        evidence_references=["test" for _ in selected],
        human_review_required=bool(flags),
    )


def test_guard_preserves_allowed_not_listed_operational_result() -> None:
    catalog = load_action_catalog(ROOT / "data/rules/action_catalog.yaml")
    current = facts(inventory_status=InventoryStatus.NOT_LISTED)
    inventory = inventory_result(InventoryStatus.NOT_LISTED)
    consistency = OperationalConsistencyResult(
        status=OperationalConsistencyStatus.CONSISTENT,
        flags=[OperationalConsistencyFlag.INVENTORY_NOT_LISTED],
        reason_codes=[OperationalConsistencyFlag.INVENTORY_NOT_LISTED.value],
        evidence_references=["inventory.inventory_status"],
        human_review_required=False,
    )
    summary = (
        "Platform envanter veri setinde kayıtlı değildir. Geçerli izin ve uçuş planı "
        "bulunmuş, aktif NOTAM kısıtı tespit edilmemiştir."
    )
    result = OutputGuard().guard(
        LLMDecision(
            decision_code=DecisionCode.AUTHORIZED_OPERATIONAL_MATCH,
            summary_tr=summary,
        ),
        constraints=constraints(DecisionCode.AUTHORIZED_OPERATIONAL_MATCH),
        facts=current,
        verification=verification(VerificationStatus.VERIFIED, []),
        risk=risk(RiskLevel.LOW),
        action_catalog=catalog,
        inventory=inventory,
        consistency=consistency,
    )
    assert result.decision.decision_code is DecisionCode.AUTHORIZED_OPERATIONAL_MATCH
    assert result.decision.summary_tr == summary
    assert "NOT_LISTED_DETERMINISTIC_MESSAGE_ENFORCED" not in {
        correction.reason for correction in result.corrections
    }


def test_guard_preserves_unverified_not_listed_result_and_blocks_hostility() -> None:
    catalog = load_action_catalog(ROOT / "data/rules/action_catalog.yaml")
    current = facts(
        inventory_status=InventoryStatus.NOT_LISTED,
        permission_status=PermissionStatus.NOT_FOUND,
        flight_plan_status=FlightPlanStatus.NOT_FOUND,
    )
    safe = OutputGuard().guard(
        LLMDecision(
            decision_code=DecisionCode.UNVERIFIED_AIRCRAFT,
            summary_tr="İzin ve uçuş planı kaydı bulunamadı; insan incelemesi gerekir.",
        ),
        constraints=constraints(DecisionCode.UNVERIFIED_AIRCRAFT),
        facts=current,
        verification=verification(VerificationStatus.UNVERIFIED),
        risk=risk(RiskLevel.MEDIUM),
        action_catalog=catalog,
        inventory=inventory_result(InventoryStatus.NOT_LISTED),
    )
    assert safe.decision.decision_code is DecisionCode.UNVERIFIED_AIRCRAFT
    assert "İzin ve uçuş planı kaydı bulunamadı" in safe.decision.summary_tr

    hostile = OutputGuard().guard(
        LLMDecision(
            decision_code=DecisionCode.UNVERIFIED_AIRCRAFT,
            summary_tr="Bu yabancı ve düşman platform kesinlikle izinsizdir.",
        ),
        constraints=constraints(DecisionCode.UNVERIFIED_AIRCRAFT),
        facts=current,
        verification=verification(VerificationStatus.UNVERIFIED),
        risk=risk(RiskLevel.MEDIUM),
        action_catalog=catalog,
        inventory=inventory_result(InventoryStatus.NOT_LISTED),
    )
    assert "yabancı" not in hostile.decision.summary_tr.casefold()
    assert "düşman" not in hostile.decision.summary_tr.casefold()


def test_unregistered_military_guard_keeps_only_context_appropriate_actions() -> None:
    catalog = load_action_catalog(ROOT / "data/rules/action_catalog.yaml")
    current = facts(
        platform_usage_domain=UsageDomain.MILITARY,
        inventory_status=InventoryStatus.NOT_LISTED,
        inventory_execution_status=ToolExecutionStatus.SUCCESS,
        permission_status=PermissionStatus.NOT_APPLICABLE,
        flight_plan_status=FlightPlanStatus.NOT_APPLICABLE,
        record_consistency=RecordConsistency.NOT_APPLICABLE,
        notam_operation_effect=NotamOperationEffect.UNKNOWN,
        permission_execution_status=ToolExecutionStatus.SKIPPED,
        notam_execution_status=ToolExecutionStatus.SKIPPED,
        visual_evidence_status=VisualEvidenceStatus.INSUFFICIENT,
    )
    result = OutputGuard().guard(
        LLMDecision(
            decision_code=DecisionCode.UNREGISTERED_MILITARY_AIRCRAFT,
            summary_tr="Envanter dışı askerî platform için doğrulama gereklidir.",
            recommended_actions=[
                RecommendedAction(
                    action_code="REQUEST_ADDITIONAL_VISUAL_EVIDENCE",
                    priority=1,
                    reason_tr="Daha kaliteli görsel sağla",
                ),
                RecommendedAction(
                    action_code="CONTINUE_TRACKING",
                    priority=2,
                    reason_tr="Takibi sürdür",
                ),
            ],
        ),
        constraints=constraints(
            DecisionCode.UNREGISTERED_MILITARY_AIRCRAFT
        ).model_copy(
            update={
                "allowed_action_codes": [
                    *constraints(
                        DecisionCode.UNREGISTERED_MILITARY_AIRCRAFT
                    ).allowed_action_codes,
                    "CONTINUE_TRACKING",
                ]
            }
        ),
        facts=current,
        verification=verification(VerificationStatus.UNVERIFIED),
        risk=risk(RiskLevel.HIGH),
        action_catalog=catalog,
        inventory=inventory_result(InventoryStatus.NOT_LISTED),
    )

    actions = result.decision.recommended_actions
    codes = {item.action_code for item in actions}
    assert "REQUEST_ADDITIONAL_VISUAL_EVIDENCE" not in codes
    assert {
        "CONTINUE_TRACKING",
        "ESCALATE_TO_AUTHORIZED_UNIT",
        "REQUEST_OPERATOR_REVIEW",
    } == codes
    assert next(
        item.reason_tr
        for item in actions
        if item.action_code == "ESCALATE_TO_AUTHORIZED_UNIT"
    ) == (
        "Türkiye envanter durumunu ve operasyonel yetkilendirmeyi "
        "yetkili birimden doğrula"
    )

def test_prompt_encodes_notam_effect_and_legal_safety_boundaries() -> None:
    system_prompt = PromptBuilder().build(evidence())[0]["content"]
    assert "INFORMATIONAL yalnız bilgilendirir" in system_prompt
    assert "PROHIBITS_OPERATION yasaklı operasyonla ciddi uyumsuzluk" in system_prompt
    assert "Permission veya Flight Plan statüsünü değiştirmez" in system_prompt
    assert "düşmanlık, kanunsuz uçuş veya kesin hukuki ihlal" in system_prompt


def test_guard_blocks_hostile_and_legal_overclaim_for_prohibiting_notam() -> None:
    catalog = load_action_catalog(ROOT / "data/rules/action_catalog.yaml")
    current = facts(
        notam_status=NotamStatus.ACTIVE_RELEVANT,
        notam_operation_effect=NotamOperationEffect.PROHIBITS_OPERATION,
    )
    result = OutputGuard().guard(
        LLMDecision(
            decision_code=DecisionCode.ACTIVE_NOTAM_PROHIBITION,
            summary_tr="Bu kesinlikle düşman hava aracıdır ve uçuş kesin olarak kanunsuzdur.",
        ),
        constraints=constraints(DecisionCode.ACTIVE_NOTAM_PROHIBITION),
        facts=current,
        verification=verification(
            VerificationStatus.UNVERIFIED,
            [VerificationReasonCode.NOTAM_PROHIBITS_OPERATION],
        ),
        risk=risk(RiskLevel.CRITICAL),
        action_catalog=catalog,
        inventory=inventory_result(InventoryStatus.CONFIRMED),
    )
    normalized = normalize_guard_text(result.decision.summary_tr)
    assert "dusman" not in normalized
    assert "kanunsuz" not in normalized
    assert "ciddi operasyonel uyumsuzluk" in normalized


def test_guard_blocks_skipped_tool_results_and_inventory_permission_conflation() -> None:
    catalog = load_action_catalog(ROOT / "data/rules/action_catalog.yaml")
    skipped = facts(
        permission_status=PermissionStatus.NOT_APPLICABLE,
        flight_plan_status=FlightPlanStatus.NOT_APPLICABLE,
        permission_execution_status=ToolExecutionStatus.SKIPPED,
        notam_execution_status=ToolExecutionStatus.SKIPPED,
    )
    skipped_result = OutputGuard().guard(
        LLMDecision(
            decision_code=DecisionCode.INDETERMINATE,
            summary_tr="Ge\u00e7erli izin var, u\u00e7u\u015f plan\u0131 var ve aktif NOTAM yok.",
        ),
        constraints=constraints(DecisionCode.INDETERMINATE),
        facts=skipped,
        verification=verification(VerificationStatus.INDETERMINATE),
        risk=risk(RiskLevel.UNKNOWN),
        action_catalog=catalog,
        inventory=inventory_result(),
        consistency=consistency_result(),
    )
    assert "izin var" not in normalize_guard_text(skipped_result.decision.summary_tr)

    conflated = OutputGuard().guard(
        LLMDecision(
            decision_code=DecisionCode.AUTHORIZED_OPERATIONAL_MATCH,
            summary_tr="Envanter do\u011fruland\u0131; bu nedenle u\u00e7u\u015f izinlidir.",
        ),
        constraints=constraints(DecisionCode.AUTHORIZED_OPERATIONAL_MATCH),
        facts=facts(),
        verification=verification(VerificationStatus.VERIFIED, []),
        risk=risk(RiskLevel.LOW),
        action_catalog=catalog,
        inventory=inventory_result(),
        consistency=consistency_result(),
    )
    assert "izinli" not in normalize_guard_text(conflated.decision.summary_tr)


def test_fallback_preserves_inventory_and_consistency_fields() -> None:
    current = facts(inventory_status=InventoryStatus.NOT_LISTED)
    inventory = inventory_result(InventoryStatus.NOT_LISTED)
    consistency = consistency_result(
        OperationalConsistencyFlag.INVENTORY_NOT_LISTED,
        OperationalConsistencyFlag.DOWNSTREAM_CHECKS_SKIPPED_INVENTORY_NOT_CONFIRMED,
    )
    final = OutputFinalizer().finalize(
        metadata=FinalizationMetadata(event_id="event-fallback", request_id="request-fallback"),
        visual=FinalVisualEvidencePackage.model_construct(
            track_id="track-1",
            visual_class=VisualClass.FIGHTER_JET,
            final_visual_hypothesis="F-16",
            visual_evidence_status=VisualEvidenceStatus.SUPPORTED,
            visual_confidence=0.9,
            uncertainty_level=UncertaintyLevel.LOW,
            uncertainty_flags=[],
            human_visual_review_required=False,
        ),
        context=ContextResolution(context_status=ContextStatus.COMPLETE),
        platform=PlatformResult(platform_status=PlatformStatus.EXPECTED, platform_id="PLT_F16"),
        permission=PermissionFlightPlanResult(
            permission_status=PermissionStatus.NOT_APPLICABLE,
            flight_plan_status=FlightPlanStatus.NOT_APPLICABLE,
            record_consistency=RecordConsistency.NOT_APPLICABLE,
        ),
        notam=NotamResult(
            notam_status=NotamStatus.NONE_ACTIVE,
            operation_effect=NotamOperationEffect.UNKNOWN,
        ),
        facts=current,
        verification=verification(VerificationStatus.INDETERMINATE),
        risk=risk(RiskLevel.UNKNOWN),
        rag=RAGResult(called=False),
        constraints=constraints(DecisionCode.REJECTED_OUT_OF_SCOPE),
        action_catalog=load_action_catalog(ROOT / "data/rules/action_catalog.yaml"),
        tool_execution_summary={},
        model_versions=ModelVersions(decision_llm="stub"),
        llm_decision=None,
        inventory=inventory,
        consistency=consistency,
    )
    assert final.decision is DecisionCode.REJECTED_OUT_OF_SCOPE
    assert final.inventory_dataset_version == "1.0.0"
    assert final.operational_consistency_flags == consistency.flags
    assert final.human_approval_required is True


def test_finalizer_does_not_force_review_for_authorized_not_listed_result() -> None:
    current = facts(inventory_status=InventoryStatus.NOT_LISTED)
    consistency = OperationalConsistencyResult(
        status=OperationalConsistencyStatus.CONSISTENT,
        flags=[OperationalConsistencyFlag.INVENTORY_NOT_LISTED],
        reason_codes=[OperationalConsistencyFlag.INVENTORY_NOT_LISTED.value],
        evidence_references=["inventory.inventory_status"],
        human_review_required=False,
    )
    allowed = constraints(DecisionCode.AUTHORIZED_OPERATIONAL_MATCH).model_copy(
        update={"minimum_risk_level": "LOW", "human_review_required": False}
    )
    final = OutputFinalizer().finalize(
        metadata=FinalizationMetadata(event_id="event-authorized", request_id="request-authorized"),
        visual=FinalVisualEvidencePackage.model_construct(
            track_id="track-1",
            visual_class=VisualClass.FIGHTER_JET,
            final_visual_hypothesis="Boeing 747",
            visual_evidence_status=VisualEvidenceStatus.SUPPORTED,
            visual_confidence=0.9,
            uncertainty_level=UncertaintyLevel.LOW,
            uncertainty_flags=[],
            human_visual_review_required=True,
        ),
        context=ContextResolution(context_status=ContextStatus.COMPLETE),
        platform=PlatformResult(
            platform_status=PlatformStatus.EXPECTED,
            platform_id="PLT_BOEING_747",
        ),
        permission=PermissionFlightPlanResult(
            permission_status=PermissionStatus.VALID,
            flight_plan_status=FlightPlanStatus.FILED,
            record_consistency=RecordConsistency.CONSISTENT,
        ),
        notam=NotamResult(
            notam_status=NotamStatus.NONE_ACTIVE,
            operation_effect=NotamOperationEffect.NO_EFFECT,
        ),
        facts=current,
        verification=verification(VerificationStatus.VERIFIED, []),
        risk=risk(RiskLevel.LOW),
        rag=RAGResult(called=False),
        constraints=allowed,
        action_catalog=load_action_catalog(ROOT / "data/rules/action_catalog.yaml"),
        tool_execution_summary={},
        model_versions=ModelVersions(decision_llm="stub"),
        llm_decision=LLMDecision(
            decision_code=DecisionCode.AUTHORIZED_OPERATIONAL_MATCH,
            summary_tr="Operasyonel kayıtlar mevcut bağlamla uyumludur.",
        ),
        inventory=inventory_result(InventoryStatus.NOT_LISTED),
        consistency=consistency,
    )
    assert final.decision is DecisionCode.AUTHORIZED_OPERATIONAL_MATCH
    assert final.verification_status is VerificationStatus.VERIFIED
    assert final.risk_level is RiskLevel.LOW
    assert final.human_approval_required is False
    assert final.human_review_reasons == []
    assert "REQUEST_OPERATOR_REVIEW" not in {
        item.action_code for item in final.recommended_actions
    }


def test_system_prompt_contains_binding_inventory_prohibitions() -> None:
    system = PromptBuilder().build(evidence())[0]["content"]
    for phrase in (
        "Platform Registry eşleşmesini Türkiye Inventory onayı olarak sunma",
        "Inventory CONFIRMED sonucunu uçuş izni",
        "Inventory NOT_LISTED sonucunu düşman, yabancı, ajan, taklit, sahte",
        "SKIPPED Permission, Flight Plan veya NOTAM için domain sonucu üretme",
        "Yeni operational consistency flag üretme",
        "JSON dışında hiçbir karakter üretme",
    ):
        assert phrase in system


def test_guard_blocks_fabricated_inventory_metadata_and_consistency_claim() -> None:
    catalog = load_action_catalog(ROOT / "data/rules/action_catalog.yaml")
    result = OutputGuard().guard(
        LLMDecision(
            decision_code=DecisionCode.AUTHORIZED_OPERATIONAL_MATCH,
            summary_tr="Dataset version 9.9; operasyonel kay\u0131tlar \u00e7eli\u015fkilidir.",
        ),
        constraints=constraints(DecisionCode.AUTHORIZED_OPERATIONAL_MATCH),
        facts=facts(),
        verification=verification(VerificationStatus.VERIFIED, []),
        risk=risk(RiskLevel.LOW),
        action_catalog=catalog,
        inventory=inventory_result(),
        consistency=consistency_result(),
    )
    normalized = normalize_guard_text(result.decision.summary_tr)
    assert "9 9" not in normalized
    assert "celiskili" not in normalized
    assert any(
        correction.reason == "TOOL_CONTRADICTION_OR_VISUAL_OVERCLAIM"
        for correction in result.corrections
    )
