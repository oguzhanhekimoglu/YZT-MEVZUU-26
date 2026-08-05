# -*- coding: utf-8 -*-
"""Füzyon: YOLO tespit+takip → İHA hedefine periyodik VRAG model tanıma.

Her kare:
  1) YoloAdapter → izlenen hedefler (bbox, id, sınıf, kinematik).
  2) İHA (class_id=2) + yeterli 'hits' olan track için, VRAG_PERIYOT_SN'de bir kez
     kırpıp VRAG'a sorar; sonucu track_id'ye cache'ler (periyodik yenile).
  3) Temiz kare üstüne kutu + etiket çizer (PIL/TTF → Türkçe doğru) → MJPEG.
  4) Hedef listesini JSON olarak döndürür (WebSocket → C# panelleri).
"""
import queue
import threading
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import ayarlar
from kayit import Kayit
from vrag_adapter import VragAdapter, dusuk_guven
from yolo_adapter import YoloAdapter

# Sınıfa göre renk (RGB) — İHA tehdit rengi, kuş/uçurtma nötr.
RENK = {0: (245, 200, 60), 1: (250, 150, 50), 2: (240, 70, 70)}
RENK_VARSAYILAN = (200, 200, 200)


def _font(boyut: int):
    for ad in ("segoeui.ttf", "arial.ttf", "calibri.ttf"):
        try:
            return ImageFont.truetype(str(Path("C:/Windows/Fonts") / ad), boyut)
        except OSError:
            continue
    return ImageFont.load_default()


