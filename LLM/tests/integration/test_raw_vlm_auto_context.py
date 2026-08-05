"""Integration tests for automated Ham VLM platform → context routing pipeline."""
# ruff: noqa: D103

import json
from pathlib import Path
from typing import Any

import pytest

from apps.demo_ui.raw_vlm_context_router import (
    load_raw_vlm_context_routes,
    raw_vlm_fallback_video_id,
    resolve_raw_vlm_video_id,
    validate_route_mapping,
)
from operational_decision.contracts.raw_vlm import RawVLMAdapterRequest
from operational_decision.input.raw_vlm_assessment import assess_raw_vlm
from operational_decision.input.upstream_vlm_adapter import adapt_friend_raw_vlm_to_request
from tests._phase7_support import build_harness

ROOT = Path(__file__).resolve().parents[2]


def _raw_vlm_payload(
    *,
    model: str,
    analysis: str,
    vehicle_class: str = "sabit_kanat",
    threat: str = "bilinmiyor",
    target_type: str = "askeri_ucak",
    origin: str = "Bilinmiyor",
) -> dict[str, Any]:
    return {
        "arac_sinifi": vehicle_class,
        "tehdit_seviyesi": threat,
        "tahmini_hedef_tipi": target_type,
        "ulke_orjini": origin,
        "hedef_modeli": model,
        "gorsel_analiz": analysis,
    }


def _assess(raw_vlm: dict[str, Any]) -> Any:
    from operational_decision.contracts.raw_vlm import RawVLMOutput

    validated = RawVLMOutput.model_validate(raw_vlm)
    return assess_raw_vlm(
        validated,
        platform_registry_path=ROOT / "data/platforms/platform_registry.json",
        platform_aliases_path=ROOT / "data/platforms/platform_aliases.json",
        inventory_path=ROOT / "data/inventory/turkey_inventory.json",
    )


def _adapter_request(raw_vlm: dict[str, Any], video_id: str) -> dict[str, Any]:
    req = RawVLMAdapterRequest.model_validate(
        {
            "raw_vlm": raw_vlm,
            "video_id": video_id,
            "track_id": "TRK_AUTO_TEST",
            "first_seen_offset_seconds": 0.0,
            "last_seen_offset_seconds": 1.0,
            "visual_confidence": 0.50,
        }
    )
    return adapt_friend_raw_vlm_to_request(req).analyze_request.model_dump(mode="json")


# ─── Route Mapping Validation ───────────────────────────────────────────────


def test_route_mapping_all_video_ids_exist_and_active() -> None:
    errors = validate_route_mapping()
    assert errors == [], errors


def test_route_mapping_all_platform_ids_are_in_registry() -> None:
    routes = load_raw_vlm_context_routes()
    registry = json.loads(
        (ROOT / "data/platforms/platform_registry.json").read_text(encoding="utf-8")
    )
    registry_ids = {
        item["platform_id"]
        for item in registry.get("platforms", [])
        if isinstance(item, dict)
    }
    for platform_id in routes:
        assert platform_id in registry_ids, f"{platform_id} not in platform_registry"


def test_route_mapping_has_no_duplicate_platform_ids() -> None:
    routes = load_raw_vlm_context_routes()
    assert len(routes) == len(set(routes.keys()))


# ─── Platform Resolution → video_id ─────────────────────────────────────────


def test_boeing_747_resolves_to_video_013() -> None:
    raw = _raw_vlm_payload(
        model="Boeing 747",
        analysis="Dört motorlu geniş gövdeli sivil yolcu uçağı.",
        target_type="yolcu_ucagi",
        vehicle_class="sabit_kanat",
    )
    result = _assess(raw)
    assert result.platform_id == "PLT_BOEING_747"
    video_id, is_fallback = resolve_raw_vlm_video_id(result.platform_id)
    assert video_id == "VIDEO_013"
    assert is_fallback is False


