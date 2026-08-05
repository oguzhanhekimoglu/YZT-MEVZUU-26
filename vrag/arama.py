"""Arama — sorgu görselinden en benzer hava aracı modellerini bulur.

Görüntü SigLIP2 ile gömülür, Qdrant'ta aranır ve sonuçlar MODEL BAZINDA
tekilleştirilir (aynı modelin varyasyonları top-k'yı doldurmaz). Nihai tahmin =
top-1 (en yüksek benzerlik). Güven kapısı: ilk iki aday çok yakınsa "düşük güven".
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from . import config
from .gomleme import gomleyici_al
from .vektor_deposu import VektorDeposu


@dataclass
class AdaySonuc:
    """Tek bir aday modelin arama sonucu."""

    model: str
    skor: float
    kategori: str
    referans_yolu: str
    ayirt_edici_ozellikler: str
    aci: str
    ulke: str = ""
    uretici: str = ""
    rol: str = ""
    motor_sayisi: int = 0


def ara(
    sorgu_yolu: str | Path,
    topk: int = config.VARSAYILAN_TOPK,
    kategori: str | None = None,
    depo: VektorDeposu | None = None,
    haric_yollar: set[str] | None = None,
    ulke: str | None = None,
    rol: str | None = None,
) -> list[AdaySonuc]:
    """Sorgu görseli için model bazında tekilleştirilmiş top-k aday döndürür.

    kategori / ulke / rol verilirse aramaya AND filtre uygulanır (yalnızca eşleşen
    referanslar). haric_yollar: bu referans dosyalarından gelen isabetler yok
    sayılır (leave-one-out ölçümü için).
    """
    sorgu_yolu = Path(sorgu_yolu)
    if not sorgu_yolu.exists():
        raise FileNotFoundError(f"Sorgu görseli bulunamadı: {sorgu_yolu}")

    gomleyici = gomleyici_al()
    with Image.open(sorgu_yolu) as im:
        vektor = gomleyici.gomle([im.convert("RGB")])[0]

    filtreler = {"kategori": kategori, "ulke": ulke, "rol": rol}
    kendi_depo = depo is None
    d = depo if depo is not None else VektorDeposu()
    try:
        ham = d.ara(vektor, limit=config.HAM_ARAMA_LIMITI, filtreler=filtreler)
    finally:
        if kendi_depo:
            d.kapat()

    # Model bazında en iyi skoru tut (tekilleştirme).
    en_iyi: dict[str, AdaySonuc] = {}
    for nokta in ham:
        pl = nokta.payload or {}
        if haric_yollar and pl.get("dosya_yolu") in haric_yollar:
            continue  # leave-one-out: sorgunun kendi referansını sayma
        model = pl.get("model", "bilinmiyor")
        skor = float(nokta.score)
        mevcut = en_iyi.get(model)
        if mevcut is None or skor > mevcut.skor:
            en_iyi[model] = AdaySonuc(
                model=model,
                skor=skor,
                kategori=pl.get("kategori", "bilinmiyor"),
                referans_yolu=pl.get("dosya_yolu", ""),
                ayirt_edici_ozellikler=pl.get("ayirt_edici_ozellikler", ""),
                aci=pl.get("aci", "bilinmiyor"),
                ulke=pl.get("ulke", ""),
                uretici=pl.get("uretici", ""),
                rol=pl.get("rol", ""),
                motor_sayisi=pl.get("motor_sayisi", 0),
            )

    return sorted(en_iyi.values(), key=lambda a: a.skor, reverse=True)[:topk]


def margin(adaylar: list[AdaySonuc]) -> float:
    """Top-1 ile top-2 skoru arasındaki fark; tek aday varsa top-1 skoru."""
    if not adaylar:
        return 0.0
    if len(adaylar) < 2:
        return float(adaylar[0].skor)
    return float(adaylar[0].skor - adaylar[1].skor)


def dusuk_guven(adaylar: list[AdaySonuc], esik: float | None = None) -> bool:
    """Margin eşikten küçükse True: ilk iki aday çok yakın -> model kararsız.

    esik verilmezse config.MARGIN_ESIGI (0 => kapı kapalı, hep emin).
    """
    esik = config.MARGIN_ESIGI if esik is None else esik
    if esik <= 0 or len(adaylar) < 2:
        return False
    return (adaylar[0].skor - adaylar[1].skor) < esik
