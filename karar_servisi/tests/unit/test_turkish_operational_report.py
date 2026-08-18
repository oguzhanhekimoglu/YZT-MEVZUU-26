"""Deterministic Turkish operational report presentation tests."""
# ruff: noqa: D103

from operational_decision.finalizer.turkish_report import (
    build_turkish_operational_report,
    build_turkish_summary,
    safe_action_items,
)


def output(**updates: object) -> dict[str, object]:
    """Return one complete finalized-fact mapping."""
    value: dict[str, object] = {
        "visual_class": "FIGHTER_JET",
        "visual_hypothesis": "F-16-like",
        "platform_status": "EXPECTED",
        "matched_platform": "F-16 Fighting Falcon",
        "inventory_status": "CONFIRMED",
        "inventory_source_type": "DEMO_MOCK",
        "permission_status": "VALID",
        "flight_plan_status": "FILED",
        "notam_status": "NONE_ACTIVE",
        "notam_operation_effect": "NO_EFFECT",
        "operational_consistency_status": "CONSISTENT",
        "operational_consistency_flags": ["INVENTORY_SCOPE_CONFIRMED"],
        "verification_status": "VERIFIED",
        "risk_level": "LOW",
        "decision": "AUTHORIZED_OPERATIONAL_MATCH",
        "human_approval_required": False,
        "recommended_actions": [],
        "tool_execution_summary": {
            "platform_tool": {"execution_status": "SUCCESS"},
            "turkey_inventory_tool": {"execution_status": "SUCCESS"},
            "permission_flight_plan_tool": {"execution_status": "SUCCESS"},
            "notam_tool": {"execution_status": "SUCCESS"},
        },
    }
    value.update(updates)
    return value


def test_short_summary_is_natural_turkish_and_distinct_from_detailed_report() -> None:
    value = output(
        permission_status="NOT_FOUND",
        flight_plan_status="FILED",
        verification_status="UNVERIFIED",
        risk_level="MEDIUM",
        decision="OPERATIONAL_AUTHORIZATION_UNVERIFIED",
        human_approval_required=True,
    )
    summary = build_turkish_summary(value)
    report = build_turkish_operational_report(value)

    assert summary != report
    assert 3 <= len([part for part in summary.split(". ") if part]) <= 4
    for forbidden in (
        "EXPECTED",
        "NOT_FOUND",
        "FILED",
        "NO_EFFECT",
        "Permission",
        "Flight Plan",
        "Verification",
        "Registry",
    ):
        assert forbidden not in summary
    assert "Operasyonel yetkilendirme doğrulanamadı" in summary


def test_human_review_and_filed_plan_actions_survive_three_item_limit() -> None:
    actions = safe_action_items(
        output(
            permission_status="NOT_FOUND",
            flight_plan_status="FILED",
            risk_level="MEDIUM",
            human_approval_required=True,
            recommended_actions=[
                {"action_code": "CHECK_PERMISSION_RECORDS", "priority": 1},
                {"action_code": "CHECK_FLIGHT_PLAN_RECORDS", "priority": 2},
                {"action_code": "REVIEW_ACTIVE_NOTAM", "priority": 3},
                {"action_code": "REQUEST_OPERATOR_REVIEW", "priority": 4},
            ],
        )
    )

    assert len(actions) == 3
    assert "REQUEST_OPERATOR_REVIEW" in {item["action_code"] for item in actions}
    plan_action = next(
        item for item in actions if item["action_code"] == "CHECK_FLIGHT_PLAN_RECORDS"
    )
    assert plan_action["reason_tr"] == (
        "Uçuş planı ile uçuş izni kaydının birlikte uyumunu doğrula"
    )


def test_verified_low_report_is_natural_and_complete() -> None:
    report = build_turkish_operational_report(output())
    assert "F-16 Fighting Falcon olarak çözülmüş" in report
    assert "operatörünü, aidiyetini veya uçuş iznini doğrulamaz" in report
    assert "geçerli bir permission kaydı" in report
    assert "uçuş planı dosyalanmış" in report
    assert "aktif NOTAM bulunmamıştır" in report
    assert "risk seviyesi düşük" in report
    assert "Ek insan onayı zorunlu değildir" in report


