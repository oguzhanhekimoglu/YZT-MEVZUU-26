"""Deterministic context-free assessment of one raw VLM output."""

import re
import unicodedata
from pathlib import Path

from operational_decision.contracts.common import (
    DecisionCode,
    InventoryStatus,
    RiskLevel,
    VlmOriginCategory,
)
from operational_decision.contracts.platform import PlatformOrigin, UsageDomain
from operational_decision.contracts.raw_vlm import RawVLMOutput
from operational_decision.contracts.raw_vlm_assessment import (
    OriginComparisonStatus,
    RawVLMAssessmentResult,
)
from operational_decision.decision.vlm_origin import classify_vlm_origin
from operational_decision.input.raw_vlm_adapter import normalize_raw_model_hypothesis
from operational_decision.input.video_event_adapter import map_video_event_projection
from operational_decision.inventory.turkey_inventory_registry import (
    load_turkey_inventory_registry,
)
from operational_decision.platform.platform_registry import (
    PlatformRegistryIndex,
    load_platform_aliases,
    load_platform_registry,
)

_UNKNOWN_ORIGIN_WORDS = {
    "",
    "bilinmiyor",
    "bilinmeyen",
    "unknown",
    "belirsiz",
    "tespit edilemedi",
}
_COUNTRY_ALIASES = {
    "TR": {"tr", "turkiye", "turkey", "turkiye cumhuriyeti", "turk"},
    "US": {
        "us",
        "usa",
        "abd",
        "amerika",
        "amerika birlesik devletleri",
        "united states",
        "united states of america",
    },
}
_COUNTRY_NAMES_TR = {"TR": "Türkiye", "US": "Amerika Birleşik Devletleri"}


def _normalize_origin(value: str | None) -> str:
    if value is None:
        return ""
    decomposed = unicodedata.normalize("NFKD", value).casefold()
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", plain).split())


def _compare_origin(
    hypothesis: str | None,
    country_code: str | None,
    platform_resolved: bool,
    inventory_status: InventoryStatus,
) -> OriginComparisonStatus:
    if not platform_resolved:
        return OriginComparisonStatus.PLATFORM_UNRESOLVED
    normalized = _normalize_origin(hypothesis)
    if normalized in _UNKNOWN_ORIGIN_WORDS:
        return OriginComparisonStatus.UNKNOWN_HYPOTHESIS
    if normalized in _COUNTRY_ALIASES["TR"]:
        if inventory_status is InventoryStatus.UNKNOWN:
            return OriginComparisonStatus.OPERATOR_AFFILIATION_UNVERIFIED
        return (
            OriginComparisonStatus.TURKEY_INVENTORY_COMPATIBLE
            if inventory_status is InventoryStatus.CONFIRMED
            else OriginComparisonStatus.MISMATCH
        )
    if country_code is not None and normalized in _COUNTRY_ALIASES.get(
        country_code, {country_code.casefold()}
    ):
        return OriginComparisonStatus.MANUFACTURER_COUNTRY_COMPATIBLE
    return OriginComparisonStatus.OPERATOR_AFFILIATION_UNVERIFIED


