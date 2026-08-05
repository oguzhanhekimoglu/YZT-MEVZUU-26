"""Deterministic Text RAG call and query-template policy."""

from dataclasses import dataclass

from operational_decision.contracts.common import (
    ContextStatus,
    FlightPlanStatus,
    InventoryStatus,
    NotamOperationEffect,
    NotamStatus,
    OperationalConsistencyFlag,
    PermissionStatus,
    PlatformStatus,
    RecordConsistency,
    RiskLevel,
    ToolHealthStatus,
    VerificationStatus,
    VisualClass,
)
from operational_decision.contracts.verification import VerificationInput
from operational_decision.decision.verification_checker import is_unregistered_military_policy


@dataclass(frozen=True)
class RAGQueryPlan:
    """One binding query template and its runtime document filter."""

    query_template_id: str
    query: str
    document_ids: tuple[str, ...]


_UNREGISTERED_MILITARY_AIRSPACE_CONTEXT = RAGQueryPlan(
    query_template_id="UNREGISTERED_MILITARY_AIRSPACE_CONTEXT",
    query=(
        "Türkiye hava sahasında yabancı veya envanter dışı askerî hava araçlarının "
        "uçuş izni, ilgili kurum koordinasyonu ve hava sahası kullanım koşulları nelerdir? "
        "Operasyonel yetkilendirmenin ayrıca doğrulanması hangi mevzuat bağlamında "
        "değerlendirilir?"
    ),
    document_ids=("LT_GEN_1_2", "LT_GEN_1_6", "LT_GEN_3_3"),
)
_PERMISSION_NOT_FOUND = RAGQueryPlan(
    query_template_id="PERMISSION_NOT_FOUND",
    query=(
        "Türk hava sahasında geçerli uçuş izni kaydı bulunmayan operasyonların "
        "izin ve inceleme bağlamı nedir?"
    ),
    document_ids=("LT_GEN_1_2", "LT_ENR_1_10"),
)
_PERMISSION_EXPIRED = RAGQueryPlan(
    query_template_id="PERMISSION_EXPIRED",
    query=(
        "Gözlem zamanında süresi dolmuş veya geri alınmış uçuş izninin "
        "operasyonel ve mevzuat bağlamı nedir?"
    ),
    document_ids=("LT_GEN_1_2",),
)
_CIVIL_UAV = RAGQueryPlan(
    query_template_id="CIVIL_UAV",
    query=(
        "Sivil İHA operasyonlarında uçuş izni, hava sahası kullanımı ve risk "
        "değerlendirmesi hangi kurallara tabidir?"
    ),
    document_ids=("SHT_IHA_REV_05",),
)
_ACTIVE_NOTAM = RAGQueryPlan(
    query_template_id="ACTIVE_NOTAM",
    query=(
        "Operasyonu kısıtlayan, yasaklayan veya izinle çelişen aktif NOTAM'ın "
        "havacılık bilgi hizmetleri açısından anlamı nedir?"
    ),
    document_ids=("LT_GEN_3_1",),
)
_FLIGHT_PLAN_WITHOUT_PERMISSION = RAGQueryPlan(
    query_template_id="FLIGHT_PLAN_WITHOUT_PERMISSION",
    query=(
        "Uçuş planı ile uçuş izni hangi ayrı işlevlere sahiptir ve birindeki "
        "geçerli kayıt diğerinin yerine geçer mi?"
    ),
    document_ids=("LT_GEN_1_2", "LT_ENR_1_10"),
)

_PERMISSION_PLAN_FLAGS = {
    OperationalConsistencyFlag.FLIGHT_PLAN_WITHOUT_VALID_PERMISSION,
    OperationalConsistencyFlag.INVALID_PERMISSION_WITH_FILED_PLAN,
    OperationalConsistencyFlag.VALID_PERMISSION_WITH_INVALID_FLIGHT_PLAN,
}
_NOTAM_FLAGS = {
    OperationalConsistencyFlag.NOTAM_CONFLICTS_WITH_PERMISSION,
    OperationalConsistencyFlag.NOTAM_RESTRICTS_OPERATION,
    OperationalConsistencyFlag.NOTAM_PROHIBITS_OPERATION,
}
_REGULATORY_EXPLANATION_FLAGS = _PERMISSION_PLAN_FLAGS | _NOTAM_FLAGS


