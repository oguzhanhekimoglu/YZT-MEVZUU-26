"""Runtime Turkey Inventory orchestration gate integration tests."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from operational_decision.decision.orchestrator import DecisionOrchestrator
from operational_decision.inventory.turkey_inventory_registry import (
    load_turkey_inventory_registry,
)
from operational_decision.tools.turkey_inventory_tool import TurkeyInventoryTool
from tests._phase7_support import Phase7Harness, build_harness, scenario_payload

ROOT = Path(__file__).resolve().parents[2]
PLATFORM_PATH = ROOT / "data/platforms/platform_registry.json"
INVENTORY_PATH = ROOT / "data/inventory/turkey_inventory.json"


def tool_rows(trace: dict[str, object]) -> dict[str, dict[str, object]]:
    """Index one event trace's single-attempt tool rows."""
    rows = trace["tool_executions"]
    assert isinstance(rows, list)
    return {str(row["tool_name"]): row for row in rows}


def replace_inventory_factory(
    harness: Phase7Harness,
    inventory_path: Path,
) -> None:
    """Install a focused file-backed Inventory factory in a test harness."""
    try:
        registry = load_turkey_inventory_registry(inventory_path, PLATFORM_PATH)
    except ValueError:
        registry = None

    def factory(event_id: str, request_id: str) -> TurkeyInventoryTool:
        if registry is not None:
            return TurkeyInventoryTool(
                registry,
                event_id=event_id,
                request_id=request_id,
                event_service=harness.event_service,
            )
        return TurkeyInventoryTool.from_files(
            inventory_path,
            PLATFORM_PATH,
            event_id=event_id,
            request_id=request_id,
            event_service=harness.event_service,
        )

    dependencies = replace(harness.orchestrator.deps, inventory_factory=factory)
    harness.orchestrator = DecisionOrchestrator(dependencies)


@pytest.mark.asyncio
async def test_confirmed_runs_downstream_and_preserves_scn01(tmp_path: Path) -> None:
    """SCN-01 remains VERIFIED/LOW and runs both confirmed downstream checks."""
    harness = await build_harness(ROOT, tmp_path)
    outcome = await harness.orchestrator.analyze(scenario_payload(ROOT, 1))
    trace = await harness.event_service.get_event_trace(outcome.event_id)
    rows = tool_rows(trace)
    assert outcome.output is not None
    assert outcome.output["schema_version"] == "final-output/2.1"
    assert outcome.output["verification_status"] == "VERIFIED"
    assert outcome.output["risk_level"] == "LOW"
    assert outcome.output["inventory_status"] == "CONFIRMED"
    assert outcome.output["inventory_record_id"] == "TR-DEMO-F16-001"
    assert outcome.output["inventory_country_code"] == "TR"
    assert outcome.output["inventory_dataset_id"] == "TR-INVENTORY-DEMO"
    assert outcome.output["inventory_dataset_version"] == "1.0.0"
    assert outcome.output["inventory_source_type"] == "DEMO_MOCK"
    assert outcome.output["operational_consistency_status"] == "CONSISTENT"
    assert outcome.output["operational_consistency_flags"] == ["INVENTORY_SCOPE_CONFIRMED"]
    assert "turkey_inventory_tool" in outcome.output["tool_execution_summary"]
    assert rows["turkey_inventory_tool"]["domain_status"] == "CONFIRMED"
    assert rows["permission_flight_plan_tool"]["execution_status"] == "SUCCESS"
    assert rows["notam_tool"]["execution_status"] == "SUCCESS"
    assert rows["notam_tool"]["request"]["platform_id"] == "PLT_F16"

    platform_end = rows["platform_tool"]["response"]["finished_at_utc"]
    inventory_start = rows["turkey_inventory_tool"]["response"]["started_at_utc"]
    inventory_end = rows["turkey_inventory_tool"]["response"]["finished_at_utc"]
    permission_start = rows["permission_flight_plan_tool"]["response"]["started_at_utc"]
    notam_start = rows["notam_tool"]["response"]["started_at_utc"]
    assert platform_end <= inventory_start
    assert inventory_end <= permission_start
    assert inventory_end <= notam_start


