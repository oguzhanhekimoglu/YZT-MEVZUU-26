# -*- coding: utf-8 -*-
"""Tespit geçmişi kaydı — her onaylı model tanısını JSONL olarak diske yazar."""
import json
import time
from threading import Lock

import ayarlar


class Kayit:
    """Track başına model tanısı değiştiğinde tek satır JSONL yazar."""

    def __init__(self, dosya=ayarlar.KAYIT_DOSYASI):
        self.dosya = dosya
        self._kilit = Lock()
        self._son_model = {}   # track_id -> son yazılan model (tekrarları engelle)

    def yaz(self, hedef, aday) -> bool:
        """Bu track için model ilk kez veya değiştiyse kaydeder. Yazdıysa True."""
        onceki = self._son_model.get(hedef.track_id)
        if onceki == aday.model:
            return False
        self._son_model[hedef.track_id] = aday.model
        satir = {
            "zaman": time.strftime("%Y-%m-%d %H:%M:%S"),
            "track_id": int(hedef.track_id),
            "sinif": hedef.class_name,
            "model": aday.model,
            "skor": round(float(aday.skor), 4),
            "ulke": aday.ulke,
            "rol": aday.rol,
            "hiz_px_s": round(float(hedef.speed_px_s), 1),
            "zigzag": round(float(hedef.zigzag_score), 3),
        }
        with self._kilit:
            with open(self.dosya, "a", encoding="utf-8") as f:
                f.write(json.dumps(satir, ensure_ascii=False) + "\n")
        return True

    def son_kayitlar(self, adet=100) -> list[dict]:
        """Son N kaydı (yeni→eski) döndürür — arayüzde 'geçmiş' paneli için."""
        try:
            with open(self.dosya, encoding="utf-8") as f:
                satirlar = f.readlines()
        except FileNotFoundError:
            return []
        out = []
        for s in reversed(satirlar[-adet:]):
            try:
                out.append(json.loads(s))
            except ValueError:
                continue
        return out
