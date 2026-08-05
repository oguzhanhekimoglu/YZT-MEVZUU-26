"""Deterministic correction of constrained local LLM output."""

import re
import unicodedata

from operational_decision.contracts.common import (
    ContextStatus,
    FlightPlanStatus,
    InventoryStatus,
    NotamOperationEffect,
    OperationalConsistencyFlag,
    PermissionStatus,
    PlatformStatus,
    RiskLevel,
    ToolExecutionStatus,
    ToolHealthStatus,
    VisualClass,
    VisualEvidenceStatus,
)
from operational_decision.contracts.final_output import GuardCorrection
from operational_decision.contracts.inventory import TurkeyInventoryResult
from operational_decision.contracts.llm import EvidenceConstraints, LLMDecision, RecommendedAction
from operational_decision.contracts.operational_consistency import OperationalConsistencyResult
from operational_decision.contracts.risk import ActionCatalog, RiskResult
from operational_decision.contracts.verification import VerificationInput, VerificationResult
from operational_decision.decision.verification_checker import (
    is_unregistered_military_policy,
)

_PERMISSION_PROBLEM = {
    PermissionStatus.NOT_FOUND,
    PermissionStatus.EXPIRED,
    PermissionStatus.NOT_YET_VALID,
    PermissionStatus.REVOKED,
    PermissionStatus.AMBIGUOUS,
    PermissionStatus.CONFLICTING,
}
_PLAN_PROBLEM = {
    FlightPlanStatus.NOT_FOUND,
    FlightPlanStatus.EXPIRED,
    FlightPlanStatus.NOT_YET_ACTIVE,
    FlightPlanStatus.CANCELLED,
    FlightPlanStatus.AMBIGUOUS,
    FlightPlanStatus.CONFLICTING,
}
_OVERCLAIM = (
    "kesin olarak",
    "kesinlikle",
    "tartışmasız",
    "%100",
    "doğrulanmış f-16",
)

_MAX_RECOMMENDED_ACTIONS = 3
_UNRESOLVED_PLATFORM_ACTIONS = (
    "VERIFY_PLATFORM_MANUALLY",
    "REQUEST_ADDITIONAL_VISUAL_EVIDENCE",
    "REQUEST_OPERATOR_REVIEW",
)
_UNRESOLVED_PLATFORM_ACTION_TEXT = {
    "VERIFY_PLATFORM_MANUALLY": "Platform kimliğini manuel doğrula",
    "REQUEST_ADDITIONAL_VISUAL_EVIDENCE": (
        "Daha kaliteli veya farklı açılardan görsel kanıt sağla"
    ),
    "REQUEST_OPERATOR_REVIEW": "Operasyonel karar için insan incelemesi yap",
}


class GuardResult:
    """Corrected decision plus an audit trail of deterministic changes."""

    def __init__(self, decision: LLMDecision, corrections: list[GuardCorrection]) -> None:
        """Store the corrected decision and its audit trail."""
        self.decision = decision
        self.corrections = corrections


def normalize_guard_text(value: str) -> str:
    """Normalize Unicode, Turkish casing, punctuation, and whitespace deterministically."""
    value = unicodedata.normalize("NFKC", value).replace("İ", "i").replace("I", "ı")
    value = value.casefold().replace("ı", "i")
    value = "".join(
        char for char in unicodedata.normalize("NFKD", value) if not unicodedata.combining(char)
    )
    return re.sub(r"\s+", " ", re.sub(r"[^\w%]+", " ", value)).strip()


def _relevant_verification_actions(
    facts: VerificationInput, verification: VerificationResult
) -> list[str]:
    codes = {code.value for code in verification.reason_codes}
    actions: list[str] = []
    if facts.platform_status in {
        PlatformStatus.UNKNOWN,
        PlatformStatus.AMBIGUOUS,
        PlatformStatus.NOT_EXPECTED,
    } or any(code.startswith("PLATFORM_") and code != "PLATFORM_EXPECTED" for code in codes):
        actions.append("VERIFY_PLATFORM_MANUALLY")
    if facts.permission_execution_status is ToolExecutionStatus.SUCCESS and (
        facts.permission_status in _PERMISSION_PROBLEM
        or any(code.startswith("PERMISSION_") and code != "PERMISSION_VALID" for code in codes)
    ):
        actions.append("CHECK_PERMISSION_RECORDS")
    if facts.permission_execution_status is ToolExecutionStatus.SUCCESS and (
        facts.flight_plan_status in _PLAN_PROBLEM or "FLIGHT_PLAN_WITHOUT_PERMISSION" in codes
    ):
        actions.append("CHECK_FLIGHT_PLAN_RECORDS")
    if facts.notam_execution_status is ToolExecutionStatus.SUCCESS and (
        facts.notam_operation_effect is not NotamOperationEffect.NO_EFFECT
        or any(code.startswith("NOTAM_") and code != "NOTAM_NONE_ACTIVE" for code in codes)
    ):
        actions.append("REVIEW_ACTIVE_NOTAM")
    if facts.visual_evidence_status in {
        VisualEvidenceStatus.WEAK,
        VisualEvidenceStatus.CONFLICTING,
        VisualEvidenceStatus.INSUFFICIENT,
    } or any(code.startswith("VISUAL_") for code in codes):
        actions.append("REQUEST_ADDITIONAL_VISUAL_EVIDENCE")
    return actions


