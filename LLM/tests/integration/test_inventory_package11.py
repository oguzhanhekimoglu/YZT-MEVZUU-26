"""Acceptance tests for micro, commercial and loitering UAS package 11."""
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

DJI = (
    ("PLT_DJI_AIR_SERIES", "DJI Air Serisi", "DJI Air", "VIDEO_RAW_DJI_AIR_DEFAULT"),
    ("PLT_DJI_MATRICE_300", "DJI Matrice 300", "Matrice 300", "VIDEO_RAW_MATRICE300_DEFAULT"),
    ("PLT_DJI_MATRICE_350", "DJI Matrice 350", "Matrice 350", "VIDEO_RAW_MATRICE350_DEFAULT"),
    ("PLT_DJI_MAVIC_2", "DJI Mavic 2", "Mavic 2", "VIDEO_RAW_MAVIC2_DEFAULT"),
    ("PLT_DJI_MAVIC_3", "DJI Mavic 3", "Mavic 3", "VIDEO_RAW_MAVIC3_DEFAULT"),
    ("PLT_DJI_MINI_SERIES", "DJI Mini Serisi", "DJI Mini", "VIDEO_RAW_DJI_MINI_DEFAULT"),
    (
        "PLT_DJI_PHANTOM_SERIES",
        "DJI Phantom Serisi",
        "DJI Phantom",
        "VIDEO_RAW_DJI_PHANTOM_DEFAULT",
    ),
)

MILITARY = (
    ("PLT_HAROP", "IAI Harop", "Harop", "VIDEO_RAW_HAROP_DEFAULT"),
    ("PLT_SHAHED136_GERAN2", "Shahed-136 / Geran-2", "Geran-2", "VIDEO_RAW_SHAHED136_DEFAULT"),
)


def _raw_vlm(model: str, target_type: str) -> RawVLMOutput:
    return RawVLMOutput.model_validate(
        {
            "arac_sinifi": "IHA" if target_type == "ticari multirotor iha" else "SIHA",
            "tehdit_seviyesi": "DUSUK",
            "tahmini_hedef_tipi": target_type,
            "ulke_orjini": "Bilinmiyor",
            "hedef_modeli": model,
            "gorsel_analiz": f"Goruntude {model} platform hipotezi bulunmaktadir.",
        }
    )


def test_package11_registry_alias_taxonomy_inventory_routes_and_catalog() -> None:
    registry = load_platform_registry(REGISTRY_PATH)
    index = PlatformRegistryIndex(registry, load_platform_aliases(ALIASES_PATH))
    inventory = load_turkey_inventory_registry(INVENTORY_PATH, registry)
    catalog = {row["platform_id"]: row for row in _active_platform_catalog()}
    records = {item.platform_id: item for item in registry.platforms}
    for platform_id, canonical_name, alias, video_id in DJI + MILITARY:
        canonical_match = index.find_exact_match(canonical_name)
        alias_match = index.find_exact_match(alias)
        assert canonical_match is not None and canonical_match.platform_id == platform_id
        assert alias_match is not None and alias_match.platform_id == platform_id
        taxonomy = records[platform_id].taxonomy
        assert taxonomy is not None
        assert taxonomy.primary_role is not None
        assert taxonomy.operational_class is not None
        assert inventory.find_active(platform_id) is None
        assert resolve_raw_vlm_video_id(platform_id) == (video_id, False)
        assert catalog[platform_id]["canonical_name"] == canonical_name
        assert catalog[platform_id]["inventory"] == "Envanter D\u0131\u015f\u0131"
    assert index.find_exact_match("DJI Mavic") is None
    assert index.find_exact_match("Harpy") is None
    assert index.find_exact_match("Shahed-136").platform_id == "PLT_SHAHED136_GERAN2"
    assert index.find_exact_match("Geran-2").platform_id == "PLT_SHAHED136_GERAN2"
    assert validate_route_mapping() == []


@pytest.mark.asyncio
async def test_package11_raw_vlm_end_to_end_and_final_taxonomy(tmp_path: Path) -> None:
    harness = await build_harness(ROOT, tmp_path)
    for is_civil, rows in ((True, DJI), (False, MILITARY)):
        target_type = "ticari multirotor iha" if is_civil else "vurucu dolasan muhimmat"
        for platform_id, canonical_name, _alias, video_id in rows:
            raw_vlm = _raw_vlm(canonical_name, target_type)
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
            assert output["platform_id"] == platform_id
            assert output["matched_platform"] == canonical_name
            assert output["canonical_name"] == canonical_name
            assert output["platform_category"] == ("UAV" if is_civil else "UCAV")
            taxonomy = output["platform_taxonomy"]
            assert taxonomy["base_category"] == (
                "MULTIROTOR_AIRCRAFT" if is_civil else "FIXED_WING_AIRCRAFT"
            )
            assert taxonomy["usage_domain"] == ("CIVIL" if is_civil else "MILITARY")
            assert taxonomy["primary_role"]
            assert taxonomy["operational_class"]
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
                assert output["verification_status"] == "UNVERIFIED"
                assert output["risk_level"] == "HIGH"
                assert output["decision"] == "UNREGISTERED_MILITARY_AIRCRAFT"
                for execution in (permission_execution, notam_execution):
                    assert execution["execution_status"] == "SKIPPED"
                    assert execution["warnings"] == ["UNREGISTERED_MILITARY_POLICY"]


def test_package11_allowlist_and_demo_scenario_scope_unchanged() -> None:
    allowlist = json.loads(
        (ROOT / "data/platforms/platform_allowlist.json").read_text(encoding="utf-8")
    )
    scenarios = json.loads((ROOT / "data/seeds/demo_scenarios.json").read_text(encoding="utf-8"))
    assert len(allowlist["platforms"]) == 111
    assert [item["scenario_id"] for item in scenarios] == [
        f"SCN-{number:02d}" for number in range(1, 24)
    ]
