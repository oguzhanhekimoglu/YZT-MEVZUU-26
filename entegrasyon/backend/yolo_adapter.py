# -*- coding: utf-8 -*-
"""Mevzuu-Yolo (arkadaşın YOLO+SAHI+ByteTrack hattı) sarmalayıcısı.

Arkadaşın kodu HİÇ DEĞİŞTİRİLMEZ; yalnızca import öncesi:
  - SHOW_WINDOW / SAVE_VIDEO kapatılır (backend'de pencere/video kaydı olmamalı),
  - VLMEngine no-op ile değiştirilir (VLM kapalı — sınıflandırmayı VRAG yapar).
"""
import logging
import sys

import ayarlar

# Arkadaşın modüllerinin ayrıntılı log gürültüsünü kıs (VLM stub + track uyarıları).
for _ad in ("pipeline", "vlm_engine", "tracker", "slicer", "enhancer", "camera_motion"):
    logging.getLogger(_ad).setLevel(logging.ERROR)

# --- Mevzuu-Yolo bare-import edilebilsin (import config / slicer / pipeline ...) ---
_YOLO_YOL = str(ayarlar.MEVZUU_YOLO_DIZINI)
if _YOLO_YOL not in sys.path:
    sys.path.insert(0, _YOLO_YOL)

# 1) Config'i pipeline import'undan ÖNCE değiştir ki 'from config import ...'
#    bizim değerleri bağlasın.
import config as _yolo_cfg  # noqa: E402
_yolo_cfg.SHOW_WINDOW = False
_yolo_cfg.SAVE_VIDEO = False
# best.pt 5 SINIFLI: {0:kite,1:bird,2:normaldrone,3:plane,4:combat_uav}. Arkadaşın
# kodu güncellenmemiş — sadece (1,2)'yi işliyordu → uçak(3) ve muharip İHA(4) atlanıyordu.
# Uçak/drone sınıflarını (2,3,4) aç + küçük/uzak İHA için güven eşiğini düşür.
_yolo_cfg.DISPLAY_ALLOWED_CLASSES = (2, 3, 4)
_yolo_cfg.DISPLAY_MIN_CONF = 0.30

# 2) VLM'i devre dışı bırak: vlm_engine.VLMEngine'i no-op ile değiştir.
#    Böylece pipeline VLM'i çağırsa bile ollama'ya gidilmez (120sn timeout yok).
import vlm_engine as _vlm_mod  # noqa: E402


class _SessizVLM:
    """VLMEngine yerine geçen no-op — hiçbir ağ çağrısı yapmaz."""

    def __init__(self, *a, **k):
        pass

    def __getattr__(self, _ad):
        return lambda *a, **k: None


_vlm_mod.VLMEngine = _SessizVLM

# 3) Artık güvenle import edilir.
from pipeline import TeknoFestPipeline, TrackedTarget  # noqa: E402,F401
import pipeline as _pipeline  # noqa: E402
import tracker as _tracker    # noqa: E402

# Tracker'ın "geçersiz satır" reddi 5 sınıfı da kabul etsin (yoksa 3/4 atılır).
_tracker._VALID_CLASS_IDS = {0, 1, 2, 3, 4}

# 5 sınıflı model için Türkçe ad/renk (arkadaşın 3-sınıf haritasının yerine).
CLASS_NAMES = {0: "Uçurtma", 1: "Kuş", 2: "Drone", 3: "Uçak", 4: "Muharip İHA"}
_pipeline.CLASS_NAMES = CLASS_NAMES
_pipeline.CLASS_COLORS = {
    0: (0, 255, 255), 1: (0, 165, 255), 2: (0, 200, 80),
    3: (255, 140, 0), 4: (0, 60, 255),
}


class YoloAdapter:
    """Kare ver → izlenen hedefler (List[TrackedTarget]) al."""

    def __init__(self, source_fps: float = 25.0):
        self.hat = TeknoFestPipeline(source_fps=source_fps)

    def isle(self, frame):
        return self.hat.process_frame(frame)

    def kapat(self):
        try:
            self.hat.release()
        except Exception:
            pass