def test_tb2_resolves_to_video_014() -> None:
    raw = _raw_vlm_payload(
        model="Bayraktar TB2",
        analysis="Taktik İHA silueti görülmektedir.",
        target_type="iha",
        vehicle_class="sabit_kanat",
    )
    result = _assess(raw)
    assert result.platform_id == "PLT_BAYRAKTAR_TB2"
    video_id, is_fallback = resolve_raw_vlm_video_id(result.platform_id)
    assert video_id == "VIDEO_014"
    assert is_fallback is False


def test_f35a_resolves_to_video_017() -> None:
    raw = _raw_vlm_payload(
        model="F-35A Lightning II",
        analysis="Stealth savaş uçağı silueti.",
    )
    result = _assess(raw)
    assert result.platform_id == "PLT_F35A"
    video_id, is_fallback = resolve_raw_vlm_video_id(result.platform_id)
    assert video_id == "VIDEO_017"
    assert is_fallback is False


def test_mq9_resolves_to_video_018() -> None:
    raw = _raw_vlm_payload(
        model="MQ-9 Reaper",
        analysis="Uzun havada kalış kabiliyetli SİHA.",
    )
    result = _assess(raw)
    assert result.platform_id == "PLT_MQ9_REAPER"
    video_id, is_fallback = resolve_raw_vlm_video_id(result.platform_id)
    assert video_id == "VIDEO_018"
    assert is_fallback is False


def test_unresolved_model_uses_fallback() -> None:
    video_id, is_fallback = resolve_raw_vlm_video_id(None)
    fallback = raw_vlm_fallback_video_id()
    assert video_id == fallback
    assert is_fallback is True


def test_unknown_platform_id_uses_fallback() -> None:
    video_id, is_fallback = resolve_raw_vlm_video_id("PLT_NONEXISTENT_XYZ")
    assert is_fallback is True


# ─── Full Pipeline: Boeing 747 (CIVIL, NOT_LISTED → VERIFIED/LOW) ────────────


@pytest.mark.asyncio
async def test_boeing_747_auto_context_full_pipeline(tmp_path: Path) -> None:
    harness = await build_harness(ROOT, tmp_path)
    raw = _raw_vlm_payload(
        model="Boeing 747",
        analysis="Dört motorlu geniş gövdeli sivil yolcu uçağı.",
        target_type="yolcu_ucagi",
        vehicle_class="sabit_kanat",
    )
    result = _assess(raw)
    assert result.platform_id == "PLT_BOEING_747"
    video_id, is_fallback = resolve_raw_vlm_video_id(result.platform_id)
    assert video_id == "VIDEO_013"
    assert is_fallback is False

    canonical = _adapter_request(raw, video_id)
    outcome = await harness.orchestrator.analyze(canonical)
    assert outcome.http_status == 200
    assert outcome.output is not None

    output = outcome.output
    assert output["matched_platform"] == "Boeing 747"
    assert output["inventory_status"] == "NOT_LISTED"
    assert output["permission_status"] == "VALID"
    assert output["flight_plan_status"] == "FILED"
    assert output["verification_status"] == "VERIFIED"
    assert output["risk_level"] == "LOW"
    assert output["decision"] == "AUTHORIZED_OPERATIONAL_MATCH"
    assert output["human_approval_required"] is False
    assert output["human_review_reasons"] == []
    assert "REQUEST_OPERATOR_REVIEW" not in {
        item["action_code"] for item in output["recommended_actions"]
    }
    assert "ek insan incelemesi gerekli değildir" in output["summary_tr"]


# ─── Full Pipeline: TB2 (Inventory CONFIRMED) ────────────────────────────────


