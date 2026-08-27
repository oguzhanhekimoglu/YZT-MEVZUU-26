"""Unit tests for the versioned platform registry contract."""
# ruff: noqa: D103

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from operational_decision.contracts.platform import (
    BaseCategory,
    IdentityScope,
    PlatformOrigin,
    PlatformRecord,
    UsageDomain,
    VariantPolicy,
)
from operational_decision.platform.platform_registry import load_platform_registry

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "data/platforms/platform_registry.json"


def _registry_payload() -> dict[str, object]:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def _write_registry(tmp_path: Path, payload: dict[str, object]) -> Path:
    path = tmp_path / "platform_registry.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _record_payload() -> dict[str, object]:
    record = load_platform_registry(REGISTRY_PATH).platforms[0]
    return record.model_dump(mode="python")


def test_registry_accepts_only_schema_version_1_1(tmp_path: Path) -> None:
    payload = _registry_payload()
    payload["schema_version"] = "platform-registry/1.0"
    with pytest.raises(ValueError, match="unsupported platform registry schema_version"):
        load_platform_registry(_write_registry(tmp_path, payload))


def test_platform_origin_enum_and_migrated_values() -> None:
    registry = load_platform_registry(REGISTRY_PATH)
    records = {record.platform_id: record for record in registry.platforms}
    assert registry.schema_version == "platform-registry/1.1"
    assert records["PLT_F16"].platform_origin is PlatformOrigin.FOREIGN_ORIGIN
    assert records["PLT_F16"].manufacturer_country_code == "US"

    assert records["PLT_BOEING_747"].platform_origin is PlatformOrigin.FOREIGN_ORIGIN
    assert records["PLT_BOEING_747"].manufacturer_country_code == "US"
    assert records["PLT_INACTIVE_DEMO"].platform_origin is PlatformOrigin.UNKNOWN
    assert records["PLT_INACTIVE_DEMO"].manufacturer_country_code is None
    assert records["PLT_BAYRAKTAR_TB2"].platform_origin is PlatformOrigin.DOMESTIC_ORIGIN
    assert records["PLT_BAYRAKTAR_TB2"].manufacturer_country_code == "TR"
    assert records["PLT_BAYRAKTAR_AKINCI"].platform_origin is PlatformOrigin.DOMESTIC_ORIGIN
    assert records["PLT_BAYRAKTAR_AKINCI"].manufacturer_country_code == "TR"
    assert records["PLT_TUSAS_ANKA"].platform_origin is PlatformOrigin.DOMESTIC_ORIGIN
    assert records["PLT_TUSAS_ANKA"].manufacturer_country_code == "TR"
    assert records["PLT_F35A"].platform_origin is PlatformOrigin.FOREIGN_ORIGIN
    assert records["PLT_F35A"].manufacturer_country_code == "US"
    assert records["PLT_MQ9_REAPER"].platform_origin is PlatformOrigin.FOREIGN_ORIGIN
    assert records["PLT_MQ9_REAPER"].manufacturer_country_code == "US"


@pytest.mark.parametrize("country_code", ["TR", "US", "GB", None])
def test_manufacturer_country_code_accepts_uppercase_alpha_2(
    country_code: str | None,
) -> None:
    payload = _record_payload()
    payload["manufacturer_country_code"] = country_code
    assert PlatformRecord.model_validate(payload).manufacturer_country_code == country_code


@pytest.mark.parametrize("country_code", ["tr", "USA", "", " US", "US "])
def test_manufacturer_country_code_rejects_invalid_values(country_code: str) -> None:
    payload = _record_payload()
    payload["manufacturer_country_code"] = country_code
    with pytest.raises(ValidationError):
        PlatformRecord.model_validate(payload)


def test_invalid_platform_origin_is_rejected() -> None:
    payload = _record_payload()
    payload["platform_origin"] = "INTERNATIONAL"
    with pytest.raises(ValidationError):
        PlatformRecord.model_validate(payload)