def _unregistered_military_policy_applies(facts: VerificationInput) -> bool:
    return (
        facts.context_status is ContextStatus.COMPLETE
        and facts.platform_status in {PlatformStatus.EXPECTED, PlatformStatus.NOT_EXPECTED}
        and is_unregistered_military_policy(
            platform_usage_domain=facts.platform_usage_domain,
            inventory_execution_status=facts.inventory_execution_status,
            inventory_status=facts.inventory_status,
        )
    )

def _minimum_actions(
    risk: RiskResult, facts: VerificationInput, verification: VerificationResult
) -> list[str]:
    if risk.risk_level is RiskLevel.LOW:
        return []
    if _unregistered_military_policy_applies(facts):
        return ["ESCALATE_TO_AUTHORIZED_UNIT", "REQUEST_OPERATOR_REVIEW"]
    required = ["REQUEST_OPERATOR_REVIEW"]
    relevant = _relevant_verification_actions(facts, verification)
    if risk.risk_level is RiskLevel.HIGH:
        required.append(relevant[0] if relevant else "VERIFY_PLATFORM_MANUALLY")
    elif risk.risk_level is RiskLevel.CRITICAL:
        required.append("ESCALATE_TO_AUTHORIZED_UNIT")
    required.extend(relevant)
    return list(dict.fromkeys(required))


def _action_reason_tr(action_code: str, default_title: str, facts: VerificationInput) -> str:
    """Return a context-aware action title without changing the action code."""
    if _unregistered_military_policy_applies(facts):
        if action_code == "ESCALATE_TO_AUTHORIZED_UNIT":
            return (
                "Türkiye envanter durumunu ve operasyonel yetkilendirmeyi "
                "yetkili birimden doğrula"
            )
        if action_code == "CONTINUE_TRACKING":
            return "Hava sahası takibini sürdür"
        if action_code == "REQUEST_OPERATOR_REVIEW":
            return "Olayı acilen yetkili operatöre ilet"
    if (
        action_code == "CHECK_FLIGHT_PLAN_RECORDS"
        and facts.flight_plan_status is FlightPlanStatus.FILED
    ):
        return "Uçuş planı ile uçuş izni kaydının birlikte uyumunu doğrula"
    return default_title


def _platform_is_unresolved(facts: VerificationInput) -> bool:
    return facts.platform_status in {PlatformStatus.UNKNOWN, PlatformStatus.AMBIGUOUS}


def _action_conflicts_with_execution(action_code: str, facts: VerificationInput) -> bool:
    if (
        _unregistered_military_policy_applies(facts)
        and action_code == "REQUEST_ADDITIONAL_VISUAL_EVIDENCE"
    ):
        return True
    if action_code == "MARK_AS_NON_AIRCRAFT" and facts.visual_class is not VisualClass.NON_AIRCRAFT:
        return True
    if facts.permission_execution_status is ToolExecutionStatus.SKIPPED and action_code in {
        "CHECK_PERMISSION_RECORDS",
        "CHECK_FLIGHT_PLAN_RECORDS",
    }:
        return True
    return (
        facts.notam_execution_status is ToolExecutionStatus.SKIPPED
        and action_code == "REVIEW_ACTIVE_NOTAM"
    )