@pytest.mark.asyncio
async def test_unregistered_military_not_listed_policy_skips_downstream(
    tmp_path: Path,
) -> None:
    """SUCCESS plus military NOT_LISTED applies a non-failure policy skip."""
    harness = await build_harness(ROOT, tmp_path)
    payload = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    payload["records"] = [
        record for record in payload["records"] if record["platform_id"] != "PLT_F16"
    ]
    inventory_path = tmp_path / "not_listed_inventory.json"
    inventory_path.write_text(json.dumps(payload), encoding="utf-8")
    replace_inventory_factory(harness, inventory_path)

    outcome = await harness.orchestrator.analyze(scenario_payload(ROOT, 1))
    rows = tool_rows(await harness.event_service.get_event_trace(outcome.event_id))
    assert outcome.output is not None
    assert outcome.output["verification_status"] == "UNVERIFIED"
    assert outcome.output["risk_level"] == "HIGH"
    assert outcome.output["decision"] == "UNREGISTERED_MILITARY_AIRCRAFT"
    assert outcome.output["human_review_priority"] == "URGENT"
    assert outcome.output["hostile_target_confirmed"] is False
    assert outcome.output["legal_violation_confirmed"] is False
    assert outcome.output["inventory_status"] == "NOT_LISTED"
    assert outcome.output["inventory_dataset_id"] == "TR-INVENTORY-DEMO"
    assert outcome.output["inventory_dataset_version"] == "1.0.0"
    # SCN-01's VLM reports Turkish origin ("TR") for a platform that is NOT in the
    # inventory: this exact claim/registry mismatch must be flagged as suspicious.
    assert outcome.output["vlm_origin_category"] == "TURKEY"
    assert "şüpheli kabul edilmeli" in outcome.output["risk_explanation"]
    assert "şüpheli kabul edilmeli" in outcome.output["summary_tr"]
    assert outcome.output["operational_consistency_status"] == "CONSISTENT"
    assert "INVENTORY_NOT_LISTED" in outcome.output["operational_consistency_flags"]
    assert (
        "DOWNSTREAM_CHECKS_SKIPPED_INVENTORY_NOT_CONFIRMED"
        not in outcome.output["operational_consistency_flags"]
    )
    # SCN-01 retains its independent VLM_ONLY visual-review requirement.
    assert outcome.output["human_approval_required"] is True
    assert outcome.output["tool_health_status"] != "FAILED"
    assert rows["turkey_inventory_tool"]["execution_status"] == "SUCCESS"
    assert rows["turkey_inventory_tool"]["domain_status"] == "NOT_LISTED"
    assert rows["text_rag"]["execution_status"] == "SUCCESS"
    assert (
        rows["text_rag"]["response"]["data"]["query_template_id"]
        == "UNREGISTERED_MILITARY_AIRSPACE_CONTEXT"
    )
    for tool_name in ("permission_flight_plan_tool", "notam_tool"):
        assert rows[tool_name]["execution_status"] == "SKIPPED"
        assert rows[tool_name]["domain_status"] is None
        assert rows[tool_name]["response"]["data"] is None
        assert rows[tool_name]["response"]["warnings"] == ["UNREGISTERED_MILITARY_POLICY"]


@pytest.mark.asyncio
async def test_inventory_error_runs_downstream_but_keeps_safe_final_result(
    tmp_path: Path,
) -> None:
    """Inventory ERROR remains visible without gating eligible downstream checks."""
    harness = await build_harness(ROOT, tmp_path)
    invalid = tmp_path / "invalid_inventory.json"
    invalid.write_text("{}", encoding="utf-8")
    replace_inventory_factory(harness, invalid)

    outcome = await harness.orchestrator.analyze(scenario_payload(ROOT, 1))
    rows = tool_rows(await harness.event_service.get_event_trace(outcome.event_id))
    assert outcome.output is not None
    assert outcome.output["verification_status"] == "INDETERMINATE"
    assert outcome.output["risk_level"] == "UNKNOWN"
    assert outcome.output["decision"] == "INDETERMINATE"
    assert outcome.output["human_approval_required"] is True
    assert outcome.output["tool_health_status"] == "FAILED"
    assert rows["turkey_inventory_tool"]["execution_status"] == "ERROR"
    assert rows["turkey_inventory_tool"]["domain_status"] == "UNKNOWN"
    assert rows["permission_flight_plan_tool"]["execution_status"] == "SUCCESS"
    assert rows["permission_flight_plan_tool"]["response"]["data"]["permission_status"] == "VALID"
    assert rows["notam_tool"]["execution_status"] == "SUCCESS"
    assert rows["notam_tool"]["response"]["data"]["notam_status"] == "NONE_ACTIVE"


