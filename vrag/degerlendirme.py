"""Leave-one-out doğruluk ölçümü.

Her referans görselini sorgu yapar ama kendi kayıtlarını hariç tutar
("veritabanında yokmuş gibi"). Retrieval top-1 / top-3 doğruluğunu ölçer.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import config
from .arama import ara


def _gorseller(klasor: Path) -> list[Path]:
    return sorted(
        p for p in klasor.iterdir()
        if p.is_file() and p.suffix.lower() in config.DESTEKLENEN_UZANTILAR
    )


def _model_klasorleri(kok: Path) -> list[Path]:
    return [p for p in sorted(kok.rglob("*")) if p.is_dir() and _gorseller(p)]


def _model_ad(klasor: Path) -> str:
    mp = klasor / "metadata.json"
    if mp.exists():
        return json.loads(mp.read_text(encoding="utf-8")).get("model") or klasor.name
    return klasor.name


def _haric(g: Path) -> set[str]:
    formlar = {str(g)}
    try:
        formlar.add(str(g.resolve().relative_to(config.PROJE_KOK)))
    except ValueError:
        pass
    return formlar


def retrieval_dogruluk(depo=None, tek_per_model: bool = False) -> dict:
    """Retrieval top-1 / top-3 doğruluğu (leave-one-out)."""
    top1 = top3 = n = 0
    for klasor in _model_klasorleri(config.VERI_DIZINI):
        gercek = _model_ad(klasor)
        gorseller = _gorseller(klasor)[:1] if tek_per_model else _gorseller(klasor)
        for g in gorseller:
            adaylar = ara(g, topk=3, depo=depo, haric_yollar=_haric(g))
            n += 1
            if adaylar and adaylar[0].model == gercek:
                top1 += 1
            if any(a.model == gercek for a in adaylar[:3]):
                top3 += 1
    return {
        "n": n, "top1": top1, "top3": top3,
        "top1_yuzde": round(100 * top1 / n, 1) if n else 0.0,
        "top3_yuzde": round(100 * top3 / n, 1) if n else 0.0,
    }
