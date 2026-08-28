# ============================================================
# pipeline.py - v3: Keyframe + Tehdit Skoru + Arena + Metrik
# ============================================================

import cv2
import numpy as np
import time
import logging
import concurrent.futures
import json
import threading
from collections import deque
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from src.detection.slicer import SmartSlicer
from src.tracking.tracker import MultiTargetTracker, Track
from src.utils.enhancer import ImageEnhancer
from src.vlm.engine import VLMEngine
from src.vlm.video_evidence import TrackVideoBuffer, analyze_track_video
from src.core.visualizer import PipelineVisualizer
from src.config import (
    MODEL_PATH, OUTPUT_DIR, SHOW_WINDOW, SAVE_VIDEO, MIN_CROP_SIZE,
    VLM_COOLDOWN_S, VLM_MIN_BBOX_PX, VLM_MIN_TRACK_CONF, VLM_MIN_HITS_FOR_COLLAGE,
    VLM_MIN_CROP_POOL_SIZE, VLM_CROP_SEND_COUNT, VLM_RECALL_IQA_GAIN,
    VLM_MIN_RECALL_INTERVAL_S, ARENA_POLYGON, THREAT_WEIGHT_CLASS,
    THREAT_WEIGHT_CONF, THREAT_WEIGHT_SIZE, THREAT_WEIGHT_CENTER,
    SCENE_CHANGE_THRESHOLD, FAR_TARGET_AREA_RATIO, MIN_OBJECT_PX,
    DISPLAY_MIN_CONF, DISPLAY_MIN_CLASS_VOTE, DISPLAY_ALLOWED_CLASSES, DISPLAY_MIN_HITS, EDGE_MARGIN_PX,
    EDGE_MAX_FRAMES, SUSPENDED_DRAW_GRACE_FRAMES, MAX_OBJECT_AREA_RATIO,
    VRAG_VOTE_WINDOW, SIRALI_DONGU_MODU, VRAG_GUVEN_ESIGI, PROC_MAX_WIDTH,
    VRAG_SWITCH_MARGIN, VRAG_MIN_RELIABLE_BBOX_PX,
)

_LOG_FILE = Path(__file__).parent / "pipeline.log"
# BUG-9 Düzeltmesi: logging.basicConfig burada çağrılmaz.
# run.py bunu zaten tek seferde yapılandırıyor; burada sadece logger alınıyor.
log = logging.getLogger(__name__)

# Modelin sınıfları: 0=kite, 1=bird, 2=class_3 (uav/drone)
# Ekranda ID=2 "İHA" olarak gösterilir.
CLASS_NAMES = {
    0: "kite",
    1: "bird",
    2: "İHA",      # model bunu "class_3" olarak biliyor, biz insanlıkla gösteriyoruz
}
CLASS_COLORS = {
    0: (0,   255, 255),   # kite   → sarı
    1: (0,   165, 255),   # bird   → turuncu
    2: (0,   80,  255),   # İHA    → kırmızı-turuncu (tehdit rengi)
}


@dataclass
class TrackedTarget:
    track_id:      int
    class_id:      int
    class_name:    str
    confidence:    float
    bbox_xyxy:     np.ndarray
    raw_bbox:      np.ndarray
    speed_px_s:    float
    velocity:      np.ndarray
    zigzag_score:  float
    hits:          int
    threat_score:  float
    in_arena:      bool
    vlm_ready:     bool
    best_crops:    list[np.ndarray] = field(default_factory=list)
    visual_heading: Optional[np.ndarray] = None
    classified_type: str = "UÇAK / İHA"
    type_confidence: float = 0.0
    vrag_matches: list[dict] = field(default_factory=list)
    vlm_result: Optional[dict] = None
    llm_result: Optional[dict] = None
    video_vlm_result: Optional[dict] = None