def test_platform_record_accepts_missing_taxonomy() -> None:
    payload = _record_payload()
    payload.pop("taxonomy")
    assert PlatformRecord.model_validate(payload).taxonomy is None


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("base_category", "AIRCRAFT"),
        ("usage_domain", "COMMERCIAL"),
        ("identity_scope", "AIRFRAME"),
        ("variant_policy", "INHERIT"),
    ],
)
def test_taxonomy_rejects_invalid_enum_values(field: str, invalid_value: str) -> None:
    payload = _record_payload()
    taxonomy = payload["taxonomy"]
    assert isinstance(taxonomy, dict)
    taxonomy[field] = invalid_value
    with pytest.raises(ValidationError):
        PlatformRecord.model_validate(payload)


@pytest.mark.parametrize("field", ["primary_role", "operational_class"])
@pytest.mark.parametrize("invalid_value", ["lowercase", "HAS SPACE", " LEADING"])
def test_taxonomy_rejects_non_controlled_uppercase_values(field: str, invalid_value: str) -> None:
    payload = _record_payload()
    taxonomy = payload["taxonomy"]
    assert isinstance(taxonomy, dict)
    taxonomy[field] = invalid_value
    with pytest.raises(ValidationError):
        PlatformRecord.model_validate(payload)


@pytest.mark.parametrize("invalid_trait", ["unmanned", "HAS SPACE", "TRAILING "])
def test_taxonomy_rejects_non_controlled_traits(invalid_trait: str) -> None:
    payload = _record_payload()
    taxonomy = payload["taxonomy"]
    assert isinstance(taxonomy, dict)
    taxonomy["traits"] = [invalid_trait]
    with pytest.raises(ValidationError):
        PlatformRecord.model_validate(payload)


def test_taxonomy_rejects_duplicate_traits() -> None:
    payload = _record_payload()
    taxonomy = payload["taxonomy"]
    assert isinstance(taxonomy, dict)
    taxonomy["traits"] = ["MANNED", "MANNED"]
    with pytest.raises(ValidationError, match="must not contain duplicates"):
        PlatformRecord.model_validate(payload)


