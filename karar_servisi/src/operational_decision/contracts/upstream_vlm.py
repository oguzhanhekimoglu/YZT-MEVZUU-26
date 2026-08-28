"""Raw Turkish-keyed upstream VLM contract."""

from typing import Literal

from pydantic import Field

from operational_decision.contracts.common import StrictContract


class UpstreamVLMOutput(StrictContract):
    """Validate the only supported raw upstream VLM payload version."""

    schema_version: Literal["upstream-vlm/1.0"] = "upstream-vlm/1.0"
    arac_sinifi: str = Field(min_length=1, max_length=100)
    tehdit_seviyesi: str | None = Field(default=None, max_length=50)
    tahmini_hedef_tipi: str | None = Field(default=None, max_length=100)
    ulke_orjini: str | None = Field(default=None, max_length=100)
    hedef_modeli: str | None = Field(default=None, max_length=150)
    gidis_yeri: str | None = Field(default=None, max_length=250)
    gorsel_analiz: str = Field(min_length=1, max_length=4000)
    guven_skoru: int = Field(ge=0, le=100)
    # BUG-FIX (kullanıcı isteği — video-VLM'i sisteme entegre et, sıfır
    # regresyon riskiyle): ikincil, bağımsız video-kanıtı VLM'inin (src/vlm/
    # video_evidence.py) SADECE gözlemsel notu - kimlik/risk/tehdit alanı
    # DEĞİL, opsiyonel. Yoksa None kalır, hiçbir mevcut davranış etkilenmez.
    video_gozlem: str | None = Field(default=None, max_length=500)
