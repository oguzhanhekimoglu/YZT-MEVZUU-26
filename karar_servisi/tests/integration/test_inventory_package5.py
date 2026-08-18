"""Acceptance tests for platform expansion package 5."""
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
        "PLT_BAYRAKTAR_TB3",
        "Bayraktar TB3",
        "TB3",
        "VIDEO_RAW_TB3_DEFAULT",
        "SIHA",
        "gemi konuslu siha",
        False,
    ),
    (
        "PLT_TUSAS_SIMSEK",
        "TUSA\u015e \u015e\u0130M\u015eEK",
        "SIMSEK",
        "VIDEO_RAW_SIMSEK_DEFAULT",
        "IHA",
        "yuksek hizli hedef iha",
        False,
    ),
    (
        "PLT_TUSAS_SUPER_SIMSEK",
        "TUSA\u015e S\u00dcPER \u015e\u0130M\u015eEK",
        "SUPER SIMSEK",
        "VIDEO_RAW_SUPER_SIMSEK_DEFAULT",
        "IHA",
        "yuksek hizli hedef iha",
        False,
    ),
    (
        "PLT_VESTEL_KARAYEL",
        "Vestel KARAYEL",
        "KARAYEL",
        "VIDEO_RAW_KARAYEL_DEFAULT",
        "IHA",
        "taktik iha",
        False,
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
    (
        "platform_id",
        "canonical_name",
        "alias",
        "video_id",
        "vehicle_class",
        "target_type",
        "inventory_confirmed",
    ),
    PLATFORMS,
)
def test_package5_registry_alias_inventory_and_routes(
    platform_id: str,
    canonical_name: str,
    alias: str,
    video_id: str,
    vehicle_class: str,
    target_type: str,
    inventory_confirmed: bool,
) -> None:
    registry = load_platform_registry(REGISTRY_PATH)
    index = PlatformRegistryIndex(registry, load_platform_aliases(ALIASES_PATH))
    canonical_match = index.find_exact_match(canonical_name)
    alias_match = index.find_exact_match(alias)
    assert canonical_match is not None and canonical_match.platform_id == platform_id
    assert alias_match is not None and alias_match.platform_id == platform_id

    inventory = load_turkey_inventory_registry(INVENTORY_PATH, registry)
    record = inventory.find_active(platform_id)
    assert (record is not None) is inventory_confirmed
    if record is not None:
        assert record.source_type == "DEMO_MOCK"

    resolved_video_id, is_fallback = resolve_raw_vlm_video_id(platform_id)
    assert resolved_video_id == video_id
    assert is_fallback is False
    assert validate_route_mapping() == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    (
        "platform_id",
        "canonical_name",
        "_alias",
        "video_id",
        "vehicle_class",
        "target_type",
        "inventory_confirmed",
    ),
    PLATFORMS,
)
async def test_package5_raw_vlm_end_to_end_policy(
    platform_id: str,
    canonical_name: str,
    _alias: str,
    video_id: str,
    vehicle_class: str,
    target_type: str,
    inventory_confirmed: bool,
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
    expected_inventory = "CONFIRMED" if inventory_confirmed else "NOT_LISTED"
    assert assessment.inventory_status.value == expected_inventory

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
    outcome = await harness.orchestrator.analyze(adapted.analyze_request.model_dump(mode="json"))
    assert outcome.http_status == 200
    assert outcome.output is not None
    output = outcome.output
    assert output["matched_platform"] == canonical_name
    assert output["inventory_status"] == expected_inventory
    permission_execution = output["tool_execution_summary"]["permission_flight_plan_tool"]
    notam_execution = output["tool_execution_summary"]["notam_tool"]
    if inventory_confirmed:
        assert output["permission_status"] == "VALID"
        assert output["flight_plan_status"] == "FILED"
        assert output["verification_status"] == "VERIFIED"
        assert output["risk_level"] == "LOW"
        assert output["decision"] == "AUTHORIZED_OPERATIONAL_MATCH"
        assert permission_execution["execution_status"] == "SUCCESS"
        assert notam_execution["execution_status"] == "SUCCESS"
    else:
        assert output["verification_status"] == "UNVERIFIED"
        assert output["risk_level"] == "HIGH"
        assert output["decision"] == "UNREGISTERED_MILITARY_AIRCRAFT"
        assert permission_execution["execution_status"] == "SKIPPED"
        assert notam_execution["execution_status"] == "SKIPPED"


def test_package5_ui_catalog_inventory_scope() -> None:
    catalog = {row["platform_id"]: row for row in _active_platform_catalog()}
    for platform_id, canonical_name, *_rest, inventory_confirmed in PLATFORMS:
        assert catalog[platform_id]["canonical_name"] == canonical_name
        expected = (
            "Envanter \u0130\u00e7i" if inventory_confirmed else "Envanter D\u0131\u015f\u0131"
        )
        assert catalog[platform_id]["inventory"] == expected


def test_package5_keeps_existing_demo_scenarios_unchanged() -> None:
    scenarios = json.loads((ROOT / "data/seeds/demo_scenarios.json").read_text(encoding="utf-8"))
    assert [item["scenario_id"] for item in scenarios] == [
        f"SCN-{number:02d}" for number in range(1, 24)
    ]
