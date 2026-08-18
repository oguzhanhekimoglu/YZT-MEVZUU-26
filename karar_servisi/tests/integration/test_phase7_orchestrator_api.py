"""Phase 7 orchestrator lifecycle and FastAPI integration tests."""
# ruff: noqa: D103

from pathlib import Path

import httpx
import pytest

from operational_decision.api.main import create_app
from operational_decision.app.container import ApplicationContainer
from operational_decision.app.health import (
    ComponentHealth,
    HealthService,
    HealthStatus,
)
from operational_decision.contracts.common import EventStatus
from operational_decision.memory.event_service import generate_event_fingerprint
from tests._phase7_support import build_harness, scenario_payload

ROOT = Path(__file__).resolve().parents[2]


def healthy_service() -> HealthService:
    async def healthy(deep: bool) -> ComponentHealth:
        del deep
        return ComponentHealth(status=HealthStatus.HEALTHY)

    return HealthService(
        {
            "operational_db": healthy,
            "event_memory_db": healthy,
            "platform_registry": healthy,
            "rag_index": healthy,
            "embedding_model": healthy,
            "ollama": healthy,
            "decision_model": healthy,
        },
        {
            "operational_db",
            "event_memory_db",
            "platform_registry",
            "rag_index",
            "embedding_model",
        },
    )


def container_for(harness):  # type: ignore[no-untyped-def]
    return ApplicationContainer(
        orchestrator=harness.orchestrator,
        event_service=harness.event_service,
        health_service=healthy_service(),
        scenario_path=ROOT / "data/seeds/demo_scenarios.json",
    )


@pytest.mark.asyncio
async def test_api_invalid_wait_resume_persistence_trace_and_idempotency(
    tmp_path: Path,
) -> None:
    harness = await build_harness(ROOT, tmp_path)
    app = create_app(container_for(harness))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        invalid = await client.post("/api/v1/events/analyze", json={"video_id": "bad"})
        assert invalid.status_code == 422
        invalid_id = invalid.json()["event_id"]
        invalid_trace = await client.get(f"/api/v1/events/{invalid_id}/trace")
        assert invalid_trace.json()["event"]["event_status"] == "REJECTED_INVALID_INPUT"
        assert invalid_trace.json()["raw_input"] is not None

        waiting_payload = scenario_payload(ROOT, 1, released=False)
        waiting = await client.post("/api/v1/events/analyze", json=waiting_payload)
        assert waiting.status_code == 202
        waiting_id = waiting.json()["event_id"]
        waiting_payload["gpu_handoff"]["gpu_release_status"] = "RELEASED"
        resumed = await client.post("/api/v1/events/analyze", json=waiting_payload)
        assert resumed.status_code == 200
        assert resumed.json()["event_id"] == waiting_id
        assert resumed.json()["event_status"] == "FINALIZED"

        duplicate = await client.post("/api/v1/events/analyze", json=waiting_payload)
        assert duplicate.status_code == 200
        assert duplicate.json()["event_id"] == waiting_id
        assert duplicate.json()["output"] == resumed.json()["output"]

        event = await client.get(f"/api/v1/events/{waiting_id}")
        trace = await client.get(f"/api/v1/events/{waiting_id}/trace")
        scenarios = await client.get("/api/v1/demo/scenarios")
        rag_status = await client.get("/api/v1/rag/status")
        health = await client.get("/health")
        assert event.json()["final_output"] is not None
        assert trace.json()["final_output"]["output"]["schema_version"] == "final-output/2.1"
        assert len(scenarios.json()) == 23
        assert rag_status.json()["rag_index"]["status"] == "HEALTHY"
        assert health.status_code == 200
        assert health.json()["status"] == "HEALTHY"


