"""Deterministic Turkish presentation report for finalized operational facts."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any

_RISK_LABELS = {
    "LOW": "düşük",
    "MEDIUM": "orta",
    "HIGH": "yüksek",
    "CRITICAL": "kritik",
    "UNKNOWN": "belirlenemedi",
}
_VERIFICATION_LABELS = {
    "VERIFIED": "doğrulandı",
    "PARTIALLY_VERIFIED": "kısmen doğrulandı",
    "UNVERIFIED": "doğrulanamadı",
    "INDETERMINATE": "belirlenemedi",
    "NOT_APPLICABLE": "uygulanabilir değil",
}
_DECISION_LABELS = {
    "AUTHORIZED_OPERATIONAL_MATCH": "operasyonel kayıtlarla uyumlu eşleşme",
    "PARTIALLY_VERIFIED_OPERATION": "kısmen doğrulanmış operasyon",
    "UNVERIFIED_AIRCRAFT": "doğrulanmamış hava aracı",
    "OPERATIONAL_AUTHORIZATION_UNVERIFIED": "operasyonel yetkilendirme doğrulanamadı",
    "UNREGISTERED_MILITARY_AIRCRAFT": ("Türkiye Envanterinde kayıtlı olmayan askerî hava aracı"),
    "UNEXPECTED_PLATFORM": "operasyon bağlamında beklenmeyen platform",
    "EXPIRED_OR_INVALID_PERMISSION": "geçersiz veya süresi dolmuş izin",
    "ACTIVE_NOTAM_PROHIBITION": "aktif NOTAM operasyonu yasaklıyor",
    "CONFLICTING_OPERATIONAL_RECORDS": "çelişkili operasyonel kayıtlar",
    "PLATFORM_UNRESOLVED": "platform çözümlenemedi",
    "NON_AIRCRAFT": "hava aracı olmayan hedef",
    "INDETERMINATE": "insan incelemesi gerektiren belirsiz sonuç",
    "REJECTED_OUT_OF_SCOPE": "Türkiye Envanteri kapsamı dışında reddedildi",
}
_USER_DECISION_LABELS = {
    **_DECISION_LABELS,
    "AUTHORIZED_OPERATIONAL_MATCH": "Operasyonel kayıtlarla uyumlu yetkili operasyon",
    "PARTIALLY_VERIFIED_OPERATION": "Operasyon kısmen doğrulandı",
    "UNVERIFIED_AIRCRAFT": "Hava aracı operasyonel olarak doğrulanamadı",
    "OPERATIONAL_AUTHORIZATION_UNVERIFIED": "Operasyonel yetkilendirme doğrulanamadı",
    "UNREGISTERED_MILITARY_AIRCRAFT": ("Türkiye Envanterinde kayıtlı olmayan askerî hava aracı"),
    "UNEXPECTED_PLATFORM": "Operasyon bağlamında beklenmeyen platform",
    "EXPIRED_OR_INVALID_PERMISSION": "Uçuş izni geçersiz veya süresi dolmuş",
    "ACTIVE_NOTAM_PROHIBITION": "Aktif NOTAM operasyonu yasaklıyor",
    "CONFLICTING_OPERATIONAL_RECORDS": "Operasyonel kayıtlar birbiriyle çelişiyor",
    "PLATFORM_UNRESOLVED": "Platform çözümlenemedi",
    "NON_AIRCRAFT": "Hava aracı olmayan hedef",
    "INDETERMINATE": "Sonuç insan incelemesi olmadan belirlenemedi",
    "REJECTED_OUT_OF_SCOPE": "Türkiye Envanteri kapsamı dışında",
}
_VISUAL_CLASS_LABELS = {
    "FIGHTER_JET": "savaş uçağı",
    "UAV": "İHA",
    "UCAV": "SİHA",
    "HELICOPTER": "helikopter",
    "TRANSPORT_AIRCRAFT": "nakliye uçağı",
    "CIVILIAN_AIRCRAFT": "sivil hava aracı",
    "MICRO_DRONE": "mikro İHA",
    "UNKNOWN_AIRCRAFT": "hava aracı",
    "NON_AIRCRAFT": "hava aracı olmayan hedef",
}


def risk_label_tr(value: object) -> str:
    """Return a user-facing Turkish risk label without exposing enum syntax."""
    return _RISK_LABELS.get(str(value), "belirlenemedi").capitalize()


def decision_label_tr(value: object) -> str:
    """Return a user-facing Turkish decision label without exposing enum syntax."""
    return _USER_DECISION_LABELS.get(str(value), "Nihai karar belirlenemedi")


_CONSISTENCY_LABELS = {
    "CONSISTENT": "tutarlı",
    "FLAGGED": "inceleme gerektiren bulgular içeriyor",
    "INDETERMINATE": "belirlenemedi",
    "NOT_APPLICABLE": "uygulanabilir değil",
}
_TECHNICAL_EXECUTIONS = {"ERROR", "TIMEOUT", "INVALID_INPUT"}
_POLICY_DESCRIPTION = (
    "Platform Türkiye Envanterinde kayıtlı değildir; uçuş izni, uçuş planı ve NOTAM "
    "kontrolleri politika gereği çalıştırılmamıştır."
)
_MAX_ACTIONS = 3
_UNRESOLVED_ACTIONS = {
    "VERIFY_PLATFORM_MANUALLY": "Platform kimliğini manuel doğrula",
    "REQUEST_ADDITIONAL_VISUAL_EVIDENCE": (
        "Daha kaliteli veya farklı açılardan görsel kanıt sağla"
    ),
    "REQUEST_OPERATOR_REVIEW": "Operasyonel karar için insan incelemesi yap",
}
_ACTION_TEXT = {
    **_UNRESOLVED_ACTIONS,
    "CHECK_PERMISSION_RECORDS": "Uçuş izni kayıtlarını kontrol et",
    "CHECK_FLIGHT_PLAN_RECORDS": "Uçuş planı kayıtlarını kontrol et",
    "REVIEW_ACTIVE_NOTAM": "Aktif NOTAM ayrıntılarını incele",
    "ESCALATE_TO_AUTHORIZED_UNIT": "Yetkili birime ilet",
    "CONTINUE_TRACKING": "Takibi sürdür",
    "MARK_AS_NON_AIRCRAFT": "Olayı hava aracı olmayan hedef olarak işaretle",
    "LOG_AND_CLOSE_EVENT": "Olayı kaydet ve kapat",
}


def _action_text_for_output(code: str, output: Mapping[str, Any]) -> str:
    """Return a contextual Turkish action label from finalized facts."""
    if output.get("decision") == "UNREGISTERED_MILITARY_AIRCRAFT":
        if code == "ESCALATE_TO_AUTHORIZED_UNIT":
            return (
                "Türkiye envanter durumunu ve operasyonel yetkilendirmeyi "
                "yetkili birimden doğrula"
            )
        if code == "CONTINUE_TRACKING":
            return "Hava sahası takibini sürdür"
        if code == "REQUEST_OPERATOR_REVIEW":
            return "Olayı acilen yetkili operatöre ilet"
    if code == "CHECK_FLIGHT_PLAN_RECORDS" and output.get("flight_plan_status") == "FILED":
        return "Uçuş planı ile uçuş izni kaydının birlikte uyumunu doğrula"
    if code == "REVIEW_ACTIVE_NOTAM":
        effect = output.get("notam_operation_effect")
        if effect == "PROHIBITS_OPERATION":
            return "Aktif NOTAM yasağına göre operasyonu durdur"
        if effect == "CONFLICTS_WITH_PERMISSION":
            return "NOTAM ile uçuş izni çelişkisini yetkili birimle doğrula"
        if effect == "RESTRICTS_OPERATION":
            return "Aktif NOTAM kısıtlarına göre operasyonu yeniden değerlendir"
    return _ACTION_TEXT[code]


def _tool_execution(output: Mapping[str, Any], tool_name: str) -> str | None:
    raw_summary = output.get("tool_execution_summary")
    if not isinstance(raw_summary, Mapping):
        return None
    raw_tool = raw_summary.get(tool_name)
    if not isinstance(raw_tool, Mapping):
        return None
    value = raw_tool.get("execution_status")
    return str(value) if value is not None else None


def _visual_sentence(output: Mapping[str, Any]) -> str:
    visual_class = output.get("visual_class")
    hypothesis = output.get("visual_hypothesis")
    if visual_class == "NON_AIRCRAFT":
        return "Görsel kanıt, hedefi hava aracı olmayan bir unsur olarak değerlendirmiştir."
    if hypothesis:
        return (
            f"Görsel kanıt, hedef için “{hypothesis}” hipotezini üretmiştir; "
            "bu görsel kimlik kesin kabul edilmemiştir."
        )
    return "Görsel kanıttan kesin bir platform hipotezi üretilememiştir."


def _platform_type_label(output: Mapping[str, Any]) -> str | None:
    taxonomy = output.get("platform_taxonomy")
    if not isinstance(taxonomy, Mapping):
        return None
    operational_class = taxonomy.get("operational_class")
    if operational_class == "STRATEGIC_BOMBER":
        return "stratejik bombard\u0131man u\u00e7a\u011f\u0131"
    if operational_class == "ATTACK_HELICOPTER":
        return "taarruz helikopteri"
    return None


def _platform_sentence(output: Mapping[str, Any]) -> str:
    execution = _tool_execution(output, "platform_tool")
    status = output.get("platform_status")
    matched = output.get("matched_platform")
    if execution in _TECHNICAL_EXECUTIONS:
        return "Platform kontrolü teknik bir hata nedeniyle tamamlanamamıştır."
    if execution == "SKIPPED":
        return "Platform kontrolü çalıştırılmamıştır."
    if status in {"UNKNOWN", "AMBIGUOUS", None} or not matched:
        return "Platform Registry üzerinde platform kesin olarak çözümlenememiştir."
    expectation = (
        "operasyon bağlamında beklenen"
        if status == "EXPECTED"
        else "operasyon bağlamında beklenmeyen"
    )
    if (
        output.get("platform_identity_scope") == "MODEL_FAMILY"
        and output.get("platform_variant_policy") == "EXPLICIT_CHILD_RECORDS"
    ):
        return (
            f"Platform, {matched} ailesi olarak çözülmüş ve {expectation} bulunmuştur; "
            "A/B/C varyantı mevcut görsel kanıtla kesinleştirilmemiştir."
        )
    type_label = _platform_type_label(output)
    display_name = f"{matched} ({type_label})" if type_label else matched
    return f"Platform, {display_name} olarak çözülmüş ve {expectation} bulunmuştur."


def _origin_sentence(output: Mapping[str, Any]) -> str | None:
    """Keep VLM origin and Registry manufacturer metadata explicitly non-attributive."""
    hypothesis = output.get("vlm_origin_hypothesis")
    manufacturer = output.get("manufacturer_country_code")
    if not hypothesis and not manufacturer:
        return None
    parts: list[str] = []
    if hypothesis:
        hypothesis_text = str(hypothesis).strip()
        simple_country_name = bool(
            re.fullmatch(r"[^\W\d_]+(?:[ -][^\W\d_]+){0,5}", hypothesis_text)
        )
        if simple_country_name:
            parts.append(
                f"VLM ülke değeri “{hypothesis_text}” yalnız görsel ülke/operatör "
                "hipotezidir; kesin aidiyet değildir."
            )
        else:
            parts.append(
                "VLM ülke alanı kontrolsüz serbest metin içerdiğinden raporda aidiyet "
                "iddiası olarak kullanılmamıştır."
            )
    if manufacturer:
        parts.append(
            f"Registry manufacturer_country_code değeri {manufacturer}, yalnız üretici "
            "ülkesini ifade eder; hedefin operatörünü veya hangi ülkeye ait olduğunu kanıtlamaz."
        )
    return " ".join(parts)


def _inventory_sentence(output: Mapping[str, Any]) -> str:
    execution = _tool_execution(output, "turkey_inventory_tool")
    status = output.get("inventory_status")
    if execution == "SKIPPED":
        return (
            "Türkiye Inventory kontrolü çalıştırılmamış; bu nedenle envanter "
            "hakkında bir domain sonucu çıkarılmamıştır."
        )
    if execution in _TECHNICAL_EXECUTIONS:
        return "Türkiye Inventory kontrolü teknik nedenle tamamlanamamıştır."
    if status == "CONFIRMED":
        platform = str(output.get("matched_platform") or "Platform")
        dataset = (
            "DEMO_MOCK Türkiye Inventory"
            if output.get("inventory_source_type") == "DEMO_MOCK"
            else "Türkiye Inventory"
        )
        return (
            f"{platform} platform ailesi mevcut {dataset} veri setinde kayıtlıdır; "
            "bu kayıt görüntüdeki uçağın operatörünü, aidiyetini veya uçuş iznini "
            "doğrulamaz."
        )
    if status == "NOT_LISTED":
        dataset = (
            "mevcut DEMO_MOCK Türkiye Inventory"
            if output.get("inventory_source_type") == "DEMO_MOCK"
            else "mevcut Türkiye Inventory"
        )
        return (
            f"Platform {dataset} veri setinde kayıtlı değildir; bu sonuç tek başına uçuş "
            "izni, operatör aidiyeti veya operasyonun hukuki durumu hakkında kanıt değildir."
        )
    if status == "NOT_APPLICABLE":
        return "Türkiye Inventory kontrolü bu hedef için uygulanabilir değildir."
    return "Türkiye Inventory sonucu belirlenememiştir."


def _permission_sentences(output: Mapping[str, Any]) -> list[str]:
    execution = _tool_execution(output, "permission_flight_plan_tool")
    if execution == "SKIPPED":
        return [
            "Permission ve Flight Plan kontrolleri çalıştırılmamış; bu alanlarda "
            "bir domain sonucu uydurulmamıştır."
        ]
    if execution in _TECHNICAL_EXECUTIONS:
        return [
            "Permission ve Flight Plan kontrolleri teknik nedenle tamamlanamamış ve "
            "insan incelemesi gerekli hâle gelmiştir."
        ]
    permission_labels = {
        "VALID": "geçerli bir permission kaydı bulundu",
        "NOT_FOUND": "permission kaydı bulunamadı",
        "EXPIRED": "permission kaydının süresi dolmuş",
        "NOT_YET_VALID": "permission kaydı henüz geçerli değil",
        "REVOKED": "permission kaydı iptal edilmiş",
        "AMBIGUOUS": "permission sonucu belirsiz",
        "CONFLICTING": "permission kayıtları çelişkili",
        "NOT_APPLICABLE": "permission kontrolü uygulanabilir değil",
    }
    plan_labels = {
        "FILED": "uçuş planı dosyalanmış",
        "NOT_FOUND": "uçuş planı bulunamadı",
        "EXPIRED": "uçuş planının süresi dolmuş",
        "NOT_YET_ACTIVE": "uçuş planı henüz aktif değil",
        "CANCELLED": "uçuş planı iptal edilmiş",
        "AMBIGUOUS": "uçuş planı sonucu belirsiz",
        "CONFLICTING": "uçuş planı kayıtları çelişkili",
        "NOT_APPLICABLE": "uçuş planı kontrolü uygulanabilir değil",
    }
    permission = permission_labels.get(str(output.get("permission_status")), "belirlenemedi")
    plan = plan_labels.get(str(output.get("flight_plan_status")), "belirlenemedi")
    sentences = [
        f"Permission değerlendirmesinde {permission}.",
        f"Flight Plan değerlendirmesinde {plan}; uçuş planı tek başına izin değildir.",
    ]
    if (
        output.get("inventory_status") == "NOT_LISTED"
        and output.get("permission_status") == "NOT_FOUND"
        and output.get("flight_plan_status") == "NOT_FOUND"
    ):
        sentences.append(
            "Doğrulanabilir uçuş izni veya uçuş planı bulunamaması kesin olarak izinsiz "
            "uçuş kanıtı değildir ve insan incelemesi gerektirir."
        )
    return sentences


def _notam_sentence(output: Mapping[str, Any]) -> str:
    execution = _tool_execution(output, "notam_tool")
    if execution == "SKIPPED":
        return (
            "NOTAM kontrolü çalıştırılmamış; aktiflik veya operasyon etkisi "
            "hakkında sonuç uydurulmamıştır."
        )
    if execution in _TECHNICAL_EXECUTIONS:
        return "NOTAM kontrolü teknik nedenle tamamlanamamıştır."
    selected_summary = _active_notam_summary(output)
    if selected_summary:
        return f"Aktif NOTAM kaydı: {selected_summary}"
    effect = output.get("notam_operation_effect")
    if effect == "PROHIBITS_OPERATION":
        return "Aktif NOTAM operasyonu açıkça yasaklamaktadır."
    if effect == "RESTRICTS_OPERATION":
        return "Aktif NOTAM operasyonu kısıtlamaktadır."
    if effect == "CONFLICTS_WITH_PERMISSION":
        return "NOTAM sonucu permission kaydıyla çelişmektedir."
    if output.get("notam_status") == "NONE_ACTIVE":
        return "İlgili observation interval için aktif NOTAM bulunmamıştır."
    if effect in {"NO_EFFECT", "INFORMATIONAL"}:
        return "NOTAM değerlendirmesinde operasyonu kısıtlayan bir etki bulunmamıştır."
    return "NOTAM sonucu belirlenememiş veya ek kontrol gerektirmiştir."


def safe_action_items(output: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return canonical action items compatible with finalized tool execution facts."""
    raw_actions = output.get("recommended_actions")
    unresolved = output.get("platform_status") in {"UNKNOWN", "AMBIGUOUS"}
    permission_skipped = _tool_execution(output, "permission_flight_plan_tool") == "SKIPPED"
    notam_skipped = _tool_execution(output, "notam_tool") == "SKIPPED"
    unregistered_military = (
        output.get("decision") == "UNREGISTERED_MILITARY_AIRCRAFT"
    )
    selected_codes: list[str] = []
    if isinstance(raw_actions, list):
        sorted_actions = sorted(
            (item for item in raw_actions if isinstance(item, Mapping)),
            key=lambda item: int(item.get("priority", 0) or 0),
        )
        for item in sorted_actions:
            code = str(item.get("action_code", ""))
            if code not in _ACTION_TEXT or code in selected_codes:
                continue
            if unresolved and code not in _UNRESOLVED_ACTIONS:
                continue
            if unregistered_military and code in {
                "REQUEST_ADDITIONAL_VISUAL_EVIDENCE",
                "CHECK_PERMISSION_RECORDS",
                "CHECK_FLIGHT_PLAN_RECORDS",
                "REVIEW_ACTIVE_NOTAM",
            }:
                continue
            if permission_skipped and code in {
                "CHECK_PERMISSION_RECORDS",
                "CHECK_FLIGHT_PLAN_RECORDS",
            }:
                continue
            if notam_skipped and code == "REVIEW_ACTIVE_NOTAM":
                continue
            if code == "MARK_AS_NON_AIRCRAFT" and output.get("visual_class") != "NON_AIRCRAFT":
                continue
            selected_codes.append(code)
    if unresolved:
        risk_level = str(output.get("risk_level"))
        selected_codes = ["VERIFY_PLATFORM_MANUALLY"]
        if risk_level in {"MEDIUM", "HIGH", "UNKNOWN"}:
            selected_codes.append("REQUEST_ADDITIONAL_VISUAL_EVIDENCE")
        if risk_level in {"MEDIUM", "HIGH", "CRITICAL", "UNKNOWN"}:
            selected_codes.append("REQUEST_OPERATOR_REVIEW")
    if output.get("human_approval_required") is True:
        if "REQUEST_OPERATOR_REVIEW" not in selected_codes[:_MAX_ACTIONS]:
            selected_codes = [
                *selected_codes[: _MAX_ACTIONS - 1],
                "REQUEST_OPERATOR_REVIEW",
                *(
                    code
                    for code in selected_codes[_MAX_ACTIONS - 1 :]
                    if code != "REQUEST_OPERATOR_REVIEW"
                ),
            ]
    return [
        {
            "action_code": code,
            "priority": index,
            "reason_tr": _action_text_for_output(code, output),
        }
        for index, code in enumerate(selected_codes[:_MAX_ACTIONS], 1)
    ]