def assess_raw_vlm(
    raw_vlm: RawVLMOutput,
    *,
    platform_registry_path: Path,
    platform_aliases_path: Path,
    inventory_path: Path | None,
) -> RawVLMAssessmentResult:
    """Resolve Registry, origin consistency, and Inventory without operational context."""
    platform_registry = load_platform_registry(platform_registry_path)
    platform_index = PlatformRegistryIndex(
        platform_registry,
        load_platform_aliases(platform_aliases_path),
    )
    inventory = (
        load_turkey_inventory_registry(inventory_path, platform_registry)
        if inventory_path is not None
        else None
    )
    hypothesis = normalize_raw_model_hypothesis(raw_vlm.hedef_modeli)
    platform = platform_index.find_exact_match(hypothesis) if hypothesis else None
    resolved = platform is not None
    country_code = platform.manufacturer_country_code if platform else None
    inventory_record = (
        inventory.find_active(platform.platform_id)
        if platform is not None and inventory is not None
        else None
    )
    if not resolved or inventory is None:
        inventory_status = InventoryStatus.UNKNOWN
    elif inventory_record is None:
        inventory_status = InventoryStatus.NOT_LISTED
    else:
        inventory_status = InventoryStatus.CONFIRMED
    comparison = _compare_origin(
        raw_vlm.ulke_orjini,
        country_code,
        resolved,
        inventory_status,
    )
    usage_domain = (
        platform.taxonomy.usage_domain
        if platform is not None and platform.taxonomy is not None
        else UsageDomain.UNKNOWN
    )
    vlm_origin_category = classify_vlm_origin(raw_vlm.ulke_orjini)
    military_listed = usage_domain is UsageDomain.MILITARY and inventory_status is (
        InventoryStatus.CONFIRMED
    )
    military_not_listed = (
        usage_domain is UsageDomain.MILITARY and inventory_status is InventoryStatus.NOT_LISTED
    )
    military_turkey_claim_mismatch = (
        military_not_listed and vlm_origin_category is VlmOriginCategory.TURKEY
    )

    origin_risk_note = ""
    if military_listed and vlm_origin_category is VlmOriginCategory.FOREIGN:
        risk = RiskLevel.HIGH
        origin_risk_note = (
            " VLM ülke hipotezi yabancı bir ülkeyi işaret ettiğinden yabancı askerî aidiyet "
            "şüphesi bulunmaktadır; bu ön bulgu risk seviyesini yükseltir ve acil insan "
            "incelemesi gerektirir."
        )
    elif military_listed and vlm_origin_category is VlmOriginCategory.UNKNOWN:
        risk = RiskLevel.MEDIUM
        origin_risk_note = (
            " VLM ülke hipotezi belirlenemediğinden aracın aidiyeti bu aşamada "
            "belirlenememiştir; bu durum düşük riskli olarak değerlendirilemez."
        )
    elif military_turkey_claim_mismatch:
        risk = RiskLevel.HIGH
        origin_risk_note = (
            " VLM ülke hipotezi Türkiye kökenini beyan etmektedir ancak platform Türkiye "
            "Inventory veri setinde kayıtlı değildir; bu çelişki şüpheli kabul edilmeli "
            "ve ayrıca doğrulanmalıdır."
        )
    else:
        risk = RiskLevel.UNKNOWN

    if comparison is OriginComparisonStatus.MISMATCH and military_turkey_claim_mismatch:
        origin_explanation = (
            "VLM Türkiye kullanım hipotezi mevcut Turkey Inventory kaydıyla desteklenmiyor; "
            "askerî kullanım alanındaki bu platform için beyan edilen Türkiye kökeni "
            "doğrulanamadığından çelişki şüpheli kabul edilmelidir."
        )
    elif comparison is OriginComparisonStatus.MISMATCH:
        origin_explanation = (
            "VLM Türkiye kullanım hipotezi mevcut Turkey Inventory kaydıyla "
            "desteklenmiyor. Bu sonuç tek başına yabancı, izinsiz veya riskli anlamına gelmez."
        )
    elif comparison is OriginComparisonStatus.TURKEY_INVENTORY_COMPATIBLE:
        origin_explanation = (
            "VLM Türkiye kullanım hipotezi mevcut Turkey Inventory kaydıyla uyumludur; "
            "bu sonuç tek başına uçuş izni veya güvenli operasyon anlamına gelmez."
        )
    elif comparison is OriginComparisonStatus.MANUFACTURER_COUNTRY_COMPATIBLE:
        origin_explanation = (
            "VLM ülke hipotezi Registry üretici ülkesiyle uyumludur; operatör aidiyeti "
            "bu karşılaştırmayla kesinleştirilmez."
        )
    elif comparison is OriginComparisonStatus.OPERATOR_AFFILIATION_UNVERIFIED:
        origin_explanation = (
            "VLM ülke/operatör hipotezi mevcut üretici ülke ve Türkiye Inventory "
            "kayıtlarıyla doğrulanamadı. Bu sonuç hipotezi kesin aidiyet veya yanlış "
            "aidiyet olarak sınıflandırmaz."
        )
    elif comparison is OriginComparisonStatus.PLATFORM_UNRESOLVED:
        origin_explanation = "Platform çözümlenemediği için ülke hipotezi değerlendirilemedi."
    else:
        origin_explanation = (
            "VLM ülke hipotezi kesin bilgiye dönüştürülmedi; Registry ve Inventory sonuçları "
            "bağımsız olarak korunmuştur."
        )

    decision = DecisionCode.INDETERMINATE if resolved else DecisionCode.PLATFORM_UNRESOLVED
    event_projection = map_video_event_projection(
        raw_vlm.video_events,
        visual_assessment_tr=raw_vlm.gorsel_analiz,
    )
    platform_text = platform.canonical_name if platform else "çözümlenemeyen platform"
    final_risk_clause = (
        "operasyonel doğrulama tamamlanamadı; nihai karar için insan incelemesi gereklidir."
        if origin_risk_note
        else "operasyonel doğrulama ve nihai risk belirlenemedi."
    )
    summary = (
        f"Görsel hipotez {platform_text} olarak değerlendirildi. {origin_explanation} "
        f"Turkey Inventory sonucu {inventory_status.value}. Operasyon alanı ve gözlem zamanı "
        "sağlanmadığı için Permission, Flight Plan ve NOTAM değerlendirilmedi;"
        f"{origin_risk_note} Bu nedenle {final_risk_clause}"
    )
    return RawVLMAssessmentResult(
        raw_vlm=raw_vlm,
        normalized_model_hypothesis=hypothesis,
        platform_resolved=resolved,
        platform_id=platform.platform_id if platform else None,
        matched_platform=platform.canonical_name if platform else None,
        registry_platform_origin=(platform.platform_origin if platform else PlatformOrigin.UNKNOWN),
        registry_country_code=country_code,
        vlm_origin_hypothesis=raw_vlm.ulke_orjini,
        vlm_origin_category=vlm_origin_category,
        origin_comparison=comparison,
        origin_explanation_tr=origin_explanation,
        inventory_status=inventory_status,
        inventory_operator_name=(inventory_record.operator_name if inventory_record else None),
        inventory_service_status=(inventory_record.service_status if inventory_record else None),
        risk_level=risk,
        decision=decision,
        summary_tr=summary,
        recommended_actions=[
            "Platform ve ülke hipotezini insan incelemesiyle doğrula.",
            "Operasyonel izin değerlendirmesi için alan ve gözlem zamanı sağla.",
        ],
        timestamped_events=event_projection.timestamped_events,
        timestamps_available=event_projection.timestamps_available,
        event_extraction_status=event_projection.event_extraction_status,
        untimestamped_visual_assessment=event_projection.untimestamped_visual_assessment,
    )