@pytest.mark.asyncio
async def test_api_duplicate_nonwaiting_active_is_409(tmp_path: Path) -> None:
    harness = await build_harness(ROOT, tmp_path)
    payload = scenario_payload(ROOT, 3)
    visual = payload["visual_evidence"]
    fingerprint = generate_event_fingerprint(
        payload["video_id"],
        visual["track_id"],
        visual["timing"]["first_seen_offset_seconds"],
    )
    created = await harness.event_service.create_event(
        raw_request=payload,
        fingerprint=fingerprint,
        video_id=payload["video_id"],
        track_id=visual["track_id"],
    )
    await harness.event_service.update_event_status(
        created.event["event_id"], EventStatus.INPUT_VALIDATED
    )
    app = create_app(container_for(harness))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/api/v1/events/analyze", json=payload)
    assert response.status_code == 409
    assert response.json()["event_id"] == created.event["event_id"]


@pytest.mark.asyncio
async def test_inventory_gated_tools_rag_policy_and_unresolved_permission_skip(
    tmp_path: Path,
) -> None:
    harness = await build_harness(ROOT, tmp_path, track_parallel=True)
    verified = await harness.orchestrator.analyze(scenario_payload(ROOT, 1))
    assert verified.http_status == 200
    events = harness.parallel_events
    assert events.index("platform:end") < events.index("notam:start")
    verified_trace = await harness.event_service.get_event_trace(verified.event_id)
    assert not any(item["tool_name"] == "text_rag" for item in verified_trace["tool_executions"])

    unresolved = await harness.orchestrator.analyze(scenario_payload(ROOT, 6))
    unresolved_trace = await harness.event_service.get_event_trace(unresolved.event_id)
    permission = next(
        item
        for item in unresolved_trace["tool_executions"]
        if item["tool_name"] == "permission_flight_plan_tool"
    )
    assert permission["execution_status"] == "SKIPPED"

    needs_rag = await harness.orchestrator.analyze(scenario_payload(ROOT, 2))
    rag_trace = await harness.event_service.get_event_trace(needs_rag.event_id)
    assert any(item["tool_name"] == "text_rag" for item in rag_trace["tool_executions"])
    assert needs_rag.output is not None
    assert needs_rag.output["inventory_status"] == "CONFIRMED"
    inventory_row = next(
        item
        for item in rag_trace["tool_executions"]
        if item["tool_name"] == "turkey_inventory_tool"
    )
    assert inventory_row["domain_status"] == "CONFIRMED"


@pytest.mark.asyncio
async def test_strong_non_aircraft_and_malformed_fallback(tmp_path: Path) -> None:
    early_harness = await build_harness(ROOT, tmp_path / "early")
    early = await early_harness.orchestrator.analyze(scenario_payload(ROOT, 8))
    early_trace = await early_harness.event_service.get_event_trace(early.event_id)
    assert early_harness.llm.generate_calls == 0
    assert not any(item["tool_name"] == "text_rag" for item in early_trace["tool_executions"])

    fallback_harness = await build_harness(
        ROOT, tmp_path / "fallback", outputs=["bad", "still bad"]
    )
    fallback = await fallback_harness.orchestrator.analyze(scenario_payload(ROOT, 13))
    assert fallback.output is not None
    assert fallback.output["decision"] == "AUTHORIZED_OPERATIONAL_MATCH"
    assert fallback.output["risk_level"] == "LOW"
    assert fallback.output["human_approval_required"] is False


@pytest.mark.asyncio
async def test_llm_runtime_states_preserve_all_canonical_decision_fields(tmp_path: Path) -> None:
    cases = (
        ("success", {}, "SUCCESS"),
        ("invalid", {"outputs": ["bad", "still bad"]}, "FALLBACK"),
        ("empty", {"outputs": ["", ""]}, "FALLBACK"),
        ("timeout", {"generate_error": "LOCAL_LLM_TIMEOUT"}, "FALLBACK"),
        ("disabled", {"llm_enabled": False}, "DISABLED_FALLBACK"),
    )
    canonical_fields = (
        "verification_status",
        "verification_reason_codes",
        "risk_level",
        "minimum_risk_level",
        "matched_rule_ids",
        "decision",
        "human_approval_required",
    )
    baseline: dict[str, object] | None = None
    for name, options, expected_audit in cases:
        harness = await build_harness(ROOT, tmp_path / name, **options)
        outcome = await harness.orchestrator.analyze(scenario_payload(ROOT, 13))
        assert outcome.http_status == 200 and outcome.output is not None
        current = {field: outcome.output[field] for field in canonical_fields}
        if baseline is None:
            baseline = current
        assert current == baseline
        assert outcome.output["decision"] == "AUTHORIZED_OPERATIONAL_MATCH"
        assert outcome.output["verification_status"] == "VERIFIED"
        assert outcome.output["risk_level"] == "LOW"
        assert outcome.output["human_approval_required"] is False
        trace = await harness.event_service.get_event_trace(outcome.event_id)
        llm_step = next(item for item in trace["steps"] if item["step_name"] == "LOCAL_LLM")
        assert llm_step["step_status"] == expected_audit
        if expected_audit != "SUCCESS":
            assert outcome.output["uncertainty_notes"]


