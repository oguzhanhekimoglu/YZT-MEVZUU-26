"""End-to-end Phase 7 acceptance for SCN-01 through SCN-23."""
# ruff: noqa: D103

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from tests._phase7_support import build_harness, scenario_payload

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("number", "verification", "risk", "decision"),
    [
        (1, "VERIFIED", "LOW", "AUTHORIZED_OPERATIONAL_MATCH"),
        (2, "UNVERIFIED", "MEDIUM", "OPERATIONAL_AUTHORIZATION_UNVERIFIED"),
        (3, "UNVERIFIED", "HIGH", "UNEXPECTED_PLATFORM"),
        (4, "UNVERIFIED", "HIGH", "EXPIRED_OR_INVALID_PERMISSION"),
        (5, "UNVERIFIED", "HIGH", "UNVERIFIED_AIRCRAFT"),
        (6, "INDETERMINATE", "UNKNOWN", "PLATFORM_UNRESOLVED"),
        (7, "INDETERMINATE", "UNKNOWN", "INDETERMINATE"),
        (8, "NOT_APPLICABLE", "LOW", "NON_AIRCRAFT"),
        (9, "UNVERIFIED", "HIGH", "CONFLICTING_OPERATIONAL_RECORDS"),
        (10, "INDETERMINATE", "UNKNOWN", "PLATFORM_UNRESOLVED"),
        (11, "UNVERIFIED", "CRITICAL", "ACTIVE_NOTAM_PROHIBITION"),
        (12, "PARTIALLY_VERIFIED", "MEDIUM", "PARTIALLY_VERIFIED_OPERATION"),
        (13, "VERIFIED", "LOW", "AUTHORIZED_OPERATIONAL_MATCH"),
        (14, "VERIFIED", "LOW", "AUTHORIZED_OPERATIONAL_MATCH"),
        (15, "UNVERIFIED", "MEDIUM", "OPERATIONAL_AUTHORIZATION_UNVERIFIED"),
        (16, "UNVERIFIED", "HIGH", "UNVERIFIED_AIRCRAFT"),
        (17, "UNVERIFIED", "HIGH", "UNREGISTERED_MILITARY_AIRCRAFT"),
        (18, "UNVERIFIED", "HIGH", "UNREGISTERED_MILITARY_AIRCRAFT"),
        (19, "UNVERIFIED", "HIGH", "EXPIRED_OR_INVALID_PERMISSION"),
        (20, "UNVERIFIED", "HIGH", "EXPIRED_OR_INVALID_PERMISSION"),
        (21, "UNVERIFIED", "CRITICAL", "ACTIVE_NOTAM_PROHIBITION"),
        (22, "UNVERIFIED", "HIGH", "CONFLICTING_OPERATIONAL_RECORDS"),
        (23, "UNVERIFIED", "HIGH", "UNVERIFIED_AIRCRAFT"),
    ],
)
async def test_phase7_scenario_end_to_end(
    number: int,
    verification: str,
    risk: str,
    decision: str,
    tmp_path: Path,
) -> None:
    harness = await build_harness(ROOT, tmp_path)
    outcome = await harness.orchestrator.analyze(scenario_payload(ROOT, number))
    assert outcome.http_status == 200
    assert outcome.event_status.value == "FINALIZED"
    assert outcome.output is not None
    assert outcome.output["verification_status"] == verification
    assert outcome.output["risk_level"] == risk
    assert outcome.output["decision"] == decision
    summary = outcome.output["summary_tr"]
    assert len(re.split(r"(?<=[.!?])\s+", summary.strip())) <= 4
    for technical_token in (
        outcome.output["decision"],
        outcome.output["verification_status"],
        outcome.output["risk_level"],
        *outcome.output["matched_rule_ids"],
    ):
        assert technical_token not in summary
    assert "RULE_" not in summary
    trace = await harness.event_service.get_event_trace(outcome.event_id)
    assert trace["final_output"]["output"]["risk_level"] == risk
    step_names = [item["step_name"] for item in trace["steps"]]
    assert "VERIFICATION" in step_names
    assert "RISK" in step_names
    if number == 8:
        assert "SKIPPED_STRONG_NON_AIRCRAFT" in {item["step_status"] for item in trace["steps"]}
        assert harness.llm.generate_calls == 0
    elif number == 13:
        assert outcome.output["platform_status"] == "EXPECTED"
        assert outcome.output["matched_platform"] == "Boeing 747"
        assert outcome.output["inventory_status"] == "NOT_LISTED"
        assert outcome.output["permission_status"] == "VALID"
        assert outcome.output["flight_plan_status"] == "FILED"
        assert outcome.output["notam_status"] == "NONE_ACTIVE"
        assert outcome.output["notam_operation_effect"] == "NO_EFFECT"
        assert outcome.output["decision"] == "AUTHORIZED_OPERATIONAL_MATCH"
        assert outcome.output["operational_consistency_status"] == "CONSISTENT"
        assert outcome.output["operational_consistency_flags"] == ["INVENTORY_NOT_LISTED"]
        assert outcome.output["human_approval_required"] is False
        assert "Risk seviyesi düşük" in summary
        assert "yetkili operasyon" in summary
        assert harness.llm.generate_calls >= 1
        for tool_name in ("permission_flight_plan_tool", "notam_tool"):
            assert (
                outcome.output["tool_execution_summary"][tool_name]["execution_status"] == "SUCCESS"
            )
        text_rag = next(step for step in trace["steps"] if step["step_name"] == "TEXT_RAG")
        assert text_rag["step_status"] == "SKIPPED"
    elif number == 6:
        assert outcome.output["inventory_status"] == "UNKNOWN"
        assert outcome.output["decision"] == "PLATFORM_UNRESOLVED"
        assert outcome.output["human_approval_required"] is True
        assert harness.llm.generate_calls >= 1
        assert (
            outcome.output["tool_execution_summary"]["turkey_inventory_tool"]["execution_status"]
            == "SKIPPED"
        )
        assert (
            outcome.output["tool_execution_summary"]["permission_flight_plan_tool"][
                "execution_status"
            ]
            == "SKIPPED"
        )
        assert (
            outcome.output["tool_execution_summary"]["notam_tool"]["execution_status"] == "SKIPPED"
        )
    elif number == 14:
        assert outcome.output["platform_status"] == "EXPECTED"
        assert outcome.output["matched_platform"] == "Bayraktar TB2"
        assert outcome.output["inventory_status"] == "CONFIRMED"
        assert outcome.output["permission_status"] == "VALID"
        assert outcome.output["flight_plan_status"] == "FILED"
        assert outcome.output["notam_status"] == "NONE_ACTIVE"
        assert outcome.output["notam_operation_effect"] == "NO_EFFECT"
        assert outcome.output["decision"] == "AUTHORIZED_OPERATIONAL_MATCH"
        assert outcome.output["operational_consistency_status"] == "CONSISTENT"
        assert outcome.output["human_approval_required"] is False
        assert outcome.output["human_review_reasons"] == []
        assert "REQUEST_OPERATOR_REVIEW" not in {
            item["action_code"] for item in outcome.output["recommended_actions"]
        }
        text_rag = next(step for step in trace["steps"] if step["step_name"] == "TEXT_RAG")
        assert text_rag["step_status"] == "SKIPPED"
        report = outcome.output["operational_report_tr"]
        assert "Bayraktar TB2" in report
        assert "Inventory" in report
        assert "Permission" in report
        assert "Flight Plan" in report
        assert "NOTAM" in report
    elif number == 15:
        assert outcome.output["platform_status"] == "EXPECTED"
        assert outcome.output["matched_platform"] == "Bayraktar AKINCI"
        assert outcome.output["inventory_status"] == "CONFIRMED"
        assert outcome.output["permission_status"] == "NOT_FOUND"
        assert outcome.output["flight_plan_status"] == "FILED"
        assert outcome.output["notam_status"] == "NONE_ACTIVE"
        assert outcome.output["notam_operation_effect"] == "NO_EFFECT"
        assert outcome.output["decision"] == "OPERATIONAL_AUTHORIZATION_UNVERIFIED"
        assert outcome.output["operational_consistency_status"] == "FLAGGED"
        assert outcome.output["operational_consistency_flags"] == [
            "INVENTORY_SCOPE_CONFIRMED",
            "FLIGHT_PLAN_WITHOUT_VALID_PERMISSION",
            "INVALID_PERMISSION_WITH_FILED_PLAN",
        ]
        assert outcome.output["human_approval_required"] is True
        text_rag = next(step for step in trace["steps"] if step["step_name"] == "TEXT_RAG")
        assert text_rag["step_status"] == "CALLED"
        report = outcome.output["operational_report_tr"]
        assert "Bayraktar AKINCI" in report
        assert "Inventory" in report
        assert "Permission" in report
        assert "Flight Plan" in report
        assert "NOTAM" in report
        normalized_report = report.casefold()
        assert all(
            claim not in normalized_report for claim in ("düşman", "tehdit", "kesin izinsiz")
        )
    elif number == 16:
        assert outcome.output["platform_status"] == "EXPECTED"
        assert outcome.output["matched_platform"] == "TUSAŞ ANKA"
        assert outcome.output["inventory_status"] == "CONFIRMED"
        assert outcome.output["permission_status"] == "VALID"
        assert outcome.output["flight_plan_status"] == "FILED"
        assert outcome.output["notam_status"] == "ACTIVE_RELEVANT"
        assert outcome.output["notam_operation_effect"] == "RESTRICTS_OPERATION"
        assert outcome.output["decision"] == "UNVERIFIED_AIRCRAFT"
        assert outcome.output["operational_consistency_status"] == "FLAGGED"
        assert outcome.output["operational_consistency_flags"] == [
            "INVENTORY_SCOPE_CONFIRMED",
            "NOTAM_RESTRICTS_OPERATION",
        ]
        assert outcome.output["human_approval_required"] is True
        text_rag = next(step for step in trace["steps"] if step["step_name"] == "TEXT_RAG")
        assert text_rag["step_status"] == "CALLED"
        report = outcome.output["operational_report_tr"]
        assert "TUSAŞ ANKA" in report
        assert "Inventory" in report
        assert "Permission" in report
        assert "Flight Plan" in report
        assert "NOTAM" in report
        normalized_report = report.casefold()
        assert all(
            claim not in normalized_report
            for claim in ("düşman", "kesin tehdit", "permission tamamen geçersiz")
        )
    elif number in {17, 18}:
        expected_platform = "F-35A Lightning II" if number == 17 else "MQ-9 Reaper"
        expected_platform_id = "PLT_F35A" if number == 17 else "PLT_MQ9_REAPER"
        assert outcome.output["platform_status"] == "EXPECTED"
        assert outcome.output["matched_platform"] == expected_platform
        assert outcome.output["inventory_status"] == "NOT_LISTED"
        assert outcome.output["permission_status"] == "NOT_APPLICABLE"
        assert outcome.output["flight_plan_status"] == "NOT_APPLICABLE"
        assert outcome.output["notam_operation_effect"] == "UNKNOWN"
        assert outcome.output["tool_health_status"] == "HEALTHY"
        assert outcome.output["decision"] == "UNREGISTERED_MILITARY_AIRCRAFT"
        assert outcome.output["human_review_priority"] == "URGENT"
        assert outcome.output["hostile_target_confirmed"] is False
        assert outcome.output["legal_violation_confirmed"] is False
        assert outcome.output["operational_consistency_status"] == "CONSISTENT"
        assert outcome.output["operational_consistency_flags"] == ["INVENTORY_NOT_LISTED"]
        assert outcome.output["human_approval_required"] is True
        assert "politika gereği çalıştırılmamıştır" in summary
        assert "uçuş izni kaydı bulunamadı" not in summary
        assert "aktif NOTAM bulunmamıştır" not in summary
        tool_summary = outcome.output["tool_execution_summary"]
        assert tool_summary["platform_tool"]["execution_status"] == "SUCCESS"
        assert tool_summary["turkey_inventory_tool"]["execution_status"] == "SUCCESS"
        assert tool_summary["turkey_inventory_tool"]["domain_status"] == "NOT_LISTED"
        for tool_name in ("permission_flight_plan_tool", "notam_tool"):
            assert tool_summary[tool_name]["execution_status"] == "SKIPPED"
            assert tool_summary[tool_name]["domain_status"] is None
            assert tool_summary[tool_name]["warnings"] == ["UNREGISTERED_MILITARY_POLICY"]
        platform_row = next(
            row for row in trace["tool_executions"] if row["tool_name"] == "platform_tool"
        )
        assert platform_row["response"]["data"]["platform_id"] == expected_platform_id
        text_rag = next(step for step in trace["steps"] if step["step_name"] == "TEXT_RAG")
        assert text_rag["step_status"] == "CALLED"
        rag_row = next(row for row in trace["tool_executions"] if row["tool_name"] == "text_rag")
        assert (
            rag_row["response"]["data"]["query_template_id"]
            == "UNREGISTERED_MILITARY_AIRSPACE_CONTEXT"
        )
        report = outcome.output["operational_report_tr"]
        assert expected_platform in report
        normalized_report = report.casefold()
        assert all(
            claim not in normalized_report
            for claim in (
                "yabancı operatör",
                "abd'ye aittir",
                "yabancı uçak",
                "düşman",
                "tehdit",
                "platform izinsizdir",
            )
        )
    elif number in {19, 20, 21, 22}:
        expected = {
            19: {
                "platform": "Bayraktar AKINCI",
                "permission": "REVOKED",
                "notam_status": "NONE_ACTIVE",
                "notam_effect": "NO_EFFECT",
                "decision": "EXPIRED_OR_INVALID_PERMISSION",
            },
            20: {
                "platform": "Bayraktar TB2",
                "permission": "EXPIRED",
                "notam_status": "NONE_ACTIVE",
                "notam_effect": "NO_EFFECT",
                "decision": "EXPIRED_OR_INVALID_PERMISSION",
            },
            21: {
                "platform": "F-16 Fighting Falcon",
                "permission": "VALID",
                "notam_status": "ACTIVE_RELEVANT",
                "notam_effect": "PROHIBITS_OPERATION",
                "decision": "ACTIVE_NOTAM_PROHIBITION",
            },
            22: {
                "platform": "TUSAŞ ANKA",
                "permission": "VALID",
                "notam_status": "CONFLICTING",
                "notam_effect": "CONFLICTS_WITH_PERMISSION",
                "decision": "CONFLICTING_OPERATIONAL_RECORDS",
            },
        }[number]
        assert outcome.output["matched_platform"] == expected["platform"]
        assert outcome.output["inventory_status"] == "CONFIRMED"
        assert outcome.output["permission_status"] == expected["permission"]
        assert outcome.output["flight_plan_status"] == "FILED"
        assert outcome.output["notam_status"] == expected["notam_status"]
        assert outcome.output["notam_operation_effect"] == expected["notam_effect"]
        assert outcome.output["decision"] == expected["decision"]
        assert outcome.output["human_approval_required"] is True
        if number == 19:
            assert "Uçuş izni iptal edilmiştir" in summary
            assert "birbiriyle çelişiyor" not in summary
        elif number == 20:
            assert "Uçuş izninin süresi dolmuştur" in summary
            assert "birbiriyle çelişiyor" not in summary
        elif number == 21:
            details = outcome.output["notam_details"]
            assert len(details) == 1
            assert details[0]["notam_id"] == "DEMO_NOTAM_SCN_21"
            assert details[0]["operational_area_id"] == "AREA_013"
            assert details[0]["valid_from_utc"] == "2026-08-11T07:00:00Z"
            assert details[0]["valid_to_utc"] == "2026-08-11T08:00:00Z"
            assert "A2121/26 numaralı NOTAM" in summary
            assert "LTAC kapsamında, 07:00-08:00 UTC aralığında" in summary
            assert "hava aracı faaliyetini yasaklamaktadır" in summary
            assert "0-30000 ft irtifa bandında" in summary
            assert "yasaklı operasyonla ciddi bir operasyonel uyumsuzluk" in summary
            assert (
                "yetkili operatöre acil bildirim ve müdahale süreci gereklidir"
                in summary
            )
            assert outcome.output["human_review_priority"] == "URGENT"
            assert outcome.output["hostile_target_confirmed"] is False
            assert outcome.output["legal_violation_confirmed"] is False
            assert "Risk seviyesi kritik" in summary
        else:
            details = outcome.output["notam_details"]
            assert len(details) == 1
            assert details[0]["notam_id"] == "DEMO_NOTAM_SCN_22"
            assert details[0]["operational_area_id"] == "AREA_014"
            assert details[0]["valid_from_utc"] == "2026-08-11T08:00:00Z"
            assert details[0]["valid_to_utc"] == "2026-08-11T09:00:00Z"
            assert "B2222/26 numaralı NOTAM" in summary
            assert "LTAA kapsamında, 08:00-09:00 UTC aralığında" in summary
            assert "izin kaydıyla çelişmektedir" in summary
            assert "daha dar veya güncel bir kısıt" in summary
            assert "uçuş izni ve uçuş planı statüleri değiştirilmemiştir" in summary
            assert "düşman" not in summary.casefold()
            assert "kanunsuz" not in summary.casefold()
        for tool_name in (
            "platform_tool",
            "turkey_inventory_tool",
            "permission_flight_plan_tool",
            "notam_tool",
        ):
            assert (
                outcome.output["tool_execution_summary"][tool_name]["execution_status"] == "SUCCESS"
            )
    elif number == 23:
        assert outcome.output["matched_platform"] == "Boeing 747"
        assert outcome.output["platform_usage_domain"] == "CIVIL"
        assert outcome.output["inventory_status"] == "NOT_LISTED"
        assert outcome.output["permission_status"] == "VALID"
        assert outcome.output["flight_plan_status"] == "FILED"
        assert outcome.output["notam_status"] == "ACTIVE_RELEVANT"
        assert outcome.output["notam_operation_effect"] == "RESTRICTS_OPERATION"
        assert outcome.output["decision"] == "UNVERIFIED_AIRCRAFT"
        assert outcome.output["primary_notam_number"] == "A1234/26"
        assert outcome.output["matched_notam_ids"] == ["DEMO_NOTAM_SCN_23"]
        assert {"TIME_OVERLAP", "AREA_MATCH", "AERODROME_MATCH", "ALTITUDE_OVERLAP"}.issubset(
            set(outcome.output["notam_matched_by"])
        )
        assert outcome.output["notam_conflict_with_permission"] is False
        assert outcome.output["notam_conflict_with_flight_plan"] is False
        details = outcome.output["notam_details"]
        assert details[0]["display_number"] == "A1234/26"
        assert details[0]["q_code"] == "QICAS"
        assert "ILS sistemi bakım nedeniyle hizmet dışıdır" in details[0]["item_e"]
        assert "A1234/26 numaralı NOTAM" in summary
        assert "zaman, meydan ve irtifa kapsamı" in summary
        assert (
            "yaklaşma, iniş veya operasyon prosedürünün belirli bölümünü kısıtlamaktadır" in summary
        )
        assert "uçuş planı dosyalanmıştır" in summary
        assert "uçuş planı iptal" not in summary.casefold()
        evidence = harness.llm.last_evidence
        assert evidence is not None
        visual_lines = " ".join(evidence["visual_evidence"])
        assert "Tehdit seviyesi yalnız görsel tahmindir, kesin değildir." in visual_lines
        assert "Görsel sınıf: CIVILIAN_AIRCRAFT" in visual_lines
        assert "hipotez: Boeing 747" in visual_lines
        assert "kanıt durumu: kısmen desteklenmiş" in visual_lines
        assert "güven: 0.85" in visual_lines
        assert "belirsizlik: orta" in visual_lines
        platform_lines = " ".join(evidence["platform_result"])
        assert "kullanım alanı: sivil" in platform_lines
        assert "Üretici ülke bilgisi operatör kimliğini belirlemez." in platform_lines
        permission_lines = " ".join(evidence["permission_flight_plan_result"])
        assert "İzin: geçerli" in permission_lines
        assert "LTBA-AREA_015-LTAC" in permission_lines
        notam_lines = " ".join(evidence["notam_result"])
        assert "A1234/26" in notam_lines
        assert (
            "ILS hizmet dışı olduğundan planlanan yaklaşma, iniş veya operasyon prosedürü"
            in notam_lines
        )
        for tool_name in ("permission_flight_plan_tool", "notam_tool"):
            assert (
                outcome.output["tool_execution_summary"][tool_name]["execution_status"] == "SUCCESS"
            )
    else:
        assert harness.llm.generate_calls >= 1


