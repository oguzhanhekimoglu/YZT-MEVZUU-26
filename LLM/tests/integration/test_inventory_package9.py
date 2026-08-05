"""Acceptance tests for foreign fighter expansion package 9."""
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

PLATFORMS = (
    ("PLT_A10_THUNDERBOLT_II", "A-10 Thunderbolt II", "A10", "VIDEO_RAW_A10_DEFAULT"),
    ("PLT_FA18EF_SUPER_HORNET", "F/A-18E/F Super Hornet", "F/A-18E/F", "VIDEO_RAW_FA18EF_DEFAULT"),
    ("PLT_J10", "Chengdu J-10", "J10", "VIDEO_RAW_J10_DEFAULT"),
    ("PLT_J20", "Chengdu J-20", "J20", "VIDEO_RAW_J20_DEFAULT"),
    ("PLT_JAS39_GRIPEN", "Saab JAS 39 Gripen", "Gripen", "VIDEO_RAW_JAS39_DEFAULT"),
    ("PLT_JF17_THUNDER", "JF-17 Thunder", "JF17", "VIDEO_RAW_JF17_DEFAULT"),
    ("PLT_MIG35", "Mikoyan MiG-35", "MiG-35", "VIDEO_RAW_MIG35_DEFAULT"),
    ("PLT_MIRAGE_2000", "Mirage 2000", "Mirage2000", "VIDEO_RAW_MIRAGE2000_DEFAULT"),
    ("PLT_SU27", "Sukhoi Su-27 Flanker", "Su27", "VIDEO_RAW_SU27_DEFAULT"),
    ("PLT_SU30", "Sukhoi Su-30", "Su30", "VIDEO_RAW_SU30_DEFAULT"),
    ("PLT_TEJAS", "HAL Tejas", "Tejas", "VIDEO_RAW_TEJAS_DEFAULT"),
)


def _raw_vlm(model: str) -> RawVLMOutput:
    return RawVLMOutput.model_validate(
        {
            "arac_sinifi": "SAVAS_UCAGI",
            "tehdit_seviyesi": "DUSUK",
            "tahmini_hedef_tipi": "askeri savas ucagi",
            "ulke_orjini": "Bilinmiyor",
            "hedef_modeli": model,
            "gorsel_analiz": f"Goruntude {model} platform hipotezi bulunmaktadir.",
        }
    )


def test_package9_registry_alias_inventory_routes_and_catalog() -> None:
    registry = load_platform_registry(REGISTRY_PATH)
    index = PlatformRegistryIndex(registry, load_platform_aliases(ALIASES_PATH))
    inventory = load_turkey_inventory_registry(INVENTORY_PATH, registry)
    catalog = {row["platform_id"]: row for row in _active_platform_catalog()}
    for platform_id, canonical_name, alias, video_id in PLATFORMS:
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
async def test_package9_raw_vlm_end_to_end_unregistered_military_policy(tmp_path: Path) -> None:
    harness = await build_harness(ROOT, tmp_path)
    for platform_id, canonical_name, _alias, video_id in PLATFORMS:
        raw_vlm = _raw_vlm(canonical_name)
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
        assert output["permission_status"] == "NOT_APPLICABLE"
        assert output["flight_plan_status"] == "NOT_APPLICABLE"
        assert output["verification_status"] == "UNVERIFIED"
        assert output["risk_level"] == "HIGH"
        assert output["decision"] == "UNREGISTERED_MILITARY_AIRCRAFT"
        for tool_name in ("permission_flight_plan_tool", "notam_tool"):
            execution = output["tool_execution_summary"][tool_name]
            assert execution["execution_status"] == "SKIPPED"
            assert execution["warnings"] == ["UNREGISTERED_MILITARY_POLICY"]


def test_package9_allowlist_and_demo_scenario_scope_unchanged() -> None:
    allowlist = json.loads(
        (ROOT / "data/platforms/platform_allowlist.json").read_text(encoding="utf-8")
    )
    scenarios = json.loads((ROOT / "data/seeds/demo_scenarios.json").read_text(encoding="utf-8"))
    assert len(allowlist["platforms"]) == 111
    assert [item["scenario_id"] for item in scenarios] == [
        f"SCN-{number:02d}" for number in range(1, 24)
    ]