@pytest.mark.asyncio
async def test_missing_production_context_is_explicit_and_never_uses_demo_fallback(
    tmp_path: Path,
) -> None:
    harness = await build_harness(ROOT, tmp_path)
    payload = scenario_payload(ROOT, 13)
    payload["video_id"] = "VIDEO_REAL_CONTEXT_NOT_REGISTERED"
    payload["visual_evidence"]["track_id"] = "TRACK_REAL_CONTEXT_NOT_REGISTERED"
    outcome = await harness.orchestrator.analyze(payload)
    assert outcome.http_status == 200 and outcome.output is not None
    assert outcome.output["video_id"] == "VIDEO_REAL_CONTEXT_NOT_REGISTERED"
    assert outcome.output["context_status"] == "MISSING"
    assert outcome.output["verification_status"] == "INDETERMINATE"
    assert outcome.output["risk_level"] == "UNKNOWN"
    assert outcome.output["decision"] == "PLATFORM_UNRESOLVED"
    for tool_name in ("permission_flight_plan_tool", "notam_tool"):
        execution = outcome.output["tool_execution_summary"][tool_name]
        assert execution["execution_status"] == "SKIPPED"
        assert execution["warnings"] == ["CONTEXT_INCOMPLETE"]


@pytest.mark.asyncio
async def test_unload_success_and_failure_do_not_change_final_result(tmp_path: Path) -> None:
    normal = await build_harness(ROOT, tmp_path / "normal")
    result = await normal.orchestrator.analyze(scenario_payload(ROOT, 1))
    assert result.event_status is EventStatus.FINALIZED
    assert normal.llm.unload_calls == 1

    failing = await build_harness(ROOT, tmp_path / "failure", unload_fails=True)
    failed_unload_result = await failing.orchestrator.analyze(scenario_payload(ROOT, 1))
    assert failed_unload_result.event_status is EventStatus.FINALIZED
    trace = await failing.event_service.get_event_trace(failed_unload_result.event_id)
    assert any(
        item["step_name"] == "OLLAMA_UNLOAD" and item["step_status"] == "WARNING"
        for item in trace["steps"]
    )
    assert failing.orchestrator.metrics.snapshot()["counters"]["ollama_unload_failure_rate"] == 1


@pytest.mark.asyncio
async def test_demo_catalog_payloads_post_with_binding_expected_results(
    tmp_path: Path,
) -> None:
    harness = await build_harness(ROOT, tmp_path)
    app = create_app(container_for(harness))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        catalog_response = await client.get("/api/v1/demo/scenarios")
        assert catalog_response.status_code == 200
        scenarios = catalog_response.json()
        outcomes = []
        for scenario in scenarios:
            response = await client.post(
                "/api/v1/events/analyze",
                json=scenario["request_payload"],
            )
            body = response.json()
            outcomes.append(
                (
                    scenario["scenario_id"],
                    response.status_code,
                    body["output"]["verification_status"],
                    body["output"]["risk_level"],
                )
            )
            assert response.status_code == 200
            assert body["output"]["verification_status"] == scenario["expected_verification_status"]
            assert body["output"]["risk_level"] == scenario["expected_risk_level"]
            assert body["output"]["matched_rule_ids"]
            assert all(
                "warnings" in item for item in body["output"]["tool_execution_summary"].values()
            )

    assert len(outcomes) == 23