def test_unresolved_platform_report_is_explicit() -> None:
    report = build_turkish_operational_report(
        output(
            platform_status="UNKNOWN",
            matched_platform=None,
            inventory_status="UNKNOWN",
            verification_status="INDETERMINATE",
            risk_level="UNKNOWN",
            decision="PLATFORM_UNRESOLVED",
        )
    )
    assert "platform kesin olarak çözümlenememiştir" in report
    assert "Türkiye Inventory sonucu belirlenememiştir" in report


def test_not_listed_report_never_adds_hostility_or_permission_claim() -> None:
    report = build_turkish_operational_report(
        output(
            inventory_status="NOT_LISTED",
            permission_status=None,
            flight_plan_status=None,
            verification_status="INDETERMINATE",
            risk_level="UNKNOWN",
            decision="REJECTED_OUT_OF_SCOPE",
            human_approval_required=True,
            tool_execution_summary={
                "platform_tool": {"execution_status": "SUCCESS"},
                "turkey_inventory_tool": {"execution_status": "SUCCESS"},
                "permission_flight_plan_tool": {"execution_status": "SKIPPED"},
                "notam_tool": {"execution_status": "SKIPPED"},
            },
        )
    )
    assert "mevcut DEMO_MOCK Türkiye Inventory veri setinde kayıtlı değildir" in report
    assert "uçuş izni, operatör aidiyeti veya operasyonun hukuki durumu" in report
    assert "domain sonucu uydurulmamıştır" in report
    assert "düşman" not in report.casefold()
    assert "yabancı" not in report.casefold()
    assert "uçuş izinlidir" not in report.casefold()


def test_not_listed_authorized_report_separates_inventory_and_operation() -> None:
    report = build_turkish_operational_report(output(inventory_status="NOT_LISTED"))
    assert "mevcut DEMO_MOCK Türkiye Inventory veri setinde kayıtlı değildir" in report
    assert "geçerli bir permission kaydı bulundu" in report
    assert "uçuş planı dosyalanmış" in report
    assert "aktif NOTAM bulunmamıştır" in report
    assert "operasyonel kayıtlarla uyumlu eşleşme" in report
    assert "Ek insan onayı zorunlu değildir" in report
    for forbidden in ("yabancı uçak", "düşman platform", "tehdittir", "izinsizdir"):
        assert forbidden not in report.casefold()


def test_not_listed_unverified_report_preserves_uncertainty() -> None:
    report = build_turkish_operational_report(
        output(
            inventory_status="NOT_LISTED",
            permission_status="NOT_FOUND",
            flight_plan_status="NOT_FOUND",
            verification_status="UNVERIFIED",
            risk_level="MEDIUM",
            decision="UNVERIFIED_AIRCRAFT",
            human_approval_required=True,
        )
    )
    assert "permission kaydı bulunamadı" in report
    assert "uçuş planı bulunamadı" in report
    assert "kesin olarak izinsiz uçuş kanıtı değildir" in report
    assert "İnsan incelemesi zorunludur" in report


def test_primary_report_is_compact_and_does_not_repeat_rule_or_full_rag_detail() -> None:
    report = build_turkish_operational_report(
        output(
            permission_status="VALID",
            flight_plan_status="FILED",
            notam_status="ACTIVE_RELEVANT",
            notam_operation_effect="RESTRICTS_OPERATION",
            verification_status="UNVERIFIED",
            risk_level="HIGH",
            decision="INDETERMINATE",
            human_approval_required=True,
            risk_explanation=(
                "Risk seviyesi RULE_NOTAM_RESTRICTS_OPERATION deterministik kuralıyla "
                "yüksek olarak belirlenmiştir."
            ),
            risk_increasing_factors=["Aktif NOTAM operasyonu kısıtlıyor."],
            risk_reducing_factors=[
                "Geçerli Permission kaydı doğrulandı.",
                "Uyumlu Flight Plan kaydı bulundu.",
                "Üçüncü ayrıntı sidebar'da kalmalı.",
            ],
            rag_summary="Uzun RAG ayrıntısı ana raporda tekrarlanmamalıdır.",
            rag_decision_effect="Uzun karar etkisi ana raporda tekrarlanmamalıdır.",
            rag_sources=[{"source_id": "SRC-1"}, {"source_id": "SRC-2"}],
            human_review_reasons=[
                "Görsel kimlik hipotezdir.",
                "Doğrulama UNVERIFIED.",
                "Üçüncü ayrıntı sidebar'da kalmalı.",
            ],
        )
    )
    assert "RULE_NOTAM_RESTRICTS_OPERATION" not in report
    assert "Uzun RAG ayrıntısı" not in report
    assert "Text RAG 2 doğrulanabilir kaynak döndürdü" in report
    assert "Aktif NOTAM operasyonu kısıtlıyor" in report
    assert "Geçerli Permission kaydı doğrulandı" in report
    assert "Üçüncü ayrıntı sidebar'da kalmalı" not in report


