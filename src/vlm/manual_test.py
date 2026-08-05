# ============================================================
# vlm_manual_test.py — VLM'i pipeline'dan tamamen izole test aracı
# ============================================================
# AMAÇ: Sistemde bir sorun olduğunda (yanlış sınıflandırma, düşük güven,
# tutarsız cevap vb.) sorunun YOLO/SAHI/tracker'dan mı yoksa VLM'in
# kendisinden mi (prompt, model, görüntü kalitesi) kaynaklandığını
# ayırt etmek için kullanılır. Elle seçilmiş 1-4 fotoğrafı doğrudan
# VLMEngine.analyze_target()'a gönderir — YOLO/SAHI/ByteTrack'in hiçbiri
# devrede değildir.
#
# KULLANIM:
#   Tek fotoğraf:
#       python vlm_manual_test.py images/foto.jpg
#
#   4 kolaj fotoğraf (tam pipeline simülasyonu):
#       python vlm_manual_test.py f1.jpg f2.jpg f3.jpg f4.jpg
#
#   Ham görüntüyle (enhancer uygulanmadan):
#       python vlm_manual_test.py foto.jpg --raw
#
#   Kolajı diske kaydet (debug):
#       python vlm_manual_test.py f1.jpg f2.jpg f3.jpg f4.jpg --save-collage
#
#   Farklı model test:
#       python vlm_manual_test.py foto.jpg --model qwen2.5vl:7b
# ============================================================

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import cv2

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s - %(message)s")
log = logging.getLogger(__name__)


def parse_args():
    p = argparse.ArgumentParser(
        description="VLM'i tek başına test et (YOLO/SAHI/tracker devre dışı)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "images", nargs="+",
        help="1-4 fotoğraf yolu — aynı hedefin farklı zaman anlarından kırpmaları. "
             "4 verilirse 2×2 kolaj, 3 verilirse 1+2 layout, 2 verilirse yan yana, "
             "1 verilirse tek 768×768 tam ekran olarak VLM'e gönderilir."
    )
    p.add_argument(
        "--raw", action="store_true",
        help="enhancer.py atla, ham görüntüyü gönder "
             "(GPU CLAHE/bilateral uygulanmaz — karşılaştırma için)"
    )
    p.add_argument(
        "--model", default=None,
        help="config.py'deki VLM_MODEL_NAME'i geçici olarak override et"
    )
    p.add_argument(
        "--yolo-class", default="bilinmeyen",
        help="Prompt'a giden simüle YOLO sınıf ipucu (varsayılan: bilinmeyen)"
    )
    p.add_argument(
        "--yolo-conf", type=float, default=0.0,
        help="Prompt'a giden simüle YOLO güven skoru 0-1 (varsayılan: 0.0)"
    )
    p.add_argument(
        "--speed", type=float, default=0.0,
        help="Simüle hız (px/s, varsayılan: 0.0)"
    )
    p.add_argument(
        "--zigzag", type=float, default=0.0,
        help="Simüle zigzag skoru 0-1 (varsayılan: 0.0)"
    )
    p.add_argument(
        "--save-collage", action="store_true",
        help="VLM'e gönderilen kolaj görüntüsünü pipeline_output/debug_vlm/'a kaydet "
             "(varsayılan: zaten kaydediliyor, bu flag çıkış yolunu loglara basar)"
    )
    return p.parse_args()


