"""Ingest — referans görselleri Qdrant'a indeksler.

veriler/<kategori>/<model>/ altındaki her model klasörünü tarar: metadata.json'dan
model/kategori/özellik okur, her görselden augmentation ile varyasyon üretir,
SigLIP2 ile gömer ve payload'larıyla Qdrant'a yazar. Her çalıştırmada sıfırdan kurar.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from PIL import Image

from . import config
from .artirma import varyasyonlar_uret
from .gomleme import gomleyici_al
from .vektor_deposu import VektorDeposu


def _aci_cikar(dosya_adi: str) -> str:
    ad = dosya_adi.lower()
    if "ust" in ad or "üst" in ad or "top" in ad:
        return "üstten"
    if "yan" in ad or "side" in ad:
        return "yandan"
    return "bilinmiyor"


def _metadata_oku(klasor: Path) -> dict:
    meta_yolu = klasor / "metadata.json"
    if meta_yolu.exists():
        with open(meta_yolu, encoding="utf-8") as f:
            meta = json.load(f)
    else:
        meta = {}
        print(f"  [uyarı] metadata.json yok: '{klasor.name}' -> klasör adı model kabul edildi")

    kategori = meta.get("kategori") or "bilinmiyor"
    if kategori != "bilinmiyor" and kategori not in config.BILINEN_KATEGORILER:
        print(f"  [uyarı] tanımsız kategori '{kategori}' ({klasor.name})")
    return {
        "model": meta.get("model") or klasor.name,
        "kategori": kategori,
        "ayirt_edici_ozellikler": meta.get("ayirt_edici_ozellikler", ""),
        "ulke": meta.get("ulke", "") or "bilinmiyor",
        "uretici": meta.get("uretici", ""),
        "rol": meta.get("rol", ""),
        "motor_sayisi": meta.get("motor_sayisi", 0),
        "silahli": bool(meta.get("silahli", False)),
    }


def _gorselleri_bul(klasor: Path) -> list[Path]:
    return sorted(
        p for p in klasor.iterdir()
        if p.is_file() and p.suffix.lower() in config.DESTEKLENEN_UZANTILAR
    )


def _model_klasorlerini_bul(referans: Path) -> list[Path]:
    """Görsel içeren her klasörü bir model klasörü kabul eder (düz veya kategorili)."""
    return sorted(p for p in referans.rglob("*") if p.is_dir() and _gorselleri_bul(p))


def calistir(sifirla: bool = True, dizin: Path | str | None = None) -> dict:
    """Referans dizinini tarar ve Qdrant indeksini (yeniden) kurar. Özet döndürür."""
    referans = Path(dizin) if dizin else config.VERI_DIZINI
    if not referans.exists():
        raise FileNotFoundError(
            f"Referans dizini bulunamadı: {referans}\n"
            "veriler/<kategori>/<model>/ klasörlerini oluşturup fotoğrafları koyun."
        )

    model_klasorleri = _model_klasorlerini_bul(referans)
    if not model_klasorleri:
        raise FileNotFoundError(f"{referans} altında görsel içeren model klasörü yok.")

    print(f"Cihaz: {config.CIHAZ} | Encoder: {config.ENCODER_MODELI}")
    gomleyici = gomleyici_al()
    print(f"Vektör boyutu: {gomleyici.boyut}")

    toplam_gorsel = toplam_vektor = 0

    # Qdrant local (embedded) modda delete_collection eski noktaları diskten
    # temizlemiyor -> gerçek "sıfırdan kurulum" için klasörü fiziksel siliyoruz.
    if sifirla and config.QDRANT_YOLU.exists():
        shutil.rmtree(config.QDRANT_YOLU)

    with VektorDeposu() as depo:
        depo.koleksiyon_kur(boyut=gomleyici.boyut, sifirla=sifirla)

        for klasor in model_klasorleri:
            meta = _metadata_oku(klasor)
            grup = klasor.parent.name if klasor.parent != referans else ""
            gorseller = _gorselleri_bul(klasor)
            if not gorseller:
                continue

            goruntuler, payloadlar = [], []
            for gorsel in gorseller:
                with Image.open(gorsel) as im:
                    im = im.convert("RGB")
                    for varyasyon, etiket in varyasyonlar_uret(im):
                        goruntuler.append(varyasyon)
                        payloadlar.append({
                            "model": meta["model"],
                            "kategori": meta["kategori"],
                            "grup": grup,
                            "ayirt_edici_ozellikler": meta["ayirt_edici_ozellikler"],
                            "ulke": meta["ulke"],
                            "uretici": meta["uretici"],
                            "rol": meta["rol"],
                            "motor_sayisi": meta["motor_sayisi"],
                            "silahli": meta["silahli"],
                            "dosya_yolu": str(gorsel.resolve().relative_to(config.PROJE_KOK)),
                            "aci": _aci_cikar(gorsel.name),
                            "varyasyon": etiket,
                        })

            vektorler = gomleyici.gomle(goruntuler)
            eklenen = depo.ekle(vektorler, payloadlar)
            toplam_gorsel += len(gorseller)
            toplam_vektor += eklenen
            print(f"- {meta['model']} ({meta['kategori']}): {len(gorseller)} görsel -> {eklenen} vektör")

        koleksiyon_toplam = depo.sayim()

    print("\n== İndeksleme tamamlandı ==")
    print(f"Model klasörü       : {len(model_klasorleri)}")
    print(f"Görsel              : {toplam_gorsel}")
    print(f"Vektör (eklenen)    : {toplam_vektor}")
    print(f"Vektör (koleksiyon) : {koleksiyon_toplam}")
    print(f"Konum               : {config.QDRANT_YOLU}")

    return {
        "model_klasoru": len(model_klasorleri),
        "gorsel": toplam_gorsel,
        "vektor": koleksiyon_toplam,
    }
