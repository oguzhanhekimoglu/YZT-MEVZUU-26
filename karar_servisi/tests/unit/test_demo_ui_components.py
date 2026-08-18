"""Pure Streamlit presentation-helper tests."""
# ruff: noqa: D103

from apps.demo_ui.components import (
    analysis_sidebar_data,
    compact_operational_summary,
    compact_recommended_actions,
    compact_risk_reasons,
    decision_summary_data,
    final_report_text,
    primary_tool_rows,
    raw_vlm_status_data,
    technical_details_available,
)


def test_backend_report_is_preferred() -> None:
    assert final_report_text({"operational_report_tr": "Kontrollü nihai rapor."}) == (
        "Kontrollü nihai rapor."
    )


def test_legacy_output_gets_deterministic_report_fallback() -> None:
    report = final_report_text(
        {
            "platform_status": "UNKNOWN",
            "inventory_status": "UNKNOWN",
            "verification_status": "INDETERMINATE",
            "risk_level": "UNKNOWN",
            "decision": "PLATFORM_UNRESOLVED",
            "human_approval_required": True,
        }
    )
    assert "platform kesin olarak çözümlenememiştir" in report
    assert "İnsan incelemesi zorunludur" in report


def test_sidebar_keeps_complete_risk_and_rag_details_collapsed_data() -> None:
    details = analysis_sidebar_data(
        {
            "risk_explanation": "Deterministik risk açıklaması.",
            "risk_increasing_factors": ["Aktif NOTAM kısıtı."],
            "risk_reducing_factors": ["Permission kaydı geçerli."],
            "human_review_reasons": ["Doğrulama tamamlanamadı."],
            "rag_summary": "İki kaynak bulundu.",
            "rag_decision_effect": "Yalnız açıklama desteği.",
            "rag_sources": [{"document_id": "DOC-1", "page_start": 3, "page_end": 4}],
        }
    )
    assert details["risk_increasing_factors"] == ["Aktif NOTAM kısıtı."]
    assert details["risk_reducing_factors"] == ["Permission kaydı geçerli."]
    assert details["human_review_reasons"] == ["Doğrulama tamamlanamadı."]
    assert details["rag_sources"][0]["document_id"] == "DOC-1"


def test_raw_vlm_compact_sections_are_bounded_and_ordered() -> None:
    output = {
        "matched_platform": "F-35 Lightning II",
        "visual_hypothesis": "F-35-like",
        "inventory_status": "NOT_LISTED",
        "permission_status": "NOT_FOUND",
        "flight_plan_status": "NOT_FOUND",
        "notam_status": "NONE_ACTIVE",
        "verification_status": "UNVERIFIED",
        "risk_level": "MEDIUM",
        "decision": "UNVERIFIED_AIRCRAFT",
        "human_approval_required": True,
        "risk_increasing_factors": ["Faktör 1", "Faktör 2", "Faktör 3"],
        "risk_reducing_factors": ["Faktör 4", "Faktör 5", "Faktör 6"],
        "recommended_actions": [
            {"action_code": "REQUEST_OPERATOR_REVIEW", "priority": 1, "reason_tr": "ignored"},
            {"action_code": "CHECK_PERMISSION_RECORDS", "priority": 2, "reason_tr": "ignored"},
            {"action_code": "CHECK_FLIGHT_PLAN_RECORDS", "priority": 3, "reason_tr": "ignored"},
            {"action_code": "REVIEW_ACTIVE_NOTAM", "priority": 4, "reason_tr": "ignored"},
        ],
    }

    status = raw_vlm_status_data(output)
    assert [label for label, _ in status] == [
        "Platform",
        "Risk",
        "Nihai karar",
        "Operatör müdahalesi",
    ]
    assert [value for _, value in status] == [
        "F-35 Lightning II",
        "Orta",
        "Hava aracı operasyonel olarak doğrulanamadı",
        "Teyit gerekli",
    ]
    assert len(compact_operational_summary(output)) == 4
    reasons = compact_risk_reasons(output)
    assert reasons == [
        "Artıran: Faktör 1",
        "Artıran: Faktör 2",
        "Azaltan: Faktör 4",
        "Azaltan: Faktör 5",
    ]
    assert len(compact_recommended_actions(output)) <= 3

    output["human_review_priority"] = "URGENT"
    assert raw_vlm_status_data(output)[-1] == ("Operatör müdahalesi", "Acil")