def test_all_active_platforms_have_expected_taxonomy_migration() -> None:
    registry = load_platform_registry(REGISTRY_PATH)
    records = {record.platform_id: record for record in registry.platforms if record.active}
    expected = {
        "PLT_F16": ("MILITARY", "AIR_COMBAT", "FIGHTER", "MODEL_FAMILY", "METADATA_ONLY"),
        "PLT_BOEING_747": (
            "CIVIL",
            "PASSENGER_TRANSPORT",
            "WIDEBODY_AIRLINER",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_BOEING_737_GENERIC": (
            "CIVIL",
            "PASSENGER_TRANSPORT",
            "NARROWBODY_AIRLINER",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_BAYRAKTAR_TB2": (
            "MILITARY",
            "ISR_STRIKE",
            "TACTICAL_UAS",
            "MODEL",
            "METADATA_ONLY",
        ),
        "PLT_BAYRAKTAR_AKINCI": (
            "MILITARY",
            "ISR_STRIKE",
            "HEAVY_UCAS",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_TUSAS_ANKA": (
            "MILITARY",
            "ISR",
            "MALE_UAS",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_F35_GENERIC": (
            "MILITARY",
            "AIR_COMBAT",
            "FIGHTER",
            "MODEL_FAMILY",
            "EXPLICIT_CHILD_RECORDS",
        ),
        "PLT_F35A": ("MILITARY", "AIR_COMBAT", "FIGHTER", "VARIANT", "EXACT_IDENTITY"),
        "PLT_F35B": ("MILITARY", "AIR_COMBAT", "FIGHTER", "VARIANT", "EXACT_IDENTITY"),
        "PLT_F35C": ("MILITARY", "AIR_COMBAT", "FIGHTER", "VARIANT", "EXACT_IDENTITY"),
        "PLT_MQ9_REAPER": (
            "MILITARY",
            "ISR_STRIKE",
            "MALE_UCAS",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_T129_ATAK": (
            "MILITARY",
            "ATTACK",
            "ATTACK_HELICOPTER",
            "MODEL",
            "METADATA_ONLY",
        ),
        "PLT_T625_GOKBEY": (
            "MILITARY",
            "UTILITY_TRANSPORT",
            "UTILITY_HELICOPTER",
            "MODEL",
            "METADATA_ONLY",
        ),
        "PLT_A400M": (
            "MILITARY",
            "MILITARY_TRANSPORT",
            "TACTICAL_AIRLIFTER",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_HURKUS": (
            "MILITARY",
            "TRAINING_LIGHT_ATTACK",
            "ADVANCED_TRAINER",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_C130": (
            "MILITARY",
            "MILITARY_TRANSPORT",
            "TACTICAL_AIRLIFTER",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_CN235": (
            "MILITARY",
            "MILITARY_TRANSPORT",
            "LIGHT_TACTICAL_AIRLIFTER",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_BOEING_E7": (
            "MILITARY",
            "AIRBORNE_EARLY_WARNING",
            "AEW_C_AIRCRAFT",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_TUSAS_AKSUNGUR": (
            "MILITARY",
            "ISR_STRIKE",
            "MALE_UAS",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_STM_KARGU": (
            "MILITARY",
            "LOITERING_MUNITION",
            "ROTARY_WING_MINI_UAS",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_STM_TOGAN": (
            "MILITARY",
            "ISR",
            "ROTARY_WING_MINI_UAS",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_STM_ALPAGU": (
            "MILITARY",
            "LOITERING_MUNITION",
            "FIXED_WING_MINI_UCAS",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_F4E_2020": (
            "MILITARY",
            "AIR_COMBAT",
            "FIGHTER",
            "VARIANT",
            "EXACT_IDENTITY",
        ),
        "PLT_BAYRAKTAR_TB3": (
            "MILITARY",
            "ISR_STRIKE",
            "TACTICAL_UAS",
            "MODEL",
            "METADATA_ONLY",
        ),
        "PLT_TUSAS_SIMSEK": (
            "MILITARY",
            "TARGET_DRONE",
            "HIGH_SPEED_UAS",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_TUSAS_SUPER_SIMSEK": (
            "MILITARY",
            "TARGET_DRONE",
            "HIGH_SPEED_UAS",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_VESTEL_KARAYEL": (
            "MILITARY",
            "ISR",
            "TACTICAL_UAS",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_EUROFIGHTER_TYPHOON": (
            "MILITARY",
            "AIR_COMBAT",
            "FIGHTER",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_SU35": (
            "MILITARY",
            "AIR_COMBAT",
            "FIGHTER",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_RAFALE": (
            "MILITARY",
            "AIR_COMBAT",
            "FIGHTER",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_AIRBUS_A320": (
            "CIVIL",
            "PASSENGER_TRANSPORT",
            "NARROWBODY_AIRLINER",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_F22_RAPTOR": (
            "MILITARY",
            "AIR_COMBAT",
            "FIGHTER",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_SU57": (
            "MILITARY",
            "AIR_COMBAT",
            "FIGHTER",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_MIG29": (
            "MILITARY",
            "AIR_COMBAT",
            "FIGHTER",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_AIRBUS_A330": (
            "CIVIL",
            "PASSENGER_TRANSPORT",
            "WIDEBODY_AIRLINER",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_BOEING_777": (
            "CIVIL",
            "PASSENGER_TRANSPORT",
            "WIDEBODY_AIRLINER",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_F15_EAGLE": ("MILITARY", "AIR_COMBAT", "FIGHTER", "MODEL_FAMILY", "METADATA_ONLY"),
        "PLT_F15EX_EAGLE_II": ("MILITARY", "AIR_COMBAT", "FIGHTER", "VARIANT", "EXACT_IDENTITY"),
        "PLT_BOEING_737_NG": (
            "CIVIL",
            "PASSENGER_TRANSPORT",
            "NARROWBODY_AIRLINER",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_BOEING_737_MAX": (
            "CIVIL",
            "PASSENGER_TRANSPORT",
            "NARROWBODY_AIRLINER",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_AH64E_APACHE_GUARDIAN": (
            "MILITARY",
            "ATTACK",
            "ATTACK_HELICOPTER",
            "VARIANT",
            "EXACT_IDENTITY",
        ),
        "PLT_F5_FREEDOM_FIGHTER": (
            "MILITARY",
            "AIR_COMBAT",
            "FIGHTER",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_NF5_TURK_YILDIZLARI": (
            "MILITARY",
            "AEROBATIC_DISPLAY",
            "AEROBATIC_TRAINER",
            "VARIANT",
            "EXACT_IDENTITY",
        ),
        "PLT_T38_TALON": (
            "MILITARY",
            "TRAINING",
            "ADVANCED_JET_TRAINER",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_SIKORSKY_S70": (
            "MILITARY",
            "UTILITY_TRANSPORT",
            "UTILITY_HELICOPTER",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_CH47F_CHINOOK": (
            "MILITARY",
            "MILITARY_TRANSPORT",
            "HEAVY_LIFT_HELICOPTER",
            "VARIANT",
            "EXACT_IDENTITY",
        ),
        "PLT_AS532_COUGAR": (
            "MILITARY",
            "UTILITY_TRANSPORT",
            "UTILITY_HELICOPTER",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_UH1_HUEY": (
            "MILITARY",
            "UTILITY_TRANSPORT",
            "UTILITY_HELICOPTER",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_AH1_SUPER_COBRA": (
            "MILITARY",
            "ATTACK",
            "ATTACK_HELICOPTER",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_A10_THUNDERBOLT_II": (
            "MILITARY",
            "AIR_COMBAT",
            "FIGHTER",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_FA18EF_SUPER_HORNET": (
            "MILITARY",
            "AIR_COMBAT",
            "FIGHTER",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_J10": ("MILITARY", "AIR_COMBAT", "FIGHTER", "MODEL_FAMILY", "METADATA_ONLY"),
        "PLT_J20": ("MILITARY", "AIR_COMBAT", "FIGHTER", "MODEL_FAMILY", "METADATA_ONLY"),
        "PLT_JAS39_GRIPEN": ("MILITARY", "AIR_COMBAT", "FIGHTER", "MODEL_FAMILY", "METADATA_ONLY"),
        "PLT_JF17_THUNDER": ("MILITARY", "AIR_COMBAT", "FIGHTER", "MODEL_FAMILY", "METADATA_ONLY"),
        "PLT_MIG35": ("MILITARY", "AIR_COMBAT", "FIGHTER", "MODEL_FAMILY", "METADATA_ONLY"),
        "PLT_MIRAGE_2000": ("MILITARY", "AIR_COMBAT", "FIGHTER", "MODEL_FAMILY", "METADATA_ONLY"),
        "PLT_SU27": ("MILITARY", "AIR_COMBAT", "FIGHTER", "MODEL_FAMILY", "METADATA_ONLY"),
        "PLT_SU30": ("MILITARY", "AIR_COMBAT", "FIGHTER", "MODEL_FAMILY", "METADATA_ONLY"),
        "PLT_TEJAS": ("MILITARY", "AIR_COMBAT", "FIGHTER", "MODEL_FAMILY", "METADATA_ONLY"),
        "PLT_A330_243_MRTT": (
            "MILITARY",
            "AIR_REFUELING",
            "AERIAL_REFUELING_TANKER",
            "VARIANT",
            "EXACT_IDENTITY",
        ),
        "PLT_AN124_RUSLAN": (
            "MILITARY",
            "MILITARY_TRANSPORT",
            "STRATEGIC_AIRLIFTER",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_C17_GLOBEMASTER_III": (
            "MILITARY",
            "MILITARY_TRANSPORT",
            "STRATEGIC_AIRLIFTER",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_C295W": (
            "MILITARY",
            "MILITARY_TRANSPORT",
            "TACTICAL_AIRLIFTER",
            "VARIANT",
            "EXACT_IDENTITY",
        ),
        "PLT_P8A_POSEIDON": (
            "MILITARY",
            "MARITIME_PATROL",
            "MARITIME_PATROL_AIRCRAFT",
            "VARIANT",
            "EXACT_IDENTITY",
        ),
        "PLT_V22_OSPREY": (
            "MILITARY",
            "UTILITY_TRANSPORT",
            "TILTROTOR_TRANSPORT",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_AIRBUS_A321": (
            "CIVIL",
            "PASSENGER_TRANSPORT",
            "NARROWBODY_AIRLINER",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_AIRBUS_A350": (
            "CIVIL",
            "PASSENGER_TRANSPORT",
            "WIDEBODY_AIRLINER",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_AIRBUS_A380": (
            "CIVIL",
            "PASSENGER_TRANSPORT",
            "WIDEBODY_AIRLINER",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_ATR72": (
            "CIVIL",
            "PASSENGER_TRANSPORT",
            "REGIONAL_AIRLINER",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_BOEING_787": (
            "CIVIL",
            "PASSENGER_TRANSPORT",
            "WIDEBODY_AIRLINER",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_CESSNA_172": (
            "CIVIL",
            "GENERAL_AVIATION",
            "LIGHT_GENERAL_AVIATION_AIRCRAFT",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_PIPER_PA28": (
            "CIVIL",
            "GENERAL_AVIATION",
            "LIGHT_GENERAL_AVIATION_AIRCRAFT",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_DJI_AIR_SERIES": (
            "CIVIL",
            "OBSERVATION",
            "COMMERCIAL_MULTIROTOR_UAS",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_DJI_MATRICE_300": (
            "CIVIL",
            "OBSERVATION",
            "COMMERCIAL_MULTIROTOR_UAS",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_DJI_MATRICE_350": (
            "CIVIL",
            "OBSERVATION",
            "COMMERCIAL_MULTIROTOR_UAS",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_DJI_MAVIC_2": (
            "CIVIL",
            "OBSERVATION",
            "COMMERCIAL_MULTIROTOR_UAS",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_DJI_MAVIC_3": (
            "CIVIL",
            "OBSERVATION",
            "COMMERCIAL_MULTIROTOR_UAS",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_DJI_MINI_SERIES": (
            "CIVIL",
            "GENERAL_PURPOSE",
            "COMMERCIAL_MULTIROTOR_UAS",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_DJI_PHANTOM_SERIES": (
            "CIVIL",
            "OBSERVATION",
            "COMMERCIAL_MULTIROTOR_UAS",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_HAROP": (
            "MILITARY",
            "LOITERING_MUNITION",
            "LOITERING_MUNITION",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_SHAHED136_GERAN2": (
            "MILITARY",
            "ONE_WAY_ATTACK",
            "LOITERING_MUNITION",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_CH4": ("MILITARY", "ISR_STRIKE", "MALE_UCAS", "MODEL_FAMILY", "METADATA_ONLY"),
        "PLT_FORPOST_R": ("MILITARY", "ISR_STRIKE", "MALE_UCAS", "MODEL_FAMILY", "METADATA_ONLY"),
        "PLT_HERMES_450": ("MILITARY", "ISR", "MALE_UAS", "MODEL_FAMILY", "METADATA_ONLY"),
        "PLT_HERMES_900": ("MILITARY", "ISR", "MALE_UAS", "MODEL_FAMILY", "METADATA_ONLY"),
        "PLT_HERON_TP": ("MILITARY", "ISR", "MALE_UAS", "MODEL_FAMILY", "METADATA_ONLY"),
        "PLT_MQ1_PREDATOR": (
            "MILITARY",
            "ISR_STRIKE",
            "MALE_UCAS",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_MQ9B_SKYGUARDIAN": ("MILITARY", "ISR", "MALE_UAS", "MODEL_FAMILY", "METADATA_ONLY"),
        "PLT_ORION_UAV": ("MILITARY", "ISR_STRIKE", "MALE_UCAS", "MODEL_FAMILY", "METADATA_ONLY"),
        "PLT_RQ170_SENTINEL": (
            "MILITARY",
            "RECONNAISSANCE",
            "STEALTH_RECONNAISSANCE_UAS",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_RQ4_GLOBAL_HAWK": (
            "MILITARY",
            "STRATEGIC_RECONNAISSANCE",
            "HALE_UAS",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_WING_LOONG_I": (
            "MILITARY",
            "ISR_STRIKE",
            "MALE_UCAS",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_WING_LOONG_II": (
            "MILITARY",
            "ISR_STRIKE",
            "MALE_UCAS",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_WZ7_SOARING_DRAGON": (
            "MILITARY",
            "STRATEGIC_RECONNAISSANCE",
            "HALE_UAS",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_B2_SPIRIT": (
            "MILITARY",
            "STRATEGIC_STRIKE",
            "STRATEGIC_BOMBER",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_B52_STRATOFORTRESS": (
            "MILITARY",
            "STRATEGIC_STRIKE",
            "STRATEGIC_BOMBER",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        "PLT_KA52_ALLIGATOR": (
            "MILITARY",
            "ATTACK",
            "ATTACK_HELICOPTER",
            "MODEL_FAMILY",
            "METADATA_ONLY",
        ),
        # NOT: Aşağıdaki 14 kayıt, VRAG'ın tanıyabildiği platformları Registry ile
        # tam kapsama getirme kararıyla eklendi (Berra, ekip onayıyla).
        "PLT_ANTONOV_AN225": (
            "DUAL_USE", "STRATEGIC_AIRLIFT", "SUPER_HEAVY_TRANSPORT_AIRCRAFT",
            "MODEL", "METADATA_ONLY",
        ),
        "PLT_F4E_PHANTOM_II": (
            "MILITARY", "AIR_COMBAT", "FIGHTER_BOMBER", "VARIANT", "EXACT_IDENTITY",
        ),
        "PLT_F5E_TIGER_II": (
            "MILITARY", "AIR_COMBAT", "LIGHT_FIGHTER", "VARIANT", "EXACT_IDENTITY",
        ),
        "PLT_GULFSTREAM_BUSINESS_JET": (
            "CIVIL", "EXECUTIVE_TRANSPORT", "BUSINESS_JET", "GENERIC_CLASS", "GENERIC_ONLY",
        ),
        "PLT_KAAN": (
            "MILITARY", "AIR_COMBAT", "FIFTH_GENERATION_FIGHTER", "MODEL", "METADATA_ONLY",
        ),
        "PLT_BAYRAKTAR_KIZILELMA": (
            "MILITARY", "AIR_COMBAT", "COMBAT_UAS", "MODEL", "METADATA_ONLY",
        ),
        "PLT_TUSAS_HURJET": (
            "MILITARY", "TRAINING", "ADVANCED_JET_TRAINER", "MODEL", "METADATA_ONLY",
        ),
        "PLT_TUSAS_ANKA3": (
            "MILITARY", "ISR_STRIKE", "STEALTH_UAS", "MODEL", "METADATA_ONLY",
        ),
        "PLT_BAYRAKTAR_DIHA": (
            "MILITARY", "ISR_STRIKE", "VTOL_TACTICAL_UAS", "MODEL", "METADATA_ONLY",
        ),
        "PLT_NEURON_UCAV": (
            "MILITARY", "STRIKE_DEMONSTRATOR", "COMBAT_UAS_DEMONSTRATOR", "MODEL",
            "METADATA_ONLY",
        ),
        "PLT_TARANIS_UCAV": (
            "MILITARY", "STRIKE_DEMONSTRATOR", "COMBAT_UAS_DEMONSTRATOR", "MODEL",
            "METADATA_ONLY",
        ),
        "PLT_WZ8": (
            "MILITARY", "RECONNAISSANCE", "SUPERSONIC_RECON_UAS", "MODEL", "METADATA_ONLY",
        ),
        "PLT_X47B": (
            "MILITARY", "STRIKE_DEMONSTRATOR", "COMBAT_UAS_DEMONSTRATOR", "MODEL",
            "METADATA_ONLY",
        ),
        "PLT_B21_RAIDER": (
            "MILITARY", "STRATEGIC_STRIKE", "STRATEGIC_BOMBER", "MODEL", "METADATA_ONLY",
        ),
    }
    assert set(records) == set(expected)
    for platform_id, expected_values in expected.items():
        taxonomy = records[platform_id].taxonomy
        assert taxonomy is not None
        if platform_id in {
            "PLT_T129_ATAK",
            "PLT_T625_GOKBEY",
            "PLT_AH64E_APACHE_GUARDIAN",
            "PLT_SIKORSKY_S70",
            "PLT_CH47F_CHINOOK",
            "PLT_AS532_COUGAR",
            "PLT_UH1_HUEY",
            "PLT_AH1_SUPER_COBRA",
            "PLT_KA52_ALLIGATOR",
        }:
            expected_base_category = BaseCategory.ROTARY_WING_AIRCRAFT
        elif platform_id in {
            "PLT_STM_KARGU",
            "PLT_STM_TOGAN",
            "PLT_DJI_AIR_SERIES",
            "PLT_DJI_MATRICE_300",
            "PLT_DJI_MATRICE_350",
            "PLT_DJI_MAVIC_2",
            "PLT_DJI_MAVIC_3",
            "PLT_DJI_MINI_SERIES",
            "PLT_DJI_PHANTOM_SERIES",
        }:
            expected_base_category = BaseCategory.MULTIROTOR_AIRCRAFT
        elif platform_id in {"PLT_V22_OSPREY", "PLT_BAYRAKTAR_DIHA"}:
            expected_base_category = BaseCategory.TILTROTOR_AIRCRAFT
        else:
            expected_base_category = BaseCategory.FIXED_WING_AIRCRAFT
        assert taxonomy.base_category is expected_base_category
        assert (
            taxonomy.usage_domain.value,
            taxonomy.primary_role,
            taxonomy.operational_class,
            taxonomy.identity_scope.value,
            taxonomy.variant_policy.value,
        ) == expected_values

    assert records["PLT_F16"].taxonomy is not None
    assert records["PLT_F16"].taxonomy.usage_domain is UsageDomain.MILITARY
    assert records["PLT_F16"].taxonomy.identity_scope is IdentityScope.MODEL_FAMILY
    assert records["PLT_F16"].taxonomy.variant_policy is VariantPolicy.METADATA_ONLY


def test_duplicate_platform_id_is_rejected(tmp_path: Path) -> None:
    payload = _registry_payload()
    platforms = payload["platforms"]
    assert isinstance(platforms, list)
    duplicate = dict(platforms[1])
    duplicate["platform_id"] = platforms[0]["platform_id"]
    platforms.append(duplicate)
    with pytest.raises(ValueError, match="duplicate platform_id"):
        load_platform_registry(_write_registry(tmp_path, payload))


def test_normalized_duplicate_canonical_name_is_rejected(tmp_path: Path) -> None:
    payload = _registry_payload()
    platforms = payload["platforms"]
    assert isinstance(platforms, list)
    duplicate = dict(platforms[1])
    duplicate["platform_id"] = "PLT_DUPLICATE_NAME"
    duplicate["canonical_name"] = "  F-16   FIGHTING FALCON  "
    duplicate["aliases"] = ["UNIQUE-DUPLICATE-ALIAS"]
    platforms.append(duplicate)
    with pytest.raises(ValueError, match="duplicate canonical_name"):
        load_platform_registry(_write_registry(tmp_path, payload))