def test_report_strips_double_punctuation_from_risk_factors() -> None:
    report = build_turkish_operational_report(
        output(
            risk_increasing_factors=["İzin süresi dolmuştur."],
            risk_reducing_factors=["Platform beklenmektedir."],
        )
    )
    assert ".;" not in report
    assert ".." not in report


def test_restrictive_and_prohibitive_notam_reports() -> None:
    restrictive = build_turkish_operational_report(
        output(
            notam_status="ACTIVE_RELEVANT",
            notam_operation_effect="RESTRICTS_OPERATION",
            risk_level="HIGH",
        )
    )
    prohibitive = build_turkish_operational_report(
        output(
            notam_status="ACTIVE_RELEVANT",
            notam_operation_effect="PROHIBITS_OPERATION",
            risk_level="CRITICAL",
        )
    )
    assert "operasyonu kısıtlamaktadır" in restrictive
    assert "risk seviyesi yüksek" in restrictive
    assert "operasyonu açıkça yasaklamaktadır" in prohibitive
    assert "risk seviyesi kritik" in prohibitive


def test_skipped_tools_do_not_gain_domain_results() -> None:
    report = build_turkish_operational_report(
        output(
            inventory_status="UNKNOWN",
            permission_status="NOT_FOUND",
            flight_plan_status="NOT_FOUND",
            notam_status="NONE_ACTIVE",
            tool_execution_summary={
                "platform_tool": {"execution_status": "SUCCESS"},
                "turkey_inventory_tool": {"execution_status": "SKIPPED"},
                "permission_flight_plan_tool": {"execution_status": "SKIPPED"},
                "notam_tool": {"execution_status": "SKIPPED"},
            },
        )
    )
    assert "Inventory kontrolü çalıştırılmamış" in report
    assert "Permission ve Flight Plan kontrolleri çalıştırılmamış" in report
    assert "NOTAM kontrolü çalıştırılmamış" in report
    assert "permission kaydı bulunamadı" not in report
    assert "aktif NOTAM bulunmamıştır" not in report


def test_aircraft_report_never_presents_non_aircraft_action() -> None:
    report = build_turkish_operational_report(
        output(
            visual_class="UCAV",
            recommended_actions=[
                {
                    "action_code": "MARK_AS_NON_AIRCRAFT",
                    "priority": 1,
                    "reason_tr": "Yanlış aksiyon",
                },
                {
                    "action_code": "CONTINUE_TRACKING",
                    "priority": 2,
                    "reason_tr": "Takibi sürdür",
                },
            ],
        )
    )
    assert "hava aracı olmayan hedef olarak işaretle" not in report.casefold()
    assert "Takibi sürdür" in report


