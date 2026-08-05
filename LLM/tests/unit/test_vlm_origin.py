"""Unit tests for raw VLM ulke_orjini normalization into a policy category."""
# ruff: noqa: D103

import pytest

from operational_decision.contracts.common import VlmOriginCategory
from operational_decision.decision.vlm_origin import classify_vlm_origin


@pytest.mark.parametrize(
    "value",
    ["Türkiye", "Turkey", "TR", "tr", "TÜRKİYE", "turkiye", "Türk", "Türkiye Cumhuriyeti"],
)
def test_turkey_variants_classify_as_turkey(value: str) -> None:
    assert classify_vlm_origin(value) is VlmOriginCategory.TURKEY


@pytest.mark.parametrize(
    "value",
    [None, "", "Bilinmiyor", "bilinmiyor", "Unknown", "UNKNOWN", "Belirsiz", "Tespit edilemedi"],
)
def test_unknown_variants_classify_as_unknown(value: str | None) -> None:
    assert classify_vlm_origin(value) is VlmOriginCategory.UNKNOWN


@pytest.mark.parametrize(
    "value",
    [
        "ABD",
        "US",
        "USA",
        "Amerika Birleşik Devletleri",
        "Rusya",
        "Russia",
        "Çin",
        "China",
        "Fransa",
    ],
)
def test_foreign_country_variants_classify_as_foreign(value: str) -> None:
    assert classify_vlm_origin(value) is VlmOriginCategory.FOREIGN


def test_classification_is_not_platform_name_specific() -> None:
    """The classifier reads only the country hypothesis, never a platform identity."""
    assert classify_vlm_origin("F-16") is VlmOriginCategory.FOREIGN
    assert classify_vlm_origin("Bayraktar TB2") is VlmOriginCategory.FOREIGN
