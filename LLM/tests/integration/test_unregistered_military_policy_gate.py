"""Unregistered military downstream policy-gate integration tests."""
# ruff: noqa: D103

from dataclasses import replace
from pathlib import Path

import pytest

from operational_decision.contracts.common import VisualClass
from operational_decision.contracts.platform import PlatformRegistry, UsageDomain
from operational_decision.decision.orchestrator import DecisionOrchestrator
from operational_decision.platform.platform_registry import (
    PlatformRegistryIndex,
    load_platform_registry,
)
from operational_decision.tools.platform_tool import PlatformTool
from tests._phase7_support import build_harness, scenario_payload

ROOT = Path(__file__).resolve().parents[2]
PLATFORM_PATH = ROOT / "data/platforms/platform_registry.json"


def tool_rows(trace: dict[str, object]) -> dict[str, dict[str, object]]:
    rows = trace["tool_executions"]
    assert isinstance(rows, list)
    return {str(row["tool_name"]): row for row in rows}


def assert_policy_skip(row: dict[str, object]) -> None:
    assert row["execution_status"] == "SKIPPED"
    assert row["domain_status"] is None
    response = row["response"]
    assert isinstance(response, dict)
    assert response["data"] is None
    assert response["error"] is None
    assert response["warnings"] == ["UNREGISTERED_MILITARY_POLICY"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("scenario_number", "platform_id"),
    [(17, "PLT_F35A"), (18, "PLT_MQ9_REAPER")],
)
async def test_unregistered_military_scenarios_skip_downstream_without_failure(
    tmp_path: Path,
    scenario_number: int,
    platform_id: str,
) -> None:
    harness = await build_harness(ROOT, tmp_path)
    outcome = await harness.orchestrator.analyze(scenario_payload(ROOT, scenario_number))
    assert outcome.output is not None
    trace = await harness.event_service.get_event_trace(outcome.event_id)
    rows = tool_rows(trace)
    platform = rows["platform_tool"]["response"]["data"]
    assert platform["platform_id"] == platform_id
    assert platform["usage_domain"] == "MILITARY"
    assert rows["turkey_inventory_tool"]["execution_status"] == "SUCCESS"
    assert rows["turkey_inventory_tool"]["domain_status"] == "NOT_LISTED"
    assert_policy_skip(rows["permission_flight_plan_tool"])
    assert_policy_skip(rows["notam_tool"])
    assert rows["text_rag"]["execution_status"] == "SUCCESS"
    assert (
        rows["text_rag"]["response"]["data"]["query_template_id"]
        == "UNREGISTERED_MILITARY_AIRSPACE_CONTEXT"
    )
    assert outcome.output["tool_health_status"] == "HEALTHY"
    assert outcome.output["verification_status"] == "UNVERIFIED"
    assert outcome.output["risk_level"] == "HIGH"
    assert outcome.output["decision"] == "UNREGISTERED_MILITARY_AIRCRAFT"
    assert outcome.output["human_approval_required"] is True
    assert outcome.output["human_review_priority"] == "URGENT"
    assert outcome.output["hostile_target_confirmed"] is False
    assert outcome.output["legal_violation_confirmed"] is False
    assert outcome.output["human_review_reasons"][:1] == ["UNREGISTERED_MILITARY_PLATFORM"]
    assert "OPERATIONAL_TOOLS_SKIPPED_BY_POLICY" in outcome.output["human_review_reasons"]
    actions = outcome.output["recommended_actions"]
    action_codes = {item["action_code"] for item in actions}
    assert len(actions) <= 3
    assert {
        "ESCALATE_TO_AUTHORIZED_UNIT",
        "REQUEST_OPERATOR_REVIEW",
    }.issubset(action_codes)
    assert action_codes <= {
        "CONTINUE_TRACKING",
        "REQUEST_OPERATOR_REVIEW",
        "VERIFY_PLATFORM_MANUALLY",
        "ESCALATE_TO_AUTHORIZED_UNIT",
    }
    assert "REQUEST_ADDITIONAL_VISUAL_EVIDENCE" not in action_codes
    escalation = next(
        item for item in actions if item["action_code"] == "ESCALATE_TO_AUTHORIZED_UNIT"
    )
    assert escalation["reason_tr"] == (
        "Türkiye envanter durumunu ve operasyonel yetkilendirmeyi "
        "yetkili birimden doğrula"
    )
    operator_action = next(
        item for item in actions if item["action_code"] == "REQUEST_OPERATOR_REVIEW"
    )
    assert operator_action["reason_tr"] == "Olayı acilen yetkili operatöre ilet"
    assert (
        "yetkili operatöre acil bildirim ve müdahale süreci gereklidir"
        in outcome.output["summary_tr"]
    )
    report = outcome.output["operational_report_tr"]
    assert (
        "Platform Türkiye Envanterinde kayıtlı değildir; uçuş izni, uçuş planı ve NOTAM "
        "kontrolleri politika gereği çalıştırılmamıştır." in report
    )
    normalized = report.casefold()
    assert all(
        claim not in normalized
        for claim in (
            "permission kaydı bulunamadı",
            "flight plan kaydı bulunamadı",
            "aktif notam bulunmamıştır",
            "düşman",
            "kesin izinsiz",
        )
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario_number", [1, 13])
async def test_confirmed_military_and_not_listed_civil_keep_downstream_running(
    tmp_path: Path,
    scenario_number: int,
) -> None:
    harness = await build_harness(ROOT, tmp_path)
    outcome = await harness.orchestrator.analyze(scenario_payload(ROOT, scenario_number))
    rows = tool_rows(await harness.event_service.get_event_trace(outcome.event_id))
    assert rows["permission_flight_plan_tool"]["execution_status"] == "SUCCESS"
    assert rows["notam_tool"]["execution_status"] == "SUCCESS"
    if "text_rag" in rows:
        assert (
            rows["text_rag"]["response"]["data"]["query_template_id"]
            != "UNREGISTERED_MILITARY_AIRSPACE_CONTEXT"
        )


def fixture_index(usage_domain: UsageDomain) -> PlatformRegistryIndex:
    source = load_platform_registry(PLATFORM_PATH)
    boeing = next(item for item in source.platforms if item.platform_id == "PLT_BOEING_747")
    assert boeing.taxonomy is not None
    fixture = boeing.model_copy(
        update={
            "platform_id": f"PLT_FIXTURE_{usage_domain.value}",
            "canonical_name": f"Fixture {usage_domain.value} UAV",
            "aliases": [f"Fixture {usage_domain.value} UAV"],
            "category": VisualClass.UAV,
            "taxonomy": boeing.taxonomy.model_copy(update={"usage_domain": usage_domain}),
        }
    )
    return PlatformRegistryIndex(
        PlatformRegistry(schema_version="platform-registry/1.1", platforms=[fixture])
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("usage_domain", [UsageDomain.DUAL_USE, UsageDomain.UNKNOWN])
async def test_dual_use_and_unknown_not_listed_do_not_gate_downstream(
    tmp_path: Path,
    usage_domain: UsageDomain,
) -> None:
    harness = await build_harness(ROOT, tmp_path)
    index = fixture_index(usage_domain)

    def platform_factory(event_id: str, request_id: str) -> PlatformTool:
        return PlatformTool(
            index,
            event_id=event_id,
            request_id=request_id,
            event_service=harness.event_service,
        )

    harness.orchestrator = DecisionOrchestrator(
        replace(harness.orchestrator.deps, platform_factory=platform_factory)
    )
    payload = scenario_payload(ROOT, 1)
    alias = f"Fixture {usage_domain.value} UAV"
    payload["visual_evidence"]["visual_class"] = "UAV"
    payload["visual_evidence"]["final_visual_hypothesis"] = alias
    payload["visual_evidence"]["candidate_matches"] = []
    outcome = await harness.orchestrator.analyze(payload)
    rows = tool_rows(await harness.event_service.get_event_trace(outcome.event_id))
    assert rows["turkey_inventory_tool"]["domain_status"] == "NOT_LISTED"
    assert rows["permission_flight_plan_tool"]["execution_status"] == "SUCCESS"
    assert rows["notam_tool"]["execution_status"] == "SUCCESS"
    if "text_rag" in rows:
        assert (
            rows["text_rag"]["response"]["data"]["query_template_id"]
            != "UNREGISTERED_MILITARY_AIRSPACE_CONTEXT"
        )
