"""Friend-team raw VLM API and decision-boundary integration tests."""
# ruff: noqa: D103

import json
from pathlib import Path

import httpx
import pytest

from operational_decision.api.main import create_app
from tests._phase7_support import build_harness
from tests.integration.test_phase7_orchestrator_api import container_for

ROOT = Path(__file__).resolve().parents[2]


def _adapter_payload(
    *,
    threat: str = "YUKSEK",
    origin: str = "ABD",
    track_id: str = "TRK_RAW_001",
) -> dict[str, object]:
    return {
        "raw_vlm": {
            "arac_sinifi": "sabit_kanat",
            "tehdit_seviyesi": threat,
            "tahmini_hedef_tipi": "askeri_ucak",
            "ulke_orjini": origin,
            "hedef_modeli": "General Dynamics F-16",
            "gorsel_analiz": "F-16 benzeri sabit kanatlı hedef",
            "_celiski_var": False,
            "_vote_count": 3,
            "_inference_duration_seconds": 999.0,
        },
        "video_id": "VIDEO_001",
        "track_id": track_id,
        "first_seen_offset_seconds": 8.2,
        "last_seen_offset_seconds": 15.6,
        "visual_confidence": 0.42,
    }


@pytest.mark.asyncio
async def test_raw_adapter_endpoint_returns_inspectable_canonical_request() -> None:
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/adapters/raw-vlm",
            json=_adapter_payload(),
        )
        invalid = await client.post(
            "/api/v1/adapters/raw-vlm",
            json={
                **_adapter_payload(),
                "raw_vlm": {
                    **_adapter_payload()["raw_vlm"],  # type: ignore[dict-item]
                    "hedef_modelli": "typo",
                },
            },
        )

    assert response.status_code == 200
    body = response.json()
    visual = body["analyze_request"]["visual_evidence"]
    assert visual["visual_class"] == "FIGHTER_JET"
    assert visual["final_visual_hypothesis"] == "F-16-like"
    assert visual["visual_confidence"] == 0.42
    assert visual["timing"] == {
        "first_seen_offset_seconds": 8.2,
        "last_seen_offset_seconds": 15.6,
    }
    assert body["helper_metadata"] == {
        "_inference_duration_seconds": 999.0,
        "_celiski_var": False,
        "_vote_count": 3,
    }
    assert invalid.status_code == 422


@pytest.mark.asyncio
async def test_upstream_threat_does_not_directly_change_operational_risk_or_timestamp(
    tmp_path: Path,
) -> None:
    harness = await build_harness(ROOT, tmp_path)
    app = create_app(container_for(harness))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        high_adapter = await client.post(
            "/api/v1/adapters/raw-vlm",
            json=_adapter_payload(threat="YUKSEK", track_id="TRK_RAW_HIGH"),
        )
        low_adapter = await client.post(
            "/api/v1/adapters/raw-vlm",
            json=_adapter_payload(threat="DUSUK", track_id="TRK_RAW_LOW"),
        )
        high = await client.post(
            "/api/v1/events/analyze",
            json=high_adapter.json()["analyze_request"],
        )
        low = await client.post(
            "/api/v1/events/analyze",
            json=low_adapter.json()["analyze_request"],
        )

    assert high.status_code == 200
    assert low.status_code == 200
    high_output = high.json()["output"]
    low_output = low.json()["output"]
    assert high_output["risk_level"] == low_output["risk_level"]
    assert high_output["minimum_risk_level"] == low_output["minimum_risk_level"]
    assert high_output["observation_time_utc"] == "2026-08-10T11:20:08.200000Z"
    assert low_output["observation_time_utc"] == "2026-08-10T11:20:08.200000Z"


