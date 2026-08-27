"""Acceptance tests for foreign UAS expansion package 12."""
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
    ("PLT_CH4", "CASC CH-4", "CH4", "VIDEO_RAW_CH4_DEFAULT", "UCAV", "ISR_STRIKE", "MALE_UCAS"),
    (
        "PLT_FORPOST_R",
        "Forpost-R",
        "Forpost R",
        "VIDEO_RAW_FORPOST_R_DEFAULT",
        "UCAV",
        "ISR_STRIKE",
        "MALE_UCAS",
    ),
    (
        "PLT_HERMES_450",
        "Elbit Hermes 450",
        "Hermes 450",
        "VIDEO_RAW_HERMES450_DEFAULT",
        "UAV",
        "ISR",
        "MALE_UAS",
    ),
    (
        "PLT_HERMES_900",
        "Elbit Hermes 900",
        "Hermes 900",
        "VIDEO_RAW_HERMES900_DEFAULT",
        "UAV",
        "ISR",
        "MALE_UAS",
    ),
    (
        "PLT_HERON_TP",
        "IAI Heron TP",
        "Heron TP",
        "VIDEO_RAW_HERON_TP_DEFAULT",
        "UAV",
        "ISR",
        "MALE_UAS",
    ),
    (
        "PLT_MQ1_PREDATOR",
        "MQ-1 Predator",
        "MQ1",
        "VIDEO_RAW_MQ1_DEFAULT",
        "UCAV",
        "ISR_STRIKE",
        "MALE_UCAS",
    ),
    (
        "PLT_MQ9B_SKYGUARDIAN",
        "MQ-9B SkyGuardian",
        "MQ9B",
        "VIDEO_RAW_MQ9B_DEFAULT",
        "UAV",
        "ISR",
        "MALE_UAS",
    ),
    (
        "PLT_ORION_UAV",
        "Kronstadt Orion \u0130HA",
        "Orion UAV",
        "VIDEO_RAW_ORION_DEFAULT",
        "UCAV",
        "ISR_STRIKE",
        "MALE_UCAS",
    ),
    (
        "PLT_RQ170_SENTINEL",
        "RQ-170 Sentinel",
        "RQ170",
        "VIDEO_RAW_RQ170_DEFAULT",
        "UAV",
        "RECONNAISSANCE",
        "STEALTH_RECONNAISSANCE_UAS",
    ),
    (
        "PLT_RQ4_GLOBAL_HAWK",
        "RQ-4 Global Hawk",
        "RQ4",
        "VIDEO_RAW_RQ4_DEFAULT",
        "UAV",
        "STRATEGIC_RECONNAISSANCE",
        "HALE_UAS",
    ),
    (
        "PLT_WING_LOONG_I",
        "Wing Loong I",
        "Wing Loong 1",
        "VIDEO_RAW_WING_LOONG_I_DEFAULT",
        "UCAV",
        "ISR_STRIKE",
        "MALE_UCAS",
    ),
    (
        "PLT_WING_LOONG_II",
        "Wing Loong II",
        "Wing Loong 2",
        "VIDEO_RAW_WING_LOONG_II_DEFAULT",
        "UCAV",
        "ISR_STRIKE",
        "MALE_UCAS",
    ),
    (
        "PLT_WZ7_SOARING_DRAGON",
        "WZ-7 Soaring Dragon",
        "WZ7",
        "VIDEO_RAW_WZ7_DEFAULT",
        "UAV",
        "STRATEGIC_RECONNAISSANCE",
        "HALE_UAS",
    ),
)


def _raw_vlm(model: str, category: str) -> RawVLMOutput:
    return RawVLMOutput.model_validate(
        {
            "arac_sinifi": "SIHA" if category == "UCAV" else "IHA",
            "tehdit_seviyesi": "DUSUK",
            "tahmini_hedef_tipi": "askeri sabit kanatli siha"
            if category == "UCAV"
            else "askeri sabit kanatli iha",
            "ulke_orjini": "Bilinmiyor",
            "hedef_modeli": model,
            "gorsel_analiz": f"Goruntude {model} platform hipotezi bulunmaktadir.",
        }
    )