@pytest.mark.asyncio
async def test_api_refreshes_stale_unresolved_21_presentation_for_same_fingerprint(
    tmp_path: Path,
) -> None:
    harness = await build_harness(ROOT, tmp_path)
    app = create_app(container_for(harness))
    payload = scenario_payload(ROOT, 6)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        first = await client.post("/api/v1/events/analyze", json=payload)
        assert first.status_code == 200
        event_id = first.json()["event_id"]
        first_output = first.json()["output"]
        assert first_output["platform_status"] == "UNKNOWN"
        assert "NOT_APPLICABLE" not in first_output["operational_report_tr"]
        assert "NONE_ACTIVE" not in first_output["operational_report_tr"]

        stale = dict(first_output)
        stale["operational_report_tr"] = (
            "Eski aksiyonlar; Permission/Flight Plan NOT_APPLICABLE; NOTAM NONE_ACTIVE."
        )
        stale["recommended_actions"] = [
            {
                "action_code": "VERIFY_PLATFORM_MANUALLY",
                "priority": 1,
                "reason_tr": "Platformu kontrol et",
            },
            {
                "action_code": "CHECK_PERMISSION_RECORDS",
                "priority": 2,
                "reason_tr": "Permission NOT_APPLICABLE",
            },
            {
                "action_code": "REVIEW_ACTIVE_NOTAM",
                "priority": 3,
                "reason_tr": "NOTAM NONE_ACTIVE",
            },
        ]
        await harness.event_service.store_final_output(event_id, "final-output/2.1", stale)

        duplicate = await client.post("/api/v1/events/analyze", json=payload)
        assert duplicate.status_code == 200
        assert duplicate.json()["event_id"] == event_id
        output = duplicate.json()["output"]
        report = output["operational_report_tr"]
        assert "NOT_APPLICABLE" not in report
        assert "NONE_ACTIVE" not in report
        assert ";" not in report.partition("Güvenli aksiyonlar:")[2]
        assert [item["action_code"] for item in output["recommended_actions"]] == [
            "VERIFY_PLATFORM_MANUALLY",
            "REQUEST_ADDITIONAL_VISUAL_EVIDENCE",
            "REQUEST_OPERATOR_REVIEW",
        ]

        persisted = await harness.event_service.get_final_output(event_id)
        assert persisted is not None
        assert persisted["output"] == output
        trace = await client.get(f"/api/v1/events/{event_id}/trace")
        assert any(
            step["step_name"] == "FINAL_PRESENTATION_REFRESH" for step in trace.json()["steps"]
        )


