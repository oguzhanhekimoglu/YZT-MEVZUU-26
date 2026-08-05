# -*- coding: utf-8 -*-
"""Adapter to connect existing src.core.pipeline to the FastAPI backend."""
import sys
from pathlib import Path

# Add project root to path so we can import src
project_root = str(Path(__file__).parent.parent.parent.resolve())
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

    def isle(self, frame):
        import cv2
        # Max 1280px genişlik ile FPS'i artırmak için yeniden boyutlandır
        h, w = frame.shape[:2]
        if w > 1280:
            scale = 1280 / w
            frame = cv2.resize(frame, (1280, int(h * scale)))

        """Returns (annotated_bgr, hedef_json_listesi) matching the Fuzyon interface."""
        targets = self.pipeline.process_frame(frame)
        
        # Pipeline içinde frame_bgr üzerine çizim yapılıyor (eğer process_frame bunu tutuyorsa)
        # Mevcut pipeline yapısına bakarak, eğer frame_bgr attribute'u yoksa orijinal kareyi döndür.
        if hasattr(self.pipeline, "frame_bgr") and self.pipeline.frame_bgr is not None:
            annotated_bgr = self.pipeline.frame_bgr.copy()
        else:
            annotated_bgr = frame.copy()
            
        json_listesi = []
        for t in targets:
            d = {
                "id": int(t.track_id),
                "sinif": t.class_name,
                "guven": round(float(t.confidence), 3),
                "bbox": [int(v) for v in t.bbox_xyxy],
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
                    "gidis_yonu": v.get("gidis_yonu", "")
                }
                d["vlm"] = vlm_payload
                self.last_vlm_payload = vlm_payload  # Durumu kaydet
            elif hasattr(self, 'last_vlm_payload') and self.last_vlm_payload:
                d["vlm"] = self.last_vlm_payload  # Eski durumu kullan
                
            # LLM Verilerini aktar
            if hasattr(t, 'llm_result') and isinstance(t.llm_result, dict):
                d["llm"] = t.llm_result
                self.last_llm_payload = t.llm_result  # Durumu kaydet
            elif hasattr(self, 'last_llm_payload') and self.last_llm_payload:
                d["llm"] = self.last_llm_payload  # Eski durumu kullan
                
            json_listesi.append(d)
            
        # Eğer hiç hedef yoksa ama son bilinen VLM/LLM verisi varsa, UI'ın sıfırlanmasını 
        # önlemek için hayalet bir hedef gönderiyoruz. (Ekranın dışına çizilmesi için bbox [0,0,0,0])
        if not json_listesi and hasattr(self, 'last_vlm_payload') and self.last_vlm_payload:
            dummy = {
                "id": -1, "sinif": "bilinmeyen", "guven": 0.0, "bbox": [0,0,0,0],
                "hiz_px_s": 0.0, "zigzag": 0.0, "hits": 0,
                "model": None, "model_skor": None, "dusuk_guven": False,
                "ulke": None, "uretici": None, "rol": None, "adaylar": [],
                "vlm": self.last_vlm_payload,
                "llm": getattr(self, 'last_llm_payload', None)
            }
            json_listesi.append(dummy)
            
        return annotated_bgr, json_listesi
        
    def kapat(self):
        if hasattr(self.pipeline, "release"):
            self.pipeline.release()
