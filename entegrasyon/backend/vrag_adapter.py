# -*- coding: utf-8 -*-
"""VRAG (SigLIP2 + Qdrant retrieval) sarmalayıcısı.

Kırpılmış hedef görüntüsünü (numpy BGR, YOLO crop) DİSKE YAZMADAN gömer ve
Qdrant'ta arar → model bazında tekilleştirilmiş adaylar. VRAG-final paketi
hiç değiştirilmez; yalnızca gomleyici + depo + AdaySonuc yeniden kullanılır.
"""
import os
import sys
import threading

import numpy as np
from PIL import Image

import ayarlar

# HF önbelleğinden çevrimdışı yükle (Teknofest offline + hızlı açılış).
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

# VRAG-final'i import edilebilir yap (from vrag import ...).
_VRAG_YOL = str(ayarlar.VRAG_DIZINI)
if _VRAG_YOL not in sys.path:
    sys.path.insert(0, _VRAG_YOL)

from vrag import config as vrag_config          # noqa: E402
from vrag.arama import AdaySonuc, margin, dusuk_guven  # noqa: E402
from vrag.gomleme import gomleyici_al            # noqa: E402
from vrag.vektor_deposu import VektorDeposu      # noqa: E402


class VragAdapter:
    """Kırpılmış hedef (BGR numpy) → model bazında top-k aday."""

    def __init__(self):
        self.gomleyici = gomleyici_al()   # SigLIP2'yi GPU'ya yükler (~1.6 GB)
        self.depo = VektorDeposu()        # VRAG-final/qdrant_db'yi açar
        self._kilit = threading.Lock()    # gomleyici + depo tek seferde (async worker)

    def tani(self, bgr_crop: np.ndarray, topk: int = ayarlar.VRAG_TOPK,
             izinli_kategoriler: set | None = None) -> list[AdaySonuc]:
        """BGR crop → tekilleştirilmiş top-k AdaySonuc (skora göre azalan).

        izinli_kategoriler verilirse yalnız o kategorilerdeki referanslar sayılır
        (YOLO sınıfına göre daraltma → alakasız eşleşmeler elenir).
        """
        if bgr_crop is None or bgr_crop.size == 0:
            return []
        rgb = bgr_crop[:, :, ::-1]                       # BGR -> RGB (cv2 gereksiz)
        pil = Image.fromarray(np.ascontiguousarray(rgb))
        with self._kilit:                               # GPU/qdrant erişimini serileştir
            vektor = self.gomleyici.gomle([pil])[0]
            ham = self.depo.ara(
                vektor, limit=vrag_config.HAM_ARAMA_LIMITI,
                filtreler={"kategori": None, "ulke": None, "rol": None},
            )
        en_iyi: dict[str, AdaySonuc] = {}
        for nokta in ham:
            pl = nokta.payload or {}
            if izinli_kategoriler and pl.get("kategori") not in izinli_kategoriler:
                continue                                 # kategori filtresi
            model = pl.get("model", "bilinmiyor")
            skor = float(nokta.score)
            mevcut = en_iyi.get(model)
            if mevcut is None or skor > mevcut.skor:
                en_iyi[model] = AdaySonuc(
                    model=model, skor=skor,
                    kategori=pl.get("kategori", "bilinmiyor"),
                    referans_yolu=pl.get("dosya_yolu", ""),
                    ayirt_edici_ozellikler=pl.get("ayirt_edici_ozellikler", ""),
                    aci=pl.get("aci", "bilinmiyor"),
                    ulke=pl.get("ulke", ""), uretici=pl.get("uretici", ""),
                    rol=pl.get("rol", ""), motor_sayisi=pl.get("motor_sayisi", 0),
                )
        return sorted(en_iyi.values(), key=lambda a: a.skor, reverse=True)[:topk]

    def kapat(self):
        try:
            self.depo.kapat()
        except Exception:
            pass


# arama yardımcılarını dışarı aç (güven kapısı için)
__all__ = ["VragAdapter", "AdaySonuc", "margin", "dusuk_guven"]