@pytest.mark.asyncio
async def test_scn13_api_resolved_boeing_747_not_listed_end_to_end(
    tmp_path: Path,
) -> None:
    harness = await build_harness(ROOT, tmp_path)
    app = create_app(container_for(harness))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        catalog = await client.get("/api/v1/demo/scenarios")
        scenario = next(item for item in catalog.json() if item["scenario_id"] == "SCN-13")
        assert (
            scenario["request_payload"]["visual_evidence"]["final_visual_hypothesis"]
            == "Boeing 747"
        )
        response = await client.post("/api/v1/events/analyze", json=scenario["request_payload"])
        assert response.status_code == 200
        body = response.json()
        output = body["output"]
        assert output["matched_platform"] == "Boeing 747"
        assert output["platform_status"] == "EXPECTED"
        assert output["inventory_status"] == "NOT_LISTED"
        assert output["permission_status"] == "VALID"
        assert output["flight_plan_status"] == "FILED"
        assert output["notam_status"] == "NONE_ACTIVE"
        assert output["notam_operation_effect"] == "NO_EFFECT"
        assert output["verification_status"] == "VERIFIED"
        assert output["risk_level"] == "LOW"
        assert output["decision"] == "AUTHORIZED_OPERATIONAL_MATCH"
        assert output["human_approval_required"] is False
        assert output["risk_explanation"]
        assert output["risk_increasing_factors"] == []
        assert any("Permission" in item for item in output["risk_reducing_factors"])
        assert output["human_review_reasons"] == []
        assert "çağrılmadı" in output["rag_summary"]
        assert output["rag_sources"] == []
        assert "etkisi olmadı" in output["rag_decision_effect"]
        assert output["turkish_report"] is None
        assert all(
            action["action_code"] != "MARK_AS_NON_AIRCRAFT"
            for action in output["recommended_actions"]
        )
        assert output["operational_consistency_status"] == "CONSISTENT"
        assert output["operational_consistency_flags"] == ["INVENTORY_NOT_LISTED"]
        summary = output["tool_execution_summary"]
        assert summary["platform_tool"]["execution_status"] == "SUCCESS"
        assert summary["turkey_inventory_tool"]["execution_status"] == "SUCCESS"
        assert summary["turkey_inventory_tool"]["domain_status"] == "NOT_LISTED"
        assert summary["permission_flight_plan_tool"]["execution_status"] == "SUCCESS"
        assert summary["notam_tool"]["execution_status"] == "SUCCESS"

        report = output["operational_report_tr"]
        assert "Boeing 747 olarak çözülmüş" in report
        assert "DEMO_MOCK Türkiye Inventory veri setinde kayıtlı değildir" in report
        assert "geçerli bir permission kaydı bulundu" in report
        assert "uçuş planı dosyalanmış" in report
        assert "aktif NOTAM bulunmamıştır" in report
        assert "Ek insan onayı zorunlu değildir" in report
        normalized_report = report.casefold()
        assert all(
            claim not in normalized_report for claim in ("düşman", "yabancı", "tehdit", "izinsiz")
        )
        assert "NOT_APPLICABLE" not in report
        assert "NONE_ACTIVE" not in report

        trace = await client.get(f"/api/v1/events/{body['event_id']}/trace")
        trace_body = trace.json()
        tool_rows = {row["tool_name"]: row for row in trace_body["tool_executions"]}
        assert tool_rows["platform_tool"]["response"]["data"]["platform_id"] == ("PLT_BOEING_747")
        assert (
            tool_rows["permission_flight_plan_tool"]["response"]["data"]["permission_status"]
            == "VALID"
        )
        assert (
            tool_rows["permission_flight_plan_tool"]["response"]["data"]["flight_plan_status"]
            == "FILED"
        )
        assert tool_rows["notam_tool"]["response"]["data"]["notam_status"] == "NONE_ACTIVE"
        assert "text_rag" not in tool_rows
        rag_step = next(step for step in trace_body["steps"] if step["step_name"] == "TEXT_RAG")
        assert rag_step["step_status"] == "SKIPPED"


@pytest.mark.asyncio
async def test_scn14_api_bayraktar_tb2_verified_end_to_end(tmp_path: Path) -> None:
    harness = await build_harness(ROOT, tmp_path)
    app = create_app(container_for(harness))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        catalog = await client.get("/api/v1/demo/scenarios")
        scenario = next(item for item in catalog.json() if item["scenario_id"] == "SCN-14")
        assert "SİHA" in scenario["name"]
        assert scenario["request_payload"]["visual_evidence"]["visual_class"] == "UCAV"
        response = await client.post("/api/v1/events/analyze", json=scenario["request_payload"])
        assert response.status_code == 200
        body = response.json()
        output = body["output"]
        assert output["matched_platform"] == "Bayraktar TB2"
        assert output["platform_status"] == "EXPECTED"
        assert output["inventory_status"] == "CONFIRMED"
        assert output["permission_status"] == "VALID"
        assert output["flight_plan_status"] == "FILED"
        assert output["notam_status"] == "NONE_ACTIVE"
        assert output["notam_operation_effect"] == "NO_EFFECT"
        assert output["verification_status"] == "VERIFIED"
        assert output["risk_level"] == "LOW"
        assert output["decision"] == "AUTHORIZED_OPERATIONAL_MATCH"
        assert output["operational_consistency_status"] == "CONSISTENT"
        summary = output["tool_execution_summary"]
        for tool_name in (
            "platform_tool",
            "turkey_inventory_tool",
            "permission_flight_plan_tool",
            "notam_tool",
        ):
            assert summary[tool_name]["execution_status"] == "SUCCESS"
        trace = await client.get(f"/api/v1/events/{body['event_id']}/trace")
        trace_body = trace.json()
        platform_row = next(
            row for row in trace_body["tool_executions"] if row["tool_name"] == "platform_tool"
        )
        assert platform_row["response"]["data"]["platform_id"] == "PLT_BAYRAKTAR_TB2"
        assert not any(row["tool_name"] == "text_rag" for row in trace_body["tool_executions"])


