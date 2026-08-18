"""Acceptance tests for remaining military platform expansion package 13."""
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
    (
        "PLT_B2_SPIRIT",
        "Northrop Grumman B-2 Spirit",
        "B-2 Spirit",
        "VIDEO_RAW_B2_DEFAULT",
        "FIGHTER_JET",
        "FIXED_WING_AIRCRAFT",
        "STRATEGIC_STRIKE",
        "STRATEGIC_BOMBER",
        "stratejik bombard\u0131man u\u00e7a\u011f\u0131",
    ),
    (
        "PLT_B52_STRATOFORTRESS",
        "Boeing B-52 Stratofortress",
        "B-52 Stratofortress",
        "VIDEO_RAW_B52_DEFAULT",
        "FIGHTER_JET",
        "FIXED_WING_AIRCRAFT",
        "STRATEGIC_STRIKE",
        "STRATEGIC_BOMBER",
        "stratejik bombard\u0131man u\u00e7a\u011f\u0131",
    ),
    (
        "PLT_KA52_ALLIGATOR",
        "Kamov Ka-52 Alligator",
        "Ka-52 Alligator",
        "VIDEO_RAW_KA52_DEFAULT",
        "HELICOPTER",
        "ROTARY_WING_AIRCRAFT",
        "ATTACK",
        "ATTACK_HELICOPTER",
        "taarruz helikopteri",
    ),
)


def _raw_vlm(model: str, category: str) -> RawVLMOutput:
    return RawVLMOutput.model_validate(
        {
            "arac_sinifi": "HELIKOPTER" if category == "HELICOPTER" else "SAVAS_UCAGI",
            "tehdit_seviyesi": "DUSUK",
            "tahmini_hedef_tipi": "askeri hava araci",
            "ulke_orjini": "Bilinmiyor",
            "hedef_modeli": model,
            "gorsel_analiz": f"Goruntude {model} platform hipotezi bulunmaktadir.",
        }
    )


def test_package13_registry_alias_taxonomy_inventory_routes_and_catalog() -> None:
    registry = load_platform_registry(REGISTRY_PATH)
    index = PlatformRegistryIndex(registry, load_platform_aliases(ALIASES_PATH))
    inventory = load_turkey_inventory_registry(INVENTORY_PATH, registry)
    catalog = {row["platform_id"]: row for row in _active_platform_catalog()}
    records = {item.platform_id: item for item in registry.platforms}
    for platform_id, canonical_name, alias, video_id, category, base, role, opclass, _ in PLATFORMS:
        canonical_match = index.find_exact_match(canonical_name)
        alias_match = index.find_exact_match(alias)
        assert canonical_match is not None and canonical_match.platform_id == platform_id
        assert alias_match is not None and alias_match.platform_id == platform_id
        record = records[platform_id]
        assert record.category.value == category
        assert record.taxonomy is not None
        assert record.taxonomy.base_category.value == base
        assert record.taxonomy.usage_domain.value == "MILITARY"
        assert record.taxonomy.primary_role == role
        assert record.taxonomy.operational_class == opclass
        assert record.taxonomy.traits
        assert inventory.find_active(platform_id) is None
        assert resolve_raw_vlm_video_id(platform_id) == (video_id, False)
        assert catalog[platform_id]["canonical_name"] == canonical_name
    assert validate_route_mapping() == []


@pytest.mark.asyncio
async def test_package13_raw_vlm_end_to_end_taxonomy_and_terminology(tmp_path: Path) -> None:
    harness = await build_harness(ROOT, tmp_path)
    for (
        platform_id,
        canonical_name,
        _alias,
        video_id,
        category,
        base,
        role,
        opclass,
        term,
    ) in PLATFORMS:
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
        taxonomy = output["platform_taxonomy"]
        assert taxonomy["base_category"] == base
        assert taxonomy["usage_domain"] == "MILITARY"
        assert taxonomy["primary_role"] == role
        assert taxonomy["operational_class"] == opclass
        assert output["inventory_status"] == "NOT_LISTED"
        assert output["verification_status"] == "UNVERIFIED"
        assert output["risk_level"] == "HIGH"
        assert output["decision"] == "UNREGISTERED_MILITARY_AIRCRAFT"
        assert term in output["summary_tr"]
        assert term in output["operational_report_tr"]
        for tool_name in ("permission_flight_plan_tool", "notam_tool"):
            execution = output["tool_execution_summary"][tool_name]
            assert execution["execution_status"] == "SKIPPED"
            assert execution["warnings"] == ["UNREGISTERED_MILITARY_POLICY"]


def test_package13_allowlist_registry_and_demo_scope_are_complete() -> None:
    registry = load_platform_registry(REGISTRY_PATH)
    allowlist = json.loads(
        (ROOT / "data/platforms/platform_allowlist.json").read_text(encoding="utf-8")
    )
    active_ids = {item.platform_id for item in registry.platforms if item.active}
    allowlist_ids = {item["platform_id"] for item in allowlist["platforms"]}
    scenarios = json.loads((ROOT / "data/seeds/demo_scenarios.json").read_text(encoding="utf-8"))
    assert len(registry.platforms) == 112
    assert len(active_ids) == 111
    assert len(allowlist_ids) == 111
    assert active_ids == allowlist_ids
    assert [item["scenario_id"] for item in scenarios] == [
        f"SCN-{number:02d}" for number in range(1, 24)
    ]
