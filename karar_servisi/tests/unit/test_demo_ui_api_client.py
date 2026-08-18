"""Unit tests for the HTTP-only Streamlit demo UI client."""
# ruff: noqa: D103

import json

import httpx

from apps.demo_ui.api_client import (
    DemoAPIClient,
    parse_json_text,
    run_demo_scenarios,
    scenario_request_payload,
)


def client_with(handler):  # type: ignore[no-untyped-def]
    http = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="http://127.0.0.1:8000",
    )
    return DemoAPIClient(client=http)


def test_health_preserves_degraded_status_and_rag_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(
                200,
                json={
                    "status": "DEGRADED",
                    "components": {"ollama": {"status": "DEGRADED", "detail": "MODEL_MISSING"}},
                },
            )
        return httpx.Response(
            200,
            json={"rag_index": {"status": "HEALTHY", "detail": None}},
        )

    client = client_with(handler)
    health = client.health()
    rag = client.rag_status()
    assert health.status_code == 200
    assert health.body["status"] == "DEGRADED"
    assert health.body["components"]["ollama"]["status"] == "DEGRADED"
    assert rag.body["rag_index"]["status"] == "HEALTHY"


def test_analyze_waiting_and_event_trace_paths_preserve_response() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path.endswith("/analyze"):
            assert json.loads(request.content) == {"same": "payload"}
            return httpx.Response(
                202,
                json={"event_id": "evt-1", "event_status": "WAITING_FOR_GPU_HANDOFF"},
            )
        return httpx.Response(200, json={"event_id": "evt-1"})

    client = client_with(handler)
    waiting = client.analyze({"same": "payload"})
    event = client.event("evt-1")
    trace = client.trace("evt-1")
    assert waiting.status_code == 202
    assert waiting.body["event_id"] == "evt-1"
    assert event.ok and trace.ok
    assert paths == [
        "/api/v1/events/analyze",
        "/api/v1/events/evt-1",
        "/api/v1/events/evt-1/trace",
    ]


def test_raw_vlm_adapter_client_preserves_backend_result() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/adapters/raw-vlm"
        assert json.loads(request.content) == {"raw_vlm": {"arac_sinifi": "sabit_kanat"}}
        return httpx.Response(
            200,
            json={"analyze_request": {"video_id": "VIDEO_001"}},
        )

    result = client_with(handler).adapt_raw_vlm({"raw_vlm": {"arac_sinifi": "sabit_kanat"}})
    assert result.status_code == 200
    assert result.body == {"analyze_request": {"video_id": "VIDEO_001"}}


def test_analyze_forwards_teknofest_response_format() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["response_format"] == "teknofest_spec"
        return httpx.Response(
            200,
            json={"summary": "Özet", "events": [], "risk": "Düşük", "actions": []},
        )

    result = client_with(handler).analyze({"payload": True}, "teknofest_spec")
    assert result.status_code == 200
    assert result.body["risk"] == "Düşük"


def test_timeout_and_connection_errors_are_sanitized() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("private timeout", request=request)

    def connection(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("private connection detail", request=request)

    timeout_result = client_with(timeout).health()
    connection_result = client_with(connection).health()
    assert timeout_result.status_code is None
    assert timeout_result.error_code == "TIMEOUT"
    assert "private timeout" not in str(timeout_result.error_message)
    assert connection_result.status_code is None
    assert connection_result.error_code == "CONNECTION_ERROR"
    assert "private connection detail" not in str(connection_result.error_message)


def test_invalid_non_json_response_remains_visible() -> None:
    client = client_with(lambda _: httpx.Response(503, text="service down"))
    result = client.health()
    assert result.status_code == 503
    assert result.body == {"raw_response": "service down"}


def test_scenario_payload_is_never_invented_and_smoke_continues_sequentially() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        calls.append(payload["scenario"])
        if payload["scenario"] == "SCN-02":
            return httpx.Response(503, json={"detail": "unavailable"})
        return httpx.Response(
            200,
            json={
                "event_status": "FINALIZED",
                "output": {
                    "verification_status": "VERIFIED",
                    "risk_level": "LOW",
                    "decision": "AUTHORIZED_OPERATIONAL_MATCH",
                },
            },
        )

    scenarios = [
        {
            "scenario_id": "SCN-00",
            "expected_verification_status": "VERIFIED",
            "expected_risk_level": "LOW",
        },
        {
            "scenario_id": "SCN-01",
            "expected_verification_status": "VERIFIED",
            "expected_risk_level": "LOW",
            "request_payload": {"scenario": "SCN-01"},
        },
        {
            "scenario_id": "SCN-02",
            "expected_verification_status": "UNVERIFIED",
            "expected_risk_level": "HIGH",
            "request_payload": {"scenario": "SCN-02"},
        },
    ]
    assert scenario_request_payload(scenarios[0]) is None
    rows = run_demo_scenarios(client_with(handler), scenarios)
    assert calls == ["SCN-01", "SCN-02"]
    assert [row["result"] for row in rows] == ["FAIL", "PASS", "FAIL"]
    assert rows[0]["error"] == "SCENARIO_REQUEST_PAYLOAD_MISSING"
    assert rows[2]["http_status"] == 503


def test_json_parser_checks_syntax_only() -> None:
    assert parse_json_text('[{"unknown_domain_field": true}]') == [{"unknown_domain_field": True}]


def test_all_scenario_ui_smoke_reports_eighteen_passes() -> None:
    expected = {
        f"SCN-{number:02d}": (verification, risk)
        for number, verification, risk in [
            (1, "VERIFIED", "LOW"),
            (2, "UNVERIFIED", "MEDIUM"),
            (3, "UNVERIFIED", "HIGH"),
            (4, "UNVERIFIED", "HIGH"),
            (5, "UNVERIFIED", "HIGH"),
            (6, "INDETERMINATE", "UNKNOWN"),
            (7, "INDETERMINATE", "UNKNOWN"),
            (8, "NOT_APPLICABLE", "LOW"),
            (9, "UNVERIFIED", "HIGH"),
            (10, "INDETERMINATE", "UNKNOWN"),
            (11, "UNVERIFIED", "CRITICAL"),
            (12, "PARTIALLY_VERIFIED", "MEDIUM"),
            (13, "INDETERMINATE", "UNKNOWN"),
            (14, "VERIFIED", "LOW"),
            (15, "UNVERIFIED", "MEDIUM"),
            (16, "UNVERIFIED", "HIGH"),
            (17, "INDETERMINATE", "UNKNOWN"),
            (18, "INDETERMINATE", "UNKNOWN"),
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        scenario_id = payload["request_metadata"]["scenario_id"]
        verification, risk = expected[scenario_id]
        return httpx.Response(
            200,
            json={
                "event_status": "FINALIZED",
                "output": {
                    "verification_status": verification,
                    "risk_level": risk,
                    "decision": "INDETERMINATE",
                },
            },
        )

    scenarios = [
        {
            "scenario_id": scenario_id,
            "expected_verification_status": verification,
            "expected_risk_level": risk,
            "request_payload": {
                "request_metadata": {
                    "scenario_id": scenario_id,
                    "source_type": "DEMO_MOCK",
                }
            },
        }
        for scenario_id, (verification, risk) in expected.items()
    ]
    rows = run_demo_scenarios(client_with(handler), scenarios)
    assert len(rows) == 18
    assert sum(row["result"] == "PASS" for row in rows) == 18
    assert sum(row["result"] == "FAIL" for row in rows) == 0
