"""API tests for direct context-free raw VLM assessment."""
# ruff: noqa: D103

import httpx
import pytest

from operational_decision.api.main import create_app


def _payload(origin: str = "Kanada") -> dict[str, object]:
    return {
        "arac_sinifi": "sabit_kanat",
        "tehdit_seviyesi": "yuksek",
        "tahmini_hedef_tipi": "askeri_ucak",
        "ulke_orjini": origin,
        "hedef_modeli": "F-35A Lightning II",
        "gorsel_analiz": "F-35A benzeri hedef.",
    }


@pytest.mark.asyncio
async def test_direct_raw_vlm_endpoint_requires_no_video_or_canonical_wrapper() -> None:
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/api/v1/analyze/raw-vlm", json=_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "raw-vlm-assessment/1.0"
    assert body["platform_id"] == "PLT_F35A"
    assert body["origin_comparison"] == "OPERATOR_AFFILIATION_UNVERIFIED"
    assert body["permission_status"] == "NOT_EVALUATED"
    assert body["flight_plan_status"] == "NOT_EVALUATED"
    assert body["notam_status"] == "NOT_EVALUATED"
    assert "video_id" not in body
    assert "analyze_request" not in body


@pytest.mark.asyncio
async def test_direct_raw_vlm_endpoint_rejects_operational_wrapper_fields() -> None:
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/analyze/raw-vlm",
            json={**_payload(), "video_id": "VIDEO_017"},
        )

    assert response.status_code == 422