@pytest.mark.asyncio
async def test_scn15_api_bayraktar_akinci_permission_missing(tmp_path: Path) -> None:
    harness = await build_harness(ROOT, tmp_path)
    app = create_app(container_for(harness))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        catalog = await client.get("/api/v1/demo/scenarios")
        scenario = next(item for item in catalog.json() if item["scenario_id"] == "SCN-15")
        assert "Ağır sınıf SİHA" in scenario["name"]
        response = await client.post("/api/v1/events/analyze", json=scenario["request_payload"])
        assert response.status_code == 200
        body = response.json()
        output = body["output"]
        assert output["matched_platform"] == "Bayraktar AKINCI"
        assert output["platform_status"] == "EXPECTED"
        assert output["inventory_status"] == "CONFIRMED"
        assert output["permission_status"] == "NOT_FOUND"
        assert output["flight_plan_status"] == "FILED"
        assert output["notam_status"] == "NONE_ACTIVE"
        assert output["notam_operation_effect"] == "NO_EFFECT"
        assert output["verification_status"] == "UNVERIFIED"
        assert output["risk_level"] == "MEDIUM"
        assert output["decision"] == "OPERATIONAL_AUTHORIZATION_UNVERIFIED"
        assert output["operational_consistency_status"] == "FLAGGED"
        assert output["operational_consistency_flags"] == [
            "INVENTORY_SCOPE_CONFIRMED",
            "FLIGHT_PLAN_WITHOUT_VALID_PERMISSION",
            "INVALID_PERMISSION_WITH_FILED_PLAN",
        ]
        assert output["human_approval_required"] is True
        assert output["summary_tr"] != output["operational_report_tr"]
        for forbidden in (
            "NOT_FOUND",
            "FILED",
            "Permission",
            "Flight Plan",
            "Verification",
            "Registry",
        ):
            assert forbidden not in output["summary_tr"]
        action_codes = {item["action_code"] for item in output["recommended_actions"]}
        assert "REQUEST_OPERATOR_REVIEW" in action_codes
        assert "CHECK_FLIGHT_PLAN_RECORDS" in action_codes, output["recommended_actions"]
        plan_action = next(
            item
            for item in output["recommended_actions"]
            if item["action_code"] == "CHECK_FLIGHT_PLAN_RECORDS"
        )
        assert plan_action["reason_tr"] == (
            "Uçuş planı ile uçuş izni kaydının birlikte uyumunu doğrula"
        )

        trace = await client.get(f"/api/v1/events/{body['event_id']}/trace")
        trace_body = trace.json()
        platform_row = next(
            row for row in trace_body["tool_executions"] if row["tool_name"] == "platform_tool"
        )
        assert platform_row["response"]["data"]["platform_id"] == ("PLT_BAYRAKTAR_AKINCI")
        rag_row = next(
            row for row in trace_body["tool_executions"] if row["tool_name"] == "text_rag"
        )
        assert rag_row["response"]["data"]["query_template_id"] == (
            "FLIGHT_PLAN_WITHOUT_PERMISSION"
        )