@pytest.mark.asyncio
async def test_platform_unknown_skips_inventory_and_downstream(tmp_path: Path) -> None:
    """An unresolved platform produces SKIPPED Inventory and downstream checks."""
    harness = await build_harness(ROOT, tmp_path)
    outcome = await harness.orchestrator.analyze(scenario_payload(ROOT, 6))
    rows = tool_rows(await harness.event_service.get_event_trace(outcome.event_id))
    assert rows["platform_tool"]["domain_status"] == "UNKNOWN"
    assert rows["turkey_inventory_tool"]["execution_status"] == "SKIPPED"
    assert rows["turkey_inventory_tool"]["domain_status"] == "UNKNOWN"
    assert rows["permission_flight_plan_tool"]["execution_status"] == "SKIPPED"
    assert rows["notam_tool"]["execution_status"] == "SKIPPED"


@pytest.mark.asyncio
async def test_non_aircraft_inventory_not_applicable_and_skipped(tmp_path: Path) -> None:
    """Strong non-aircraft preserves early LLM exit and skips all operational checks."""
    harness = await build_harness(ROOT, tmp_path)
    outcome = await harness.orchestrator.analyze(scenario_payload(ROOT, 8))
    rows = tool_rows(await harness.event_service.get_event_trace(outcome.event_id))
    assert rows["turkey_inventory_tool"]["execution_status"] == "SKIPPED"
    assert rows["turkey_inventory_tool"]["domain_status"] == "NOT_APPLICABLE"
    assert rows["permission_flight_plan_tool"]["execution_status"] == "SKIPPED"
    assert rows["notam_tool"]["execution_status"] == "SKIPPED"
    assert harness.llm.generate_calls == 0


def _military_listed_payload(
    root: Path, *, visual_class: str, final_visual_hypothesis: str, ulke_orjini: str
) -> dict[str, object]:
    """Build a MILITARY + Inventory-listed payload for a given real platform and origin."""
    payload = scenario_payload(root, 1)
    visual = payload["visual_evidence"]
    visual["visual_class"] = visual_class
    visual["final_visual_hypothesis"] = final_visual_hypothesis
    visual["candidate_matches"] = []
    visual["upstream_vlm_output"]["ulke_orjini"] = ulke_orjini
    visual["upstream_vlm_output"]["hedef_modeli"] = final_visual_hypothesis
    return payload


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("visual_class", "hypothesis"),
    [
        ("UCAV", "Bayraktar TB2"),
        ("UCAV", "AKINCI"),
        ("UAV", "ANKA"),
        ("HELICOPTER", "T129 ATAK"),
        ("FIGHTER_JET", "F-4E"),
    ],
)
async def test_military_listed_foreign_origin_is_high_and_urgent_regardless_of_platform(
    visual_class: str, hypothesis: str, tmp_path: Path
) -> None:
    """FOREIGN VLM origin must raise risk for any inventory-listed military platform."""
    harness = await build_harness(ROOT, tmp_path)
    payload = _military_listed_payload(
        ROOT, visual_class=visual_class, final_visual_hypothesis=hypothesis, ulke_orjini="Rusya"
    )
    outcome = await harness.orchestrator.analyze(payload)
    assert outcome.output is not None
    assert outcome.output["platform_usage_domain"] == "MILITARY"
    assert outcome.output["inventory_status"] == "CONFIRMED"
    assert outcome.output["vlm_origin_category"] == "FOREIGN"
    assert outcome.output["risk_level"] == "HIGH"
    assert outcome.output["human_approval_required"] is True
    assert outcome.output["human_review_priority"] == "URGENT"
    assert "yabancı askerî aidiyet şüphesi" in outcome.output["summary_tr"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("visual_class", "hypothesis"),
    [
        ("UCAV", "Bayraktar TB2"),
        ("UCAV", "AKINCI"),
        ("UAV", "ANKA"),
        ("HELICOPTER", "T129 ATAK"),
        ("FIGHTER_JET", "F-4E"),
    ],
)
async def test_military_listed_unknown_origin_cannot_be_low_regardless_of_platform(
    visual_class: str, hypothesis: str, tmp_path: Path
) -> None:
    """UNKNOWN VLM origin must block LOW and force review for any listed military platform."""
    harness = await build_harness(ROOT, tmp_path)
    payload = _military_listed_payload(
        ROOT,
        visual_class=visual_class,
        final_visual_hypothesis=hypothesis,
        ulke_orjini="Bilinmiyor",
    )
    outcome = await harness.orchestrator.analyze(payload)
    assert outcome.output is not None
    assert outcome.output["platform_usage_domain"] == "MILITARY"
    assert outcome.output["inventory_status"] == "CONFIRMED"
    assert outcome.output["vlm_origin_category"] == "UNKNOWN"
    assert outcome.output["risk_level"] != "LOW"
    assert outcome.output["human_approval_required"] is True
    assert "aidiyeti bu aşamada belirlenememiştir" in outcome.output["summary_tr"]