class Fuzyon:
    def __init__(self, source_fps: float = 25.0):
        self.yolo = YoloAdapter(source_fps=source_fps)
        self.vrag = VragAdapter()
        self.kayit = Kayit()
        self._cache: dict[int, dict] = {}   # track_id -> {adaylar, dusuk, t}
        self._font = _font(18)
        # VRAG'ı arka planda koştur → kare döngüsü bloklanmaz (akıcı video).
        self._kilit = threading.Lock()
        self._son_istek: dict[int, float] = {}   # track_id -> son sıraya alma zamanı
        self._bekleyen: set[int] = set()          # işlenmeyi bekleyen track'ler
        self._q: queue.Queue = queue.Queue()
        self._calisiyor = True
        self._worker = threading.Thread(target=self._vrag_worker, daemon=True)
        self._worker.start()
        # VLM doğrulayıcı (VRAG sonrası, AYRI yavaş worker — track başına bir kez).
        self._vlm_cache: dict[int, dict] = {}
        self._vlm_bekleyen: set[int] = set()
        self._vlm_q: queue.Queue = queue.Queue()
        if ayarlar.VLM_AKTIF:
            threading.Thread(target=self._vlm_worker, daemon=True).start()

    def _vlm_worker(self):
        """Yavaş: VRAG'ın çözdüğü track'i gemma ile denetler (track başına bir kez)."""
        import vlm_dogrula
        while self._calisiyor:
            try:
                tid, crop, adaylar = self._vlm_q.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                sonuc = vlm_dogrula.dogrula(crop, adaylar)
                if sonuc:
                    with self._kilit:
                        self._vlm_cache[tid] = sonuc
            except Exception:
                pass
            finally:
                self._vlm_bekleyen.discard(tid)

    def _vrag_worker(self):
        """Arka plan: sıradaki crop'u VRAG'a sorar, sonucu cache'ler."""
        while self._calisiyor:
            try:
                tid, crop, kategoriler = self._q.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                adaylar = self.vrag.tani(crop, topk=ayarlar.VRAG_TOPK,
                                         izinli_kategoriler=kategoriler)
                if adaylar:
                    with self._kilit:
                        self._cache[tid] = {"adaylar": adaylar,
                                            "dusuk": dusuk_guven(adaylar), "t": time.time()}
                    # VLM denetimi: bu track için bir kez sıraya al.
                    if (ayarlar.VLM_AKTIF and tid not in self._vlm_bekleyen
                            and tid not in self._vlm_cache):
                        self._vlm_bekleyen.add(tid)
                        self._vlm_q.put((tid, crop, adaylar))
            except Exception:
                pass
            finally:
                self._bekleyen.discard(tid)

    def _enqueue_gerek(self, t, simdi) -> bool:
        if t.class_id not in ayarlar.VRAG_UCAK_SINIFLARI:
            return False   # kuş/uçurtma → model tanıma yok
        if t.hits < ayarlar.VRAG_MIN_HITS:
            return False
        if t.track_id in self._bekleyen:
            return False
        return (simdi - self._son_istek.get(t.track_id, 0.0)) >= ayarlar.VRAG_PERIYOT_SN

    def _kategori_seti(self, t):
        if not ayarlar.KATEGORI_FILTRESI_AKTIF:
            return None
        return ayarlar.SINIF_KATEGORILERI.get(t.class_id)

    def _crop_al(self, t, temiz):
        # SADECE bounding box içi — tam kareye/bağlama bakma (best_crops %25 padding
        # ekliyordu). Tight kırpı → uçak kadrajı doldurur, VRAG daha çok detay görür.
        x1, y1, x2, y2 = (int(v) for v in t.bbox_xyxy)
        h, w = temiz.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        if x2 <= x1 or y2 <= y1:
            return None
        return temiz[y1:y2, x1:x2].copy()

    def _json(self, t, durum, vlm=None) -> dict:
        d = {
            "id": int(t.track_id),
            "sinif": t.class_name,
            "guven": round(float(t.confidence), 3),
            "bbox": [int(v) for v in t.bbox_xyxy],
            "hiz_px_s": round(float(t.speed_px_s), 1),
            "zigzag": round(float(t.zigzag_score), 3),
            "hits": int(t.hits),
            "model": None, "model_skor": None, "dusuk_guven": None,
            "ulke": None, "uretici": None, "rol": None, "adaylar": [],
            "vlm": vlm,   # VLM denetim sonucu (dogrulama/tehdit/analiz) veya None
        }
        if durum:
            a0 = durum["adaylar"][0]
            d.update({
                "model": a0.model, "model_skor": round(a0.skor, 3),
                "dusuk_guven": durum["dusuk"], "ulke": a0.ulke,
                "uretici": a0.uretici, "rol": a0.rol,
                "adaylar": [{"model": a.model, "skor": round(a.skor, 3),
                             "ulke": a.ulke, "rol": a.rol} for a in durum["adaylar"]],
            })
        return d

    def _etiket(self, t, durum) -> str:
        if durum and durum["adaylar"]:
            if durum["dusuk"]:
                return f"{t.class_name}#{t.track_id} · belirsiz"
            a0 = durum["adaylar"][0]
            return f"{t.class_name}#{t.track_id} · {a0.model} {a0.skor:.2f}"
        return f"{t.class_name}#{t.track_id}"

    def _ciz(self, temiz_bgr, hedefler, durumlar) -> np.ndarray:
        rgb = temiz_bgr[:, :, ::-1]
        im = Image.fromarray(np.ascontiguousarray(rgb))
        dr = ImageDraw.Draw(im)
        for t, durum in zip(hedefler, durumlar):
            x1, y1, x2, y2 = (int(v) for v in t.bbox_xyxy)
            renk = RENK.get(t.class_id, RENK_VARSAYILAN)
            dr.rectangle([x1, y1, x2, y2], outline=renk, width=2)
            metin = self._etiket(t, durum)
            tw = dr.textlength(metin, font=self._font)
            yb = max(0, y1 - 22)
            dr.rectangle([x1, yb, x1 + tw + 10, yb + 22], fill=renk)
            dr.text((x1 + 5, yb + 2), metin, fill=(20, 20, 20), font=self._font)
        return np.ascontiguousarray(np.asarray(im)[:, :, ::-1])   # RGB->BGR

    def isle(self, frame):
        """Tek kare → (annotated_bgr, hedef_json_listesi). VRAG bloklamaz (arka planda)."""
        temiz = frame.copy()                 # pipeline frame'i değiştirebilir; temizi sakla
        hedefler = self.yolo.isle(frame)
        simdi = time.time()
        # Gereken track'ler için VRAG'ı SIRAYA al (kare döngüsünü bloklamadan).
        for t in hedefler:
            if self._enqueue_gerek(t, simdi):
                crop = self._crop_al(t, temiz)
                if crop is not None:
                    self._bekleyen.add(t.track_id)
                    self._son_istek[t.track_id] = simdi
                    self._q.put((t.track_id, crop.copy(), self._kategori_seti(t)))
        # Cache'ten mevcut sonuçları oku (worker güncelledikçe dolar).
        with self._kilit:
            durumlar = [self._cache.get(t.track_id) for t in hedefler]
            vlmler = [self._vlm_cache.get(int(t.track_id)) for t in hedefler]
        for t, durum in zip(hedefler, durumlar):
            if durum and durum["adaylar"]:
                self.kayit.yaz(t, durum["adaylar"][0])   # tekrarları kendi eler
        annotated = self._ciz(temiz, hedefler, durumlar)
        cikti = [self._json(t, d, v) for t, d, v in zip(hedefler, durumlar, vlmler)]
        self._temizle(hedefler)
        return annotated, cikti

    def _temizle(self, hedefler):
        """Artık görünmeyen track'lerin cache'ini at (bellek sızıntısını önle)."""
        canli = {int(t.track_id) for t in hedefler}
        with self._kilit:
            for tid in list(self._cache):
                if tid not in canli:
                    self._cache.pop(tid, None)
            for tid in list(self._vlm_cache):
                if tid not in canli:
                    self._vlm_cache.pop(tid, None)
        for tid in list(self._son_istek):
            if tid not in canli:
                self._son_istek.pop(tid, None)

    def kapat(self):
        self._calisiyor = False
        self.yolo.kapat()
        self.vrag.kapat()
