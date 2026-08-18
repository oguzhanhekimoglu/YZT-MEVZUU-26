"""Acceptance tests for Turkey Inventory expansion package 3."""
# ruff: noqa: D103

import json
from pathlib import Path

import pytest

from apps.demo_ui.app import _active_platform_catalog
from apps.demo_ui.raw_vlm_context_router import (
    resolve_raw_vlm_video_id,
    validate_route_mapping,
)
from operational_decision.contracts.raw_vlm import RawVLMAdapterRequest, RawVLMOutput
from operational_decision.input.raw_vlm_assessment import assess_raw_vlm
from operational_decision.input.upstream_vlm_adapter import adapt_friend_raw_vlm_to_request
from operational_decision.inventory.turkey_inventory_registry import (
    load_turkey_inventory_registry,
)
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
        "PLT_TUSAS_AKSUNGUR",
        "TUSA\u015e AKSUNGUR",
        "AKSUNGUR",
        "VIDEO_RAW_AKSUNGUR_DEFAULT",
        "IHA",
        "askeri iha",
    ),
    (
        "PLT_STM_KARGU",
        "STM KARGU",
        "KARGU",
        "VIDEO_RAW_KARGU_DEFAULT",
        "MIKRO_DRONE",
        "mini iha",
    ),
    (
        "PLT_STM_TOGAN",
        "STM TOGAN",
        "TOGAN",
        "VIDEO_RAW_TOGAN_DEFAULT",
        "MIKRO_DRONE",
        "mini iha",
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


@pytest.mark.parametrize(
    ("platform_id", "canonical_name", "alias", "video_id", "vehicle_class", "target_type"),
    PLATFORMS,
)
def test_package3_registry_alias_inventory_and_routes(
    platform_id: str,
    canonical_name: str,
    alias: str,
    video_id: str,
    vehicle_class: str,
    target_type: str,
) -> None:
    registry = load_platform_registry(REGISTRY_PATH)
    index = PlatformRegistryIndex(registry, load_platform_aliases(ALIASES_PATH))
    canonical_match = index.find_exact_match(canonical_name)
    alias_match = index.find_exact_match(alias)
    assert canonical_match is not None and canonical_match.platform_id == platform_id
    assert alias_match is not None and alias_match.platform_id == platform_id

    inventory = load_turkey_inventory_registry(INVENTORY_PATH, registry)
    record = inventory.find_active(platform_id)
    assert record is not None
    assert record.source_type == "DEMO_MOCK"

    resolved_video_id, is_fallback = resolve_raw_vlm_video_id(platform_id)
    assert resolved_video_id == video_id
    assert is_fallback is False
    assert validate_route_mapping() == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("platform_id", "canonical_name", "_alias", "video_id", "vehicle_class", "target_type"),
    PLATFORMS,
)
async def test_package3_raw_vlm_end_to_end_is_verified_low(
    platform_id: str,
    canonical_name: str,
    _alias: str,
    video_id: str,
    vehicle_class: str,
    target_type: str,
    tmp_path: Path,
) -> None:
    harness = await build_harness(ROOT, tmp_path)
    raw_vlm = _raw_vlm(canonical_name, vehicle_class, target_type)
    assessment = assess_raw_vlm(
        raw_vlm,
        platform_registry_path=REGISTRY_PATH,
        platform_aliases_path=ALIASES_PATH,
        inventory_path=INVENTORY_PATH,
    )
    assert assessment.platform_id == platform_id
    assert assessment.inventory_status.value == "CONFIRMED"

    routed_video_id, is_fallback = resolve_raw_vlm_video_id(assessment.platform_id)
    assert routed_video_id == video_id
    assert is_fallback is False
    adapted = adapt_friend_raw_vlm_to_request(
        RawVLMAdapterRequest(
            raw_vlm=raw_vlm,
            video_id=routed_video_id,
            track_id=f"TRK_{platform_id}",
            first_seen_offset_seconds=8.2,
            last_seen_offset_seconds=15.6,
            visual_confidence=0.85,
        )
    )
    outcome = await harness.orchestrator.analyze(
        adapted.analyze_request.model_dump(mode="json")
    )
    assert outcome.http_status == 200
    assert outcome.output is not None
    assert outcome.output["matched_platform"] == canonical_name
    assert outcome.output["inventory_status"] == "CONFIRMED"
    assert outcome.output["permission_status"] == "VALID"
    assert outcome.output["flight_plan_status"] == "FILED"
    assert outcome.output["notam_status"] == "NONE_ACTIVE"
    assert outcome.output["verification_status"] == "VERIFIED"
    assert outcome.output["risk_level"] == "LOW"
    assert outcome.output["decision"] == "AUTHORIZED_OPERATIONAL_MATCH"


def test_package3_ui_catalog_is_registry_and_inventory_backed() -> None:
    catalog = {row["platform_id"]: row for row in _active_platform_catalog()}
    for platform_id, canonical_name, *_unused in PLATFORMS:
        assert catalog[platform_id]["canonical_name"] == canonical_name
        assert catalog[platform_id]["inventory"] == "Envanter \u0130\u00e7i"
    assert catalog["PLT_TUSAS_AKSUNGUR"]["user_type"] == "\u0130HA"
    assert catalog["PLT_STM_KARGU"]["user_type"] == "Mini \u0130HA"
    assert catalog["PLT_STM_TOGAN"]["user_type"] == "Mini \u0130HA"


def test_package3_keeps_existing_demo_scenarios_unchanged() -> None:
    scenarios = json.loads(
        (ROOT / "data/seeds/demo_scenarios.json").read_text(encoding="utf-8")
    )
    assert [item["scenario_id"] for item in scenarios] == [
        f"SCN-{number:02d}" for number in range(1, 24)
    ]
