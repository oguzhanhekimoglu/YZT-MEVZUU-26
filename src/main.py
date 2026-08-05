# ============================================================
# run.py - Başlatıcı
# ============================================================
# KULLANIM:
#   Kamera (0 = İlk kamera):
#       python run.py
#   Video dosyası:
#       python run.py --source video.mp4
#   Belirli kamera:
#       python run.py --source 1
# ============================================================

import sys
import cv2
import argparse
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.core.pipeline import TeknoFestPipeline, CLASS_NAMES

# ─── Merkezi Logging Yapılandırması (BUG-9) ───────────────────────────────────
# pipeline.py'de tekrar basicConfig çağrılmasını önlemek için logging burada,
# tek seferde, FileHandler dahil yapılandırılıyor.
_LOG_FILE = Path(__file__).parent / "pipeline.log"
_root_logger = logging.getLogger()
if not _root_logger.handlers:          # Çift yapılandırmayı engelle
    _root_logger.setLevel(logging.INFO)
    _fmt = logging.Formatter("[%(asctime)s] %(levelname)s - %(message)s")
    _sh = logging.StreamHandler()
    _sh.setFormatter(_fmt)
    _fh = logging.FileHandler(str(_LOG_FILE), encoding="utf-8")
    _fh.setFormatter(_fmt)
    _root_logger.addHandler(_sh)
    _root_logger.addHandler(_fh)
    
    # Gürültü yapan 3. parti kütüphane loglarını sustur
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("huggingface_hub").setLevel(logging.WARNING)
    logging.getLogger("transformers").setLevel(logging.WARNING)

log = logging.getLogger(__name__)


def parse_args():
    p = argparse.ArgumentParser(description="TeknoFest Pipeline v2")
    p.add_argument("--source", type=str, default="0",
                   help="Kamera indeksi (0,1...) veya video/resim yolu")
    return p.parse_args()



def main():
    args = parse_args()
    src  = int(args.source) if args.source.isdigit() else args.source

    log.info(f"Kamera/Video kaynağı açılıyor: {src} ... (Eğer burada takılı kalıyorsa kameranız kullanımda olabilir veya Windows ile uyum sorunu yaşanıyor olabilir)")
    if isinstance(src, int):
        # Windows'ta kamerasız veya sorunlu Media Foundation durumlarında 
        # VideoCapture(0)'ın sonsuza kadar donmasını önlemek için DirectShow (CAP_DSHOW) kullanıyoruz.
        cap = cv2.VideoCapture(src, cv2.CAP_DSHOW)
    else:
        cap = cv2.VideoCapture(src)
        
    if not cap.isOpened():
        log.error(f"Kaynak açılamadı: {src}")
        sys.exit(1)

    log.info(f"Kaynak açıldı: {src}")

    # BUG-7 Düzeltmesi: Gerçek FPS'i source'tan al, pipeline'a ilet
    source_fps = cap.get(cv2.CAP_PROP_FPS)
    if source_fps <= 0 or source_fps > 240:
        source_fps = 25.0   # Kamera veya bilinmeyen kaynak için güvenli varsayılan
    log.info(f"Kaynak FPS: {source_fps:.1f}")
    pipeline = TeknoFestPipeline(source_fps=source_fps)
    frame_no = 0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                log.info("Video bitti veya kamera bağlantısı kesildi.")
                break

            # ================================================
            # TEK SATIR: Tüm pipeline buradan çalışıyor.
            # ================================================
            targets = pipeline.process_frame(frame)

            # Her 30 frame'de terminal özeti
            if frame_no % 30 == 0:
                log.info(
                    f"Frame {frame_no:05d} | "
                    f"Onaylanan: {len(targets)}"
                )
                for t in targets:
                    log.info(
                        f"  ID#{t.track_id:3d} | {t.class_name:12s} | "
                        f"conf:{t.confidence:.2f} | "
                        f"spd:{t.speed_px_s:.1f}px/s | "
                        f"zz:{t.zigzag_score:.2f} | "
                        f"hits:{t.hits:3d} | "
                        f"VLM:{'HAZIR' if t.vlm_ready else 'YOK'}"
                    )
            frame_no += 1

            # Python 3.11 ile GUI tekrar aktif olduğu için bekleme ekliyoruz
            if cv2.waitKey(1) & 0xFF == ord('q'):
                log.info("Kullanıcı çıkışı.")
                break

    except KeyboardInterrupt:
        log.info("Ctrl+C ile durduruldu.")
    finally:
        cap.release()
        pipeline.release()


if __name__ == "__main__":
    main()