def test_package12_registry_alias_taxonomy_inventory_routes_and_catalog() -> None:
    registry = load_platform_registry(REGISTRY_PATH)
    index = PlatformRegistryIndex(registry, load_platform_aliases(ALIASES_PATH))
    inventory = load_turkey_inventory_registry(INVENTORY_PATH, registry)
    catalog = {row["platform_id"]: row for row in _active_platform_catalog()}
    records = {item.platform_id: item for item in registry.platforms}
    for platform_id, canonical_name, alias, video_id, category, role, opclass in PLATFORMS:
        canonical_match = index.find_exact_match(canonical_name)
        alias_match = index.find_exact_match(alias)
        assert canonical_match is not None and canonical_match.platform_id == platform_id
        assert alias_match is not None and alias_match.platform_id == platform_id
        record = records[platform_id]
        assert record.category.value == category
        assert record.taxonomy is not None
        assert record.taxonomy.base_category.value == "FIXED_WING_AIRCRAFT"
        assert record.taxonomy.usage_domain.value == "MILITARY"
        assert record.taxonomy.primary_role == role
        assert record.taxonomy.operational_class == opclass
        assert inventory.find_active(platform_id) is None
        assert resolve_raw_vlm_video_id(platform_id) == (video_id, False)
        assert catalog[platform_id]["canonical_name"] == canonical_name
        assert catalog[platform_id]["user_type"] == (
            "S\u0130HA" if category == "UCAV" else "\u0130HA"
        )
    assert index.find_exact_match("Predator").platform_id == "PLT_MQ1_PREDATOR"
    assert index.find_exact_match("MQ-9").platform_id == "PLT_MQ9_REAPER"
    assert index.find_exact_match("MQ9").platform_id == "PLT_MQ9_REAPER"
    assert index.find_exact_match("Wing Loong") is None
    assert validate_route_mapping() == []


@pytest.mark.asyncio
async def test_package12_raw_vlm_end_to_end_and_final_taxonomy(tmp_path: Path) -> None:
    harness = await build_harness(ROOT, tmp_path)
    for platform_id, canonical_name, _alias, video_id, category, role, opclass in PLATFORMS:
        raw_vlm = _raw_vlm(canonical_name, category)
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
        assert output["canonical_name"] == canonical_name
        assert output["platform_category"] == category
        taxonomy = output["platform_taxonomy"]
        assert taxonomy["base_category"] == "FIXED_WING_AIRCRAFT"
        assert taxonomy["usage_domain"] == "MILITARY"
        assert taxonomy["primary_role"] == role
        assert taxonomy["operational_class"] == opclass
        assert output["inventory_status"] == "NOT_LISTED"
        assert output["verification_status"] == "UNVERIFIED"
        assert output["risk_level"] == "HIGH"
        assert output["decision"] == "UNREGISTERED_MILITARY_AIRCRAFT"
        for tool_name in ("permission_flight_plan_tool", "notam_tool"):
            execution = output["tool_execution_summary"][tool_name]
            assert execution["execution_status"] == "SKIPPED"
            assert execution["warnings"] == ["UNREGISTERED_MILITARY_POLICY"]


def test_package12_allowlist_and_demo_scenario_scope_unchanged() -> None:
    allowlist = json.loads(
        (ROOT / "data/platforms/platform_allowlist.json").read_text(encoding="utf-8")
    )
    scenarios = json.loads((ROOT / "data/seeds/demo_scenarios.json").read_text(encoding="utf-8"))
    assert len(allowlist["platforms"]) == 112
    assert [item["scenario_id"] for item in scenarios] == [
        f"SCN-{number:02d}" for number in range(1, 24)
    ]
