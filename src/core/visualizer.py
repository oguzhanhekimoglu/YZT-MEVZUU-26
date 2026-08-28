import cv2
import numpy as np
import logging
import src.config as cfg
from src.config import SAVE_VIDEO, OUTPUT_DIR

log = logging.getLogger(__name__)

class PipelineVisualizer:
    """Kaydeder / (isteğe bağlı) yerel pencerede gösterir — kareyi ARTIK
    ANNOTATE ETMEZ.

    BUG-FIX (mimari değişiklik — kullanıcı isteği): bounding box, HUD (FPS/
    Slicer/Tracker/Ham/Onay/VLM) ve teknik debug metinleri (conf/spd/zz/thr)
    burada kareye piksel olarak "yakılıyordu". Artık TEK görsel katman
    frontend'deki TacticalOverlay - backend sadece ham kareyi akışa/dosyaya
    verir, tüm kutu/etiket çizimi tarayıcıda JSON verisinden yapılır.
    Performans telemetrisi (FPS, Slicer/Tracker ms) artık pipeline.py'de
    saklanıp /durum üzerinden okunuyor (bkz. TeknoFestPipeline.performans).
    """

    def __init__(self, source_fps: float):
        self._source_fps = source_fps
        self._video_writer = None
        self._window_created = False

    def draw_and_save(self, frame):
        if cfg.SHOW_WINDOW:
            if not self._window_created:
                h, w = frame.shape[:2]
                cv2.namedWindow("TeknoFest Pipeline v3", cv2.WINDOW_NORMAL)
                cv2.resizeWindow("TeknoFest Pipeline v3", w, h)
                self._window_created = True
            cv2.imshow("TeknoFest Pipeline v3", frame)
            cv2.waitKey(1)

        if SAVE_VIDEO:
            if self._video_writer is None:
                h, w = frame.shape[:2]
                out_path = str(OUTPUT_DIR / "output.avi")
                self._video_writer = cv2.VideoWriter(
                    out_path, cv2.VideoWriter_fourcc(*"XVID"), self._source_fps, (w, h))
                log.info(f"Video: {out_path} @ {self._source_fps:.1f} FPS")
            self._video_writer.write(frame)

        return frame

    def release(self):
        if self._video_writer:
            self._video_writer.release()
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass
