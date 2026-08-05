"""Safe pre-validation and classification helpers for raw upstream VLM payloads."""

import json
import re
import unicodedata

from operational_decision.contracts.common import VisualClass
from operational_decision.contracts.platform import BaseCategory
from operational_decision.contracts.upstream_vlm import UpstreamVLMOutput
from operational_decision.platform.platform_registry import PlatformRegistryIndex

_TRANSLATION = str.maketrans({"ı": "i", "ş": "s", "ğ": "g", "ç": "c", "ö": "o", "ü": "u"})

# BUG-FIX (platform kapsamı): safe_vehicle_mapping_key eskiden yalnızca F-16/F-35/
# F-35A'yı (bkz. _fighter_model altındaki dar regex) "savaş uçağı modeli" olarak
# tanıyordu. Registry'de kayıtlı diğer 90+ platform (Kaan, Su-27, MiG-29, Eurofighter
# vb. — VRAG'ın artık isabetle üretebildiği isimler) hep BILINMEYEN_HAVA_ARACI'ya
# düşüyordu. Bu tablo, Registry'nin zaten yapılandırılmış category alanını (VisualClass)
# safe_vehicle_mapping_key'in ürettiği ham anahtar string'lerine çevirir — aynı
# çeviri config/visual_adapter.yaml'da ters yönde tanımlı; burada tekrar okumak
# yerine küçük/durağan bir tabloyla tutuluyor (döngüsel import'tan kaçınmak için).
_REGISTRY_CATEGORY_TO_RAW_KEY: dict[VisualClass, str] = {
    VisualClass.FIGHTER_JET: "SAVAS_UCAGI",
    VisualClass.CIVILIAN_AIRCRAFT: "SIVIL_UCAK",
    VisualClass.HELICOPTER: "HELIKOPTER",
    VisualClass.TRANSPORT_AIRCRAFT: "NAKLIYE_UCAGI",
    VisualClass.UAV: "IHA",
    VisualClass.UCAV: "SIHA",
    VisualClass.MICRO_DRONE: "MIKRO_DRONE",
    VisualClass.UNKNOWN_AIRCRAFT: "BILINMEYEN_HAVA_ARACI",
    VisualClass.NON_AIRCRAFT: "HAVA_ARACI_DEGIL",
}

# Registry eşleşmesini VLM'in kendi arac_sinifi beyanıyla çapraz doğrulamak için:
# VLM "sabit kanat" derken Registry o ismi bir helikoptere bağlarsa (ör. isim
# çakışması/halüsinasyon), bu tutarsızlık sinyali — eşleşmeyi kullanma, eski
# (daha temkinli) yola düş.
_EXPECTED_BASE_CATEGORY: dict[str, set[BaseCategory]] = {
    "sabit kanat": {
        BaseCategory.FIXED_WING_AIRCRAFT,
        BaseCategory.LOITERING_MUNITION,
    },
    "doner kanat": {
        BaseCategory.ROTARY_WING_AIRCRAFT,
        BaseCategory.MULTIROTOR_AIRCRAFT,
        BaseCategory.TILTROTOR_AIRCRAFT,
    },
}


def normalized_raw_text(value: object) -> str:
    """Normalize separators, casing, and Turkish characters for exact rule checks."""
    if not isinstance(value, str):
        return ""
    decomposed = unicodedata.normalize("NFKD", value).casefold().translate(_TRANSLATION)
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.sub(r"[_\-]+", " ", without_marks).split())


def _fighter_model(value: object) -> str | None:
    normalized = normalized_raw_text(value)
    if re.search(r"\bf\s*16\b", normalized):
        return "F-16-like"
    if re.search(r"\bf\s*35\s*a\b", normalized):
        return "F-35A-like"
    if re.search(r"\bf\s*35\b", normalized):
        return "F-35-like"
    return None


def normalize_raw_model_hypothesis(value: str | None) -> str | None:
    """Normalize known fighter aliases and preserve other exact model hypotheses."""
    fighter = _fighter_model(value)
    if fighter is not None:
        return fighter
    if value is None:
        return None
    cleaned = " ".join(value.split())
    if not cleaned:
        return None
    return cleaned


def _registry_mapping_key(
    payload: dict[str, object], raw_class: str, platform_index: PlatformRegistryIndex
) -> str | None:
    """Resolve hedef_modeli against the full Platform Registry (exact alias match).

    Only trusted when the matched platform's own base_category is consistent
    with the VLM's arac_sinifi (sabit/döner kanat) — an exact registry alias
    match is a much stronger signal than the narrow _fighter_model regex, so
    the same fighter+military+not-civilian cross-check isn't required, but the
    base-category consistency check is kept as a cheap extra safety net.
    """
    expected = _EXPECTED_BASE_CATEGORY.get(raw_class)
    if expected is None:
        return None
    hedef_modeli = payload.get("hedef_modeli")
    hypothesis = normalize_raw_model_hypothesis(
        hedef_modeli if isinstance(hedef_modeli, str) else None
    )
    if not hypothesis:
        return None
    platform = platform_index.find_exact_match(hypothesis)
    if platform is None or platform.taxonomy is None:
        return None
    if platform.taxonomy.base_category not in expected:
        return None
    return _REGISTRY_CATEGORY_TO_RAW_KEY.get(platform.category)


def safe_vehicle_mapping_key(
    payload: dict[str, object], platform_index: PlatformRegistryIndex | None = None
) -> str | None:
    """Return a configured mapping key without promoting broad fixed-wing evidence.

    BUG-FIX (platform kapsamı): `platform_index` verilirse önce hedef_modeli'ni
    tam Platform Registry'de (97 platform / 489 alias) arar — eskiden yalnızca
    F-16/F-35/F-35A'yı tanıyan dar bir regex vardı (_fighter_model), VRAG'ın artık
    isabetle ürettiği diğer isimler (Kaan, Su-27 Flanker, MiG-29 vb.) hep
    BILINMEYEN_HAVA_ARACI'ya düşüyordu. `platform_index` verilmezse (ör. eski
    çağıranlar, mevcut testler) bu adım sessizce atlanır ve aşağıdaki özgün dar
    regex mantığına değişmeden düşülür — geriye dönük uyumluluk korunur.
    """
    raw_class = normalized_raw_text(payload.get("arac_sinifi"))

    if platform_index is not None:
        registry_key = _registry_mapping_key(payload, raw_class, platform_index)
        if registry_key is not None:
            return registry_key

    subtype = normalized_raw_text(payload.get("tahmini_hedef_tipi"))
    model = normalized_raw_text(payload.get("hedef_modeli"))
    analysis = normalized_raw_text(payload.get("gorsel_analiz"))
    evidence = " ".join((subtype, model, analysis))

    if raw_class == "sabit kanat":
        fighter_model = _fighter_model(payload.get("hedef_modeli")) is not None
        military_subtype = "askeri ucak" in subtype
        civilian_evidence = "yolcu ucagi" in subtype or "boeing" in model or "airbus" in model
        if fighter_model and military_subtype and not civilian_evidence:
            return "SAVAS_UCAGI"
        if civilian_evidence and not (fighter_model and military_subtype):
            return "SIVIL_UCAK"
        return "BILINMEYEN_HAVA_ARACI"
    if raw_class == "doner kanat":
        return "HELIKOPTER" if "helikopter" in evidence else "BILINMEYEN_HAVA_ARACI"
    return None


def adapt_raw_vlm_payload(
    raw_payload: dict[str, object], platform_index: PlatformRegistryIndex | None = None
) -> UpstreamVLMOutput:
    """Adapt the legacy scored payload while preserving its strict public contract."""
    cleaned = {key: value for key, value in raw_payload.items() if not key.startswith("_")}
    safe_class = safe_vehicle_mapping_key(cleaned, platform_index)
    if safe_class is not None:
        cleaned["arac_sinifi"] = safe_class
    return UpstreamVLMOutput.model_validate_json(
        json.dumps(cleaned, ensure_ascii=False),
        strict=True,
    )
