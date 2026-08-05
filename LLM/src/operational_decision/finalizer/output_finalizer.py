"""Assemble immutable deterministic facts and guarded narrative into final output."""

from datetime import datetime

from pydantic import Field, field_validator

from operational_decision.contracts.common import (
    EventStatus,
    InventoryStatus,
    OperationalConsistencyFlag,
    RiskLevel,
    StrictContract,
)
from operational_decision.contracts.context import ContextResolution
from operational_decision.contracts.final_output import (
    FinalDecisionOutput,
    FlightPlanEvidence,
    ModelVersions,
    NotamEvidence,
    PermissionEvidence,
    SourceReference,
    ToolExecutionSummaryItem,
)
from operational_decision.contracts.inventory import TurkeyInventoryResult
from operational_decision.contracts.llm import EvidenceConstraints, LLMDecision, RecommendedAction
from operational_decision.contracts.notam import NotamRecord, NotamResult
from operational_decision.contracts.operational_consistency import OperationalConsistencyResult
from operational_decision.contracts.permission import (
    FlightPlanRecord,
    PermissionFlightPlanResult,
    PermissionRecord,
)
from operational_decision.contracts.platform import PlatformResult
from operational_decision.contracts.rag import RAGResult, RAGSource
from operational_decision.contracts.risk import ActionCatalog, RiskResult
from operational_decision.contracts.verification import VerificationInput, VerificationResult
from operational_decision.contracts.visual import (
    FinalVisualEvidencePackage,
    _require_aware_datetime,
)
from operational_decision.finalizer.output_guard import OutputGuard
from operational_decision.finalizer.turkish_report import (
    build_turkish_operational_report,
    build_turkish_summary,
)

_FALLBACK_SUMMARY = (
    "Karar ajanÄ± geÃ§erli ve tutarlÄ± bir Ã§Ä±ktÄ± Ã¼retemedi. "
    "YapÄ±landÄ±rÄ±lmÄ±ÅŸ kayÄ±tlar operatÃ¶r incelemesine aktarÄ±lmÄ±ÅŸtÄ±r."
)


def _deterministic_fallback_decision(
    constraints: EvidenceConstraints, failure_notes: list[str] | None
) -> LLMDecision:
    """Build narrative fallback without changing the deterministic decision policy."""
    return LLMDecision(
        decision_code=constraints.allowed_decision_codes[0],
        summary_tr=_FALLBACK_SUMMARY,
        recommended_actions=[
            RecommendedAction(
                action_code="REQUEST_OPERATOR_REVIEW",
                priority=1,
                reason_tr="Operat\u00f6r incelemesi iste",
            )
        ],
        uncertainty_notes=failure_notes or ["LOCAL_LLM_OUTPUT_INVALID"],
    )


class FinalizationMetadata(StrictContract):
    """Request and latency metadata not selected by the LLM."""

    event_id: str = Field(min_length=1, max_length=100)
    request_id: str = Field(min_length=1, max_length=100)
    video_id: str | None = Field(default=None, max_length=150)
    observation_time_utc: datetime | None = None
    observation_end_time_utc: datetime | None = None
    processing_latency_ms: int | None = Field(default=None, ge=0)

    @field_validator("observation_time_utc", "observation_end_time_utc")
    @classmethod
    def _aware_times(cls, value: datetime | None) -> datetime | None:
        return _require_aware_datetime(value) if value is not None else None


def _rag_summary(rag: RAGResult, *, unregistered_military_policy: bool = False) -> str:
    """Summarize retrieval without inventing legal provisions or decision weight."""
    if not rag.called:
        return (
            "Text RAG deterministik çağrı politikası kapsamında çağrılmadı; "
            "rapora mevzuat iddiası eklenmedi."
        )
    if unregistered_military_policy:
        if not rag.sources:
            return (
                "Bu olay için ilgili mevzuat kaynağı getirilememiştir; risk ve karar mevcut "
                "platform ve envanter politikasına göre korunmuştur."
            )
        return (
            "İlgili mevzuat kaynakları, envanter dışı askerî hava araçlarının hava sahası "
            "kullanımında izin ve koordinasyon koşullarının ayrıca değerlendirilmesine yönelik "
            "açıklama sağlamaktadır. Bu kaynaklar mevcut risk ve kararı değiştirmemektedir."
        )
    if not rag.sources:
        return (
            "Text RAG ilgili bir mevzuat kaynağı döndürmedi; mevzuat maddesi "
            "uydurulmadı ve RAG nihai kararı etkilemedi."
        )
    return (
        f"Text RAG {len(rag.sources)} doğrulanabilir kaynak parçasından kısmi mevzuat "
        "kanıtı döndürdü. Bu kanıt açıklamayı destekler; risk, yetki veya nihai kararı "
        "tek başına belirlemez."
    )


def _rag_decision_effect(rag: RAGResult) -> str:
    """State the bounded role of RAG in the final decision."""
    if not rag.called:
        return "Text RAG çağrılmadı; risk ve nihai karar üzerinde etkisi olmadı."
    if not rag.sources:
        return "Text RAG kaynak döndürmedi; risk ve nihai karar üzerinde etkisi olmadı."
    return (
        "Text RAG yalnız mevzuat açıklaması ve kaynak gösterimi sağladı; Permission, "
        "Verification, risk seviyesi veya izin durumunu değiştirmedi."
    )


def _human_review_reasons(
    *,
    visual: FinalVisualEvidencePackage,
    verification: VerificationResult,
    risk: RiskResult,
    consistency: OperationalConsistencyResult,
    fallback: bool,
    required: bool,
) -> list[str]:
    """Return deterministic review reasons from finalized facts."""
    if not required:
        return []
    if risk.selected_rule_id == "RULE_UNREGISTERED_MILITARY_PLATFORM":
        policy_reasons = ["UNREGISTERED_MILITARY_PLATFORM"]
        if bool(getattr(visual, "human_visual_review_required", False)):
            policy_reasons.append("VISUAL_IDENTITY_NOT_CONFIRMED")
        policy_reasons.append("OPERATIONAL_TOOLS_SKIPPED_BY_POLICY")
        if OperationalConsistencyFlag.PLATFORM_CONTEXT_MISMATCH in consistency.flags:
            policy_reasons.append(OperationalConsistencyFlag.PLATFORM_CONTEXT_MISMATCH.value)
        return policy_reasons
    reasons: list[str] = []
    if bool(getattr(visual, "human_visual_review_required", False)):
        reasons.append("Görsel platform kimliği kesin doğrulanmamış bir hipotezdir.")
    if verification.verification_status.value in {"UNVERIFIED", "INDETERMINATE"}:
        reasons.append(f"Operational Verification sonucu {verification.verification_status.value}.")
    if risk.human_review_required:
        reasons.append(
            f"Risk Advisor kuralı insan incelemesi gerektiriyor: {risk.selected_rule_id}."
        )
    if consistency.human_review_required:
        reasons.append("Operasyonel tutarlılık kontrolü insan incelemesi gerektiriyor.")
    if fallback and required:
        reasons.append("Local LLM geçerli karar üretemedi; güvenli fallback uygulandı.")
    if required and not reasons:
        reasons.append("Nihai güvenlik kısıtları insan incelemesi gerektiriyor.")
    return list(dict.fromkeys(reasons))


