"""Acceptance tests for foreign platform expansion package 6."""
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
        "PLT_F15_EAGLE",
        "F-15 Eagle",
        "F15",
        "VIDEO_RAW_F15_EAGLE_DEFAULT",
        "SAVAS_UCAGI",
        "askeri savas ucagi",
        False,
    ),
    (
        "PLT_F15EX_EAGLE_II",
        "F-15EX Eagle II",
        "F15EX",
        "VIDEO_RAW_F15EX_DEFAULT",
        "SAVAS_UCAGI",
        "askeri savas ucagi",
        False,
    ),
    (
        "PLT_EUROFIGHTER_TYPHOON",
        "Eurofighter Typhoon",
        "Typhoon",
        "VIDEO_RAW_EUROFIGHTER_DEFAULT",
        "SAVAS_UCAGI",
        "askeri savas ucagi",
        False,
    ),
    (
        "PLT_SU35",
        "Sukhoi Su-35",
        "SU-35",
        "VIDEO_RAW_SU35_DEFAULT",
        "SAVAS_UCAGI",
        "askeri savas ucagi",
        False,
    ),
    (
        "PLT_RAFALE",
        "Dassault Rafale",
        "Rafale",
        "VIDEO_RAW_RAFALE_DEFAULT",
        "SAVAS_UCAGI",
        "askeri savas ucagi",
        False,
    ),
    (
        "PLT_AIRBUS_A320",
        "Airbus A320",
        "A320",
        "VIDEO_RAW_A320_DEFAULT",
        "SIVIL_UCAK",
        "yolcu ucagi",
        True,
    ),
    (
        "PLT_BOEING_737_NG",
        "Boeing 737 NG",
        "737 NG",
        "VIDEO_RAW_B737_NG_DEFAULT",
        "SIVIL_UCAK",
        "yolcu ucagi",
        True,
    ),
    (
        "PLT_BOEING_737_MAX",
        "Boeing 737 MAX",
        "737 MAX",
        "VIDEO_RAW_B737_MAX_DEFAULT",
        "SIVIL_UCAK",
        "yolcu ucagi",
        True,
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


@pytest.mark.parametrize(
    (
        "platform_id",
        "canonical_name",
        "alias",
        "video_id",
        "vehicle_class",
        "target_type",
        "is_civil",
    ),
    PLATFORMS,
)
def test_package6_registry_alias_inventory_and_routes(
    platform_id: str,
    canonical_name: str,
    alias: str,
    video_id: str,
    vehicle_class: str,
    target_type: str,
    is_civil: bool,
) -> None:
    registry = load_platform_registry(REGISTRY_PATH)
    index = PlatformRegistryIndex(registry, load_platform_aliases(ALIASES_PATH))
    canonical_match = index.find_exact_match(canonical_name)
    alias_match = index.find_exact_match(alias)
    assert canonical_match is not None and canonical_match.platform_id == platform_id
    assert alias_match is not None and alias_match.platform_id == platform_id

    inventory = load_turkey_inventory_registry(INVENTORY_PATH, registry)
    assert inventory.find_active(platform_id) is None
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
        "is_civil",
    ),
    PLATFORMS,
)
async def test_package6_raw_vlm_end_to_end_policy(
    platform_id: str,
    canonical_name: str,
    _alias: str,
    video_id: str,
    vehicle_class: str,
    target_type: str,
    is_civil: bool,
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
    assert assessment.inventory_status.value == "NOT_LISTED"

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
    assert output["inventory_status"] == "NOT_LISTED"
    permission_execution = output["tool_execution_summary"]["permission_flight_plan_tool"]
    notam_execution = output["tool_execution_summary"]["notam_tool"]
    if is_civil:
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


def test_generic_boeing_737_alias_resolves_to_generic_family_record() -> None:
    """VRAG'in referans veri seti Boeing 737'yi tek (versiyonsuz) aile olarak
    tutuyor - bu yuzden generic "Boeing 737"/"B737" artik PLT_BOEING_737_GENERIC'e
    cozumleniyor (kullanicinin acikca istedigi degisiklik). Eskiden "PLT_BOEING_737"
    ID'siyle bir kayit varmis ve kaldirilmisti (bkz. test_platform_allowlist.py'deki
    REMOVED_PLATFORM_IDS) - bu yeni kayit BILEREK farkli bir ID (PLT_BOEING_737_GENERIC)
    kullaniyor, kaldirilan ID'yi geri getirmiyor."""
    registry = load_platform_registry(REGISTRY_PATH)
    index = PlatformRegistryIndex(registry, load_platform_aliases(ALIASES_PATH))
    match = index.find_exact_match("Boeing 737")
    assert match is not None
    assert match.platform_id == "PLT_BOEING_737_GENERIC"
    assert index.find_exact_match("B737").platform_id == "PLT_BOEING_737_GENERIC"


def test_package6_ui_catalog_marks_all_new_platforms_outside_inventory() -> None:
    catalog = {row["platform_id"]: row for row in _active_platform_catalog()}
    for platform_id, canonical_name, *_unused in PLATFORMS:
        assert catalog[platform_id]["canonical_name"] == canonical_name
        assert catalog[platform_id]["inventory"] == "Envanter D\u0131\u015f\u0131"


def test_package6_keeps_existing_demo_scenarios_unchanged() -> None:
    scenarios = json.loads((ROOT / "data/seeds/demo_scenarios.json").read_text(encoding="utf-8"))
    assert [item["scenario_id"] for item in scenarios] == [
        f"SCN-{number:02d}" for number in range(1, 24)
    ]