def test_unresolved_actions_drop_skipped_results_deduplicate_and_limit() -> None:
    report = build_turkish_operational_report(
        output(
            platform_status="UNKNOWN",
            matched_platform=None,
            inventory_status="UNKNOWN",
            permission_status="NOT_APPLICABLE",
            flight_plan_status="NOT_APPLICABLE",
            notam_status="NONE_ACTIVE",
            verification_status="INDETERMINATE",
            risk_level="UNKNOWN",
            decision="PLATFORM_UNRESOLVED",
            human_approval_required=True,
            recommended_actions=[
                {
                    "action_code": "CHECK_PERMISSION_RECORDS",
                    "priority": 1,
                    "reason_tr": "Permission NOT_APPLICABLE",
                },
                {
                    "action_code": "REVIEW_ACTIVE_NOTAM",
                    "priority": 2,
                    "reason_tr": "NOTAM NONE_ACTIVE",
                },
                {
                    "action_code": "VERIFY_PLATFORM_MANUALLY",
                    "priority": 3,
                    "reason_tr": "Aynı öneri",
                },
                {
                    "action_code": "VERIFY_PLATFORM_MANUALLY",
                    "priority": 4,
                    "reason_tr": "Aynı öneri",
                },
                {
                    "action_code": "ESCALATE_TO_AUTHORIZED_UNIT",
                    "priority": 5,
                    "reason_tr": "Yetkisiz dördüncü öneri",
                },
            ],
            tool_execution_summary={
                "platform_tool": {"execution_status": "SUCCESS"},
                "turkey_inventory_tool": {"execution_status": "SKIPPED"},
                "permission_flight_plan_tool": {"execution_status": "SKIPPED"},
                "notam_tool": {"execution_status": "SKIPPED"},
            },
        )
    )
    assert "Permission NOT_APPLICABLE" not in report
    assert "NOTAM NONE_ACTIVE" not in report
    assert "Platform kimliğini manuel doğrula" in report
    assert "Daha kaliteli veya farklı açılardan görsel kanıt sağla" in report
    assert "Operasyonel karar için insan incelemesi yap" in report
    assert report.count("Platform kimliğini manuel doğrula") == 1
    action_section = report.split("Güvenli aksiyonlar:", 1)[1]
    assert "4." not in action_section
    assert ";" not in action_section


def test_informational_notam_is_explained_without_restriction_or_risk_escalation() -> None:
    value = output(
        notam_status="ACTIVE_RELEVANT",
        notam_operation_effect="INFORMATIONAL",
        decision="AUTHORIZED_OPERATIONAL_MATCH",
        risk_level="LOW",
        notam_matched_by=["TIME_OVERLAP", "AREA_MATCH", "ALTITUDE_OVERLAP"],
        notam_details=[
            {
                "notam_id": "INFO-1",
                "display_number": "C0100/26",
                "operational_area_id": "AREA_INFO",
                "valid_from_utc": "2026-08-11T10:00:00Z",
                "valid_to_utc": "2026-08-11T11:00:00Z",
                "lower_limit": 0,
                "upper_limit": 5000,
                "notam_status": "ACTIVE_RELEVANT",
                "operation_effect": "INFORMATIONAL",
                "item_e": "OPERATÖRLERE BİLGİ AMAÇLI DUYURU",
                "summary_tr": "Bilgilendirme kaydı.",
                "source_type": "DEMO_MOCK",
            }
        ],
    )
    summary = build_turkish_summary(value)
    assert "yalnız bilgilendirme sağlamaktadır" in summary
    assert "tek başına risk artışı oluşturmaz" in summary
    assert "yasaklı operasyon" not in summary
    assert "Risk seviyesi düşük" in summary


def test_selected_notam_evidence_drives_summary_and_action_text() -> None:
    value = output(
        notam_status="CONFLICTING",
        notam_operation_effect="CONFLICTS_WITH_PERMISSION",
        decision="CONFLICTING_OPERATIONAL_RECORDS",
        risk_level="HIGH",
        human_approval_required=True,
        notam_details=[
            {
                "notam_id": "DEMO_NOTAM_SCN_22",
                "operational_area_id": "AREA_014",
                "valid_from_utc": "2026-08-11T08:00:00Z",
                "valid_to_utc": "2026-08-11T09:00:00Z",
                "notam_status": "CONFLICTING",
                "operation_effect": "CONFLICTS_WITH_PERMISSION",
                "summary_tr": (
                    "SCN-22 için AREA_014 operasyon alanındaki ANKA uçuş kısıtı "
                    "mevcut Permission kaydıyla çelişmektedir."
                ),
                "source_type": "DEMO_MOCK",
                "source_reference": None,
            }
        ],
        recommended_actions=[
            {"action_code": "REVIEW_ACTIVE_NOTAM", "priority": 1},
            {"action_code": "REQUEST_OPERATOR_REVIEW", "priority": 2},
        ],
    )

    summary = build_turkish_summary(value)
    assert "SCN-22" not in summary
    assert "AREA_014 operasyon alanındaki ANKA uçuş kısıtı" in summary
    assert "izin kaydıyla çelişmektedir" in summary
    assert "daha dar veya güncel bir kısıt" in summary
    assert "uçuş izni ve uçuş planı statüleri değiştirilmemiştir" in summary
    actions = safe_action_items(value)
    assert actions[0]["reason_tr"] == ("NOTAM ile uçuş izni çelişkisini yetkili birimle doğrula")