def main():
    args = parse_args()

    if len(args.images) > 4:
        log.warning(
            f"4'ten fazla görüntü verildi ({len(args.images)}), "
            "sadece ilk 4'ü kullanılacak (build_visual_grid en fazla 4 crop destekliyor)."
        )
        args.images = args.images[:4]

    # --- Görüntüleri oku ---
    crops = []
    for path in args.images:
        p = Path(path)
        if not p.exists():
            log.error(f"Dosya bulunamadı: {path}")
            sys.exit(1)
        img = cv2.imread(str(p))
        if img is None:
            log.error(f"Görüntü okunamadı (bozuk/desteklenmeyen format): {path}")
            sys.exit(1)
        crops.append(img)
        log.info(f"  Yüklendi: {path}  ({img.shape[1]}×{img.shape[0]} px)")

    # --- Config ve modüller ---
    from src.config import VLM_MODEL_NAME, VLM_API_URL, VLM_MIN_RECALL_INTERVAL_S, VLM_VOTE_WINDOW
    from src.vlm.engine import VLMEngine
    from src.utils.enhancer import ImageEnhancer

    # --- Enhancer uygula (--raw verilmediyse) ---
    if not args.raw:
        enhancer = ImageEnhancer()
        enhanced_crops = []
        for idx, c in enumerate(crops):
            enc = enhancer.enhance(c)
            if enc is not None:
                enhanced_crops.append(enc)
                log.info(
                    f"  crop[{idx}] iyileştirildi: "
                    f"{c.shape[1]}×{c.shape[0]} → {enc.shape[1]}×{enc.shape[0]} px"
                )
            else:
                # Enhance başarısız olduysa ham haliyle devam et
                enhanced_crops.append(c)
                log.warning(
                    f"  crop[{idx}] enhancer None döndürdü → ham görüntü kullanılıyor"
                )
        crops = enhanced_crops
        gpu_mode = enhancer._use_gpu
        log.info(
            f"enhancer.py uygulandı — "
            f"{'GPU (CUDA CLAHE + bilateral)' if gpu_mode else 'CPU (gray-world + bilateral)'}. "
            "Ham görüntüyle test etmek için --raw kullanın."
        )
    else:
        log.info("--raw: enhancer.py ATLANDI, görüntüler olduğu gibi gönderiliyor.")

    # Kolaj layout bilgisi
    n = len(crops)
    if n == 1:
        layout_info = "tek 768×768"
    elif n == 2:
        layout_info = "yan yana 768×387 (2-pane)"
    elif n == 3:
        layout_info = "üst büyük + alt 2 küçük (3-pane)"
    else:
        layout_info = "2×2 grid 768×768 (4-pane)"

    log.info(
        f"\n{'='*60}\n"
        f"  Kolaj layout  : {layout_info}\n"
        f"  Crop sayısı   : {n}\n"
        f"  YOLO ipucu    : {args.yolo_class} @ {args.yolo_conf:.0%}\n"
        f"  Hız/Zigzag    : {args.speed:.1f} px/s  |  {args.zigzag:.2f}\n"
        f"{'='*60}"
    )

    # --- VLM motorunu başlat ---
    model_name = args.model or VLM_MODEL_NAME
    engine = VLMEngine(
        model_name=model_name,
        api_url=VLM_API_URL,
        # Manuel testte cooldown/oylama devreye girmesin diye her çağrı
        # BENZERSİZ bir track_id kullanır (bkz. aşağıda time.time()) —
        # bu, gerçek pipeline'daki "track başına sınırlı deneme" mantığını
        # manuel test için anlamsız kılan bir durumu (art arda testlerin
        # cooldown'a takılması) önler.
        min_recall_interval_s=VLM_MIN_RECALL_INTERVAL_S,
        vote_window=VLM_VOTE_WINDOW,
    )

    fake_track_id = int(time.time() * 1000) % 1_000_000

    log.info(
        f"VLM'e gönderiliyor → model={model_name} | "
        f"track_id(fake)={fake_track_id}"
    )

    t0 = time.perf_counter()
    result = engine.analyze_target(
        track_id=fake_track_id,
        crops=crops,
        speed=args.speed,
        zigzag=args.zigzag,
        threat=0.0,
        yolo_class=args.yolo_class,
        yolo_conf=args.yolo_conf,
    )
    elapsed_s = time.perf_counter() - t0

    # --- Sonuç ---
    print("\n" + "=" * 60)
    if result is None:
        print("SONUÇ: VLM geçerli bir analiz döndürmedi (None).")
        print(
            "Olası nedenler:\n"
            "  • Ollama çalışmıyor (ollama serve)\n"
            "  • Model adı yanlış (ollama list ile kontrol et)\n"
            "  • JSON parse hatası (yukarıdaki log satırlarına bakın)\n"
            "  • Timeout (VLM_TIMEOUT_S artırılabilir)"
        )
    else:
        print(f"SONUÇ ({elapsed_s:.1f}s):")
        print(json.dumps(result, indent=2, ensure_ascii=False))
    print("=" * 60)

    # Kolaj dosyasını logla
    debug_dir = Path("pipeline_output/debug_vlm")
    if debug_dir.exists():
        saved = sorted(debug_dir.glob(f"track_{fake_track_id}_*.jpg"))
        if saved:
            print(f"\nVLM'e gönderilen kolaj: {saved[-1]}")
        else:
            print(f"\nKolaj kaydedilemedi — {debug_dir} kontrol edin.")

    if args.save_collage:
        # Kolajı ayrıca isimlendirilmiş olarak kaydet (debug karşılaştırması için)
        collage_path = debug_dir / f"manual_collage_{fake_track_id}.jpg"
        if collage_path.exists():
            print(f"Kolaj (isimlendirilmiş): {collage_path}")


if __name__ == "__main__":
    main()