class TeknoFestPipeline:
    def __init__(self, source_fps: float = 25.0):
        """source_fps: Kaynak videonun gerçek FPS değeri (video yazma için kullanılır)."""
        log.info("=== TeknoFest Pipeline v3 Başlatılıyor ===")
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        self._source_fps = max(1.0, source_fps)   # BUG-7: Video FPS doğru kaydedilsin
        # BUG-FIX (video-geneli özet karışıyordu): _async_llm_task karar_servisi'ne
        # hep sabit "live_video" video_id'siyle gidiyordu, yani farklı videolardaki
        # olaylar event_memory.db'de aynı video_id altında karışıyordu. backend/main.py
        # her yeni oturumda bunu gerçek video adına günceller (bkz. _video_dongu).
        self.video_id = "live_video"

        self.slicer   = SmartSlicer(MODEL_PATH)
        # BUG-FIX: MultiTargetTracker eskiden fps parametresi almıyordu ve
        # içeride sabit 30 FPS varsayıyordu (ByteTrack frame_rate + her Track'in
        # hız hesabı). Artık gerçek kaynak FPS'i buraya iletiliyor.
        self.tracker  = MultiTargetTracker(fps=self._source_fps)
        self.enhancer = ImageEnhancer()
        self.vlm      = VLMEngine()
        self.visualizer = PipelineVisualizer(source_fps=self._source_fps)

        # Prensip 1: Asenkron ve Bloke Etmeyen Mimari için paralel işleme worker havuzu (VLMPool)
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="VLMPool")

        # BUG-FIX (VRAG'ın süresiz donması): Tek bir kilit (_ai_gate) eskiden VRAG
        # (SigLIP2 embedding) ile VLM çağrılarının İKİSİNİ BİRDEN sıralıyordu.
        # Aralarında gerçek kaynak çakışması yok — VLM artık uzak EVREN API'sine
        # gidiyor (yerel GPU/CPU hiç kullanmıyor), VRAG kendi hızlandırıcısında
        # (DEVICE/VRAG_DEVICE, bkz. config.py) bağımsız çalışıyor.
        # Ortak kilidin bedeli ağırdı: VLM'in zaman aşımı 120 saniye, ve bu süre
        # boyunca TÜM VRAG aramaları (ve diğer track'lerin VLM çağrıları) donuyordu
        # (canlı testte doğrulandı — bir VRAG görevi kilidi hiç alamadan
        # dakikalarca askıda kaldı, kuyruktaki sonraki hedefler hiç başlayamadı).
        # Artık VRAG ve VLM ayrı kilitlere sahip.
        self._vrag_gate = threading.Lock()
        # BUG-FIX (image-VLM'de 40sn'ye varan kuyruk gecikmesi): tam bir Lock()
        # aynı anda SADECE 1 image-VLM çağrısına izin veriyordu - birden fazla
        # track (+ VLM_MIN_RECALL_INTERVAL_S'in agresif tekrar tetiklemesi)
        # aynı anda kuyruğa girince, kuyruğun sonundaki iş "istek sayısı ×
        # ortalama çağrı süresi" kadar bekliyordu (canlı testte 5 istek ×
        # ~8sn ≈ 40sn olarak gözlemlendi). Semaphore(2) ile en az 2 istek
        # paralel gidebiliyor - EVREN'in key başına eş zamanlı istek limitini
        # bilmiyoruz, 2 ihtiyatlı bir başlangıç (429 gözlenirse 1'e dönülür).
        self._vlm_gate = threading.Semaphore(2)

        # Video-kanıtı (MVP TrackEvidenceBuilder-lite, bkz. src/vlm/video_evidence.py):
        # Track nesnesine gömülmez, track_id -> TrackVideoBuffer ile ayrı tutulur.
        # Image (crop) yolunun yanında, ondan bağımsız ikinci bir kanıt kaynağı —
        # biri diğerinin yerini almaz, ikisi de kalıcı olarak birlikte çalışır.
        self._video_buffers: dict[int, TrackVideoBuffer] = {}
        
        # --- CUDA WARMUP ---
        # PyTorch modelleri (YOLO ve SigLIP) ilk çalıştıklarında CUDA bellek tahsisi ve derleme
        # yaptıkları için videoyu 10-15 saniye dondururlar. Bunu engellemek için boş bir 
        # görüntü ile "ısınma (warmup)" turu attırıyoruz.
        try:
            log.info("[PIPELINE] CUDA Isınma turu başlatılıyor (Video donmasını engellemek için)...")
            import numpy as np
            dummy_img = np.zeros((640, 640, 3), dtype=np.uint8)
            # YOLO Warmup
            self.slicer.detect(dummy_img)
            # VRAG Warmup (Eğer aktifse)
            if self.vlm.vrag_engine:
                self.vlm.vrag_engine.search_similar_vehicle(dummy_img, top_k=1)
            log.info("[PIPELINE] CUDA Isınma tamamlandı!")
        except Exception as e:
            log.warning(f"CUDA Warmup sırasında hata (önemsiz): {e}")

        self._video_writer  = None
        self._frame_count   = 0
        self._prev_gray     = None
        # /durum üzerinden okunan canlı performans telemetrisi (bkz.
        # _update_performance_snapshot) - ilk kare işlenene kadar boş.
        self.performans: dict = {}

        # INFO-3: deque ile maksimum bellekte 100 eleman tutulur (bellek sızıntısı önlendi)
        self._t_slicer:  deque[float] = deque(maxlen=100)
        self._t_tracker: deque[float] = deque(maxlen=100)
        self._t_enhance: deque[float] = deque(maxlen=100)

        log.info("Pipeline v3 hazır.")

    # ──────────────────────────────────────────────────────────
    # [YENİ] SAHTE POZİTİF TEMİZLEYİCİ
    # ──────────────────────────────────────────────────────────
    def _filter_false_positives(self, targets: list[TrackedTarget], frame: np.ndarray) -> list[TrackedTarget]:
        """Sahte pozitifleri tespit et ve temizle."""
        if not targets:
            return targets
        
        fh, fw = frame.shape[:2]
        filtered = []
        
        for t in targets:
            x1, y1, x2, y2 = t.bbox_xyxy
            area = (x2 - x1) * (y2 - y1)

            if area / (fw * fh) > MAX_OBJECT_AREA_RATIO:
                continue

            track = self.tracker._states.get(t.track_id)
            class_share = track.voted_class_share if track is not None else 0.0
            disp_conf = track.display_confidence if track is not None else t.confidence

            if track is not None and track.suspended and track.suspended_streak > SUSPENDED_DRAW_GRACE_FRAMES:
                continue

            if track is not None and track.edge_touch_frames > 30:
                continue

            if t.class_id not in DISPLAY_ALLOWED_CLASSES:
                continue

            area_ratio = area / (fw * fh)
            min_hits_required = 2
            if t.hits < min_hits_required:
                continue

            if disp_conf < DISPLAY_MIN_CONF or class_share < DISPLAY_MIN_CLASS_VOTE:
                continue

            if area < (MIN_OBJECT_PX * MIN_OBJECT_PX) * 2:
                continue
            
            # 3. Aynı bölgede çok fazla hedef varsa (gürültü patlaması)
            nearby = sum(1 for other in targets if other != t and 
                        abs((other.bbox_xyxy[0] + other.bbox_xyxy[2])/2 - (x1+x2)/2) < 50 and
                        abs((other.bbox_xyxy[1] + other.bbox_xyxy[3])/2 - (y1+y2)/2) < 50)
            if nearby > 3:
                continue
            
            filtered.append(t)

        # BUG-FIX (aynı uçağa 2 kutu — SON SAVUNMA KATMANI): slicer.py artık
        # kaynağında (ham tespit seviyesinde) bunu önlüyor, ama zaten ikiye
        # bölünmüş halde ByteTrack'e girmiş eski/kalıcı bir track çifti (ör.
        # slicer düzeltmesinden ÖNCE açılmış bir ID) hâlâ ekranda aynı uçak
        # için iki ayrı kutu olarak durabilir. Burada, biri diğerinin büyük
        # kısmına gömülüyse (IoA), düşük tehdit skorlu/düşük güvenli olanı
        # gizliyoruz — sınıf/track_id farkı önemsiz, salt geometri.
        if len(filtered) > 1:
            ordered = sorted(filtered, key=lambda x: x.threat_score, reverse=True)
            deduped: list[TrackedTarget] = []
            for cand in ordered:
                cx1, cy1, cx2, cy2 = cand.bbox_xyxy
                cand_area = max(1.0, (cx2 - cx1) * (cy2 - cy1))
                dropped = False
                for kept in deduped:
                    kx1, ky1, kx2, ky2 = kept.bbox_xyxy
                    ix1, iy1 = max(cx1, kx1), max(cy1, ky1)
                    ix2, iy2 = min(cx2, kx2), min(cy2, ky2)
                    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
                    if inter <= 0.0:
                        continue
                    k_area = max(1.0, (kx2 - kx1) * (ky2 - ky1))
                    # BUG-FIX (Yakın uçuşta çoklu kutu): Eskiden 0.55 idi. Yaklaşan büyük
                    # uçakta kanat veya motor tespitleri ayrı kutu olarak kalabiliyordu.
                    # 0.35'e düşürüldü ki büyük gövde tespitinin içine azıcık bile gömülen
                    # zayıf parçalar (düşük threat_score) yutulsun.
                    ioa = inter / min(cand_area, k_area)
                    if ioa >= 0.35:
                        dropped = True
                        break
                if not dropped:
                    deduped.append(cand)
            filtered = deduped

        return filtered

    # ──────────────────────────────────────────────────────────
    # ANA FONKSİYON
    # ──────────────────────────────────────────────────────────
    def process_frame(self, frame_bgr: np.ndarray) -> list[TrackedTarget]:
        t_total = time.perf_counter()
        self._frame_count += 1

        # İşleme çözünürlüğü tavanı: pipeline'a girmeden en başta küçült, böylece
        # detection/tracking/crop/çizim hepsi aynı uzayda kalır (koordinat geri-
        # eşlemesi gerekmez). Zaten daha küçük gönderilen kareler (ör. backend
        # adaptöründeki 1280px sınırı) burada zaten eşiğin altında kalıp no-op olur.
        if PROC_MAX_WIDTH and frame_bgr.shape[1] > PROC_MAX_WIDTH:
            olcek = PROC_MAX_WIDTH / frame_bgr.shape[1]
            frame_bgr = cv2.resize(
                frame_bgr, (PROC_MAX_WIDTH, int(round(frame_bgr.shape[0] * olcek))),
                interpolation=cv2.INTER_AREA,
            )

        fh, fw = frame_bgr.shape[:2]

        # ======================================================
        # 0. SAHNE DEĞİŞİMİ TESPİTİ
        # ======================================================
        curr_gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        # BUG-FIX (çözünürlük değişimi çökmesi): Pipeline nesnesi oturumlar arası
        # yeniden kullanılıyor (main.py bir kez oluşturup saklıyor), bu yüzden
        # _prev_gray önceki videodan kalabilir. Yeni video farklı çözünürlükteyse
        # cv2.absdiff boyut uyuşmazlığından patlıyordu — şekil kontrolü eklendi.
        if self._prev_gray is not None and self._prev_gray.shape == curr_gray.shape:
            diff = cv2.absdiff(self._prev_gray, curr_gray)
            mean_diff = float(diff.mean())
            if mean_diff > SCENE_CHANGE_THRESHOLD:
                log.info(f"[SAHNE GEÇİŞİ] diff={mean_diff:.1f} > {SCENE_CHANGE_THRESHOLD} → Tüm track'ler sıfırlandı!")
                self.tracker.reset()
        self._prev_gray = curr_gray

        # ======================================================
        # 1. SAHI + YOLO
        # ======================================================
        t0 = time.perf_counter()
        hint_positions = [
            tuple(t.kalman.position)
            for t in (self.tracker.tracks + self.tracker.suspended_tracks)
        ]
        raw_dets = self.slicer.detect(frame_bgr, hint_positions=hint_positions or None)
        self._t_slicer.append(time.perf_counter() - t0)

        # ======================================================
        # 2. TRACKER
        # ======================================================
        t0 = time.perf_counter()
        valid_tracks: list[Track] = self.tracker.update(raw_dets, frame_bgr)
        self._t_tracker.append(time.perf_counter() - t0)

        # ======================================================
        # 3. CROP + CLAHE + KEYFRAME + TEHDIT SKORU + ARENA
        # ======================================================
        t0 = time.perf_counter()
        now = time.perf_counter()
        results: list[TrackedTarget] = []

        for track in valid_tracks:
            smooth_box = track.kalman_bbox().astype(int)
            x1 = max(0, smooth_box[0]); y1 = max(0, smooth_box[1])
            x2 = min(fw, smooth_box[2]); y2 = min(fh, smooth_box[3])
            bw, bh = x2 - x1, y2 - y1

            if bw < MIN_CROP_SIZE or bh < MIN_CROP_SIZE:
                continue

            # --- Arena Sınırı Kontrolü ---
            cx_t = int((x1 + x2) / 2)
            cy_t = int((y1 + y2) / 2)
            in_arena = self._in_arena((cx_t, cy_t), fw, fh)

            # --- Tehdit Skoru Hesapla ---
            # ID=2 modelimizin drone/uav sınıfı → yüksek öncelik
            class_bonus  = THREAT_WEIGHT_CLASS if track.class_id == 2 else 0.0
            conf_score   = track.confidence * THREAT_WEIGHT_CONF
            size_score   = (bw * bh) / (fw * fh) * THREAT_WEIGHT_SIZE
            dx = abs(cx_t - fw / 2) / (fw / 2)
            dy = abs(cy_t - fh / 2) / (fh / 2)
            center_score = (1.0 - min(1.0, (dx + dy) / 2)) * THREAT_WEIGHT_CENTER
            threat_score = class_bonus + conf_score + size_score + center_score

            # --- VLM Tetikleme ---
            # Uçaklar uzaktadayken aşırı yatık (örn. 80x14 px) görünür; her iki yönün >=20 olması
            # VLM tetiklemesini sonsuza dek engelleyebiliyordu. Genişlik >= 15 ve yükseklik >= 10 yeterli kılındı.
            size_ok = (bw >= 15) and (bh >= 10) and max(bw, bh) >= VLM_MIN_BBOX_PX
            
            # --- [YENİ] Bağımsız VRAG Araması ---
            # VLM'i beklemeden doğrudan VRAG'ı çalıştırıp HUD'a yansıtabilmek için.
            #
            # DENEYSEL (SIRALI_DONGU_MODU): Açıksa VRAG artık "bağımsız" değil —
            # yalnızca track'in dongu_asamasi "vrag" iken tetiklenir (VLM/LLM
            # turunu bekler). Bkz. config.py'deki SIRALI_DONGU_MODU notu.
            dongu_vrag_sirasi = (
                not SIRALI_DONGU_MODU
                or self.vlm.vrag_engine is None
                or getattr(track, "dongu_asamasi", "vrag") == "vrag"
            )
            # BUG-FIX (kullanıcı isteği — "kesin karara varana kadar stabil model
            # gözüksün"): track için LLM zaten kesin bir karar verdiyse (bkz.
            # _async_llm_task'taki decision_locked ataması), VRAG/VLM'i bir daha
            # hiç tetikleme — ne ekrandaki kimlik ne de zaman damgası bir daha
            # değişir, gereksiz EVREN çağrısı da yapılmaz.
            karar_kilitli = getattr(track, "decision_locked", False)
            if size_ok and len(track._crop_buffer) > 0 and dongu_vrag_sirasi and not karar_kilitli:
                if not hasattr(track, "vrag_last_time"):
                    track.vrag_last_time = 0.0
                if not hasattr(track, "vrag_is_running"):
                    track.vrag_is_running = False

                if not track.vrag_is_running and (now - track.vrag_last_time > 1.0):
                    # BUG-FIX ("bazen kutu fazla dar"): bu blok eskiden PAYLAŞILAN
                    # x1,y1,x2,y2 değişkenlerini (raporlanan bbox_xyxy'nin kaynağı)
                    # geçici olarak ham/titrek track.bbox ile EZİYORDU - VRAG kırpma
                    # kutusunun hiçbir ilgisi olmayan bu değerler, döngünün geri
                    # kalanında yanlışlıkla ekrana gönderilen kutu haline geliyordu
                    # (VRAG tetiklendiği ~1 saniyede bir, hedefin kutusu aniden
                    # Kalman-yumuşatılmış boyuttan ham/dar tespit boyutuna sıçrıyordu).
                    # Kendi yerel değişkenlerine taşındı, paylaşılan x1..y2'ye dokunmaz.
                    vx1, vy1, vx2, vy2 = map(int, track.bbox)
                    pad_x, pad_y = int(bw * 0.15), int(bh * 0.15)
                    cx1, cy1 = max(0, vx1 - pad_x), max(0, vy1 - pad_y)
                    cx2, cy2 = min(frame_bgr.shape[1], vx2 + pad_x), min(frame_bgr.shape[0], vy2 + pad_y)
                    live_crop = frame_bgr[cy1:cy2, cx1:cx2]

                    if live_crop.size > 0 and self.vlm.vrag_engine:
                        track.vrag_is_running = True
                        # BUG-FIX (kök neden araştırması — "küçük/uzak hedeflerde
                        # VRAG kararsız"): VLM_MIN_BBOX_PX yalnızca "tetiklemeye
                        # yeter" - bu ölçekte iki farklı uçağı gerçekten ayırt
                        # etmek güvenilir değil. Kırpım yeterince büyük değilse
                        # yine aranır (kullanıcıdan gizlenmez) ama sonucu track'in
                        # oylama geçmişine EKLENMEZ (bkz. _async_vrag_task).
                        boyut_guvenilir = max(bw, bh) >= VRAG_MIN_RELIABLE_BBOX_PX
                        self.executor.submit(self._async_vrag_task, track, live_crop, boyut_guvenilir)

            # --- [YENİ] Video-kanıtı toplama (MVP) ---
            # Image (crop) yolundan bağımsız — her karede ayrı bir tampona
            # eklenir, image tetiklemesini beklemez/etkilemez.
            if size_ok:
                x1i, y1i, x2i, y2i = map(int, track.bbox)
                pad_x, pad_y = int(bw * 0.25), int(bh * 0.25)
                vx1, vy1 = max(0, x1i - pad_x), max(0, y1i - pad_y)
                vx2, vy2 = min(frame_bgr.shape[1], x2i + pad_x), min(frame_bgr.shape[0], y2i + pad_y)
                video_crop = frame_bgr[vy1:vy2, vx1:vx2]
                buf = self._video_buffers.get(track.track_id)
                if buf is None:
                    buf = TrackVideoBuffer(fps=self._source_fps)
                    self._video_buffers[track.track_id] = buf
                buf.add(video_crop)

            # Prensip 3: Kontrastı ve köşe netliği en yüksek olan EN İYİ kareyi seç.
            # BUG-FIX: Eskiden crop_buffer_ready sadece "en az 1 kare var mı?" diye
            # bakıyordu — bu yüzden hedef daha 8. frame'de, buffer 3-6 kareyken
            # tetikleniyor ve o küçük/kötü havuzun "en iyisi" seçiliyordu.
            # Artık gerçek buffer doluluğuna (VLM_MIN_CROP_POOL_SIZE) bakıyoruz,
            # yani hedef ekranda biraz daha gezinip zengin bir kare havuzu
            # oluşturmadan VLM'e gitmiyoruz. Gönderilecek kare sayısı da
            # config'ten (VLM_CROP_SEND_COUNT, varsayılan=1 → tek en iyi foto).
            raw_crops = track.get_best_crops(max_crops=VLM_CROP_SEND_COUNT)

            crop_buffer_ready = (len(track._crop_buffer) >= VLM_MIN_CROP_POOL_SIZE)
            # Yeterli frame görülmeden VLM'e gitmesin (0.5s sahte/kısa track koruması korunur!)
            hits_ok = (track.hits >= VLM_MIN_HITS_FOR_COLLAGE)

            # BUG-FIX (VLM pipeline tetiklenmiyordu): aynı anlık-güven sorunu
            # burada da crop havuzunu doldurma/VLM tetikleme kararını
            # bozuyordu — display_confidence ile stabilize edildi.
            conf_ok = track.display_confidence >= VLM_MIN_TRACK_CONF
            # BUG-FIX: EDGE_MAX_FRAMES config.py'de tanımlıydı ("kenarda takılı
            # kalma filtresi — yaprak/dal için") ama hiçbir yerde kontrol
            # edilmiyordu. edge_touch_frames zaten Track.update() içinde
            # doğru hesaplanıyordu, sadece burada tüketilmiyordu. Ekranın
            # kenarında EDGE_MAX_FRAMES'ten uzun süredir takılı kalan
            # (muhtemelen yaprak/dal/gürültü) hedefler artık VLM'e gitmiyor.
            edge_ok = track.edge_touch_frames < EDGE_MAX_FRAMES
            vlm_ready = in_arena and size_ok and crop_buffer_ready and conf_ok and hits_ok and edge_ok

            # --- [YENİ] Video-kanıtı tetikleme (MVP) ---
            # Aynı kalite kapısını (vlm_ready) kullanır ama image tetiklemesinden
            # TAMAMEN bağımsız çalışır — image sonucu bekletmez/etkilemez, ve
            # image evidence'ı ASLA ezmez (ayrı bir sonuç alanına yazılır,
            # bkz. _async_video_vlm_task). TEKRARLI ama YAVAŞLATILMIŞ: track
            # başına en az VIDEO_REPEAT_COOLDOWN_S (varsayılan 8sn) aralıkla —
            # image-VLM'in EVREN kapasitesini video isteklerine kaptırıp
            # ciddi gecikmesi (~6sn->~40sn, canlı testte gözlemlendi) önlendi.
            video_buf = self._video_buffers.get(track.track_id)
            if (
                video_buf is not None and video_buf.ready
                and vlm_ready and not getattr(track, "is_video_vlm_querying", False)
            ):
                track.is_video_vlm_querying = True
                video_buf.last_sent_time = time.monotonic()
                frames_to_send = list(video_buf.frames)
                video_buf.frames.clear()  # gönderildi, tampon yeniden dolmaya başlar
                log.info(
                    f"[VIDEO-VLM] Track {track.track_id} → {len(frames_to_send)} karelik "
                    f"video-kanıtı gönderiliyor."
                )
                self.executor.submit(self._async_video_vlm_task, track, frames_to_send)

            # IQA kalitesi artış kontrolü (Recall): Uçak yan dönüp bayrak/geniş silüet açığa çıktığında skor %25 artmışsa VLM analizi yenilenir
            current_best_iqa = max((c[1] for c in track._crop_buffer), default=0.0) if track._crop_buffer else 0.0
            last_iqa = getattr(track, "last_vlm_iqa_score", 0.0)
            time_since_vlm = now - getattr(track, "last_vlm_time", 0.0)
            is_superior_recall = track.vlm_done and (time_since_vlm >= VLM_MIN_RECALL_INTERVAL_S) and (current_best_iqa >= last_iqa * VLM_RECALL_IQA_GAIN)

            if not vlm_ready and not track.vlm_done and not track.is_vlm_querying and track.hits >= 10 and track.hits % 10 == 0:
                # BUG-FIX: Eskiden yalnızca hits TAM OLARAK 15/30/60/100 iken
                # loglanıyordu. Track'ler bölünme/yeniden-ID nedeniyle bu
                # sayılara hiç ulaşamayabiliyordu — sonuç: VLM neden
                # tetiklenmiyor hiç görünmüyordu. Artık her 10 hit'te bir
                # (>=10) tetiklenir ve HANGİ kapının tıkalı olduğunu (crop
                # havuzu doluluğu dahil) açıkça gösterir.
                log.info(
                    f"[VLM BEKLEMEDE] Track #{track.track_id} | arena:{in_arena} | "
                    f"boyut:{size_ok} ({bw}x{bh}px) | "
                    f"crop_havuzu:{len(track._crop_buffer)}/{VLM_MIN_CROP_POOL_SIZE} | "
                    f"hits:{track.hits}/{VLM_MIN_HITS_FOR_COLLAGE} | "
                    f"güven:{conf_ok} (disp={track.display_confidence:.2f} eşik={VLM_MIN_TRACK_CONF}) | "
                    f"edge_ok:{edge_ok} (edge_frames={track.edge_touch_frames})"
                )

            # DENEYSEL (SIRALI_DONGU_MODU): Aktifse VLM, "hiç analiz edilmemiş
            # ya da çok daha net kare geldi" mantığı yerine SADECE track'in
            # dongu_asamasi "vlm" olduğunda (yani VRAG az önce bitirip sırayı
            # devrettiğinde) tetiklenir — her turda vlm_done'a bakmaksızın
            # yeniden analiz eder.
            sirali_mod_aktif = SIRALI_DONGU_MODU and self.vlm.vrag_engine is not None
            if sirali_mod_aktif:
                vlm_calissin_mi = (
                    getattr(track, "dongu_asamasi", "vrag") == "vlm"
                    and not track.is_vlm_querying
                )
            else:
                vlm_calissin_mi = (
                    (not track.is_vlm_querying or is_superior_recall)
                    and (not track.vlm_done or is_superior_recall)
                )

            if vlm_ready and vlm_calissin_mi and not karar_kilitli:
                if is_superior_recall:
                    log.info(
                        f"[VLM-RECALL / SÜPER KARE] Track {track.track_id} → "
                        f"Daha net yan silüet / bayrak anı yakalandı! "
                        f"(Yeni IQA: {current_best_iqa:.1f} > Eski: {last_iqa:.1f}) | hits={track.hits}"
                    )
                    # Eski bulanık fotoğrafın tahminlerini çöpe at, yeni net fotoğrafa %100 güven!
                    self.vlm.forget_track(track.track_id)
                else:
                    log.info(
                        f"[VLM-AKILLI SEÇİM] Track {track.track_id} → "
                        f"En yüksek netlik ve kontrasta sahip {len(raw_crops)} süper kare seçildi | "
                        f"hits={track.hits} | conf={track.confidence:.2f} | "
                        f"bbox={bw}x{bh}px"
                    )
                if len(raw_crops) >= 1:
                    raw_cls = CLASS_NAMES.get(track.voted_class_id, "bilinmeyen")
                    yolo_cls_name = "hava_araci (ucak, iha veya helikopter)" if raw_cls == "İHA" else raw_cls

                    track.is_vlm_querying = True
                    track.last_vlm_time = now
                    track.last_vlm_iqa_score = current_best_iqa
                    # Prensip 1 (Zero-Latency): Enhance (CLAHE) ve kolaj işlemleri dahil tümü ana ipliği sıfır bekletmeyle worker thread'e devredildi!
                    # BUG-FIX: video_id burada (crop'un yakalandığı asıl an)
                    # yakalanıp göreve taşınıyor - bkz. _async_vlm_task/_async_llm_task
                    # içindeki notlar.
                    self.executor.submit(
                        self._async_vlm_task,
                        track,
                        raw_crops,
                        track.speed_px_s,
                        track.zigzag_score,
                        threat_score,
                        yolo_cls_name,
                        track.confidence,
                        self.video_id,
                    )

            # --- [YENİ] LLM Tetikleme ---
            if not karar_kilitli and getattr(track, "vlm_done", False) and getattr(track, "vlm_result", None):
                current_vlm_hash = self._vlm_identity_signature(track.vlm_result)
                if not getattr(track, "is_llm_querying", False) and self._confirm_stable_vlm_hash(
                    track, current_vlm_hash
                ):
                    track.is_llm_querying = True
                    track.last_llm_vlm_hash = current_vlm_hash
                    # BUG-FIX: self.video_id gorevin ICINDE degil, SUNULDUGU anda
                    # yakalanmali - aksi halde kullanici gorev kuyrukta beklerken
                    # baska bir videoya gecerse, bu gorev calistiginda YANLIS
                    # (yeni) video_id ile karar_servisi'ne gonderilip o videonun
                    # nihai kayitlarini kirletiyordu ("2. videodayken 1. videonun
                    # cikisi geliyor" sikayeti).
                    self.executor.submit(self._async_llm_task, track, track.vlm_result, self.video_id)

            clamped_box = np.array([x1, y1, x2, y2])
            raw_clamped = np.array([
                max(0, int(track.bbox[0])),
                max(0, int(track.bbox[1])),
                min(fw, int(track.bbox[2])),
                min(fh, int(track.bbox[3]))
            ])

            cls_type, cls_conf = track.classify_bird_vs_aircraft()

            results.append(TrackedTarget(
                track_id      = track.track_id,
                class_id      = track.voted_class_id,
                class_name    = CLASS_NAMES.get(track.voted_class_id, "unknown"),
                confidence    = track.confidence,
                bbox_xyxy     = clamped_box,
                raw_bbox      = raw_clamped,
                speed_px_s    = track.speed_px_s,
                velocity      = track.smooth_velocity,
                zigzag_score  = track.zigzag_score,
                hits          = track.hits,
                threat_score  = threat_score,
                in_arena      = in_arena,
                vlm_ready     = vlm_ready,
                best_crops    = raw_crops,
                visual_heading= track.visual_heading,
                classified_type = cls_type,
                type_confidence = cls_conf,
                vrag_matches  = getattr(track, "vrag_matches", []),
                vlm_result    = getattr(track, "vlm_result", None),
                llm_result    = getattr(track, "llm_result", None),
                video_vlm_result = getattr(track, "video_vlm_result", None),
            ))

        # ======================================================
        # [YENİ] SAHTE POZİTİF TEMİZLEME
        # ======================================================
        results = self._filter_false_positives(results, frame_bgr)

        # Tehdit skoruna göre sırala
        results.sort(key=lambda t: t.threat_score, reverse=True)

        self._t_enhance.append(time.perf_counter() - t0)

        # ======================================================
        # 4. PERFORMANS METRİKLERİ
        # ======================================================
        if self._frame_count % 100 == 0:
            self._log_metrics()

        # ======================================================
        # 5. ÇIZIM VE KAYIT
        # ======================================================
        total_ms = (time.perf_counter() - t_total) * 1000
        fps = 1000.0 / max(total_ms, 1.0)
        # BUG-FIX (mimari değişiklik): bu telemetri eskiden yalnızca kareye
        # yakılan yeşil HUD metni olarak vardı (bkz. visualizer.py). Artık
        # /durum üzerinden okunabilecek şekilde saklanıyor — "Canlı
        # Performans" paneli (frontend) buradan besleniyor.
        self._update_performance_snapshot(fps, total_ms, len(raw_dets), len(results))
        self.frame_bgr = self.visualizer.draw_and_save(frame_bgr)

        return results

    # ──────────────────────────────────────────────────────────
    # ARENA SINIRI
    # ──────────────────────────────────────────────────────────
    def _in_arena(self, point: tuple, fw: int, fh: int) -> bool:
        if not ARENA_POLYGON:
            return True
        pts = np.array(
            [(int(px * fw), int(py * fh)) for px, py in ARENA_POLYGON],
            dtype=np.int32
        )
        result = cv2.pointPolygonTest(pts, point, False)
        return result >= 0

    # ──────────────────────────────────────────────────────────
    # PERFORMANS METRİKLERİ
    # ──────────────────────────────────────────────────────────
    def _log_metrics(self):
        def avg_ms(d):
            if not d: return 0.0
            return (sum(d) / len(d)) * 1000

        log.info(
            f"[PERF Frame {self._frame_count}] "
            f"Slicer:{avg_ms(self._t_slicer):.1f}ms | "
            f"Tracker:{avg_ms(self._t_tracker):.1f}ms | "
            f"Enhance:{avg_ms(self._t_enhance):.1f}ms | "
            f"Suspended Tracks:{len(self.tracker.suspended_tracks)}"
        )

    def _update_performance_snapshot(self, fps: float, total_ms: float, raw_count: int, confirmed_count: int) -> None:
        """/durum üzerinden okunacak canlı performans telemetrisini günceller
        (bkz. backend/main.py durum_al) - kareye çizilmez."""
        def avg_ms(d):
            if not d:
                return 0.0
            return (sum(d) / len(d)) * 1000

        self.performans = {
            "fps": round(fps, 1),
            "frame_ms": round(total_ms, 1),
            "slicer_ms": round(avg_ms(self._t_slicer), 1),
            "tracker_ms": round(avg_ms(self._t_tracker), 1),
            "ham_tespit": raw_count,
            "onayli_hedef": confirmed_count,
            "askida_hedef": len(self.tracker.suspended_tracks),
        }

    # BUG-FIX (KÖKTEN — "nihai çıktı bazen hiç gelmiyor"): _confirm_stable_vlm_hash
    # eskiden str(json_result) ile TÜM VLM çıktısını (gorsel_analiz gibi VLM'in
    # her seferinde YENİDEN ÜRETTİĞİ serbest metni + ondalıklı skorları dahil)
    # karşılaştırıyordu. gorsel_analiz bir dil modelinin serbest cümlesi olduğu
    # için aynı sonuç/kimlik olsa bile kelimesi kelimesine iki kez aynı çıkması
    # neredeyse imkansızdı — "2 ardışık kararlı sonuç" şartı pratikte hemen hiç
    # sağlanamıyor, LLM tetiklenmiyor, event_memory.db'ye hiçbir kayıt düşmüyordu.
    # Artık SADECE kimlik/karar açısından anlamlı, ayrık alanlar imzaya giriyor.
    _VLM_IDENTITY_FIELDS = ("arac_sinifi", "tahmini_hedef_tipi", "hedef_modeli", "ulke_orjini", "tehdit_seviyesi")

    def _vlm_identity_signature(self, vlm_result: dict) -> str:
        return str(tuple(vlm_result.get(field) for field in self._VLM_IDENTITY_FIELDS))

    def _confirm_stable_vlm_hash(self, track, current_vlm_hash: str) -> bool:
        """BUG-FIX (kökten): bir hedefin VLM hipotezi değiştiği ANDA, tek bir
        anlık/yanlış sınıflandırma bile (ör. tek bir turda "Vestel KARAYEL")
        hemen LLM'e gönderilip event_memory.db'ye KALICI bir nihai karar
        olarak yazılıyordu — video-geneli özet de bu tek seferlik kaydı
        güvenilir bir bulgu gibi raporluyordu ("10ms olsa bile nihai çıktıya
        giriyor"). Artık yeni bir hipotez önce SADECE 'beklemede' sayılır;
        BİR SONRAKİ turda da AYNI hipotez tekrar görülürse (yani en az 2
        ardışık turda kararlı kalırsa) LLM tetiklenir/kaydedilir."""
        last_hash = getattr(track, "last_llm_vlm_hash", None)
        if current_vlm_hash == last_hash:
            return False
        pending_hash = getattr(track, "pending_llm_vlm_hash", None)
        if pending_hash == current_vlm_hash:
            track.pending_llm_vlm_hash = None
            return True
        track.pending_llm_vlm_hash = current_vlm_hash
        return False

    def release(self):
        self.visualizer.release()
        self._log_metrics()
        
        log.info("VLM arka plan görevlerinin tamamlanması bekleniyor (Lütfen kapatmayın)...")
        self.executor.shutdown(wait=True)

        # BUG-FIX: tracker._crop_pool (CropPool) hiç kapatılmıyordu.
        self.tracker.close()

        log.info(f"Pipeline kapatıldı. Toplam: {self._frame_count} frame.")

    def _async_vrag_task(self, track, live_crop, boyut_guvenilir=True):
        try:
            import time
            # VRAG kendi kilidini kullanır — VLM'in (Ollama, 120sn'ye kadar sürebilir)
            # kilidini beklemek zorunda değil.
            with self._vrag_gate:
                matches = self.vlm.vrag_engine.search_similar_vehicle(live_crop)
            if matches:
                # BUG-FIX (kök neden araştırması — "küçük/uzak hedeflerde VRAG
                # kararsız"): kırpım VRAG_MIN_RELIABLE_BBOX_PX'ten küçükse bu
                # sonuç ne oylama geçmişine eklenir ne de onaylı kimliği
                # değiştirir - hâlâ ekranda bir "bekleme" tahmini gösterilir
                # (aşağıdaki elif) ama kalıcı/kararlı kimliğe hiç karışmaz.
                if not boyut_guvenilir:
                    if not getattr(track, "vrag_matches", None):
                        track.vrag_matches = matches
                    return

                # Zamansal oylama: VRAG track başına ~saniyede bir çalışıyor, tek
                # karenin sonucu titreyebiliyor (aynı hedef için art arda farklı
                # modeller — örn. F-16→WZ-7→F-4E→WZ-7). Ham en-son sonucu doğrudan
                # göstermek yerine, son VRAG_VOTE_WINDOW aramanın en sık tekrar eden
                # top-1 modelini gösteriyoruz (VLM tarafındaki TrackVoteAggregator
                # ile aynı mantık) — titreme azalır, gerçekten baskın olan cevaba
                # yakınsama ihtimali artar.
                if not hasattr(track, "vrag_history"):
                    track.vrag_history = deque(maxlen=VRAG_VOTE_WINDOW)
                track.vrag_history.append(matches)

                from collections import Counter
                top1_adlari = [m[0]["model"] for m in track.vrag_history if m]
                counts = Counter(top1_adlari)
                secilen_model, oy_sayisi = counts.most_common(1)[0]
                toplam_oy = len(top1_adlari)
                oy_orani = oy_sayisi / toplam_oy

                # BUG-FIX ("her şeye X diyor" + "VRAG çok ani karar değiştiriyor"):
                # basit %50 çoğunluk tek başına, pencere büyütülse bile, ufak bir
                # kayma anında onaylı kimliği başka bir modele kaydırabiliyordu -
                # bu da VLM/LLM'in "2 ardışık aynı kimlik" kilidini (bkz.
                # _confirm_stable_vlm_hash) hiç sağlanamaz hale getiriyordu.
                # Artık HİSTEREZİS var: zaten onaylı bir model varsa, YENİ bir
                # modelin onu devirmesi için sadece önde olması yetmiyor, oy
                # oranı farkının da VRAG_SWITCH_MARGIN'i (kullanıcı tercihiyle
                # %5) geçmesi gerekiyor - küçük gürültüde onaylı kimlik sabit
                # kalır, gerçekten baskın bir değişiklik olursa yine geçiş yapar.
                mevcut_onayli = getattr(track, "vrag_confirmed_model", None)
                mevcut_oran = (counts[mevcut_onayli] / toplam_oy) if mevcut_onayli else 0.0
                kabul_edilebilir = oy_orani >= 0.5 and (
                    mevcut_onayli is None
                    or secilen_model == mevcut_onayli
                    or (oy_orani - mevcut_oran) >= VRAG_SWITCH_MARGIN
                )

                if kabul_edilebilir:
                    # Oylanan modele ait EN SON (en güncel) eşleşme bilgisini kullan
                    secilen_match = next(
                        (m[0] for m in reversed(track.vrag_history) if m and m[0]["model"] == secilen_model),
                        matches[0],
                    )
                    track.vrag_matches = [secilen_match] + matches[1:]
                    track.vrag_confirmed_model = secilen_model
                    # BUG-FIX (kök neden araştırması — "risk analizindeki güven
                    # sayısı sağlıklı değil"): kimlik güveninin karar_servisi'ne
                    # gerçekten ne kadar baskın kazanıldığını yansıtabilmesi için
                    # oy oranı burada saklanıyor (bkz. _async_llm_task).
                    track.vrag_oy_orani = oy_orani
                elif not getattr(track, "vrag_matches", None):
                    track.vrag_matches = matches
        except Exception as e:
            log.warning(f"VRAG error: {e}")
        finally:
            track.vrag_is_running = False
            track.vrag_last_time = time.perf_counter()
            # DENEYSEL (SIRALI_DONGU_MODU): VRAG turunu bitirdi, sırayı VLM'e devret.
            if SIRALI_DONGU_MODU:
                track.dongu_asamasi = "vlm"

    def _async_video_vlm_task(self, track, frames):
        """MVP video-kanıtı çağrısı (bkz. src/vlm/video_evidence.py). Image
        VLM'den tamamen bağımsız kilit/sonuç alanı kullanır — image
        sonucunu beklemez, ezmez. RETRY YOK (video_evidence.py'de bilinçli)."""
        try:
            result = analyze_track_video(frames, track.track_id)
            track.video_vlm_result = result
            if result:
                log.info(
                    f"[VIDEO-VLM] Track {track.track_id} → sınıf={result.get('arac_sinifi')} "
                    f"hareket={result.get('hareket_tanimi')!r} model_ipucu={result.get('model_ipucu')}"
                )
        finally:
            track.is_video_vlm_querying = False

    def _async_vlm_task(self, track, crops, speed, zigzag, threat_score, yolo_class="bilinmeyen", yolo_conf=0.5, video_id=None):
        vrag_matches = getattr(track, "vrag_matches", [])
        should_reset_querying = True
        try:
            # Prensip 1 (Zero-Latency): Enhance (CLAHE vb) arka plan iş ipliğinde asenkron olarak icra edilir
            enhanced_crops = []
            for c in crops:
                enc = self.enhancer.enhance(c)
                if enc is not None:
                    enhanced_crops.append(enc)
            if not enhanced_crops:
                enhanced_crops = crops

            # VLM kendi kilidini kullanır — aynı anda yalnızca bir Ollama çağrısı çalışsın,
            # ama artık VRAG'ı bloklamaz.
            with self._vlm_gate:
                json_result = self.vlm.analyze_target(
                    track_id  = track.track_id,
                    crops     = enhanced_crops,
                    speed     = speed,
                    zigzag    = zigzag,
                    threat    = threat_score,
                    yolo_class= yolo_class,
                    yolo_conf = yolo_conf,
                    vrag_matches = vrag_matches
                )

            if json_result == "IN_FLIGHT":
                should_reset_querying = False
                return

            if json_result is not None:
                track.vlm_done = True   # BUG-2: Başarılı sonuçtan sonra işaretle
                # DENEYSEL (SIRALI_DONGU_MODU): VLM turu bitti, sırayı LLM'e devret.
                # "vlm" olarak kalsaydı, LLM daha işini bitirmeden VLM tetikleme
                # koşulu (dongu_asamasi=="vlm" and not is_vlm_querying) yeniden
                # doğru olur ve VLM gereksiz yere tekrar tetiklenirdi.
                if SIRALI_DONGU_MODU:
                    track.dongu_asamasi = "llm"

                # DENEYSEL (VRAG_GUVEN_ESIGI): VRAG'ın en iyi eşleşmesi eşik ve
                # üzerindeyse, VLM'in kendi bağımsız yorumu yerine VRAG'ın model/
                # ülke bilgisi nihai sonuç olarak kullanılır — kullanıcının
                # istediği VLM-vs-VRAG karşılaştırmasını görünür kılmak için
                # "_guvenilen_kaynak" alanı da ekleniyor.
                # UYARI (kodda not edildi, config.py'de detaylı): Bu oturumda
                # VRAG'ın >= %90 skorla dahi yanlış olabildiği kanıtlanmıştı —
                # bu eşik doğruluğu garanti etmez, sadece kıyaslama sağlar.
                if vrag_matches and vrag_matches[0].get("score", 0.0) >= VRAG_GUVEN_ESIGI:
                    en_iyi_vrag = vrag_matches[0]
                    json_result["hedef_modeli"] = en_iyi_vrag.get("model", json_result.get("hedef_modeli"))
                    if en_iyi_vrag.get("ulke", "Bilinmiyor") != "Bilinmiyor":
                        json_result["ulke_orjini"] = en_iyi_vrag["ulke"]
                    json_result["_guvenilen_kaynak"] = "VRAG"
                else:
                    json_result["_guvenilen_kaynak"] = "VLM"

                # [YENİ] VLM kararı kaydedilir (kuş filtresi için)
                track.vlm_class = json_result.get("arac_sinifi")

                # [YENİ] UI'a tam json göndermek için vlm_result kaydet
                track.vlm_result = json_result

                # BUG-FIX (KRİTİK — LLM hiç tetiklenmeyebiliyordu): LLM tetiklemesi
                # eskiden SADECE process_frame'in "for track in valid_tracks" döngüsünde
                # (yani track hâlâ takip listesindeyken) kontrol ediliyordu. VLM ~13-20sn
                # sürebiliyor; bu süre boyunca hedef KALMAN_SUSPENDED_AGE'den (75 kare,
                # ~3sn) uzun süre tespit edilemezse tracker track'i TAMAMEN SİLİYOR
                # (bkz. tracker.py: dead_ids). Track silinince valid_tracks'te bir daha
                # hiç görünmüyor, ana döngüdeki LLM kontrolü asla bu track'i göremiyor
                # ve LLM sonsuza dek tetiklenmiyordu — sessizce. Artık VLM bittiği anda,
                # aynı thread içinde, track'in ana döngüde hâlâ var olup olmadığına
                # bakmaksızın LLM'i DOĞRUDAN tetikliyoruz. process_frame'deki eski
                # kontrol de duruyor (hash+is_llm_querying ile çift tetiklemeyi zaten
                # engelliyor) — track hâlâ aktifse o da çalışabilir, zararı yok.
                current_vlm_hash = self._vlm_identity_signature(json_result)
                if not getattr(track, "decision_locked", False) and not getattr(track, "is_llm_querying", False) and self._confirm_stable_vlm_hash(
                    track, current_vlm_hash
                ):
                    track.is_llm_querying = True
                    track.last_llm_vlm_hash = current_vlm_hash
                    # BUG-FIX: burada self.video_id'yi TEKRAR okumuyoruz - VLM
                    # analizi (bu fonksiyonun kendisi) saniyeler surebilir, o
                    # sure icinde video degismis olabilir. video_id parametresi
                    # crop'un asil yakalandigi ANDA (_async_vlm_task'in kendisi
                    # sunulurken) yakalanmis olan degerdir - bkz. process_frame.
                    self.executor.submit(self._async_llm_task, track, json_result, video_id)

                # Prompt'tan guven_skoru kaldırılıp tracker/YOLO sistemine devredildiği için
                # JSON'da olmadığında 0% basmamak adına doğrudan sistem skoru kullanılır.
                guven = float(json_result.get("guven_skoru", 0.0))
                if guven > 1.0:
                    guven = guven / 100.0
                if guven <= 0.001:
                    guven = float(yolo_conf)

                tehdit = json_result.get("tehdit_seviyesi", "dusuk")
                # Askeri hedef sınıfları (SİHA, Kamikaze, Askeri Uçak) sistem gereği yüksek tehdit sayılmalı
                hedef_tipi = str(json_result.get("tahmini_hedef_tipi", "")).lower()
                if hedef_tipi in ("siha", "kamikaze", "askeri_ucak") and tehdit in ("dusuk", "yok", "orta"):
                    tehdit = "yuksek"

                tehdit_isareti = {"yuksek": "[YUKSEK]", "orta": "[ORTA]", "dusuk": "[DUSUK]", "yok": "[YOK]"}.get(tehdit, "[?]")

                # Prompt'ta gidiş yönünün tahmini VLM'den silindiği için takipçinin (Tracker) hız vektöründen bulunur
                vx, vy = track.smooth_velocity
                if abs(vx) > 0.5 or abs(vy) > 0.5:
                    yön = ("Saga" if vx > 0 else "Sola")
                    dikey = (" / Yukseliyor (Uzaga)" if vy < 0 else " / Alcaliyor (Yakina)")
                    gidis_str = yön + dikey
                else:
                    gidis_str = json_result.get("gidis_yeri", "Seyir Halinde")

                uyarilar = []
                if json_result.get("_celiski_var"):
                    uyarilar.append("! CELISKI: gorsel_analiz metni arac_sinifi ile uyusmuyor")
                # WARN-2: _dusuk_guven hiçbir zaman True set edilmedi — kontrol kaldırıldı
                uyari_satiri = f"  Uyari      : {' | '.join(uyarilar)}\n" if uyarilar else ""

                if not json_result.get("gorsel_analiz") or len(str(json_result.get("gorsel_analiz", ""))) < 3:
                    json_result["gorsel_analiz"] = "Gorsel analiz basarisiz oldu"

                log.info(
                    f"\n{'='*55}\n"
                    f"  [VLM ANALIZ] -> Track ID: {track.track_id}\n"
                    f"{'='*55}\n"
                    f"  Sinif      : {json_result.get('arac_sinifi', '?')}\n"
                    f"  Tehdit     : {tehdit_isareti} {tehdit.upper()}\n"
                    f"  Tip        : {json_result.get('tahmini_hedef_tipi', '?').upper()}\n"
                    f"  Ülke       : {json_result.get('ulke_orjini', 'Bilinmiyor')}\n"
                    f"  Model      : {json_result.get('hedef_modeli', 'Bilinmiyor')}\n"
                    f"  Gidiş Yeri : {gidis_str}\n"
                    f"  Görsel     : {json_result.get('gorsel_analiz', '?')}\n"
                    f"  Güven      : {guven:.0%}\n"
                    f"{uyari_satiri}"
                    f"  [YOLO: {yolo_class} @ {yolo_conf:.0%}]\n"
                    f"{'='*55}"
                )
            else:
                log.warning(f"[VLM] Track {track.track_id}: Geçerli analiz döndürülemedi.")
                # DENEYSEL (SIRALI_DONGU_MODU): Geçerli sonuç yok, LLM'e devredecek
                # bir şey olmadığı için turu burada VRAG'a geri sarıyoruz —
                # yoksa dongu_asamasi "vlm"de takılı kalıp cycle durur.
                if SIRALI_DONGU_MODU:
                    track.dongu_asamasi = "vrag"

        except Exception as e:
            log.error(f"[VLM] Asenkron Hata (Track {track.track_id}): {e}")
            if SIRALI_DONGU_MODU:
                track.dongu_asamasi = "vrag"
        finally:
            if should_reset_querying:
                track.is_vlm_querying = False

    def _async_llm_task(self, track, vlm_result, video_id):
        import requests
        # BUG-FIX (kök neden araştırması — "LLM yanıt vermiyor"): last_llm_vlm_hash
        # bu görev SUNULURKEN (aşağıdaki iki tetikleme noktasında) yazılıyor,
        # BAŞARIYA bakılmaksızın. Yani adapter/analyze çağrısı bir kere
        # başarısız olursa (ağ hatası, 5xx, zaman aşımı — tam olarak biraz önce
        # düzelttiğimiz 500 hatası gibi), _confirm_stable_vlm_hash o kimlik
        # imzasını "zaten denendi" sanıp track'in KALAN ÖMRÜ boyunca BİR DAHA
        # HİÇ yeniden denemiyordu - tek bir geçici hata, o hedef için nihai
        # kararı kalıcı olarak imkansız kılıyordu. Artık başarısızlıkta
        # last_llm_vlm_hash sıfırlanıyor; aynı kimlik yeniden 2 kez ardışık
        # doğrulanırsa (bir sonraki VLM turlarında) tekrar denenebiliyor.
        basarili = False
        try:
            # 1. Adapt Raw VLM
            allowed_vlm_keys = {
                "arac_sinifi", "tehdit_seviyesi", "tahmini_hedef_tipi", 
                "ulke_orjini", "hedef_modeli", "gorsel_analiz", 
                "_celiski_var", "_vote_count", "video_events"
            }
            cleaned_vlm_result = {k: v for k, v in vlm_result.items() if k in allowed_vlm_keys or str(k).startswith("_")}

            # BUG-FIX: VLM kendi "ulke_orjini"nı çoğunlukla "Bilinmiyor" veriyor (kırpılmış
            # görüntüden ülke tahmini zor). VRAG'ın kendi referans metadata'sında (artık
            # engine.py'de zenginleştirilmiş) bilinen bir ülke varsa ve eşleşme yeterince
            # güvenliyse (VRAG_MIN_SCORE üstü, zaten filtrelenmiş), bunu yedek olarak kullan
            # — LLM'deki köken tutarlılık kontrolü (VLM ülke hipotezi belirlenemedi uyarısı)
            # boş yere insan incelemesi istemesin.
            vrag_matches = getattr(track, "vrag_matches", [])
            if (
                cleaned_vlm_result.get("ulke_orjini", "Bilinmiyor") in (None, "", "Bilinmiyor")
                and vrag_matches
                and vrag_matches[0].get("ulke", "Bilinmiyor") != "Bilinmiyor"
            ):
                cleaned_vlm_result["ulke_orjini"] = vrag_matches[0]["ulke"]

            # BUG-FIX (kök neden araştırması — "risk analizindeki güven sayısı
            # sağlıklı değil"): karar_servisi'nin RawVLMOutput'u "_" ile başlayan
            # her alanı yardımcı metadata olarak kabul edip helper_metadata()
            # üzerinden LLM'e taşıyor - kod tarafında yeni bir alan tanımlamaya
            # gerek yok. VRAG'ın oy oranını (kimlik ne kadar baskın kazanıldı)
            # buradan taşıyoruz; karar_servisi tarafında upstream_vlm_adapter.py
            # bunu uncertainty_level'i zenginleştirmek için okuyor.
            vrag_oy_orani = getattr(track, "vrag_oy_orani", None)
            if vrag_oy_orani is not None:
                cleaned_vlm_result["_vrag_oy_orani"] = round(float(vrag_oy_orani), 3)

            current_time_offset = float(time.time() % 10000)
            # BUG-FIX (kök neden araştırması — "guven_skoru aslında YOLO tespit
            # güveniydi, kimlik güveni değil"): VLM'in prompt'undan guven_skoru
            # kaldırıldığı için (bkz. aşağıdaki json_result.get("guven_skoru"))
            # buraya eskiden doğrudan track.confidence (YOLO/tracker tespit
            # güveni — "burada bir hava aracı var" güveni) gönderiliyordu, "bu
            # kesinlikle X modeli" güveniyle hiç ilgisi yok. Artık VRAG'ın asıl
            # kimlik sinyali kullanılıyor: en iyi eşleşme skoru İLE oy oranının
            # ZAYIF olanı (ikisi de yüksek değilse güven abartılmasın). VRAG
            # hiç eşleşme üretmediyse (devre dışı/arıza) eski davranışa
            # (track.confidence) geri dönülür.
            if vrag_matches and vrag_oy_orani is not None:
                kimlik_guveni = min(float(vrag_matches[0].get("score", 0.0)), float(vrag_oy_orani))
            else:
                kimlik_guveni = float(track.confidence)
            kimlik_guveni = max(0.0, min(1.0, kimlik_guveni))
            adapter_payload = {
                "raw_vlm": cleaned_vlm_result,
                "video_id": video_id,
                "track_id": str(track.track_id),
                "first_seen_offset_seconds": current_time_offset,
                "last_seen_offset_seconds": current_time_offset + 1.0,
                "visual_confidence": kimlik_guveni
            }
            res = requests.post("http://127.0.0.1:8001/api/v1/adapters/raw-vlm", json=adapter_payload, timeout=5.0)
            if res.status_code == 200:
                analyze_req = res.json().get("analyze_request")
                if analyze_req:
                    # 2. Analyze
                    analyze_res = requests.post(
                        "http://127.0.0.1:8001/api/v1/events/analyze?response_format=teknofest_spec",
                        json=analyze_req,
                        timeout=30.0
                    )
                    if analyze_res.status_code == 200:
                        track.llm_result = analyze_res.json()
                        # BUG-FIX (kullanıcı isteği — "kesin karara varana kadar
                        # stabil model gözüksün"): bu track için artık kesin bir
                        # karar var - VRAG/VLM/LLM bir daha tetiklenmeyecek (bkz.
                        # process_frame'deki karar_kilitli kontrolleri), ekranda
                        # gösterilen kimlik ve zaman damgası bundan sonra sabit
                        # kalır.
                        track.decision_locked = True
                        basarili = True
                        log.info(f"[LLM] Track {track.track_id} için Stratejik Karar alındı — kimlik kilitlendi.")
                    else:
                        log.warning(f"[LLM] Analyze Error: {analyze_res.text}")
            else:
                log.warning(f"[LLM] Adapter Error: {res.text}")
        except Exception as e:
            log.error(f"[LLM] Asenkron Hata: {e}")
        finally:
            if not basarili:
                track.last_llm_vlm_hash = None
            track.is_llm_querying = False
            # DENEYSEL (SIRALI_DONGU_MODU): Tur tamamlandı, VRAG'a yeni crop ile geri dön.
            if SIRALI_DONGU_MODU:
                track.dongu_asamasi = "vrag"