def _ensure_operator_review_action(
    decision: LLMDecision, *, urgent: bool
) -> LLMDecision:
    """Keep REQUEST_OPERATOR_REVIEW inside the binding three-action limit."""
    ordered = sorted(decision.recommended_actions, key=lambda item: item.priority)
    existing_review = next(
        (item for item in ordered if item.action_code == "REQUEST_OPERATOR_REVIEW"),
        None,
    )
    reason_tr = (
        "Olayı acilen yetkili operatöre ilet"
        if urgent
        else "Operasyonel karar için insan incelemesi yap"
    )
    review = (
        existing_review.model_copy(update={"reason_tr": reason_tr})
        if existing_review is not None
        else RecommendedAction(
            action_code="REQUEST_OPERATOR_REVIEW",
            priority=1,
            reason_tr=reason_tr,
        )
    )
    ordered = [
        review if item.action_code == "REQUEST_OPERATOR_REVIEW" else item for item in ordered
    ]
    selected = ordered[:3]
    if review not in selected:
        selected = [*selected[:2], review]
    actions = [
        item.model_copy(update={"priority": index}) for index, item in enumerate(selected, 1)
    ]
    return decision.model_copy(update={"recommended_actions": actions})

def _source_reference(source: RAGSource) -> SourceReference:
    return SourceReference(
        source_id=source.source_id,
        document_id=source.document_id,
        filename=source.filename,
        page_start=source.page_start,
        page_end=source.page_end,
        section_title=source.section_title,
        revision_date=source.revision_date,
        effective_date=source.effective_date,
    )


def _notam_evidence(record: NotamRecord) -> NotamEvidence:
    """Project one selected NOTAM record into bounded final-output evidence."""
    return NotamEvidence(
        notam_id=record.notam_id,
        operational_area_id=record.operational_area_id,
        valid_from_utc=record.valid_from_utc,
        valid_to_utc=record.valid_to_utc,
        notam_status=record.notam_status,
        operation_effect=record.operation_effect,
        display_number=record.display_number,
        series=record.series,
        number=record.number,
        year=record.year,
        q_code=record.q_code,
        item_e=record.item_e,
        estimated_end=record.estimated_end,
        permanent=record.permanent,
        lower_limit=record.lower_limit,
        upper_limit=record.upper_limit,
        fir_code=record.fir_code,
        aerodrome_code=record.aerodrome_code,
        operational_reason_tr=record.operational_reason_tr,
        conflict_with_permission=record.conflict_with_permission,
        conflict_with_flight_plan=record.conflict_with_flight_plan,
        summary_tr=record.summary_tr,
        source_type=record.source_type,
        source_reference=record.source_reference,
    )


def _permission_evidence(record: PermissionRecord) -> PermissionEvidence:
    return PermissionEvidence(
        permission_id=record.permission_id,
        valid_from_utc=record.valid_from_utc,
        valid_to_utc=record.valid_to_utc,
        permission_status=record.permission_status,
        operator_name=record.operator_name,
        flight_purpose=record.flight_purpose,
        altitude_ft_msl=record.altitude_ft_msl,
        departure_aerodrome=record.departure_aerodrome,
        arrival_aerodrome=record.arrival_aerodrome,
        source_type=record.source_type,
    )


def _flight_plan_evidence(record: FlightPlanRecord) -> FlightPlanEvidence:
    return FlightPlanEvidence(
        flight_plan_id=record.flight_plan_id,
        planned_departure_utc=record.planned_departure_utc,
        planned_arrival_utc=record.planned_arrival_utc,
        flight_plan_status=record.flight_plan_status,
        callsign=record.callsign,
        departure_aerodrome=record.departure_aerodrome,
        arrival_aerodrome=record.arrival_aerodrome,
        route_or_area=record.route_or_area,
        source_type=record.source_type,
    )


