"""Acceptance tests for transport, special mission and civil package 10."""
# ruff: noqa: D103

import json
from pathlib import Path

import pytest

from apps.demo_ui.app import _active_platform_catalog
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

MILITARY = (
    (
        "PLT_A330_243_MRTT",
        "Airbus A330-243 MRTT",
        "A330 MRTT",
        "VIDEO_RAW_A330_MRTT_DEFAULT",
        "NAKLIYE_UCAGI",
        "askeri tanker ucagi",
    ),
    (
        "PLT_AN124_RUSLAN",
        "Antonov An-124 Ruslan",
        "An124",
        "VIDEO_RAW_AN124_DEFAULT",
        "NAKLIYE_UCAGI",
        "askeri nakliye ucagi",
    ),
    (
        "PLT_C17_GLOBEMASTER_III",
        "C-17 Globemaster III",
        "C17",
        "VIDEO_RAW_C17_DEFAULT",
        "NAKLIYE_UCAGI",
        "askeri nakliye ucagi",
    ),
    (
        "PLT_C295W",
        "Airbus C-295W",
        "C295W",
        "VIDEO_RAW_C295W_DEFAULT",
        "NAKLIYE_UCAGI",
        "askeri nakliye ucagi",
    ),
    (
        "PLT_P8A_POSEIDON",
        "Boeing P-8A Poseidon",
        "P8A",
        "VIDEO_RAW_P8A_DEFAULT",
        "NAKLIYE_UCAGI",
        "ozel gorev ucagi",
    ),
    (
        "PLT_V22_OSPREY",
        "Bell Boeing V-22 Osprey",
        "V22",
        "VIDEO_RAW_V22_DEFAULT",
        "HELIKOPTER",
        "tiltrotor askeri nakliye",
    ),
)

CIVIL = (
    (
        "PLT_AIRBUS_A321",
        "Airbus A321",
        "A321",
        "VIDEO_RAW_A321_DEFAULT",
        "SIVIL_UCAK",
        "yolcu ucagi",
    ),
    (
        "PLT_AIRBUS_A350",
        "Airbus A350",
        "A350",
        "VIDEO_RAW_A350_DEFAULT",
        "SIVIL_UCAK",
        "yolcu ucagi",
    ),
    (
        "PLT_AIRBUS_A380",
        "Airbus A380",
        "A380",
        "VIDEO_RAW_A380_DEFAULT",
        "SIVIL_UCAK",
        "yolcu ucagi",
    ),
    (
        "PLT_ATR72",
        "ATR 72",
        "ATR72",
        "VIDEO_RAW_ATR72_DEFAULT",
        "SIVIL_UCAK",
        "bolgesel yolcu ucagi",
    ),
    (
        "PLT_BOEING_787",
        "Boeing 787 Dreamliner",
        "B787",
        "VIDEO_RAW_B787_DEFAULT",
        "SIVIL_UCAK",
        "yolcu ucagi",
    ),
    (
        "PLT_CESSNA_172",
        "Cessna 172 Skyhawk",
        "C172",
        "VIDEO_RAW_CESSNA172_DEFAULT",
        "SIVIL_UCAK",
        "genel havacilik ucagi",
    ),
    (
        "PLT_PIPER_PA28",
        "Piper PA-28 Cherokee",
        "PA28",
        "VIDEO_RAW_PIPER_PA28_DEFAULT",
        "SIVIL_UCAK",
        "genel havacilik ucagi",
    ),
)


def _raw_vlm(model: str, vehicle_class: str, target_type: str) -> RawVLMOutput:
    return RawVLMOutput.model_validate(
        {
            "arac_sinifi": vehicle_class,
            "tehdit_seviyesi": "DUSUK",
            "tahmini_hedef_tipi": target_type,
            "ulke_orjini": "Bilinmiyor",
            "hedef_modeli": model,
            "gorsel_analiz": f"Goruntude {model} platform hipotezi bulunmaktadir.",
        }
    )


def test_package10_registry_alias_inventory_routes_and_catalog() -> None:
    registry = load_platform_registry(REGISTRY_PATH)
    index = PlatformRegistryIndex(registry, load_platform_aliases(ALIASES_PATH))
    inventory = load_turkey_inventory_registry(INVENTORY_PATH, registry)
    catalog = {row["platform_id"]: row for row in _active_platform_catalog()}
    for platform_id, canonical_name, alias, video_id, *_unused in MILITARY + CIVIL:
        canonical_match = index.find_exact_match(canonical_name)
        alias_match = index.find_exact_match(alias)
        assert canonical_match is not None and canonical_match.platform_id == platform_id
        assert alias_match is not None and alias_match.platform_id == platform_id
        assert inventory.find_active(platform_id) is None
        assert resolve_raw_vlm_video_id(platform_id) == (video_id, False)
        assert catalog[platform_id]["canonical_name"] == canonical_name
        assert catalog[platform_id]["inventory"] == "Envanter D\u0131\u015f\u0131"
    assert validate_route_mapping() == []


@pytest.mark.asyncio
async def test_package10_raw_vlm_end_to_end_policies(tmp_path: Path) -> None:
    harness = await build_harness(ROOT, tmp_path)
    for is_civil, rows in ((False, MILITARY), (True, CIVIL)):
        for platform_id, canonical_name, _alias, video_id, vehicle_class, target_type in rows:
            raw_vlm = _raw_vlm(canonical_name, vehicle_class, target_type)
            assessment = assess_raw_vlm(
                raw_vlm,
                platform_registry_path=REGISTRY_PATH,
                platform_aliases_path=ALIASES_PATH,
                inventory_path=INVENTORY_PATH,
            )
            assert assessment.platform_id == platform_id
            assert assessment.inventory_status.value == "NOT_LISTED"
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
            assert output["inventory_status"] == "NOT_LISTED"
            permission_execution = output["tool_execution_summary"]["permission_flight_plan_tool"]
            notam_execution = output["tool_execution_summary"]["notam_tool"]
            if is_civil:
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
                for execution in (permission_execution, notam_execution):
                    assert execution["execution_status"] == "SKIPPED"
                    assert execution["warnings"] == ["UNREGISTERED_MILITARY_POLICY"]


def test_package10_allowlist_and_demo_scenario_scope_unchanged() -> None:
    allowlist = json.loads(
        (ROOT / "data/platforms/platform_allowlist.json").read_text(encoding="utf-8")
    )
    scenarios = json.loads((ROOT / "data/seeds/demo_scenarios.json").read_text(encoding="utf-8"))
    assert len(allowlist["platforms"]) == 111
    assert [item["scenario_id"] for item in scenarios] == [
        f"SCN-{number:02d}" for number in range(1, 24)
    ]