@pytest.mark.asyncio
async def test_unregistered_military_foreign_origin_is_not_labeled_a_turkey_claim(
    tmp_path: Path,
) -> None:
    """A NOT_LISTED military platform claiming FOREIGN origin keeps the generic explanation."""
    harness = await build_harness(ROOT, tmp_path)
    payload = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    payload["records"] = [
        record for record in payload["records"] if record["platform_id"] != "PLT_F16"
    ]
    inventory_path = tmp_path / "not_listed_inventory_foreign.json"
    inventory_path.write_text(json.dumps(payload), encoding="utf-8")
    replace_inventory_factory(harness, inventory_path)

    request_payload = scenario_payload(ROOT, 1)
    request_payload["visual_evidence"]["upstream_vlm_output"]["ulke_orjini"] = "Rusya"
    outcome = await harness.orchestrator.analyze(request_payload)
    assert outcome.output is not None
    assert outcome.output["inventory_status"] == "NOT_LISTED"
    assert outcome.output["vlm_origin_category"] == "FOREIGN"
    assert outcome.output["risk_level"] == "HIGH"
    assert outcome.output["decision"] == "UNREGISTERED_MILITARY_AIRCRAFT"
    assert "şüpheli kabul edilmeli" not in outcome.output["risk_explanation"]


@pytest.mark.asyncio
async def test_military_listed_turkey_origin_still_allows_low_for_bayraktar_tb2(
    tmp_path: Path,
) -> None:
    """Turkey origin must not itself force elevated risk when tools are otherwise clean.

    SCN-14 has real seeded permission/flight-plan/NOTAM records for Bayraktar TB2, unlike
    a synthetic payload that would inherit SCN-01's F-16-specific operational records.
    """
    harness = await build_harness(ROOT, tmp_path)
    outcome = await harness.orchestrator.analyze(scenario_payload(ROOT, 14))
    assert outcome.output is not None
    assert outcome.output["matched_platform"] == "Bayraktar TB2"
    assert outcome.output["platform_usage_domain"] == "MILITARY"
    assert outcome.output["inventory_status"] == "CONFIRMED"
    assert outcome.output["vlm_origin_category"] == "TURKEY"
    assert outcome.output["risk_level"] == "LOW"
    assert outcome.output["human_approval_required"] is False


@pytest.mark.asyncio
async def test_incomplete_context_skips_permission_and_notam_but_runs_inventory(
    tmp_path: Path,
) -> None:
    """Incomplete context prevents Permission/NOTAM checks but not Inventory.

    SCN-10's platform (F-16) is resolved by identity alone (candidate match),
    independent of context — only the EXPECTED/NOT_EXPECTED expectation needs
    a complete context. Inventory only needs a resolved platform_id, so it
    still runs and returns a real result (IDENTIFIED_CONTEXT_UNKNOWN is
    deliberately distinct from UNKNOWN so identity-only checks are not
    forced to skip; see PlatformStatus.IDENTIFIED_CONTEXT_UNKNOWN).
    """
    harness = await build_harness(ROOT, tmp_path)
    outcome = await harness.orchestrator.analyze(scenario_payload(ROOT, 10))
    rows = tool_rows(await harness.event_service.get_event_trace(outcome.event_id))
    assert rows["turkey_inventory_tool"]["execution_status"] == "SUCCESS"
    assert rows["turkey_inventory_tool"]["domain_status"] == "CONFIRMED"
    assert rows["permission_flight_plan_tool"]["execution_status"] == "SKIPPED"
    assert rows["notam_tool"]["execution_status"] == "SKIPPED"
    assert rows["permission_flight_plan_tool"]["response"]["warnings"] == ["CONTEXT_INCOMPLETE"]
    assert rows["notam_tool"]["response"]["warnings"] == ["CONTEXT_INCOMPLETE"]