class OutputFinalizer:
    """Guarantee final risk/tool facts and deterministic safe fallback."""

    def __init__(self, guard: OutputGuard | None = None) -> None:
        """Configure the deterministic output guard."""
        self._guard = guard or OutputGuard()

    def finalize(
        self,
        *,
        metadata: FinalizationMetadata,
        visual: FinalVisualEvidencePackage,
        context: ContextResolution,
        platform: PlatformResult,
        permission: PermissionFlightPlanResult,
        notam: NotamResult,
        facts: VerificationInput,
        verification: VerificationResult,
        risk: RiskResult,
        rag: RAGResult,
        constraints: EvidenceConstraints,
        action_catalog: ActionCatalog,
        tool_execution_summary: dict[str, ToolExecutionSummaryItem],
        model_versions: ModelVersions,
        llm_decision: LLMDecision | None,
        inventory: TurkeyInventoryResult | None = None,
        consistency: OperationalConsistencyResult | None = None,
        failure_notes: list[str] | None = None,
    ) -> FinalDecisionOutput:
        """Finalize guarded output; None means deterministic safe fallback."""
        fallback = llm_decision is None
        inventory = inventory or TurkeyInventoryResult(
            inventory_status=facts.inventory_status,
            platform_id="UNRESOLVED",
            reason_codes=[facts.inventory_status.value],
            safe_message=(
                "Platform mevcut T\u00fcrkiye envanter veri setinde bulunamad\u0131."
                if facts.inventory_status is InventoryStatus.NOT_LISTED
                else "Türkiye inventory sonucu deterministik facts üzerinden korunmuştur."
            ),
            warnings=[],
        )
        consistency = consistency or OperationalConsistencyResult(
            status=facts.operational_consistency_status,
            flags=facts.operational_consistency_flags,
            reason_codes=[flag.value for flag in facts.operational_consistency_flags],
            evidence_references=[
                "verification_input.operational_consistency_flags"
                for _ in facts.operational_consistency_flags
            ],
            human_review_required=(
                facts.operational_consistency_status.value in {"FLAGGED", "INDETERMINATE"}
            ),
        )
        candidate = llm_decision or _deterministic_fallback_decision(constraints, failure_notes)
        guarded = self._guard.guard(
            candidate,
            constraints=constraints,
            facts=facts,
            verification=verification,
            risk=risk,
            action_catalog=action_catalog,
            inventory=inventory,
            consistency=consistency,
        )
        decision = guarded.decision
        selected_ids = set(decision.source_ids)
        selected_sources = (
            rag.sources
            if fallback
            else [item for item in rag.sources if item.source_id in selected_ids]
        )
        record = context.record
        human_review_required = risk.risk_level is not RiskLevel.LOW and (
            risk.human_review_required
            or constraints.human_review_required
            or consistency.human_review_required
        )
        if human_review_required:
            decision = _ensure_operator_review_action(
                decision, urgent=risk.human_review_priority == "URGENT"
            )
        review_reasons = _human_review_reasons(
            visual=visual,
            verification=verification,
            risk=risk,
            consistency=consistency,
            fallback=fallback,
            required=human_review_required,
        )
        output = FinalDecisionOutput(
            event_id=metadata.event_id,
            request_id=metadata.request_id,
            event_status=EventStatus.FINALIZED,
            video_id=metadata.video_id,
            camera_id=record.camera_id if record else None,
            context_id=record.context_id if record else None,
            operational_area_id=record.operational_area_id if record else None,
            scenario_id=record.scenario_id if record else None,
            track_id=visual.track_id,
            observation_time_utc=metadata.observation_time_utc,
            observation_end_time_utc=metadata.observation_end_time_utc,
            visual_class=visual.visual_class,
            visual_hypothesis=visual.final_visual_hypothesis,
            visual_analysis_tr=getattr(
                getattr(visual, "upstream_vlm_output", None), "gorsel_analiz", None
            ),
            timestamped_events=visual.video_event_projection.timestamped_events,
            timestamps_available=visual.video_event_projection.timestamps_available,
            event_extraction_status=visual.video_event_projection.event_extraction_status,
            untimestamped_visual_assessment=(
                visual.video_event_projection.untimestamped_visual_assessment
            ),
            visual_evidence_status=visual.visual_evidence_status,
            visual_confidence=visual.visual_confidence,
            uncertainty_level=visual.uncertainty_level,
            uncertainty_flags=visual.uncertainty_flags,
            platform_status=platform.platform_status,
            platform_id=platform.platform_id,
            matched_platform=platform.matched_platform,
            canonical_name=platform.canonical_name,
            platform_category=platform.category,
            platform_taxonomy=platform.taxonomy,
            platform_usage_domain=platform.usage_domain,
            platform_origin=(platform.platform_origin.value if platform.platform_origin else None),
            manufacturer_country_code=platform.manufacturer_country_code,
            platform_identity_scope=(
                platform.identity_scope.value if platform.identity_scope else None
            ),
            platform_variant_policy=(
                platform.variant_policy.value if platform.variant_policy else None
            ),
            vlm_origin_hypothesis=getattr(
                getattr(visual, "upstream_vlm_output", None), "ulke_orjini", None
            ),
            vlm_origin_category=facts.vlm_origin_category,
            inventory_status=inventory.inventory_status,
            inventory_registry_version=inventory.dataset_version,
            inventory_record_id=inventory.inventory_record_id,
            inventory_country_code=inventory.country_code,
            inventory_operator_name=inventory.operator_name,
            inventory_service_status=inventory.service_status,
            inventory_dataset_id=inventory.dataset_id,
            inventory_dataset_version=inventory.dataset_version,
            inventory_source_type=inventory.source_type,
            inventory_reason_codes=inventory.reason_codes,
            operational_consistency_status=consistency.status,
            operational_consistency_flags=consistency.flags,
            permission_status=permission.permission_status,
            permission_details=[
                _permission_evidence(item) for item in permission.permission_records
            ],
            flight_plan_status=permission.flight_plan_status,
            flight_plan_details=[
                _flight_plan_evidence(item) for item in permission.flight_plan_records
            ],
            record_consistency=permission.record_consistency,
            notam_status=notam.notam_status,
            notam_operation_effect=notam.operation_effect,
            notam_details=[_notam_evidence(record) for record in notam.active_notams],
            matched_notam_ids=notam.matched_notam_ids,
            primary_notam_number=notam.primary_notam_number,
            notam_reason_tr=notam.reason_tr,
            notam_matched_by=notam.matched_by,
            notam_conflict_with_permission=notam.conflict_with_permission,
            notam_conflict_with_flight_plan=notam.conflict_with_flight_plan,
            context_status=context.context_status,
            verification_status=verification.verification_status,
            verification_reason_codes=[item.value for item in verification.reason_codes],
            tool_health_status=verification.tool_health_status,
            decision=decision.decision_code,
            decision_confidence=risk.decision_confidence,
            risk_level=risk.risk_level,
            minimum_risk_level=risk.minimum_risk_level,
            risk_assessment_confidence=risk.risk_assessment_confidence,
            evidence_quality_score=risk.evidence_quality_score,
            matched_rule_ids=risk.matched_rule_ids,
            risk_explanation=risk.explanation,
            risk_increasing_factors=risk.increasing_factors,
            risk_reducing_factors=risk.reducing_factors,
            rag_summary=_rag_summary(
                rag,
                unregistered_military_policy=(
                    risk.selected_rule_id == "RULE_UNREGISTERED_MILITARY_PLATFORM"
                ),
            ),
            rag_sources=[_source_reference(item) for item in rag.sources],
            rag_decision_effect=_rag_decision_effect(rag),
            human_review_reasons=review_reasons,
            human_review_priority=risk.human_review_priority,
            hostile_target_confirmed=False,
            legal_violation_confirmed=False,
            summary_tr=decision.summary_tr,
            evidence_summary=decision.evidence_summary,
            recommended_actions=decision.recommended_actions,
            human_approval_required=human_review_required,
            uncertainty_notes=list(
                dict.fromkeys([*risk.uncertainties, *decision.uncertainty_notes])
            ),
            sources=[_source_reference(item) for item in selected_sources],
            tool_execution_summary=tool_execution_summary,
            guard_corrections=guarded.corrections,
            processing_latency_ms=metadata.processing_latency_ms,
            model_versions=model_versions,
        )
        output_data = output.model_dump(mode="json")
        report = build_turkish_operational_report(output_data)
        summary = build_turkish_summary(output_data)
        return output.model_copy(
            update={
                "summary_tr": summary,
                "operational_report_tr": report,
                "turkish_report": None,
            }
        )