@pytest.mark.asyncio
async def test_new_notams_do_not_leak_into_existing_scenarios(tmp_path: Path) -> None:
    behavior_notam_ids = {
        item["notam_id"]
        for item in json.loads((ROOT / "data/seeds/notams.json").read_text(encoding="utf-8"))
        if item["scenario_id"].startswith("NOTAM-BEHAVIOR-")
    }
    expected = {
        1: ("NONE_ACTIVE", "NO_EFFECT", set()),
        14: ("NONE_ACTIVE", "NO_EFFECT", set()),
        16: ("ACTIVE_RELEVANT", "RESTRICTS_OPERATION", {"DEMO_NOTAM_SCN_16"}),
    }
    for number, (status, effect, expected_ids) in expected.items():
        harness = await build_harness(ROOT, tmp_path / f"scenario-{number}")
        outcome = await harness.orchestrator.analyze(scenario_payload(ROOT, number))
        assert outcome.output is not None
        assert outcome.output["notam_status"] == status
        assert outcome.output["notam_operation_effect"] == effect
        trace = await harness.event_service.get_event_trace(outcome.event_id)
        row = next(item for item in trace["tool_executions"] if item["tool_name"] == "notam_tool")
        active = row["response"]["data"]["active_notams"]
        active_ids = {item["notam_id"] for item in active}
        assert active_ids == expected_ids
        assert active_ids.isdisjoint(
            {"DEMO_NOTAM_SCN_21", "DEMO_NOTAM_SCN_22", "DEMO_NOTAM_SCN_23"}
        )
        assert active_ids.isdisjoint(behavior_notam_ids)


