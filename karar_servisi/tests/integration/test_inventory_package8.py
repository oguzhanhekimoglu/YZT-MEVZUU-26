"""Acceptance tests for Turkey Inventory accuracy and expansion package 8."""
# ruff: noqa: D103

import json
from pathlib import Path

import pytest

from apps.demo_ui.raw_vlm_context_router import resolve_raw_vlm_video_id, validate_route_mapping
from operational_decision.contracts.raw_vlm import RawVLMAdapterRequest, RawVLMOutput
from operational_decision.input.raw_vlm_assessment import assess_raw_vlm
from operational_decision.input.upstream_vlm_adapter import adapt_friend_raw_vlm_to_request
from operational_decision.inventory.turkey_inventory_registry import load_turkey_inventory_registry
from operational_decision.platform.platform_registry import (
    PlatformRegistryIndex,
    load_platform_aliases,
    load_platform_registry,
)
from tests._phase7_support import build_harness

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "data/platforms/platform_registry.json"
ALIASES_PATH = ROOT / "data/platforms/platform_aliases.json"
INVENTORY_PATH = ROOT / "data/inventory/turkey_inventory.json"

CORRECTED_NOT_LISTED = (
    (
        "PLT_HURKUS",
        "TUSA\u015e H\u00dcRKU\u015e",
        "HURKUS",
        "VIDEO_RAW_HURKUS_DEFAULT",
        "SAVAS_UCAGI",
        "egitim ucagi",
    ),
    ("PLT_STM_ALPAGU", "STM ALPAGU", "ALPAGU", "VIDEO_RAW_ALPAGU_DEFAULT", "SIHA", "vurucu iha"),
    (
        "PLT_TUSAS_SUPER_SIMSEK",
        "TUSA\u015e S\u00dcPER \u015e\u0130M\u015eEK",
        "SUPER SIMSEK",
        "VIDEO_RAW_SUPER_SIMSEK_DEFAULT",
        "IHA",
        "hedef iha",
    ),
)

NEW_CONFIRMED = (
    (
        "PLT_F5_FREEDOM_FIGHTER",
        "F-5 Freedom Fighter",
        "F5",
        "VIDEO_RAW_F5_DEFAULT",
        "SAVAS_UCAGI",
        "savas ucagi",
    ),
    (
        "PLT_NF5_TURK_YILDIZLARI",
        "NF-5 T\u00fcrk Y\u0131ld\u0131zlar\u0131",
        "NF5",
        "VIDEO_RAW_NF5_DEFAULT",
        "SAVAS_UCAGI",
        "akrobasi ucagi",
    ),
    ("PLT_T38_TALON", "T-38 Talon", "T38", "VIDEO_RAW_T38_DEFAULT", "SAVAS_UCAGI", "egitim ucagi"),
    (
        "PLT_SIKORSKY_S70",
        "Sikorsky S-70 Black Hawk",
        "Black Hawk",
        "VIDEO_RAW_S70_DEFAULT",
        "HELIKOPTER",
        "genel maksat helikopteri",
    ),
    (
        "PLT_CH47F_CHINOOK",
        "Boeing CH-47F Chinook",
        "CH47F",
        "VIDEO_RAW_CH47F_DEFAULT",
        "HELIKOPTER",
        "agir nakliye helikopteri",
    ),
    (
        "PLT_AS532_COUGAR",
        "Airbus AS532 Cougar",
        "AS532",
        "VIDEO_RAW_AS532_DEFAULT",
        "HELIKOPTER",
        "genel maksat helikopteri",
    ),
    (
        "PLT_UH1_HUEY",
        "Bell UH-1 Huey",
        "UH1",
        "VIDEO_RAW_UH1_DEFAULT",
        "HELIKOPTER",
        "genel maksat helikopteri",
    ),
    (
        "PLT_AH1_SUPER_COBRA",
        "Bell AH-1 Super Cobra",
        "AH1",
        "VIDEO_RAW_AH1_DEFAULT",
        "HELIKOPTER",
        "taarruz helikopteri",
    ),
)


def _raw_vlm(model: str, vehicle_class: str, target_type: str) -> RawVLMOutput:
    return RawVLMOutput.model_validate(
        {
            "arac_sinifi": vehicle_class,
            "tehdit_seviyesi": "DUSUK",
            "tahmini_hedef_tipi": target_type,
            "ulke_orjini": "TR",
            "hedef_modeli": model,
            "gorsel_analiz": f"Goruntude {model} platform hipotezi bulunmaktadir.",
        }
    )