def safe_action_recommendations(output: Mapping[str, Any]) -> list[str]:
    """Return deterministic, deduplicated action text for user presentation."""
    return [str(item["reason_tr"]) for item in safe_action_items(output)]


def _action_sentence(output: Mapping[str, Any]) -> str:
    actions = safe_action_recommendations(output)
    if actions:
        numbered = " ".join(
            f"{index}. {action.rstrip('.')}." for index, action in enumerate(actions, 1)
        )
        return f"Güvenli aksiyonlar: {numbered}"
    if output.get("human_approval_required") is True:
        return (
            "Güvenli aksiyon önerisi: İnsan incelemesi tamamlanmadan operasyonel "
            "işlem uygulanmamalıdır."
        )
    return "Güvenli aksiyon önerisi: Ek bir operasyonel aksiyon önerilmemektedir."


def _risk_factor_sentence(output: Mapping[str, Any]) -> str | None:
    increasing = output.get("risk_increasing_factors")
    reducing = output.get("risk_reducing_factors")
    parts: list[str] = []
    if isinstance(increasing, list) and increasing:
        items = [str(item).rstrip(" .;") for item in increasing[:2]]
        parts.append("artıran: " + "; ".join(items))
    if isinstance(reducing, list) and reducing:
        items = [str(item).rstrip(" .;") for item in reducing[:2]]
        parts.append("azaltan: " + "; ".join(items))
    return "Risk faktörleri — " + " | ".join(parts) + "." if parts else None


