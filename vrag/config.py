"""VRAG ayarları — tek encoder, retrieval-only, optimal yapılandırma.

Tüm sabitler tek yerde. Sistem kazanan yapılandırmaya sabitlenmiştir:
SigLIP2-so400m encoder + Qdrant retrieval + perspektif augmentation + güven kapısı.
"""
from __future__ import annotations

from pathlib import Path

import torch

# --- Yollar -----------------------------------------------------------------
PROJE_KOK = Path(__file__).resolve().parent.parent
VERI_DIZINI = PROJE_KOK / "veriler"      # referans veri (kategorili yapı)
QDRANT_YOLU = PROJE_KOK / "qdrant_db"    # embedded Qdrant indeksi

# --- Encoder (tek) ----------------------------------------------------------
# Benchmark'ta en iyi çıkan encoder (leave-one-out top-1 %88.5; DINOv2/CLIP'i
# ve diğer SigLIP'leri geçti). Kontrastif SigLIP2 ailesi silüet işinde en iyisi.
ENCODER_MODELI = "google/siglip2-so400m-patch14-384"
CIHAZ = "cuda" if torch.cuda.is_available() else "cpu"
TOPLU_BOYUT = 16             # embedding çıkarımında batch (8 GB VRAM'e uygun)

# --- Qdrant -----------------------------------------------------------------
KOLEKSIYON_ADI = "hava_araclari"
# Vektörler L2-normalize edildiğinden kosinüs benzerliği kullanılır.

# --- Arama ------------------------------------------------------------------
VARSAYILAN_TOPK = 5
# Model bazında tekilleştirmeden ÖNCE Qdrant'tan çekilecek ham sonuç sayısı.
HAM_ARAMA_LIMITI = 64
# Güven kapısı: top-1 ile top-2 skorunun farkı (margin) bundan KÜÇÜKSE tahmin
# "düşük güven" sayılır (ilk iki aday neredeyse eşit -> model kararsız). Mutlak
# skor doğrulukla kalibre değil; margin iyi ayırıyor (yanlış medyan 0.007, doğru
# 0.057). m=0.015'te yanlışların ~%86'sı yakalanır. 0 => kapı kapalı.
MARGIN_ESIGI = 0.015

# --- Augmentation (drone kamerası + bakış açısı varyasyonlarını simüle eder) -
# Her referans görselden orijinal + aşağıdaki dönüşümlerle varyasyonlar üretilir.
DONME_ACILARI = (-12, 12)          # derece cinsinden döndürme
OLCEK_FAKTORLERI = (0.8,)          # küçültme / uzaklaşma
BULANIKLIK_YARICAPI = 1.2          # Gaussian blur (drone kamerası netsizliği)
# Perspektif (eğim): yandan referansa hafif eğik-bakış varyasyonu. Yalnızca
# indeks tarafı -> sorgu hızını etkilemez; ölçümde +0.8 top-1 kazandırdı.
PERSPEKTIF_AKTIF = True
PERSPEKTIF_EGIM = 0.18             # üst kenarın içe kayma oranı (0..0.5)

# --- Kategoriler & dosya türleri --------------------------------------------
BILINEN_KATEGORILER = (
    "Savaş Uçağı",
    "Bombardıman Uçağı",
    "Nakliye/Özel Görev Uçağı",
    "Helikopter",
    "İHA",
    "SİHA",
    "Yolcu Uçağı",
    "Drone",
)
DESTEKLENEN_UZANTILAR = (".jpg", ".jpeg", ".png")
