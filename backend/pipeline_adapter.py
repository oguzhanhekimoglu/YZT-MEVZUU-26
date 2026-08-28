# -*- coding: utf-8 -*-
"""Adapter to connect existing src.core.pipeline to the FastAPI backend."""
import sys
from pathlib import Path

# Add project root to path so we can import src
project_root = str(Path(__file__).parent.parent.resolve())
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import src.config as cfg
# Görüntüyü backend üzerinden stream edeceğimiz için yerel imshow penceresini kapatalım.
cfg.SHOW_WINDOW = False

from src.core.pipeline import TeknoFestPipeline

class PipelineAdapter:
    def __init__(self, source_fps: float = 25.0):
        print("[ADAPTER] TeknoFestPipeline başlatılıyor...", flush=True)
        self.pipeline = TeknoFestPipeline(source_fps=source_fps)
        print("[ADAPTER] Pipeline hazır.", flush=True)
        # BUG-FIX: eskiden last_vlm_payload/last_llm_payload TEK bir global
        # değerdi (tüm track'ler arasında paylaşılıyordu) — bir hedefin VLM/LLM
        # sonucu, kendi analizi hiç bitmemiş BAŞKA bir (genelde yeni) hedefe
        # sızıyor, arayüz VRAG'dan sonra VLM/LLM hiç gelmeden "nihai karar"
        # gösteriyordu. Artık track_id başına ayrı tutuluyor.
        self._last_vlm_payload_by_track = {}
        self._last_llm_payload_by_track = {}
        self._last_seen_reset_generation = self.pipeline.tracker.reset_generation
        # Sadece "hiç hedef kalmadı" hayalet-hedef durumunda kullanılır (id=-1,
        # frontend tarafından zaten filtreleniyor) — hangi track'in en son
        # veri ürettiğini tutar.
        self._most_recent_track_id = None

    def isle(self, frame):
        import cv2
        # Max 1280px genişlik ile FPS'i artırmak için yeniden boyutlandır
        h, w = frame.shape[:2]
        if w > 1280:
            scale = 1280 / w
            frame = cv2.resize(frame, (1280, int(h * scale)))
        # BUG-FIX: t.bbox_xyxy, process_frame'e verilen (yeniden boyutlandırılmış
        # olabilecek) bu karenin piksel uzayında hesaplanıyor - normalize etmek
        # için bu karenin KENDİ boyutları kullanılmalı, resize öncesi h/w değil.
        frame_h, frame_w = frame.shape[:2]

        """Returns (annotated_bgr, hedef_json_listesi) matching the Fuzyon interface."""
        targets = self.pipeline.process_frame(frame)

        # Sahne geçişi / oturum sıfırlaması: track ID'leri sıfırdan yeniden
        # dağıtılıyor, bu yüzden eski ID'lere ait önbellek artık FARKLI bir
        # fiziksel nesneye ait olabilir — tamamen temizle.
        current_generation = self.pipeline.tracker.reset_generation
        if current_generation != self._last_seen_reset_generation:
            self._last_vlm_payload_by_track.clear()
            self._last_llm_payload_by_track.clear()
            self._last_seen_reset_generation = current_generation
        
        # Pipeline içinde frame_bgr üzerine çizim yapılıyor (eğer process_frame bunu tutuyorsa)
        # Mevcut pipeline yapısına bakarak, eğer frame_bgr attribute'u yoksa orijinal kareyi döndür.
        if hasattr(self.pipeline, "frame_bgr") and self.pipeline.frame_bgr is not None:
            annotated_bgr = self.pipeline.frame_bgr.copy()
        else:
            annotated_bgr = frame.copy()
            
        json_listesi = []
        for t in targets:
            # BUG-FIX (bounding box hiç görünmüyordu): t.bbox_xyxy piksel
            # cinsinden [x1,y1,x2,y2] - frontend'in TacticalOverlay'i ise
            # normalize edilmiş (0-1) {x,y,width,height} bekliyor
            # (bkz. backend-parser.ts parseTrackingBox). Eskiden ham piksel
            # dörtlüsü gönderiliyordu, frontend bunu bir DİZİ olduğu için
            # (obje değil) tanımıyor ve sessizce hiç kutu çizmiyordu.
            x1, y1, x2, y2 = (float(v) for v in t.bbox_xyxy)
            x1 = max(0.0, min(x1, frame_w))
            y1 = max(0.0, min(y1, frame_h))
            x2 = max(0.0, min(x2, frame_w))
            y2 = max(0.0, min(y2, frame_h))
            bbox_normalized = {
                "x": round(x1 / frame_w, 4) if frame_w else 0.0,
                "y": round(y1 / frame_h, 4) if frame_h else 0.0,
                "width": round(max(0.0, x2 - x1) / frame_w, 4) if frame_w else 0.0,
                "height": round(max(0.0, y2 - y1) / frame_h, 4) if frame_h else 0.0,
            }
            d = {
                "id": int(t.track_id),
                "sinif": t.class_name,
                "guven": round(float(t.confidence), 3),
                "bbox": bbox_normalized,
                "hiz_px_s": round(float(t.speed_px_s), 1),
                "zigzag": round(float(t.zigzag_score), 3),
                "hits": int(t.hits),
                "model": None, "model_skor": None, "dusuk_guven": False,
                "ulke": None, "uretici": None, "rol": None, "adaylar": [],
                "vlm": None
            }
            
            # VRAG Verilerini aktar
            if hasattr(t, 'vrag_matches') and getattr(t, 'vrag_matches'):
                best = t.vrag_matches[0]
                d["model"] = best.get("model", "")
                d["model_skor"] = round(best.get("score", 0.0), 3)
                # Yeni ingest'te metadata yoksa varsayılan koyalım
                d["ulke"] = best.get("ulke", "Bilinmiyor")
                d["uretici"] = best.get("uretici", "Bilinmiyor")
                d["rol"] = best.get("rol", "Bilinmiyor")
                
                adaylar = []
                for m in t.vrag_matches:
                    adaylar.append({
                        "model": m.get("model", ""),
                        "skor": round(m.get("score", 0.0), 3),
                        "ulke": m.get("ulke", "Bilinmiyor"),
                        "rol": m.get("rol", "Bilinmiyor")
                    })
                d["adaylar"] = adaylar
                
                # Basit bir düşük güven hesaplaması
                if len(t.vrag_matches) >= 2:
                    diff = t.vrag_matches[0].get("score", 0.0) - t.vrag_matches[1].get("score", 0.0)
                    if diff < 0.05 and t.vrag_matches[0].get("score", 0.0) < 0.65:
                        d["dusuk_guven"] = True
                        
            # VLM Verilerini aktar (Pipeline'da vlm_result varsa veya son bilinen VLM'i kullan)
            if hasattr(t, 'vlm_result') and isinstance(t.vlm_result, dict):
                v = t.vlm_result
                # gorsel_analiz önce kendi alanından, yoksa İngilizce visual_analysis'ten al
                gorsel = v.get("gorsel_analiz", "") or v.get("visual_analysis", "")
                # arac_sinifi → türkçe etiket → gercek_tahmin olarak kullan
                sinif_map = {
                    "sabit_kanat": "Sabit Kanat", "doner_kanat": "Döner Kanat",
                    "kus": "Kuş", "bilinmeyen": "Bilinmeyen"
                }
                tip_map = {
                    "kamikaze": "Kamikaze", "siha": "SİHA", "iha": "İHA",
                    "askeri_ucak": "Askeri Uçak", "yolcu_ucagi": "Yolcu Uçağı",
                    "gozetleme": "Gözetleme İHA", "ticari_drone": "Ticari Drone",
                    "dogal_yasam": "Doğal Yaşam", "tanimsiz": "Tanımsız"
                }
                arac = v.get("arac_sinifi", "bilinmeyen")
                tip = v.get("tahmini_hedef_tipi", "tanimsiz")
                hedef_model = v.get("hedef_modeli", "Bilinmiyor")
                ulke = v.get("ulke_orjini", "Bilinmiyor")
                gercek = f"{tip_map.get(tip, tip)} / {sinif_map.get(arac, arac)}"
                if hedef_model and hedef_model != "Bilinmiyor":
                    gercek = f"{hedef_model} ({gercek})"
                
                vlm_payload = {
                    "dogrulama": "onaylandı" if not v.get("_celiski_var") else "çelişki",
                    "tehdit_seviyesi": v.get("tehdit_seviyesi", "dusuk"),
                    "gorsel_analiz": gorsel,
                    "gercek_tahmin": gercek,
                    "arac_sinifi": sinif_map.get(arac, arac),
                    "ulke_orjini": ulke,
                    "gidis_yonu": v.get("gidis_yonu", ""),
                    "hedef_modeli_tutarlilik": v.get("_hedef_modeli_tutarlilik", ""),
                    # DENEYSEL (VRAG_GUVEN_ESIGI): nihai model/ülke bilgisi VRAG'tan mı
                    # yoksa VLM'in kendi bağımsız yorumundan mı geldi.
                    "guvenilen_kaynak": v.get("_guvenilen_kaynak", "")
                }
                d["vlm"] = vlm_payload
                self._last_vlm_payload_by_track[t.track_id] = vlm_payload  # Bu track icin durumu kaydet
                self._most_recent_track_id = t.track_id
            elif t.track_id in self._last_vlm_payload_by_track:
                d["vlm"] = self._last_vlm_payload_by_track[t.track_id]  # Ayni track'in eski durumunu kullan
                
            # LLM Verilerini aktar
            if hasattr(t, 'llm_result') and isinstance(t.llm_result, dict):
                d["llm"] = t.llm_result
                self._last_llm_payload_by_track[t.track_id] = t.llm_result  # Bu track icin durumu kaydet
                self._most_recent_track_id = t.track_id
            elif t.track_id in self._last_llm_payload_by_track:
                d["llm"] = self._last_llm_payload_by_track[t.track_id]  # Ayni track'in eski durumunu kullan
                
            json_listesi.append(d)
            
        # Eğer hiç hedef yoksa ama son bilinen VLM/LLM verisi varsa, UI'ın sıfırlanmasını
        # önlemek için hayalet bir hedef gönderiyoruz. (Ekranın dışına çizilmesi için bbox [0,0,0,0])
        last_vlm = self._last_vlm_payload_by_track.get(self._most_recent_track_id)
        if not json_listesi and last_vlm:
            dummy = {
                "id": -1, "sinif": "bilinmeyen", "guven": 0.0, "bbox": [0,0,0,0],
                "hiz_px_s": 0.0, "zigzag": 0.0, "hits": 0,
                "model": None, "model_skor": None, "dusuk_guven": False,
                "ulke": None, "uretici": None, "rol": None, "adaylar": [],
                "vlm": last_vlm,
                "llm": self._last_llm_payload_by_track.get(self._most_recent_track_id)
            }
            json_listesi.append(dummy)
            
        return annotated_bgr, json_listesi
        
    def kapat(self):
        if hasattr(self.pipeline, "release"):
            self.pipeline.release()