def _rag_sentence(output: Mapping[str, Any]) -> str:
    raw_sources = output.get("rag_sources")
    sources = raw_sources if isinstance(raw_sources, list) else []
    if output.get("decision") == "UNREGISTERED_MILITARY_AIRCRAFT":
        if sources:
            return (
                "İlgili mevzuat kaynakları, envanter dışı askerî hava araçlarının hava sahası "
                "kullanımında özel izin ve koordinasyon koşullarının ayrıca değerlendirilmesi "
                "gerektiğini göstermektedir. Bu kaynaklar mevcut risk ve kararı "
                "değiştirmemektedir."
            )
        return (
            "Bu olay için ilgili mevzuat kaynağı getirilememiştir; risk ve karar mevcut "
            "platform ve envanter politikasına göre korunmuştur."
        )
    if sources:
        return (
            f"Text RAG {len(sources)} doğrulanabilir kaynak döndürdü; yalnız açıklama "
            "desteğidir ve Permission, Verification veya risk sonucunu değiştirmez."
        )
    summary = str(output.get("rag_summary") or "")
    if "çağrılmadı" in summary:
        return "Text RAG bu olay için çağrılmadı; mevzuat iddiası eklenmedi."
    return "Text RAG kaynak döndürmedi; mevzuat maddesi uydurulmadı."