def _safe_summary(
    facts: VerificationInput,
    verification: VerificationResult,
    inventory: TurkeyInventoryResult | None,
) -> str:
    if facts.notam_operation_effect is NotamOperationEffect.PROHIBITS_OPERATION:
        return (
            "İlgili aktif NOTAM, eşleşen operasyon kapsamında hava aracı faaliyetini "
            "yasaklamaktadır; ciddi operasyonel uyumsuzluk acil doğrulama gerektirir."
        )
    if facts.permission_status is PermissionStatus.NOT_FOUND:
        return "Geçerli uçuş izni kaydı doğrulanamamıştır; operatör incelemesi gereklidir."
    if facts.permission_status in _PERMISSION_PROBLEM:
        return "Uçuş izni geçerli olarak doğrulanamamıştır; operatör incelemesi gereklidir."
    if facts.platform_status in {PlatformStatus.UNKNOWN, PlatformStatus.AMBIGUOUS}:
        return "Platform kimliği çözülememiştir; görsel sınıflandırma yalnız hipotezdir."
    if verification.tool_health_status is ToolHealthStatus.FAILED:
        return "Kritik operasyonel doğrulama tamamlanamamıştır; operatör incelemesi gereklidir."
    if facts.inventory_status is InventoryStatus.NOT_LISTED:
        dataset = (
            "DEMO_MOCK Türkiye Inventory"
            if inventory is not None and inventory.source_type == "DEMO_MOCK"
            else "Türkiye Inventory"
        )
        if (
            facts.permission_status is PermissionStatus.VALID
            and facts.flight_plan_status is FlightPlanStatus.FILED
            and facts.notam_operation_effect is NotamOperationEffect.NO_EFFECT
        ):
            return (
                f"Platform mevcut {dataset} veri setinde kayıtlı değildir; geçerli permission "
                "ve uçuş planı bulunmuş, operasyonu kısıtlayan bir NOTAM etkisi tespit "
                "edilmemiştir."
            )
        return (
            f"Platform mevcut {dataset} veri setinde kayıtlı değildir; "
            "bu durum tek başına izinsiz operasyon kanıtı değildir."
        )
    return "Görsel kimlik kesin değildir; mevcut değerlendirme bir görsel hipotezdir."


def _metadata_claim_is_invalid(normalized: str, inventory: TurkeyInventoryResult | None) -> bool:
    labels = (
        "inventory_record_id",
        "inventory record id",
        "dataset_version",
        "dataset version",
        "inventory source",
        "source type",
    )
    if inventory is None:
        return any(label in normalized for label in labels)
    pairs = (
        ("inventory_record_id", inventory.inventory_record_id),
        ("inventory record id", inventory.inventory_record_id),
        ("dataset_version", inventory.dataset_version),
        ("dataset version", inventory.dataset_version),
        ("inventory source", inventory.source_type),
        ("source type", inventory.source_type),
    )
    return any(
        label in normalized and (actual is None or normalize_guard_text(actual) not in normalized)
        for label, actual in pairs
    )


def _summary_contradicts(
    summary: str,
    facts: VerificationInput,
    verification: VerificationResult,
    inventory: TurkeyInventoryResult | None = None,
    consistency: OperationalConsistencyResult | None = None,
) -> bool:
    normalized = normalize_guard_text(summary)
    permission_claim = any(
        phrase in normalized
        for phrase in ("izin var", "izinli", "gecerli izin", "izin dogrulandi", "izinsiz")
    )
    inventory_claim = any(
        phrase in normalized
        for phrase in (
            "turkiye envanterindedir",
            "turkiye envanterinde",
            "envanter dogrulandi",
            "envanter kaydi dogrulandi",
            "envanter onaylandi",
        )
    )
    hostile_claim = any(
        phrase in normalized for phrase in ("dusman", "yabanci", "ajan", "taklit", "sahte", "decoy")
    )
    if facts.inventory_status is not InventoryStatus.CONFIRMED and inventory_claim:
        return True
    if facts.inventory_status is InventoryStatus.CONFIRMED and inventory_claim and permission_claim:
        return True
    legal_overclaim = any(
        phrase in normalized
        for phrase in (
            "kanunsuz",
            "yasa disi",
            "illegal",
            "hukuka aykiri",
            "kesin ihlal",
        )
    )
    if hostile_claim or legal_overclaim:
        return True
    if facts.permission_execution_status is ToolExecutionStatus.SKIPPED and permission_claim:
        return True
    plan_claim = any(
        phrase in normalized
        for phrase in ("ucus plani var", "ucus plani yok", "plan dosyalandi", "plan iptal")
    )
    if facts.permission_execution_status is ToolExecutionStatus.SKIPPED and plan_claim:
        return True
    notam_claim = any(
        phrase in normalized
        for phrase in ("notam var", "notam yok", "aktif notam", "notam kisit", "notam yasak")
    )
    if facts.notam_execution_status is ToolExecutionStatus.SKIPPED and notam_claim:
        return True
    if _metadata_claim_is_invalid(normalized, inventory):
        return True
    consistency_flags = set(
        consistency.flags if consistency is not None else facts.operational_consistency_flags
    )
    substantive_flags = consistency_flags - {OperationalConsistencyFlag.INVENTORY_SCOPE_CONFIRMED}
    if (
        any(word in normalized for word in ("celiski", "tutarsiz", "uyumsuz"))
        and not substantive_flags
    ):
        return True

    platform_claim = any(normalize_guard_text(phrase) in normalized for phrase in _OVERCLAIM)
    authorized_claim = any(
        phrase in normalized for phrase in ("yetkili operasyon", "operasyon yetkili")
    )
    if facts.permission_status in _PERMISSION_PROBLEM and permission_claim:
        return True
    if (
        facts.flight_plan_status is FlightPlanStatus.FILED
        and facts.permission_status is not PermissionStatus.VALID
        and permission_claim
    ):
        return True
    if (
        facts.platform_status in {PlatformStatus.UNKNOWN, PlatformStatus.AMBIGUOUS}
        and platform_claim
    ):
        return True
    if verification.tool_health_status is ToolHealthStatus.FAILED and authorized_claim:
        return True
    return any(normalize_guard_text(phrase) in normalized for phrase in _OVERCLAIM)


