"""YAML-driven deterministic risk selection and confidence indicators."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import cast

import yaml

from operational_decision.contracts.common import (
    ContextStatus,
    FlightPlanStatus,
    InventoryStatus,
    NotamOperationEffect,
    PermissionStatus,
    PlatformStatus,
    RecordConsistency,
    RiskLevel,
    ToolHealthStatus,
    UncertaintyLevel,
    VerificationStatus,
    VisualEvidenceStatus,
)
from operational_decision.contracts.risk import RiskResult
from operational_decision.contracts.verification import VerificationInput, VerificationResult
from operational_decision.decision.verification_checker import (
    is_military_listed_foreign_origin,
    is_military_listed_unknown_origin,
    is_unregistered_military_policy,
    is_unregistered_military_turkey_claim,
)

_RISK_ORDER = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.CRITICAL: 3,
}
_CONTEXT_SCORE = {
    ContextStatus.COMPLETE: 1.0,
    ContextStatus.PARTIAL: 0.6,
    ContextStatus.INACTIVE: 0.2,
    ContextStatus.MISSING: 0.0,
    ContextStatus.INVALID: 0.0,
}
_VERIFICATION_SCORE = {
    VerificationStatus.VERIFIED: 1.0,
    VerificationStatus.UNVERIFIED: 1.0,
    VerificationStatus.NOT_APPLICABLE: 1.0,
    VerificationStatus.PARTIALLY_VERIFIED: 0.7,
    VerificationStatus.INDETERMINATE: 0.3,
}
_ALLOWED_FIELDS = {
    "context_status",
    "inventory_status",
    "inventory_execution_status",
    "operational_consistency_status",
    "operational_consistency_flags",
    "tool_health_status",
    "verification_status",
    "platform_status",
    "platform_usage_domain",
    "vlm_origin_category",
    "permission_status",
    "flight_plan_status",
    "record_consistency",
    "notam_status",
    "notam_operation_effect",
    "uncertainty_level",
    "visual_class",
    "visual_evidence_status",
}


@dataclass(frozen=True, slots=True)
class _RiskRule:
    rule_id: str
    priority: int
    conditions: dict[str, str | tuple[str, ...]]
    minimum_risk: RiskLevel
    human_review: bool

    @property
    def specificity(self) -> float:
        return 1.0 if len(self.conditions) > 1 else 0.85


def calculate_tool_coverage(verification: VerificationResult) -> float:
    """Calculate successful required tools divided by all required tools."""
    if not verification.required_tools:
        return 1.0
    return round(
        len(verification.successful_required_tools) / len(verification.required_tools),
        3,
    )


def calculate_evidence_quality(
    *,
    visual_confidence: float,
    tool_coverage_score: float,
    context_status: ContextStatus,
    verification_status: VerificationStatus,
) -> float:
    """Apply the specification-defined internal evidence quality formula."""
    if not 0.0 <= visual_confidence <= 1.0:
        raise ValueError("visual_confidence must be between 0 and 1")
    if not 0.0 <= tool_coverage_score <= 1.0:
        raise ValueError("tool_coverage_score must be between 0 and 1")
    return round(
        0.45 * visual_confidence
        + 0.25 * tool_coverage_score
        + 0.20 * _CONTEXT_SCORE[context_status]
        + 0.10 * _VERIFICATION_SCORE[verification_status],
        3,
    )


def calculate_risk_assessment_confidence(
    evidence_quality_score: float,
    rule_specificity: float,
    risk_level: RiskLevel,
) -> float:
    """Calculate risk confidence and cap UNKNOWN at 0.50."""
    confidence = round(evidence_quality_score * rule_specificity, 3)
    return min(confidence, 0.5) if risk_level is RiskLevel.UNKNOWN else confidence


def calculate_decision_confidence(
    evidence_quality_score: float, risk_assessment_confidence: float
) -> float:
    """Use the lower deterministic quality indicator."""
    return round(min(evidence_quality_score, risk_assessment_confidence), 3)


def _string_value(value: object) -> str:
    if isinstance(value, StrEnum):
        return value.value
    return str(value)


def _fact_values(
    facts: VerificationInput, verification: VerificationResult
) -> dict[str, str | tuple[str, ...]]:
    return {
        "context_status": facts.context_status.value,
        "inventory_status": facts.inventory_status.value,
        "inventory_execution_status": facts.inventory_execution_status.value,
        "operational_consistency_status": facts.operational_consistency_status.value,
        "operational_consistency_flags": tuple(
            flag.value for flag in facts.operational_consistency_flags
        ),
        "tool_health_status": verification.tool_health_status.value,
        "verification_status": verification.verification_status.value,
        "platform_status": facts.platform_status.value,
        "platform_usage_domain": facts.platform_usage_domain.value,
        "vlm_origin_category": facts.vlm_origin_category.value,
        "permission_status": facts.permission_status.value,
        "flight_plan_status": facts.flight_plan_status.value,
        "record_consistency": facts.record_consistency.value,
        "notam_status": facts.notam_status.value,
        "notam_operation_effect": facts.notam_operation_effect.value,
        "uncertainty_level": facts.uncertainty_level.value,
        "visual_class": facts.visual_class.value,
        "visual_evidence_status": facts.visual_evidence_status.value,
    }


def _matches(rule: _RiskRule, values: dict[str, str | tuple[str, ...]]) -> bool:
    for field_name, expected in rule.conditions.items():
        actual = values[field_name]
        if isinstance(actual, tuple):
            if isinstance(expected, tuple):
                if not set(actual).intersection(expected):
                    return False
            elif expected not in actual:
                return False
        elif isinstance(expected, tuple):
            if actual not in expected:
                return False
        elif actual != expected:
            return False
    return True


def _risk_factors(
    facts: VerificationInput,
    verification: VerificationResult,
) -> tuple[list[str], list[str]]:
    """Explain risk using only validated facts, without changing rule selection."""
    increasing: list[str] = []
    reducing: list[str] = []

    if (
        is_unregistered_military_policy(
            platform_usage_domain=facts.platform_usage_domain,
            inventory_execution_status=facts.inventory_execution_status,
            inventory_status=facts.inventory_status,
        )
        and facts.platform_status in {PlatformStatus.EXPECTED, PlatformStatus.NOT_EXPECTED}
        and facts.context_status is ContextStatus.COMPLETE
    ):
        increasing.append(
            "Askerî kullanım alanındaki platform Türkiye Inventory veri setinde kayıtlı değildir."
        )
        if is_unregistered_military_turkey_claim(facts):
            increasing.append(
                "VLM ülke hipotezi Türkiye kökenini beyan etmektedir ancak platform Türkiye "
                "Inventory veri setinde kayıtlı değildir; bu çelişki şüpheli kabul edilmeli "
                "ve ayrıca doğrulanmalıdır."
            )

    if is_military_listed_foreign_origin(facts):
        increasing.append(
            "VLM ülke hipotezi, Türkiye Inventory veri setinde kayıtlı askerî platform için "
            "yabancı kökeni işaret etmektedir; yabancı askerî aidiyet şüphesi bulunmaktadır."
        )
    elif is_military_listed_unknown_origin(facts):
        increasing.append(
            "VLM ülke hipotezi belirlenemediğinden Türkiye Inventory veri setinde kayıtlı "
            "askerî platformun aidiyeti bu aşamada belirlenememiştir."
        )

    if verification.tool_health_status is ToolHealthStatus.FAILED:
        increasing.append("Gerekli operasyonel kontrollerden en az biri tamamlanamadı.")
    if facts.platform_status is PlatformStatus.NOT_EXPECTED:
        increasing.append("Platform seçilen operasyon bağlamında beklenmiyor.")
    elif facts.platform_status in {PlatformStatus.UNKNOWN, PlatformStatus.AMBIGUOUS}:
        increasing.append("Platform kimliği Registry üzerinde kesin çözümlenemedi.")
    elif facts.platform_status is PlatformStatus.EXPECTED:
        reducing.append("Platform seçilen operasyon bağlamında beklenen olarak kayıtlı.")

    if facts.permission_status is PermissionStatus.VALID:
        reducing.append("Geçerli Permission kaydı doğrulandı.")
    elif facts.permission_status is PermissionStatus.NOT_FOUND:
        increasing.append(
            "Permission kaydı bulunamadı; bu durum tek başına izinsiz uçuş kanıtı değildir."
        )
    elif facts.permission_status in {
        PermissionStatus.EXPIRED,
        PermissionStatus.NOT_YET_VALID,
        PermissionStatus.REVOKED,
        PermissionStatus.AMBIGUOUS,
        PermissionStatus.CONFLICTING,
    }:
        increasing.append("Permission kaydı geçerli olarak doğrulanamadı.")

    if facts.flight_plan_status is FlightPlanStatus.FILED:
        if (
            facts.permission_status is PermissionStatus.VALID
            and facts.record_consistency is not RecordConsistency.CONFLICTING
        ):
            reducing.append("Uçuş planı kaydı bulundu; bu kayıt tek başına izin değildir.")
        else:
            increasing.append(
                "Uçuş planı kayıtlıdır ancak geçerli uçuş izniyle birlikte doğrulanamamıştır."
            )
    elif facts.flight_plan_status is FlightPlanStatus.NOT_FOUND:
        increasing.append("Flight Plan kaydı bulunamadı.")
    elif facts.flight_plan_status in {
        FlightPlanStatus.EXPIRED,
        FlightPlanStatus.NOT_YET_ACTIVE,
        FlightPlanStatus.CANCELLED,
        FlightPlanStatus.AMBIGUOUS,
        FlightPlanStatus.CONFLICTING,
    }:
        increasing.append("Flight Plan kaydı operasyonla uyumlu olarak doğrulanamadı.")

    if facts.notam_operation_effect is NotamOperationEffect.PROHIBITS_OPERATION:
        increasing.append("Aktif NOTAM operasyonu yasaklıyor.")
    elif facts.notam_operation_effect in {
        NotamOperationEffect.RESTRICTS_OPERATION,
        NotamOperationEffect.CONFLICTS_WITH_PERMISSION,
    }:
        increasing.append("Aktif NOTAM operasyonu kısıtlıyor veya Permission ile çelişiyor.")
    elif facts.notam_operation_effect is NotamOperationEffect.NO_EFFECT:
        reducing.append(
            "Operasyonu kısıtlayan aktif NOTAM etkisi bulunmadı; bu durum yetki kanıtı değildir."
        )

    if facts.uncertainty_level is UncertaintyLevel.HIGH:
        increasing.append("Görsel kanıt belirsizliği yüksek.")
    if facts.visual_evidence_status in {
        VisualEvidenceStatus.WEAK,
        VisualEvidenceStatus.CONFLICTING,
        VisualEvidenceStatus.INSUFFICIENT,
    }:
        increasing.append("Görsel kanıt kimliği kesin doğrulamak için yetersiz veya çelişkili.")

    return list(dict.fromkeys(increasing)), list(dict.fromkeys(reducing))


def _risk_uncertainties(
    facts: VerificationInput,
    verification: VerificationResult,
) -> list[str]:
    """Describe evidentiary limits without changing risk selection."""
    uncertainties: list[str] = []
    if is_military_listed_unknown_origin(facts):
        uncertainties.append(
            "VLM ülke hipotezinin belirlenememesi aracın aidiyetini kesin olarak belirlemez."
        )
    if facts.visual_human_review_required:
        uncertainties.append("Görsel platform kimliği kesin doğrulanmış değildir.")
    if facts.inventory_status is InventoryStatus.NOT_LISTED:
        uncertainties.append(
            "Türkiye Inventory kaydının bulunmaması tek başına tehdit veya "
            "izinsiz uçuş kanıtı değildir."
        )
    if facts.permission_status is PermissionStatus.NOT_FOUND:
        uncertainties.append(
            "Permission kaydının bulunmaması kesin olarak izinsiz uçuş anlamına gelmez."
        )
    if (
        facts.flight_plan_status is FlightPlanStatus.FILED
        and facts.permission_status is not PermissionStatus.VALID
    ):
        uncertainties.append("Flight Plan kaydı tek başına operasyonel izin sağlamaz.")
    if facts.notam_operation_effect is NotamOperationEffect.NO_EFFECT:
        uncertainties.append(
            "Aktif NOTAM çatışması bulunmaması operasyonun yetkili olduğunu kanıtlamaz."
        )
    if verification.tool_health_status is ToolHealthStatus.FAILED:
        uncertainties.append("Teknik olarak tamamlanamayan kontroller nedeniyle sonuç eksiktir.")
    return list(dict.fromkeys(uncertainties))


def _risk_explanation(
    risk_level: RiskLevel,
    selected_rule_id: str,
    increasing: list[str],
    reducing: list[str],
    facts: VerificationInput,
) -> str:
    if selected_rule_id == "RULE_UNREGISTERED_MILITARY_PLATFORM":
        explanation = (
            "Platform askerî kullanım alanında olup Türkiye Inventory veri setinde "
            "kayıtlı değildir."
        )
        if is_unregistered_military_turkey_claim(facts):
            explanation += (
                " VLM ülke hipotezi Türkiye kökenini beyan etmektedir ancak bu beyan "
                "Türkiye Inventory kaydıyla doğrulanamamıştır; bu çelişki şüpheli kabul "
                "edilmeli ve ayrıca doğrulanmalıdır."
            )
        return explanation

    labels = {
        RiskLevel.LOW: "düşük",
        RiskLevel.MEDIUM: "orta",
        RiskLevel.HIGH: "yüksek",
        RiskLevel.CRITICAL: "kritik",
        RiskLevel.UNKNOWN: "belirlenemeyen",
    }
    explanation = (
        f"Risk seviyesi {selected_rule_id} deterministik kuralıyla "
        f"{labels[risk_level]} olarak belirlenmiştir."
    )
    if increasing:
        explanation += " Risk artıran başlıca bulgu: " + increasing[0]
    if reducing:
        explanation += " Risk azaltan başlıca bulgu: " + reducing[0]
    return explanation


def _parse_condition(value: object) -> str | tuple[str, ...]:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        typed = cast(dict[object, object], value)
        allowed = typed.get("in")
        if isinstance(allowed, list) and all(isinstance(item, str) for item in allowed):
            return tuple(cast(list[str], allowed))
    raise ValueError("risk condition must be a string or an in-list")


def _parse_rules(payload: object) -> list[_RiskRule]:
    if not isinstance(payload, dict):
        raise ValueError("risk rules YAML must be an object")
    root = cast(dict[object, object], payload)
    raw_rules = root.get("rules")
    if not isinstance(raw_rules, list):
        raise ValueError("risk rules YAML must contain a rules list")
    rules: list[_RiskRule] = []
    seen_ids: set[str] = set()
    for raw_rule in raw_rules:
        if not isinstance(raw_rule, dict):
            raise ValueError("each risk rule must be an object")
        item = cast(dict[object, object], raw_rule)
        rule_id = item.get("id")
        priority = item.get("priority")
        raw_when = item.get("when")
        minimum_risk = item.get("minimum_risk")
        human_review = item.get("human_review")
        if not isinstance(rule_id, str) or not rule_id:
            raise ValueError("risk rule id must be a non-empty string")
        if rule_id in seen_ids:
            raise ValueError(f"duplicate risk rule id: {rule_id}")
        if not isinstance(priority, int) or isinstance(priority, bool):
            raise ValueError(f"risk rule priority must be an integer: {rule_id}")
        if not isinstance(raw_when, dict) or not raw_when:
            raise ValueError(f"risk rule conditions cannot be empty: {rule_id}")
        if not isinstance(minimum_risk, str):
            raise ValueError(f"minimum_risk must be a string: {rule_id}")
        if not isinstance(human_review, bool):
            raise ValueError(f"human_review must be boolean: {rule_id}")
        conditions: dict[str, str | tuple[str, ...]] = {}
        for raw_name, raw_value in cast(dict[object, object], raw_when).items():
            if not isinstance(raw_name, str) or raw_name not in _ALLOWED_FIELDS:
                raise ValueError(f"unknown risk condition field: {raw_name}")
            conditions[raw_name] = _parse_condition(raw_value)
        rules.append(
            _RiskRule(
                rule_id=rule_id,
                priority=priority,
                conditions=conditions,
                minimum_risk=RiskLevel(minimum_risk),
                human_review=human_review,
            )
        )
        seen_ids.add(rule_id)
    return sorted(rules, key=lambda rule: (-rule.priority, rule.rule_id))


class RiskAdvisor:
    """Evaluate validated YAML rules without LLM participation."""

    def __init__(self, rules: list[_RiskRule]) -> None:
        """Store priority-ordered deterministic rules."""
        self._rules = rules

    @classmethod
    def from_yaml(cls, path: Path) -> "RiskAdvisor":
        """Load and validate a YAML risk rule file."""
        return cls(_parse_rules(yaml.safe_load(path.read_text(encoding="utf-8"))))

    def assess(self, facts: VerificationInput, verification: VerificationResult) -> RiskResult:
        """Combine matching minimum risks, review flags, and confidence indicators."""
        values = _fact_values(facts, verification)
        matching = [rule for rule in self._rules if _matches(rule, values)]
        if not matching:
            selected = _RiskRule(
                rule_id="RULE_FALLBACK_UNKNOWN",
                priority=0,
                conditions={},
                minimum_risk=RiskLevel.UNKNOWN,
                human_review=True,
            )
            matched_rule_ids = [selected.rule_id]
            specificity = 0.5
            risk_level = RiskLevel.UNKNOWN
            human_review = True
        else:
            unknown_rules = [rule for rule in matching if rule.minimum_risk is RiskLevel.UNKNOWN]
            if unknown_rules:
                selected = max(unknown_rules, key=lambda rule: rule.priority)
                risk_level = RiskLevel.UNKNOWN
            else:
                selected = max(
                    matching,
                    key=lambda rule: (_RISK_ORDER[rule.minimum_risk], rule.priority),
                )
                risk_level = selected.minimum_risk
            matched_rule_ids = [rule.rule_id for rule in matching]
            specificity = selected.specificity
            human_review = risk_level is not RiskLevel.LOW and (
                facts.visual_human_review_required
                or any(rule.human_review for rule in matching)
            )

        if is_military_listed_foreign_origin(facts) or is_military_listed_unknown_origin(facts):
            human_review = True

        evidence_quality = calculate_evidence_quality(
            visual_confidence=facts.visual_confidence,
            tool_coverage_score=calculate_tool_coverage(verification),
            context_status=facts.context_status,
            verification_status=verification.verification_status,
        )
        risk_confidence = calculate_risk_assessment_confidence(
            evidence_quality, specificity, risk_level
        )
        increasing_factors, reducing_factors = _risk_factors(facts, verification)
        return RiskResult(
            risk_level=risk_level,
            minimum_risk_level=risk_level,
            human_review_required=human_review,
            human_review_priority=(
                "URGENT"
                if selected.rule_id
                in {
                    "RULE_UNREGISTERED_MILITARY_PLATFORM",
                    "RULE_NOTAM_PROHIBITS_OPERATION",
                }
                or is_military_listed_foreign_origin(facts)
                else "NORMAL"
            ),
            matched_rule_ids=matched_rule_ids,
            selected_rule_id=selected.rule_id,
            rule_specificity=specificity,
            evidence_quality_score=evidence_quality,
            risk_assessment_confidence=risk_confidence,
            decision_confidence=calculate_decision_confidence(evidence_quality, risk_confidence),
            explanation=_risk_explanation(
                risk_level,
                selected.rule_id,
                increasing_factors,
                reducing_factors,
                facts,
            ),
            increasing_factors=increasing_factors,
            reducing_factors=reducing_factors,
            uncertainties=_risk_uncertainties(facts, verification),
        )