def _permission_plan_conflict(facts: VerificationInput) -> bool:
    return (
        facts.record_consistency is RecordConsistency.CONFLICTING
        or (
            facts.flight_plan_status is FlightPlanStatus.FILED
            and facts.permission_status is not PermissionStatus.VALID
        )
        or (
            facts.permission_status is PermissionStatus.VALID
            and facts.flight_plan_status
            in {
                FlightPlanStatus.CANCELLED,
                FlightPlanStatus.EXPIRED,
                FlightPlanStatus.NOT_FOUND,
            }
        )
        or bool(_PERMISSION_PLAN_FLAGS.intersection(facts.operational_consistency_flags))
    )


def _notam_requires_explanation(facts: VerificationInput) -> bool:
    return (
        facts.notam_operation_effect
        in {
            NotamOperationEffect.RESTRICTS_OPERATION,
            NotamOperationEffect.PROHIBITS_OPERATION,
            NotamOperationEffect.CONFLICTS_WITH_PERMISSION,
        }
        or facts.notam_status
        in {NotamStatus.ACTIVE_RELEVANT, NotamStatus.CONFLICTING, NotamStatus.AMBIGUOUS}
        or bool(_NOTAM_FLAGS.intersection(facts.operational_consistency_flags))
    )


def select_text_rag_query(facts: VerificationInput) -> RAGQueryPlan | None:
    """Select only a non-inventory query backed by an existing runtime document."""
    if (
        facts.context_status is ContextStatus.COMPLETE
        and facts.platform_status in {PlatformStatus.EXPECTED, PlatformStatus.NOT_EXPECTED}
        and is_unregistered_military_policy(
            platform_usage_domain=facts.platform_usage_domain,
            inventory_execution_status=facts.inventory_execution_status,
            inventory_status=facts.inventory_status,
        )
    ):
        return _UNREGISTERED_MILITARY_AIRSPACE_CONTEXT
    if _permission_plan_conflict(facts):
        return _FLIGHT_PLAN_WITHOUT_PERMISSION
    if facts.permission_status is PermissionStatus.NOT_FOUND:
        return _PERMISSION_NOT_FOUND
    if facts.permission_status in {PermissionStatus.EXPIRED, PermissionStatus.REVOKED}:
        return _PERMISSION_EXPIRED
    if _notam_requires_explanation(facts):
        return _ACTIVE_NOTAM

    # Turkey Inventory truth is registry-only; no inventory retrieval template exists.
    if facts.inventory_status is InventoryStatus.NOT_LISTED:
        return None
    if facts.visual_class in {VisualClass.UAV, VisualClass.MICRO_DRONE}:
        return _CIVIL_UAV
    return None


def should_call_text_rag(
    *,
    verification_status: VerificationStatus,
    risk_level: RiskLevel,
    tool_health_status: ToolHealthStatus,
    facts: VerificationInput,
    explanation_requested: bool,
    strong_non_aircraft: bool = False,
) -> bool:
    """Call RAG only when a supported non-inventory explanation template exists."""
    if strong_non_aircraft or facts.visual_class is VisualClass.NON_AIRCRAFT:
        return False
    plan = select_text_rag_query(facts)
    if plan is None:
        return False
    if explanation_requested:
        return True
    if (
        verification_status is VerificationStatus.VERIFIED
        and risk_level is RiskLevel.LOW
        and tool_health_status is ToolHealthStatus.HEALTHY
    ):
        return False
    if facts.permission_status in {
        PermissionStatus.NOT_FOUND,
        PermissionStatus.EXPIRED,
        PermissionStatus.REVOKED,
    }:
        return True
    if _permission_plan_conflict(facts) or _notam_requires_explanation(facts):
        return True
    if verification_status in {
        VerificationStatus.UNVERIFIED,
        VerificationStatus.INDETERMINATE,
    }:
        return True
    if risk_level in {
        RiskLevel.MEDIUM,
        RiskLevel.HIGH,
        RiskLevel.CRITICAL,
        RiskLevel.UNKNOWN,
    }:
        return True
    return bool(_REGULATORY_EXPLANATION_FLAGS.intersection(facts.operational_consistency_flags))