def _unsupported_normative_claim(value: str) -> bool:
    """Reject untraceable absolute regulatory claims from free-form LLM evidence."""
    normalized = normalize_guard_text(value)
    normative = any(
        phrase in normalized for phrase in ("mutlak", "zorunlu", "yasaktir", "gereklidir")
    )
    regulatory = any(
        phrase in normalized
        for phrase in (
            "tescil",
            "ucus amaci",
            "ucus izni",
            "mevzuat",
            "askeri",
            "tehlikeli yuk",
        )
    )
    return normative and regulatory


class OutputGuard:
    """Validate decisions, sources, actions, risk alignment, and text claims."""

    def guard(
        self,
        decision: LLMDecision,
        *,
        constraints: EvidenceConstraints,
        facts: VerificationInput,
        verification: VerificationResult,
        risk: RiskResult,
        action_catalog: ActionCatalog,
        inventory: TurkeyInventoryResult | None = None,
        consistency: OperationalConsistencyResult | None = None,
    ) -> GuardResult:
        """Return a deterministic corrected decision without any LLM rewrite."""
        corrections: list[GuardCorrection] = []
        final_code = decision.decision_code
        if final_code not in constraints.allowed_decision_codes:
            replacement = constraints.allowed_decision_codes[0]
            corrections.append(
                GuardCorrection(
                    field="decision_code",
                    llm_value=final_code.value,
                    final_value=replacement.value,
                    reason="DECISION_NOT_ALLOWED",
                )
            )
            final_code = replacement

        source_ids = list(dict.fromkeys(decision.source_ids))
        valid_sources = [item for item in source_ids if item in constraints.allowed_source_ids]
        if valid_sources != source_ids:
            corrections.append(
                GuardCorrection(
                    field="source_ids",
                    llm_value=source_ids,
                    final_value=valid_sources,
                    reason="UNKNOWN_SOURCE_ID_REMOVED",
                )
            )

        definitions = {action.code: action for action in action_catalog.actions}
        allowed_codes = set(constraints.allowed_action_codes)
        platform_unresolved = _platform_is_unresolved(facts)
        if platform_unresolved:
            allowed_codes.intersection_update(_UNRESOLVED_PLATFORM_ACTIONS)
        actions: list[RecommendedAction] = []
        seen: set[str] = set()
        seen_reasons: set[str] = set()
        removed: list[str] = []
        for item in sorted(decision.recommended_actions, key=lambda value: value.priority):
            definition = definitions.get(item.action_code)
            reason_tr = (
                _UNRESOLVED_PLATFORM_ACTION_TEXT[item.action_code]
                if platform_unresolved and item.action_code in _UNRESOLVED_PLATFORM_ACTION_TEXT
                else _action_reason_tr(item.action_code, definition.title_tr, facts)
                if definition is not None
                else item.reason_tr.strip()
            )
            normalized_reason = normalize_guard_text(reason_tr)
            if (
                definition is None
                or item.action_code not in allowed_codes
                or risk.risk_level not in definition.allowed_risks
                or item.action_code in seen
                or normalized_reason in seen_reasons
                or _action_conflicts_with_execution(item.action_code, facts)
            ):
                removed.append(item.action_code)
                continue
            seen.add(item.action_code)
            seen_reasons.add(normalized_reason)
            actions.append(item.model_copy(update={"reason_tr": reason_tr}))
        if removed:
            corrections.append(
                GuardCorrection(
                    field="recommended_actions",
                    llm_value=removed,
                    final_value=[item.action_code for item in actions],
                    reason="INVALID_OR_RISK_INCOMPATIBLE_ACTION_REMOVED",
                )
            )

        required_actions = (
            list(_UNRESOLVED_PLATFORM_ACTIONS)
            if platform_unresolved
            else _minimum_actions(risk, facts, verification)
        )
        missing = [
            code
            for code in required_actions
            if code not in seen
            and code in definitions
            and code in allowed_codes
            and risk.risk_level in definitions[code].allowed_risks
            and not _action_conflicts_with_execution(code, facts)
        ]
        for code in missing:
            reason_tr = (
                _UNRESOLVED_PLATFORM_ACTION_TEXT[code]
                if platform_unresolved
                else _action_reason_tr(code, definitions[code].title_tr, facts)
            )
            normalized_reason = normalize_guard_text(reason_tr)
            if normalized_reason in seen_reasons:
                continue
            actions.append(
                RecommendedAction(
                    action_code=code,
                    priority=len(actions) + 1,
                    reason_tr=reason_tr,
                )
            )
            seen.add(code)
            seen_reasons.add(normalized_reason)
        if missing:
            corrections.append(
                GuardCorrection(
                    field="recommended_actions",
                    llm_value=[item.action_code for item in decision.recommended_actions],
                    final_value=[item.action_code for item in actions],
                    reason="MINIMUM_ACTIONS_ADDED",
                )
            )
        if platform_unresolved:
            action_order = {code: index for index, code in enumerate(_UNRESOLVED_PLATFORM_ACTIONS)}
            actions.sort(key=lambda item: action_order[item.action_code])
        protected_codes: list[str] = []
        if constraints.human_review_required:
            protected_codes.append("REQUEST_OPERATOR_REVIEW")
        if _unregistered_military_policy_applies(facts):
            protected_codes.append("ESCALATE_TO_AUTHORIZED_UNIT")
        if facts.flight_plan_status is FlightPlanStatus.FILED:
            protected_codes.append("CHECK_FLIGHT_PLAN_RECORDS")
        if len(actions) > _MAX_RECOMMENDED_ACTIONS:
            kept = actions[:_MAX_RECOMMENDED_ACTIONS]
            for code in protected_codes:
                protected_action = next(
                    (item for item in actions if item.action_code == code),
                    None,
                )
                if protected_action is None or protected_action in kept:
                    continue
                replace_at = next(
                    (
                        index
                        for index in range(len(kept) - 1, -1, -1)
                        if kept[index].action_code not in protected_codes
                    ),
                    None,
                )
                if replace_at is not None:
                    kept[replace_at] = protected_action
            removed_for_limit = [item.action_code for item in actions if item not in kept]
            actions = kept
            corrections.append(
                GuardCorrection(
                    field="recommended_actions",
                    llm_value=removed_for_limit,
                    final_value=[item.action_code for item in actions],
                    reason="ACTION_LIMIT_APPLIED",
                )
            )
        actions = [
            item.model_copy(update={"priority": index}) for index, item in enumerate(actions, 1)
        ]

        summary = decision.summary_tr.strip()
        if _summary_contradicts(summary, facts, verification, inventory, consistency):
            replacement_summary = _safe_summary(facts, verification, inventory)
            corrections.append(
                GuardCorrection(
                    field="summary_tr",
                    llm_value=summary,
                    final_value=replacement_summary,
                    reason="TOOL_CONTRADICTION_OR_VISUAL_OVERCLAIM",
                )
            )
            summary = replacement_summary

        evidence_summary = [
            item
            for item in decision.evidence_summary
            if not _summary_contradicts(item, facts, verification, inventory, consistency)
            and not _unsupported_normative_claim(item)
        ]
        if evidence_summary != decision.evidence_summary:
            corrections.append(
                GuardCorrection(
                    field="evidence_summary",
                    llm_value=decision.evidence_summary,
                    final_value=evidence_summary,
                    reason="UNSUPPORTED_OR_CONTRADICTORY_EVIDENCE_REMOVED",
                )
            )

        corrected = decision.model_copy(
            update={
                "decision_code": final_code,
                "summary_tr": summary,
                "evidence_summary": evidence_summary,
                "source_ids": valid_sources,
                "recommended_actions": actions,
            }
        )
        return GuardResult(corrected, corrections)
