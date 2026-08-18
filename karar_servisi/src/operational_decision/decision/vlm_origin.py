"""Normalize the raw VLM-reported ulke_orjini hypothesis into a policy category.

This classifies only the VLM's self-reported country/operator-affiliation
hypothesis for the observed vehicle. It must not be confused with the
Platform Registry's manufacturer_country_code, which describes where a
platform model is built, not who is operating the observed vehicle.
"""

import re
import unicodedata

from operational_decision.contracts.common import VlmOriginCategory

_UNKNOWN_WORDS = {
    "",
    "bilinmiyor",
    "bilinmeyen",
    "unknown",
    "belirsiz",
    "tespit edilemedi",
}
_TURKEY_WORDS = {
    "tr",
    "turkiye",
    "turkey",
    "turkiye cumhuriyeti",
    "turk",
}


def _normalize(value: str | None) -> str:
    if value is None:
        return ""
    decomposed = unicodedata.normalize("NFKD", value).casefold()
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", plain).split())


def classify_vlm_origin(value: str | None) -> VlmOriginCategory:
    """Classify a raw VLM ulke_orjini hypothesis into TURKEY/UNKNOWN/FOREIGN."""
    normalized = _normalize(value)
    if normalized in _UNKNOWN_WORDS:
        return VlmOriginCategory.UNKNOWN
    if normalized in _TURKEY_WORDS:
        return VlmOriginCategory.TURKEY
    return VlmOriginCategory.FOREIGN