@pytest.mark.asyncio
async def test_origin_is_audit_metadata_and_never_inventory_evidence(tmp_path: Path) -> None:
    harness = await build_harness(ROOT, tmp_path)
    app = create_app(container_for(harness))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        unknown_adapter = await client.post(
            "/api/v1/adapters/raw-vlm",
            json=_adapter_payload(origin="Bilinmiyor", track_id="TRK_RAW_ORIGIN_UNKNOWN"),
        )
        tr_adapter = await client.post(
            "/api/v1/adapters/raw-vlm",
            json=_adapter_payload(origin="TR", track_id="TRK_RAW_ORIGIN_TR"),
        )
        unknown_request = unknown_adapter.json()["analyze_request"]
        tr_request = tr_adapter.json()["analyze_request"]
        unknown = await client.post("/api/v1/events/analyze", json=unknown_request)
        tr = await client.post("/api/v1/events/analyze", json=tr_request)

    assert unknown_request["request_metadata"]["visual_origin_hypothesis"] == "Bilinmiyor"
    assert tr_request["request_metadata"]["visual_origin_hypothesis"] == "TR"
    assert "inventory_status" not in unknown_request["request_metadata"]
    assert unknown.json()["output"]["inventory_status"] == "CONFIRMED"
    assert tr.json()["output"]["inventory_status"] == "CONFIRMED"


@pytest.mark.asyncio
async def test_raw_adapter_validation_returns_turkish_field_message() -> None:
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/adapters/raw-vlm",
            json={
                **_adapter_payload(),
                "raw_vlm": {
                    **_adapter_payload()["raw_vlm"],  # type: ignore[dict-item]
                    "hedef_modelli": "typo",
                },
            },
        )

    assert response.status_code == 422
    body = response.json()
    assert body["detail"] == "VALIDATION_ERROR"
    assert body["validation_errors"] == [
        {
            "field": "raw_vlm",
            "message": "Desteklenmeyen ham VLM alanı: hedef_modelli.",
        }
    ]


@pytest.mark.asyncio
async def test_mq9_raw_adapter_endpoint_reaches_not_listed(tmp_path: Path) -> None:
    raw_vlm = json.loads((ROOT / "examples/raw_vlm_mq9_reaper.json").read_text(encoding="utf-8"))
    harness = await build_harness(ROOT, tmp_path)
    app = create_app(container_for(harness))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        adapted = await client.post(
            "/api/v1/adapters/raw-vlm",
            json={
                "raw_vlm": raw_vlm,
                "video_id": "VIDEO_018",
                "track_id": "TRK_RAW_MQ9",
                "first_seen_offset_seconds": 8.2,
                "last_seen_offset_seconds": 15.6,
                "visual_confidence": 0.85,
            },
        )
        assert adapted.status_code == 200
        canonical = adapted.json()["analyze_request"]
        assert canonical["visual_evidence"]["final_visual_hypothesis"] == "MQ-9 Reaper"
        assert canonical["request_metadata"]["upstream_visual_threat_hypothesis"] == "dusuk"
        assert canonical["request_metadata"]["visual_origin_hypothesis"] == "Bilinmiyor"
        assert "inventory_status" not in canonical["request_metadata"]
        analyzed = await client.post("/api/v1/events/analyze", json=canonical)

    assert analyzed.status_code == 200
    output = analyzed.json()["output"]
    assert output["matched_platform"] == "MQ-9 Reaper"
    assert output["inventory_status"] == "NOT_LISTED"
    assert output["permission_status"] == "NOT_APPLICABLE"
    assert output["flight_plan_status"] == "NOT_APPLICABLE"
    assert output["notam_operation_effect"] == "UNKNOWN"
    assert output["tool_health_status"] == "HEALTHY"
    assert output["verification_status"] == "UNVERIFIED"
    assert output["risk_level"] == "HIGH"
    assert output["decision"] == "UNREGISTERED_MILITARY_AIRCRAFT"
    for tool_name in ("permission_flight_plan_tool", "notam_tool"):
        item = output["tool_execution_summary"][tool_name]
        assert item["execution_status"] == "SKIPPED"
        assert item["warnings"] == ["UNREGISTERED_MILITARY_POLICY"]
    assert output["human_approval_required"] is True
    assert "dusuk" not in output["matched_rule_ids"]
    assert "Bilinmiyor" not in output["inventory_reason_codes"]