def test_technical_details_are_hidden_only_when_all_sources_are_empty() -> None:
    assert technical_details_available({}, {}) is False
    assert technical_details_available({"verification_status": "UNVERIFIED"}, {}) is True
    assert technical_details_available({}, {"origin_comparison": "MISMATCH"}) is True
    assert technical_details_available({"rag_sources": [{"source_id": "SRC-1"}]}, {}) is True


def test_summary_and_tool_rows_follow_required_order() -> None:
    output = {
        "matched_platform": "F-16 Fighting Falcon",
        "platform_status": "EXPECTED",
        "inventory_status": "CONFIRMED",
        "verification_status": "VERIFIED",
        "risk_level": "LOW",
        "decision": "AUTHORIZED_OPERATIONAL_MATCH",
        "human_approval_required": False,
        "permission_status": "VALID",
        "flight_plan_status": "FILED",
        "notam_operation_effect": "NO_EFFECT",
        "tool_execution_summary": {
            "platform_tool": {"execution_status": "SUCCESS"},
            "turkey_inventory_tool": {"execution_status": "SUCCESS"},
            "permission_flight_plan_tool": {"execution_status": "SUCCESS"},
            "notam_tool": {"execution_status": "SUCCESS"},
        },
    }
    assert [label for label, _ in decision_summary_data(output)] == [
        "Platform",
        "Inventory",
        "Verification",
        "Risk",
        "Decision",
        "Human Review",
    ]
    rows = primary_tool_rows(output)
    assert [row["Kontrol"] for row in rows] == [
        "Platform Tool",
        "Turkey Inventory",
        "Permission",
        "Flight Plan",
        "NOTAM",
    ]
    assert all(row["Execution"] == "SUCCESS" for row in rows)


def test_stale_21_report_and_skipped_tool_rows_are_repaired_for_rendering() -> None:
    output = {
        "schema_version": "final-output/2.1",
        "visual_hypothesis": "Boeing 747",
        "platform_status": "UNKNOWN",
        "inventory_status": "UNKNOWN",
        "permission_status": "NOT_APPLICABLE",
        "flight_plan_status": "NOT_APPLICABLE",
        "notam_status": "NONE_ACTIVE",
        "notam_operation_effect": "UNKNOWN",
        "operational_consistency_status": "INDETERMINATE",
        "verification_status": "INDETERMINATE",
        "risk_level": "UNKNOWN",
        "decision": "PLATFORM_UNRESOLVED",
        "human_approval_required": True,
        "operational_report_tr": (
            "Eski rapor; Permission/Flight Plan NOT_APPLICABLE; NOTAM NONE_ACTIVE."
        ),
        "recommended_actions": [
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
        ],
        "tool_execution_summary": {
            "platform_tool": {"execution_status": "SUCCESS"},
            "turkey_inventory_tool": {"execution_status": "SKIPPED"},
            "permission_flight_plan_tool": {"execution_status": "SKIPPED"},
            "notam_tool": {"execution_status": "SKIPPED"},
        },
    }
    report = final_report_text(output)
    assert "NOT_APPLICABLE" not in report
    assert "NONE_ACTIVE" not in report
    assert "Platform kimliğini manuel doğrula" in report
    assert report.count("Güvenli aksiyonlar:") == 1

    rows = primary_tool_rows(output)
    by_name = {str(row["Kontrol"]): row for row in rows}
    assert by_name["Permission"]["Sonuç"] == "Mevcut değil"
    assert by_name["Flight Plan"]["Sonuç"] == "Mevcut değil"
    assert by_name["NOTAM"]["Sonuç"] == "Mevcut değil"
