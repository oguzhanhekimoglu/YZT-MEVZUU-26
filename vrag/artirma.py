"""Augmentation — referans görsellerden varyasyon üretir.

Drone kamerasıyla havadan çekim koşullarını taklit eder: döndürme, ölçekleme,
hafif blur ve (varsayılan açık) hafif perspektif eğim. Tek referans fotoğraftan
birkaç varyasyon indekslenir -> retrieval isabeti artar. Her varyasyon bir etiketle döner.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter

from . import config


def _dondur(goruntu: Image.Image, aci: int) -> Image.Image:
    # expand=True: döndürünce köşeler kırpılmasın (uçağın tamamı görünür kalsın).
    return goruntu.rotate(aci, resample=Image.BICUBIC, expand=True)


def _olcekle(goruntu: Image.Image, faktor: float) -> Image.Image:
    yeni = (max(1, int(goruntu.width * faktor)), max(1, int(goruntu.height * faktor)))
    return goruntu.resize(yeni, resample=Image.BICUBIC)


def _bulaniklastir(goruntu: Image.Image, yaricap: float) -> Image.Image:
    return goruntu.filter(ImageFilter.GaussianBlur(radius=yaricap))


def _perspektif_katsayilari(hedef, kaynak) -> list[float]:
    """PIL PERSPECTIVE için katsayılar: kaynak dörtgenini hedef dörtgenine eşler."""
    A = []
    for (hx, hy), (kx, ky) in zip(hedef, kaynak):
        A.append([kx, ky, 1, 0, 0, 0, -hx * kx, -hx * ky])
        A.append([0, 0, 0, kx, ky, 1, -hy * kx, -hy * ky])
    A = np.array(A, dtype=np.float64)
    B = np.array(hedef, dtype=np.float64).reshape(8)
    return np.linalg.solve(A, B).tolist()


def _perspektif(goruntu: Image.Image, egim: float) -> Image.Image:
    """Üst kenarı içe alan hafif perspektif (oblik/eğik bakış açısı hissi)."""
    g, y = goruntu.width * egim, goruntu.height
    kaynak = [(0, 0), (goruntu.width, 0), (goruntu.width, y), (0, y)]
    hedef = [(g, 0), (goruntu.width - g, 0), (goruntu.width, y), (0, y)]
    kats = _perspektif_katsayilari(kaynak, hedef)
    return goruntu.transform((goruntu.width, y), Image.PERSPECTIVE, kats,
                             resample=Image.BICUBIC)


def varyasyonlar_uret(goruntu: Image.Image) -> list[tuple[Image.Image, str]]:
    """Bir görselden (varyasyon, etiket) çiftleri üretir. Orijinal daima ilktir."""
    goruntu = goruntu.convert("RGB")
    varyasyonlar: list[tuple[Image.Image, str]] = [(goruntu, "orijinal")]

    for aci in config.DONME_ACILARI:
        varyasyonlar.append((_dondur(goruntu, aci), f"donme_{aci:+d}"))
    for faktor in config.OLCEK_FAKTORLERI:
        varyasyonlar.append((_olcekle(goruntu, faktor), f"olcek_{faktor}"))
    varyasyonlar.append((_bulaniklastir(goruntu, config.BULANIKLIK_YARICAPI), "bulanik"))
    if config.PERSPEKTIF_AKTIF:
        varyasyonlar.append((_perspektif(goruntu, config.PERSPEKTIF_EGIM), "perspektif"))

    return varyasyonlar