@pytest.mark.asyncio
async def test_tb2_auto_context_full_pipeline(tmp_path: Path) -> None:
    harness = await build_harness(ROOT, tmp_path)
    raw = _raw_vlm_payload(
        model="Bayraktar TB2",
        analysis="Taktik İHA silueti görülmektedir.",
        target_type="iha",
        vehicle_class="sabit_kanat",
    )
    result = _assess(raw)
    assert result.platform_id == "PLT_BAYRAKTAR_TB2"
    video_id, is_fallback = resolve_raw_vlm_video_id(result.platform_id)
    assert video_id == "VIDEO_014"

    canonical = _adapter_request(raw, video_id)
    outcome = await harness.orchestrator.analyze(canonical)
    assert outcome.http_status == 200
    assert outcome.output is not None

    output = outcome.output
    assert output["inventory_status"] == "CONFIRMED"

    trace = await harness.event_service.get_event_trace(outcome.event_id)
    tool_names = [row["tool_name"] for row in trace["tool_executions"]]
    assert "permission_flight_plan_tool" in tool_names
    assert "notam_tool" in tool_names


# ─── Full Pipeline: F-35A (MILITARY NOT_LISTED → HIGH) ───────────────────────


@pytest.mark.asyncio
async def test_f35a_auto_context_unregistered_military_policy(tmp_path: Path) -> None:
    harness = await build_harness(ROOT, tmp_path)
    raw = _raw_vlm_payload(
        model="F-35A Lightning II",
        analysis="Stealth savaş uçağı silueti.",
    )
    result = _assess(raw)
    assert result.platform_id == "PLT_F35A"
    video_id, is_fallback = resolve_raw_vlm_video_id(result.platform_id)
    assert video_id == "VIDEO_017"

    canonical = _adapter_request(raw, video_id)
    outcome = await harness.orchestrator.analyze(canonical)
    assert outcome.http_status == 200
    assert outcome.output is not None

    output = outcome.output
    assert output["risk_level"] == "HIGH"
    assert output["verification_status"] == "UNVERIFIED"
    assert output["decision"] == "UNREGISTERED_MILITARY_AIRCRAFT"

    trace = await harness.event_service.get_event_trace(outcome.event_id)
    for row in trace["tool_executions"]:
        if row["tool_name"] in ("permission_flight_plan_tool", "notam_tool"):
            assert row["response"]["execution_status"] == "SKIPPED"


# ─── Full Pipeline: MQ-9 (MILITARY NOT_LISTED → HIGH) ────────────────────────


@pytest.mark.asyncio
async def test_mq9_auto_context_unregistered_military_policy(tmp_path: Path) -> None:
    harness = await build_harness(ROOT, tmp_path)
    raw = _raw_vlm_payload(
        model="MQ-9 Reaper",
        analysis="Uzun havada kalış kabiliyetli SİHA.",
    )
    result = _assess(raw)
    assert result.platform_id == "PLT_MQ9_REAPER"
    video_id, is_fallback = resolve_raw_vlm_video_id(result.platform_id)
    assert video_id == "VIDEO_018"

    canonical = _adapter_request(raw, video_id)
    outcome = await harness.orchestrator.analyze(canonical)
    assert outcome.http_status == 200
    assert outcome.output is not None

    output = outcome.output
    assert output["risk_level"] == "HIGH"
    assert output["verification_status"] == "UNVERIFIED"
    assert output["decision"] == "UNREGISTERED_MILITARY_AIRCRAFT"


# ─── Full Pipeline: Unresolved Model → Fallback ──────────────────────────────


@pytest.mark.asyncio
async def test_unresolved_model_fallback_context_pipeline(tmp_path: Path) -> None:
    _ = await build_harness(ROOT, tmp_path)
    raw = _raw_vlm_payload(
        model="Tanımlanamayan Hava Aracı",
        analysis="Belirsiz siluet görülmektedir.",
        target_type="bilinmeyen",
        vehicle_class="sabit_kanat",
    )
    result = _assess(raw)
    assert result.platform_id is None

    video_id, is_fallback = resolve_raw_vlm_video_id(result.platform_id)
    assert is_fallback is True