@pytest.mark.asyncio
async def test_scn16_api_tusas_anka_notam_restriction(tmp_path: Path) -> None:
    harness = await build_harness(ROOT, tmp_path)
    app = create_app(container_for(harness))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        catalog = await client.get("/api/v1/demo/scenarios")
        scenario = next(item for item in catalog.json() if item["scenario_id"] == "SCN-16")
        assert "Orta irtifa uzun havada kalışlı İHA" in scenario["name"]
        response = await client.post("/api/v1/events/analyze", json=scenario["request_payload"])
        assert response.status_code == 200
        body = response.json()
        output = body["output"]
        assert output["matched_platform"] == "TUSAŞ ANKA"
        assert output["platform_status"] == "EXPECTED"
        assert output["inventory_status"] == "CONFIRMED"
        assert output["permission_status"] == "VALID"
        assert output["flight_plan_status"] == "FILED"
        assert output["notam_status"] == "ACTIVE_RELEVANT"
        assert output["notam_operation_effect"] == "RESTRICTS_OPERATION"
        assert output["verification_status"] == "UNVERIFIED"
        assert output["risk_level"] == "HIGH"
        assert output["decision"] == "UNVERIFIED_AIRCRAFT"
        assert output["operational_consistency_status"] == "FLAGGED"
        assert output["operational_consistency_flags"] == [
            "INVENTORY_SCOPE_CONFIRMED",
            "NOTAM_RESTRICTS_OPERATION",
        ]
        assert output["human_approval_required"] is True

        trace = await client.get(f"/api/v1/events/{body['event_id']}/trace")
        trace_body = trace.json()
        platform_row = next(
            row for row in trace_body["tool_executions"] if row["tool_name"] == "platform_tool"
        )
        assert platform_row["response"]["data"]["platform_id"] == "PLT_TUSAS_ANKA"
        rag_row = next(
            row for row in trace_body["tool_executions"] if row["tool_name"] == "text_rag"
        )
        assert rag_row["response"]["data"]["query_template_id"] == "ACTIVE_NOTAM"


@pytest.mark.asyncio
async def test_scn17_api_f35a_not_listed(tmp_path: Path) -> None:
    harness = await build_harness(ROOT, tmp_path)
    app = create_app(container_for(harness))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        catalog = await client.get("/api/v1/demo/scenarios")
        scenario = next(item for item in catalog.json() if item["scenario_id"] == "SCN-17")
        assert "savaş uçağı" in scenario["name"]
        response = await client.post("/api/v1/events/analyze", json=scenario["request_payload"])
        assert response.status_code == 200
        body = response.json()
        output = body["output"]
        assert output["matched_platform"] == "F-35A Lightning II"
        assert output["platform_status"] == "EXPECTED"
        assert output["inventory_status"] == "NOT_LISTED"
        assert output["permission_status"] == "NOT_APPLICABLE"
        assert output["flight_plan_status"] == "NOT_APPLICABLE"
        assert output["notam_status"] == "NONE_ACTIVE"
        assert output["notam_operation_effect"] == "UNKNOWN"
        assert output["verification_status"] == "UNVERIFIED"
        assert output["risk_level"] == "HIGH"
        assert output["decision"] == "UNREGISTERED_MILITARY_AIRCRAFT"
        assert output["human_review_priority"] == "URGENT"
        assert output["hostile_target_confirmed"] is False
        assert output["legal_violation_confirmed"] is False
        assert output["operational_consistency_status"] == "CONSISTENT"
        assert output["operational_consistency_flags"] == ["INVENTORY_NOT_LISTED"]
        assert output["human_approval_required"] is True
        summary = output["tool_execution_summary"]
        assert summary["platform_tool"]["execution_status"] == "SUCCESS"
        assert summary["turkey_inventory_tool"]["execution_status"] == "SUCCESS"
        assert summary["turkey_inventory_tool"]["domain_status"] == "NOT_LISTED"
        assert summary["permission_flight_plan_tool"]["execution_status"] == "SKIPPED"
        assert summary["notam_tool"]["execution_status"] == "SKIPPED"

        trace = await client.get(f"/api/v1/events/{body['event_id']}/trace")
        trace_body = trace.json()
        platform_row = next(
            row for row in trace_body["tool_executions"] if row["tool_name"] == "platform_tool"
        )
        assert platform_row["response"]["data"]["platform_id"] == "PLT_F35A"
        inventory_row = next(
            row
            for row in trace_body["tool_executions"]
            if row["tool_name"] == "turkey_inventory_tool"
        )
        assert inventory_row["response"]["data"]["safe_message"] == (
            "Platform mevcut Türkiye envanter veri setinde bulunamadı."
        )
        rag_row = next(
            row for row in trace_body["tool_executions"] if row["tool_name"] == "text_rag"
        )
        assert (
            rag_row["response"]["data"]["query_template_id"]
            == "UNREGISTERED_MILITARY_AIRSPACE_CONTEXT"
        )
        for tool_name in ("permission_flight_plan_tool", "notam_tool"):
            row = next(
                item for item in trace_body["tool_executions"] if item["tool_name"] == tool_name
            )
            assert row["response"]["warnings"] == ["UNREGISTERED_MILITARY_POLICY"]