def test_package8_registry_alias_inventory_routes_and_collision_boundaries() -> None:
    registry = load_platform_registry(REGISTRY_PATH)
    aliases = load_platform_aliases(ALIASES_PATH)
    index = PlatformRegistryIndex(registry, aliases)
    inventory = load_turkey_inventory_registry(INVENTORY_PATH, registry)

    for platform_id, canonical_name, alias, video_id, *_unused in CORRECTED_NOT_LISTED:
        assert index.find_exact_match(canonical_name).platform_id == platform_id
        assert index.find_exact_match(alias).platform_id == platform_id
        assert inventory.find_active(platform_id) is None
        assert resolve_raw_vlm_video_id(platform_id) == (video_id, False)

    for platform_id, canonical_name, alias, video_id, *_unused in NEW_CONFIRMED:
        assert index.find_exact_match(canonical_name).platform_id == platform_id
        assert index.find_exact_match(alias).platform_id == platform_id
        record = inventory.find_active(platform_id)
        assert record is not None and record.source_type == "DEMO_MOCK"
        assert resolve_raw_vlm_video_id(platform_id) == (video_id, False)

    assert index.find_exact_match("Black Hawk").platform_id == "PLT_SIKORSKY_S70"
    assert index.find_exact_match("F-5").platform_id == "PLT_F5_FREEDOM_FIGHTER"
    assert index.find_exact_match("NF-5").platform_id == "PLT_NF5_TURK_YILDIZLARI"
    assert validate_route_mapping() == []


@pytest.mark.asyncio
async def test_package8_raw_vlm_end_to_end_policies(tmp_path: Path) -> None:
    harness = await build_harness(ROOT, tmp_path)
    for expected_confirmed, rows in ((False, CORRECTED_NOT_LISTED), (True, NEW_CONFIRMED)):
        for platform_id, canonical_name, _alias, video_id, vehicle_class, target_type in rows:
            raw_vlm = _raw_vlm(canonical_name, vehicle_class, target_type)
            assessment = assess_raw_vlm(
                raw_vlm,
                platform_registry_path=REGISTRY_PATH,
                platform_aliases_path=ALIASES_PATH,
                inventory_path=INVENTORY_PATH,
            )
            assert assessment.platform_id == platform_id
            expected_inventory = "CONFIRMED" if expected_confirmed else "NOT_LISTED"
            assert assessment.inventory_status.value == expected_inventory
            adapted = adapt_friend_raw_vlm_to_request(
                RawVLMAdapterRequest(
                    raw_vlm=raw_vlm,
                    video_id=video_id,
                    track_id=f"TRK_{platform_id}",
                    first_seen_offset_seconds=8.2,
                    last_seen_offset_seconds=15.6,
                    visual_confidence=0.85,
                )
            )
            outcome = await harness.orchestrator.analyze(
                adapted.analyze_request.model_dump(mode="json")
            )
            assert outcome.http_status == 200 and outcome.output is not None
            output = outcome.output
            assert output["matched_platform"] == canonical_name
            assert output["inventory_status"] == expected_inventory
            permission_execution = output["tool_execution_summary"]["permission_flight_plan_tool"]
            notam_execution = output["tool_execution_summary"]["notam_tool"]
            if expected_confirmed:
                assert output["permission_status"] == "VALID"
                assert output["flight_plan_status"] == "FILED"
                assert output["notam_status"] == "NONE_ACTIVE"
                assert output["verification_status"] == "VERIFIED"
                assert output["risk_level"] == "LOW"
                assert output["decision"] == "AUTHORIZED_OPERATIONAL_MATCH"
                assert permission_execution["execution_status"] == "SUCCESS"
                assert notam_execution["execution_status"] == "SUCCESS"
            else:
                assert output["permission_status"] == "NOT_APPLICABLE"
                assert output["flight_plan_status"] == "NOT_APPLICABLE"
                assert output["verification_status"] == "UNVERIFIED"
                assert output["risk_level"] == "HIGH"
                assert output["decision"] == "UNREGISTERED_MILITARY_AIRCRAFT"
                assert permission_execution["execution_status"] == "SKIPPED"
                assert notam_execution["execution_status"] == "SKIPPED"


def test_package8_keeps_allowlist_and_demo_scenario_scope() -> None:
    allowlist = json.loads(
        (ROOT / "data/platforms/platform_allowlist.json").read_text(encoding="utf-8")
    )
    scenarios = json.loads((ROOT / "data/seeds/demo_scenarios.json").read_text(encoding="utf-8"))
    assert len(allowlist["platforms"]) == 112
    assert [item["scenario_id"] for item in scenarios] == [
        f"SCN-{number:02d}" for number in range(1, 24)
    ]
