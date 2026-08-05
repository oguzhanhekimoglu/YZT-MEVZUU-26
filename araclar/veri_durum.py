# -*- coding: utf-8 -*-
"""Veri sağlık kontrolü — nereyi genişletmeli gösterir.

Her model klasörü için: foto sayısı, metadata var mı, eksik alan var mı.
En az fotolu modelleri (öncelik) ve metadata eksiklerini raporlar.

Kullanım:  python araclar/veri_durum.py
"""
import json
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent / "veriler"
EXT = (".jpg", ".jpeg", ".png")
GEREKLI = ["model", "kategori", "ayirt_edici_ozellikler", "ulke", "uretici",
           "rol", "alternatif_adlar", "motor_sayisi", "silahli"]


def gorseller(d: Path):
    return [p for p in d.iterdir() if p.is_file() and p.suffix.lower() in EXT]


def bos(v):
    return v is None or v == "" or v == []


modeller = [p for p in sorted(KOK.rglob("*")) if p.is_dir() and gorseller(p)]
satirlar = []
for k in modeller:
    n = len(gorseller(k))
    mp = k / "metadata.json"
    meta = json.loads(mp.read_text(encoding="utf-8")) if mp.exists() else {}
    eksik = [a for a in GEREKLI if a not in meta or bos(meta[a])]
    satirlar.append((n, k.name, mp.exists(), eksik))

toplam = sum(s[0] for s in satirlar)
print(f"Toplam: {len(satirlar)} model · {toplam} foto · ort {toplam/len(satirlar):.1f} foto/model")
print(f"Vektör (x6 augmentation): ~{toplam*6}")

print("\n=== EN AZ FOTOLU 12 MODEL (öncelik: foto ekle) ===")
for n, ad, _, _ in sorted(satirlar)[:12]:
    isaret = "  <-- zayıf" if n < 8 else ""
    print(f"  {n:3d} foto  {ad}{isaret}")

print("\n=== METADATA SORUNLARI ===")
sorunlu = [(ad, var, eksik) for n, ad, var, eksik in satirlar if not var or eksik]
if not sorunlu:
    print("  (hepsi tam)")
for ad, var, eksik in sorunlu:
    if not var:
        print(f"  {ad}: metadata.json YOK")
    else:
        print(f"  {ad}: eksik alan -> {', '.join(eksik)}")
