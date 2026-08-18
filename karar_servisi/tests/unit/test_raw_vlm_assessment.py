"""Tests for safe context-free raw VLM assessment."""
# ruff: noqa: D103

import pytest

from operational_decision.app.config import AppSettings
from operational_decision.contracts.raw_vlm import RawVLMOutput
from operational_decision.input.raw_vlm_assessment import assess_raw_vlm


def _assess(*, model: str, origin: str, threat: str = "yuksek"):  # type: ignore[no-untyped-def]
    settings = AppSettings()
    raw = RawVLMOutput.model_validate(
        {
            "arac_sinifi": "sabit_kanat",
            "tehdit_seviyesi": threat,
            "tahmini_hedef_tipi": "askeri_ucak",
            "ulke_orjini": origin,
            "hedef_modeli": model,
            "gorsel_analiz": "Kontrollü test açıklaması.",
        }
    )
    return assess_raw_vlm(
        raw,
        platform_registry_path=settings.platform_registry_path,
        platform_aliases_path=settings.platform_aliases_path,
        inventory_path=settings.turkey_inventory_registry_path,
    )


def test_non_turkey_hypothesis_is_not_promoted_to_registry_fact() -> None:
    result = _assess(model="F-35A Lightning II", origin="Kanada")

    assert result.platform_id == "PLT_F35A"
    assert result.registry_country_code == "US"
    assert result.registry_platform_origin == "FOREIGN_ORIGIN"
    assert result.origin_comparison == "OPERATOR_AFFILIATION_UNVERIFIED"
    assert result.inventory_status == "NOT_LISTED"
    assert result.risk_level == "UNKNOWN"


def test_mexico_marking_claim_remains_unverified_operator_affiliation() -> None:
    result = _assess(model="General Dynamics F-16 Fighting Falcon", origin="Meksika")

    assert result.platform_id == "PLT_F16"
    assert result.registry_country_code == "US"
    assert result.inventory_status == "CONFIRMED"
    assert result.origin_comparison == "OPERATOR_AFFILIATION_UNVERIFIED"
    assert "kesin aidiyet" in result.origin_explanation_tr
    assert result.decision == "INDETERMINATE"


def test_f16_turkey_hypothesis_is_consistent_with_turkey_inventory() -> None:
    result = _assess(model="F-16 Fighting Falcon", origin="Türkiye")

    assert result.platform_id == "PLT_F16"
    assert result.registry_country_code == "US"
    assert result.inventory_status == "CONFIRMED"
    assert result.origin_comparison == "TURKEY_INVENTORY_COMPATIBLE"
    assert "Turkey Inventory kaydıyla uyumludur" in result.origin_explanation_tr
    assert result.risk_level == "UNKNOWN"


def test_turkey_hypothesis_without_inventory_support_is_treated_as_suspicious() -> None:
    """A military platform claiming Turkish origin but absent from inventory is suspicious."""
    result = _assess(model="F-35A Lightning II", origin="Türkiye")

    assert result.platform_id == "PLT_F35A"
    assert result.inventory_status == "NOT_LISTED"
    assert result.origin_comparison == "MISMATCH"
    assert result.vlm_origin_category == "TURKEY"
    assert result.risk_level == "HIGH"
    assert result.human_review_required is True
    assert "şüpheli kabul edilmeli" in result.origin_explanation_tr
    assert "şüpheli kabul edilmeli" in result.summary_tr


def test_registry_origin_match_does_not_create_operational_authorization() -> None:
    result = _assess(model="F-35A Lightning II", origin="Amerika Birleşik Devletleri")

    assert result.origin_comparison == "MANUFACTURER_COUNTRY_COMPATIBLE"
    assert result.permission_status == "NOT_EVALUATED"
    assert result.flight_plan_status == "NOT_EVALUATED"
    assert result.notam_status == "NOT_EVALUATED"
    assert result.verification_status == "INDETERMINATE"
    assert result.risk_level == "UNKNOWN"
    assert result.rag_called is False


def test_domestic_inventory_confirmation_is_not_automatic_trust_or_low_risk() -> None:
    result = _assess(model="Bayraktar TB2", origin="Türkiye")

    assert result.registry_platform_origin == "DOMESTIC_ORIGIN"
    assert result.origin_comparison == "TURKEY_INVENTORY_COMPATIBLE"
    assert result.inventory_status == "CONFIRMED"
    assert result.risk_level == "UNKNOWN"
    assert result.decision == "INDETERMINATE"
    assert result.human_review_required is True


def test_threat_hypothesis_does_not_change_context_free_facts() -> None:
    high = _assess(model="F-35A Lightning II", origin="Kanada", threat="yuksek")
    low = _assess(model="F-35A Lightning II", origin="Kanada", threat="dusuk")

    ignored = {"raw_vlm", "summary_tr"}
    assert high.model_dump(exclude=ignored) == low.model_dump(exclude=ignored)


def test_generic_f35_input_resolves_to_family_without_promoting_f35a() -> None:
    """A bare F-35 mention resolves to the family record, never silently to the A variant."""
    result = _assess(model="F-35 Lightning II", origin="ABD")

    assert result.normalized_model_hypothesis == "F-35-like"
    assert result.platform_resolved is True
    assert result.platform_id == "PLT_F35_GENERIC"
    assert result.matched_platform == "F-35 Lightning II"
    assert result.inventory_status == "NOT_LISTED"


# Regression coverage for context-free risk elevation by VLM origin category.
# This must apply uniformly to every MILITARY, Inventory-listed (CONFIRMED)
# platform, so it is parametrized across real inventory platforms of
# different visual classes rather than F-16 alone.
@pytest.mark.parametrize(
    "model",
    ["F-16 Fighting Falcon", "Bayraktar TB2", "Bayraktar AKINCI", "T129 ATAK"],
)
def test_military_listed_foreign_origin_is_high_without_operational_context(model: str) -> None:
    result = _assess(model=model, origin="Rusya")

    assert result.inventory_status == "CONFIRMED"
    assert result.vlm_origin_category == "FOREIGN"
    assert result.risk_level == "HIGH"
    assert result.human_review_required is True
    assert "yabancı askerî aidiyet şüphesi" in result.summary_tr


@pytest.mark.parametrize(
    "model",
    ["F-16 Fighting Falcon", "Bayraktar TB2", "Bayraktar AKINCI", "T129 ATAK"],
)
def test_military_listed_unknown_origin_is_medium_without_operational_context(model: str) -> None:
    result = _assess(model=model, origin="Bilinmiyor")

    assert result.inventory_status == "CONFIRMED"
    assert result.vlm_origin_category == "UNKNOWN"
    assert result.risk_level == "MEDIUM"
    assert result.human_review_required is True
    assert "aidiyeti bu aşamada belirlenememiştir" in result.summary_tr


def test_turkey_unknown_and_foreign_origin_no_longer_share_identical_output() -> None:
    """The exact regression this endpoint previously had: risk was always UNKNOWN."""
    turkey = _assess(model="F-16 Fighting Falcon", origin="Türkiye")
    unknown = _assess(model="F-16 Fighting Falcon", origin="Bilinmiyor")
    foreign = _assess(model="F-16 Fighting Falcon", origin="Rusya")

    assert {turkey.risk_level, unknown.risk_level, foreign.risk_level} == {
        "UNKNOWN",
        "MEDIUM",
        "HIGH",
    }