def test_all_demo_notam_seed_scopes_are_isolated() -> None:
    notams = json.loads((ROOT / "data/seeds/notams.json").read_text(encoding="utf-8"))
    scenario_notams = [item for item in notams if item["scenario_id"].startswith("SCN-")]
    behavior_notams = [
        item for item in notams if item["scenario_id"].startswith("NOTAM-BEHAVIOR-")
    ]
    contexts = {
        item["scenario_id"]: item
        for item in json.loads(
            (ROOT / "data/seeds/video_contexts.json").read_text(encoding="utf-8")
        )
    }
    assert len({item["notam_id"] for item in notams}) == len(notams)
    assert len({item["scenario_id"] for item in notams}) == len(notams)
    assert len(scenario_notams) == 6
    assert len(behavior_notams) == 6
    assert all(item["operational_area_id"].startswith("AREA_NOTAM_") for item in behavior_notams)
    for notam in scenario_notams:
        context = contexts[notam["scenario_id"]]
        assert context["operational_area_id"] == notam["operational_area_id"]
        assert context.get("fir_code") == notam.get("fir_code")
        assert context.get("aerodrome_code") == notam.get("aerodrome_code")
        assert context["operation_upper_limit"] >= notam["lower_limit"]
        assert context["operation_lower_limit"] <= notam["upper_limit"]
        payload = scenario_payload(ROOT, int(notam["scenario_id"].split("-")[1]))
        timing = payload["visual_evidence"]["timing"]
        start = datetime.fromisoformat(context["video_start_time_utc"].replace("Z", "+00:00"))
        observation_start = start + timedelta(seconds=timing["first_seen_offset_seconds"])
        observation_end = start + timedelta(seconds=timing["last_seen_offset_seconds"])
        valid_from = datetime.fromisoformat(notam["valid_from_utc"].replace("Z", "+00:00"))
        valid_to = datetime.fromisoformat(notam["valid_to_utc"].replace("Z", "+00:00"))
        assert valid_from <= observation_end
        assert valid_to >= observation_start