def _human_review_sentence(output: Mapping[str, Any]) -> str:
    if output.get("human_approval_required") is not True:
        return "Ek insan onayı zorunlu değildir."
    if output.get("human_review_priority") == "URGENT":
        return "Yetkili operatöre acil bildirim ve müdahale süreci zorunludur."
    reasons = output.get("human_review_reasons")
    if isinstance(reasons, list) and reasons:
        return (
            "İnsan incelemesi zorunludur: "
            + "; ".join(str(item).rstrip(".") for item in reasons[:2])
            + "."
        )
    return "İnsan incelemesi zorunludur."


def _parse_utc(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _summary_platform_sentence(output: Mapping[str, Any]) -> str:
    matched = output.get("matched_platform")
    visual = output.get("visual_hypothesis")
    platform = matched or visual
    usage = {
        "MILITARY": "askerî",
        "CIVIL": "sivil",
        "DUAL_USE": "çift kullanımlı",
        "UNKNOWN": "kullanım alanı belirlenemeyen",
        "DEMO": "demo",
    }.get(str(output.get("platform_usage_domain")), "kullanım alanı belirlenemeyen")
    inventory = {
        "CONFIRMED": "Türkiye Envanterindeki kayıt doğrulanmıştır",
        "NOT_LISTED": "Türkiye Envanterinde kayıt bulunmamaktadır",
        "UNKNOWN": "Türkiye Envanter sonucu belirlenememiştir",
    }.get(str(output.get("inventory_status")), "Türkiye Envanter sonucu belirlenememiştir")
    if platform and output.get("platform_status") not in {"UNKNOWN", "AMBIGUOUS"}:
        type_label = _platform_type_label(output)
        display_name = f"{platform} ({type_label})" if type_label else platform
        return (
            f"Görsel platform hipotezi {visual or platform} olup platform kaydı eşleşmesi "
            f"{display_name} ve kullanım alanı {usage} olarak doğrulanmıştır; {inventory}."
        )
    return f"Görsel platform hipotezi kesin çözümlenememiştir; {inventory}."


def _summary_origin_sentence(output: Mapping[str, Any]) -> str | None:
    """State VLM-origin-driven affiliation suspicion or uncertainty for military assets."""
    if output.get("platform_usage_domain") != "MILITARY":
        return None
    inventory_status = output.get("inventory_status")
    category = output.get("vlm_origin_category")
    if inventory_status == "CONFIRMED":
        if category == "FOREIGN":
            return (
                "VLM ülke hipotezi yabancı bir ülkeyi işaret ettiğinden yabancı askerî aidiyet "
                "şüphesi bulunmaktadır."
            )
        if category == "UNKNOWN":
            return (
                "VLM ülke hipotezi belirlenemediğinden aracın aidiyeti bu aşamada "
                "belirlenememiştir."
            )
        return None
    if inventory_status == "NOT_LISTED" and category == "TURKEY":
        return (
            "VLM ülke hipotezi Türkiye kökenini beyan etmektedir ancak platform Türkiye "
            "Inventory veri setinde kayıtlı değildir; bu çelişki şüpheli kabul edilmeli "
            "ve ayrıca doğrulanmalıdır."
        )
    return None


def _summary_permission_plan_sentence(output: Mapping[str, Any]) -> str:
    if _tool_execution(output, "permission_flight_plan_tool") == "SKIPPED":
        if output.get("decision") == "UNREGISTERED_MILITARY_AIRCRAFT":
            return "Uçuş izni, uçuş planı ve NOTAM kontrolleri politika gereği çalıştırılmamıştır."
        return (
            "Uçuş izni ve uçuş planı kontrolleri çalıştırılmadığı için "
            "kayıt sonucu çıkarılmamıştır."
        )
    permission = {
        "VALID": "Uçuş izni geçerlidir",
        "NOT_FOUND": "Uçuş izni doğrulanamamıştır",
        "EXPIRED": "Uçuş izninin süresi dolmuştur",
        "REVOKED": "Uçuş izni iptal edilmiştir",
        "NOT_YET_VALID": "Uçuş izni henüz geçerli değildir",
        "CONFLICTING": "Uçuş izni kayıtları çelişmektedir",
        "AMBIGUOUS": "Uçuş izni kaydı belirsizdir",
    }.get(str(output.get("permission_status")), "Uçuş izni sonucu belirlenememiştir")
    plan = {
        "FILED": "uçuş planı dosyalanmıştır",
        "NOT_FOUND": "uçuş planı doğrulanamamıştır",
        "EXPIRED": "uçuş planının süresi dolmuştur",
        "CANCELLED": "uçuş planı iptal edilmiştir",
        "NOT_YET_ACTIVE": "uçuş planı henüz aktif değildir",
        "CONFLICTING": "uçuş planı kayıtları çelişmektedir",
        "AMBIGUOUS": "uçuş planı kaydı belirsizdir",
    }.get(str(output.get("flight_plan_status")), "uçuş planı sonucu belirlenememiştir")
    suffix = ""
    if (
        output.get("decision") == "EXPIRED_OR_INVALID_PERMISSION"
        and output.get("flight_plan_status") == "FILED"
    ):
        suffix = "; dosyalanmış uçuş planı izni geçerli hâle getirmez"
    return f"{permission}; {plan}{suffix}."


def _active_notam_summary(output: Mapping[str, Any]) -> str | None:
    """Explain an active relevant NOTAM with its actual number, scope, time, and effect."""
    raw_details = output.get("notam_details")
    if not isinstance(raw_details, list) or not raw_details:
        return None
    raw = next((item for item in raw_details if isinstance(item, Mapping)), None)
    if raw is None:
        return None
    number = raw.get("display_number") or output.get("primary_notam_number") or raw.get("notam_id")
    item_e = raw.get("item_e") or raw.get("summary_tr")
    if not isinstance(item_e, str) or not item_e.strip():
        return None
    item_e = re.sub(r"^SCN-\d+\s+için\s+", "", item_e.strip(), flags=re.IGNORECASE).rstrip(".")
    scope = raw.get("aerodrome_code") or raw.get("fir_code") or raw.get("operational_area_id")
    start = _parse_utc(raw.get("valid_from_utc"))
    end = _parse_utc(raw.get("valid_to_utc"))
    interval = ""
    if start is not None and end is not None:
        interval = f", {start:%H:%M}-{end:%H:%M} UTC aralığında"
    altitude = ""
    lower = raw.get("lower_limit")
    upper = raw.get("upper_limit")
    if isinstance(lower, int | float) and isinstance(upper, int | float):
        altitude = f", {lower:g}-{upper:g} ft irtifa bandında"
    matched = set(output.get("notam_matched_by") or [])
    dimensions: list[str] = []
    if "TIME_OVERLAP" in matched:
        dimensions.append("zaman")
    if "AERODROME_MATCH" in matched:
        dimensions.append("meydan")
    elif "FIR_MATCH" in matched:
        dimensions.append("FIR")
    elif "AREA_MATCH" in matched:
        dimensions.append("alan")
    if "ALTITUDE_OVERLAP" in matched:
        dimensions.append("irtifa")
    if len(dimensions) > 1:
        match_text = ", ".join(dimensions[:-1]) + f" ve {dimensions[-1]}"
    else:
        match_text = dimensions[0] if dimensions else "operasyon"
    effect = str(output.get("notam_operation_effect"))
    if effect == "PROHIBITS_OPERATION":
        effect_text = (
            "hava aracı faaliyetini yasaklamaktadır; bu durum yasaklı operasyonla ciddi "
            "bir operasyonel uyumsuzluk oluşturur ve acil operasyonel doğrulama gerektirir"
        )
    elif effect == "CONFLICTS_WITH_PERMISSION":
        effect_text = (
            "geçerli uçuş izninden daha dar veya güncel bir kısıt oluşturarak izin "
            "kaydıyla çelişmektedir; uçuş izni ve uçuş planı statüleri değiştirilmemiştir"
        )
    else:
        effect_text = {
            "RESTRICTS_OPERATION": (
                "planlanan yaklaşma, iniş veya operasyon prosedürünün belirli bölümünü "
                "kısıtlamaktadır"
            ),
            "REQUIRES_ADDITIONAL_CHECK": "operasyon öncesinde ek kontrol gerektirmektedir",
            "INFORMATIONAL": (
                "yalnız bilgilendirme sağlamaktadır ve tek başına risk artışı oluşturmaz"
            ),
        }.get(effect, "operasyonu etkilemektedir")
    return (
        f"{number} numaralı NOTAM, {scope} kapsamında{interval}{altitude} "
        f"{item_e} bilgisini vermektedir; {match_text} kapsamı planlanan operasyonla "
        f"örtüştüğü için {effect_text}."
    )


def build_turkish_summary(output: Mapping[str, Any]) -> str:
    """Build at most four deterministic Turkish sentences from finalized facts."""
    sentences = [
        _summary_platform_sentence(output),
        _summary_permission_plan_sentence(output),
    ]
    origin_sentence = _summary_origin_sentence(output)
    if origin_sentence:
        sentences.append(origin_sentence)
    notam_summary = _active_notam_summary(output)
    if notam_summary and output.get("notam_status") in {"ACTIVE_RELEVANT", "CONFLICTING"}:
        sentences.append(notam_summary)
    elif (
        not origin_sentence
        and output.get("notam_status") in {"NONE_ACTIVE", "EXPIRED_ONLY", "NOT_YET_ACTIVE"}
        and _tool_execution(output, "notam_tool") != "SKIPPED"
    ):
        sentences.append("Operasyonu kısıtlayan aktif NOTAM tespit edilmemiştir.")
    risk = risk_label_tr(output.get("risk_level")).casefold()
    decision = decision_label_tr(output.get("decision"))
    if output.get("human_review_priority") == "URGENT":
        review = "yetkili operatöre acil bildirim ve müdahale süreci gereklidir"
    elif output.get("human_approval_required") is True:
        review = "insan incelemesi gereklidir"
    else:
        review = "ek insan incelemesi gerekli değildir"
    sentences.append(f"Risk seviyesi {risk}; nihai değerlendirme: {decision}; {review}.")
    return " ".join(sentences)


def build_turkish_operational_report(output: Mapping[str, Any]) -> str:
    """Build a concise report from immutable final facts, never from raw VLM claims."""
    origin_sentence = _origin_sentence(output)
    if output.get("decision") == "UNREGISTERED_MILITARY_AIRCRAFT":
        operational_facts = [_POLICY_DESCRIPTION]
    else:
        operational_facts = [
            _inventory_sentence(output),
            *_permission_sentences(output),
            _notam_sentence(output),
        ]
    military_origin_sentence = _summary_origin_sentence(output)
    sentences = [
        _visual_sentence(output),
        _platform_sentence(output),
        *([origin_sentence] if origin_sentence else []),
        *([military_origin_sentence] if military_origin_sentence else []),
        *operational_facts,
        _rag_sentence(output),
    ]
    consistency = _CONSISTENCY_LABELS.get(
        str(output.get("operational_consistency_status")),
        "belirlenemedi",
    )
    verification = _VERIFICATION_LABELS.get(
        str(output.get("verification_status")),
        "belirlenemedi",
    )
    risk = _RISK_LABELS.get(str(output.get("risk_level")), "belirlenemedi")
    decision = _DECISION_LABELS.get(
        str(output.get("decision")),
        "belirlenemeyen nihai karar",
    )
    risk_factors = _risk_factor_sentence(output)
    sentences.extend(
        [
            f"Operasyonel tutarlılık değerlendirmesi {consistency}.",
            f"Deterministik doğrulama sonucu {verification}; risk seviyesi {risk} "
            "olarak belirlenmiştir.",
            *([risk_factors] if risk_factors else []),
            f"Nihai karar: {decision}.",
            _human_review_sentence(output),
            _action_sentence(output),
        ]
    )
    return " ".join(sentences)


def refresh_final_presentation(output: Mapping[str, Any]) -> dict[str, Any]:
    """Refresh derived report/action presentation without changing decision facts."""
    refreshed = dict(output)
    refreshed["recommended_actions"] = safe_action_items(refreshed)
    refreshed["summary_tr"] = build_turkish_summary(refreshed)
    report = build_turkish_operational_report(refreshed)
    refreshed["operational_report_tr"] = report
    refreshed["turkish_report"] = None
    return refreshed