@pytest.mark.asyncio
async def test_scn18_api_mq9_raw_adapter_not_listed(tmp_path: Path) -> None:
    harness = await build_harness(ROOT, tmp_path)
    app = create_app(container_for(harness))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        catalog = await client.get("/api/v1/demo/scenarios")
        scenario = next(item for item in catalog.json() if item["scenario_id"] == "SCN-18")
        assert "Orta irtifa uzun havada kalışlı SİHA" in scenario["name"]
        request = scenario["request_payload"]
        assert request["visual_evidence"]["final_visual_hypothesis"] == "MQ-9 Reaper"
        assert request["request_metadata"]["upstream_visual_threat_hypothesis"] == "dusuk"
        assert request["request_metadata"]["visual_origin_hypothesis"] == "Bilinmiyor"
        assert "inventory_status" not in request["request_metadata"]
        response = await client.post("/api/v1/events/analyze", json=request)
        assert response.status_code == 200
        body = response.json()
        output = body["output"]
        assert output["matched_platform"] == "MQ-9 Reaper"
        assert output["platform_status"] == "EXPECTED"
        assert output["inventory_status"] == "NOT_LISTED"
        assert output["permission_status"] == "NOT_APPLICABLE"
        assert output["flight_plan_status"] == "NOT_APPLICABLE"
        assert output["notam_status"] == "NONE_ACTIVE"
        assert output["notam_operation_effect"] == "UNKNOWN"
        assert output["verification_status"] == "UNVERIFIED"
        assert output["risk_level"] == "HIGH"
        assert output["decision"] == "UNREGISTERED_MILITARY_AIRCRAFT"
        assert output["human_review_priority"] == "URGENT"
        assert output["hostile_target_confirmed"] is False
        assert output["legal_violation_confirmed"] is False
        assert output["operational_consistency_status"] == "CONSISTENT"
        assert output["operational_consistency_flags"] == ["INVENTORY_NOT_LISTED"]
        assert output["human_approval_required"] is True
        summary = output["tool_execution_summary"]
        assert summary["permission_flight_plan_tool"]["execution_status"] == "SKIPPED"
        assert summary["notam_tool"]["execution_status"] == "SKIPPED"

        trace = await client.get(f"/api/v1/events/{body['event_id']}/trace")
        trace_body = trace.json()
        platform_row = next(
            row for row in trace_body["tool_executions"] if row["tool_name"] == "platform_tool"
        )
        assert platform_row["response"]["data"]["platform_id"] == "PLT_MQ9_REAPER"
        rag_row = next(
            row for row in trace_body["tool_executions"] if row["tool_name"] == "text_rag"
        )
        assert (
            rag_row["response"]["data"]["query_template_id"]
            == "UNREGISTERED_MILITARY_AIRSPACE_CONTEXT"
        )
        for tool_name in ("permission_flight_plan_tool", "notam_tool"):
            row = next(
                item for item in trace_body["tool_executions"] if item["tool_name"] == tool_name
            )
            assert row["response"]["warnings"] == ["UNREGISTERED_MILITARY_POLICY"]
