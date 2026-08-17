# ============================================================
# tracker.py - ByteTrack TabanlÄ± Ã‡ok Hedef Takip Sistemi
# ============================================================

import numpy as np
import time
import logging
import cv2
import threading
import concurrent.futures
from typing import Dict
from src.config import (
    KALMAN_MAX_AGE, KALMAN_MIN_HITS, KALMAN_SUSPENDED_AGE,
    CLASS_VOTE_HISTORY, CLASS_PRIORITY_THRESHOLD, CLASS_VOTE_MIN_CONF,
    MIN_SPEED_PX_S, MIN_SPEED_CHECK_HITS, MAX_PLAUSIBLE_JUMP_PX,
    BYTETRACK_MIN_CONF, BYTETRACK_TRACK_THRESH, BYTETRACK_MATCH_THRESH,
    KALMAN_PROCESS_NOISE, KALMAN_MEASURE_NOISE,
    VLM_CROP_MIN_CONF, VLM_CROP_BUFFER_SIZE, VLM_CROP_CONTEXT_RATIO,
    EDGE_MARGIN_PX, EDGE_MAX_FRAMES, TYPE_LABEL_SMOOTH_WINDOW,
    MIN_WORLD_PATH_PX_PER_S, WORLD_PATH_WINDOW_S, MAX_OBJECT_AREA_RATIO,
)
from src.detection.slicer import RawDetection
from src.tracking.camera_motion import CameraMotionCompensator

log = logging.getLogger(__name__)

_VALID_CLASS_IDS = {0, 1, 2}


def _is_sane_detection(x1, y1, x2, y2, conf, cls) -> bool:
    vals = (x1, y1, x2, y2, conf)
    if not all(np.isfinite(v) for v in vals):
        return False
    if (x2 - x1) <= 0 or (y2 - y1) <= 0:
        return False
    if cls not in _VALID_CLASS_IDS:
        return False
    return True


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# TRACK: GÃ¼ncellenmiÅŸ SÄ±nÄ±f
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
class Track:
    def __init__(self, track_id: int, x1, y1, x2, y2, conf: float, cls: int, fps: float = 30.0):
        self.track_id   = int(track_id)
        # BUG-FIX: smooth_velocity eskiden sabit fps=30.0 varsayÄ±yordu â€” kaynak
        # video/kamera 30 FPS'ten farklÄ±ysa (Ã¶r. 25 veya 60) hÄ±z (px/s), tehdit
        # skoru ve VLM tetiklemesi sistematik olarak yanlÄ±ÅŸ hesaplanÄ±yordu.
        # ArtÄ±k run.py'nin algÄ±ladÄ±ÄŸÄ± gerÃ§ek kaynak FPS'i uÃ§tan uca buraya kadar
        # iletiliyor (bkz. MultiTargetTracker(fps=...) ve pipeline.py).
        self._fps       = max(1.0, float(fps))
        self.bbox       = np.array([x1, y1, x2, y2], dtype=np.float32)
        self.confidence = float(conf)
        self.class_id   = int(cls)
        self.hits       = 1

        # BUG-FIX (KRÄ°TÄ°K â€” "dev kutu"): kalman_bbox() Ã§izim iÃ§in kullanÄ±lan
        # statePost boyutunun MAX_OBJECT_AREA_RATIO'yu aÅŸÄ±p aÅŸmadÄ±ÄŸÄ±nÄ± kontrol
        # edebilmesi iÃ§in son bilinen gerÃ§ek frame boyutunu burada saklÄ±yoruz.
        # update() her karede fw_fr/fh_fr ile bunu tazeler.
        self._last_fw = 1920.0
        self._last_fh = 1080.0
        self.suspended  = False
        # BUG-FIX (kutu havada geziniyor): kaÃ§ ardÄ±ÅŸÄ±k karedir GERÃ‡EK bir
        # tespit almadan salt Kalman ekstrapolasyonuyla "coasting" yapÄ±ldÄ±ÄŸÄ±nÄ±
        # sayar. pipeline.py bunu SUSPENDED_DRAW_GRACE_FRAMES ile karÅŸÄ±laÅŸtÄ±rÄ±p
        # uzun sÃ¼redir kayÄ±p olan track'i gÃ¼venle Ã§izmeyi bÄ±rakÄ±r.
        self.suspended_streak = 0
        self.last_vlm_time  = 0.0
        self.is_vlm_querying = False
        self.vlm_done        = False
        self.vlm_class       = None  # [YENÄ°] VLM SÄ±nÄ±f Tahmini
        
        # [YENÄ°] Uzaktaki hedef Ã¶zellikleri
        self.is_far_target = False
        self.far_target_frames = 0
        self.is_confirmed = False
        self.confidence_history = []
        self.first_seen_frame = time.time()
        
        # Kenarda takÄ±lÄ± kalma sayacÄ± (yaprak filtresi iÃ§in)
        self.edge_touch_frames = 0

        # BUG-FIX (video'ya gÃ¶re deÄŸiÅŸen kutu titremesi): Kalman'Ä±n "ani
        # manevra" moduna (bkz. update()) TEK karelik gÃ¼rÃ¼ltÃ¼lÃ¼ bir tespitle
        # deÄŸil, ancak 2 ardÄ±ÅŸÄ±k kare Ã¼st Ã¼ste eÅŸik aÅŸÄ±nca girmesi iÃ§in sayaÃ§.
        self._maneuver_streak = 0

        # BUG-FIX (arada kuÅŸ olarak iÅŸaretleme titremesi): classify_bird_vs_aircraft()
        # Ã§Ä±ktÄ±sÄ±nÄ±n son birkaÃ§ karesini tutar; nihai rozet bu pencerenin
        # Ã§oÄŸunluk oyuna gÃ¶re belirlenir (bkz. classify_bird_vs_aircraft()).
        self._type_label_history: list[tuple[bool, float]] = []

        # SÄ±nÄ±f oylamasÄ±
        self._class_history: list[tuple[int, float]] = [(int(cls), float(conf))]

        # En/Boy OranÄ± (Aspect Ratio) geÃ§miÅŸi - KuÅŸ kanat Ã§Ä±rpma tespiti iÃ§in
        w = max(1.0, float(x2 - x1))
        h = max(1.0, float(y2 - y1))
        self._ar_history: list[float] = [w / h]

        # Pozisyon geÃ§miÅŸi â€” BUG-FIX: (cx, cy, frame_idx) formatÄ±
        # smooth_velocity'de np.arange yerine gerÃ§ek frame aralÄ±ÄŸÄ± kullanÄ±lÄ±r,
        # oklÃ¼zyon sonrasÄ± fiziksel olarak imkansÄ±z hÄ±z spike'larÄ±nÄ± Ã¶nler.
        cx, cy = self._center()
        self._frame_idx: int = 0
        self._pos_history: list[tuple[float, float, int]] = [(cx, cy, 0)]
        
        # Scale-Static Filtresi iÃ§in (HUD/Watermark reddi): cx, cy, w, h, frame_idx
        w = max(1.0, float(x2 - x1))
        h = max(1.0, float(y2 - y1))
        self._screen_history: list[tuple[float, float, float, float, int]] = [(cx, cy, w, h, 0)]
        
        # Solid-Body (KatÄ± GÃ¶vde) Doluluk OranÄ± geÃ§miÅŸi (bilgi amaÃ§lÄ±)
        self.fill_ratio_history: list[float] = []

        self.zigzag_score: float = 0.0

        # EMA hÄ±z
        self._ema_vel: np.ndarray = np.array([0.0, 0.0])
        self._ema_ready: bool = False
        self.visual_heading = None
        
        # VLM iÃ§in crop buffer ve thread gÃ¼venliÄŸi kilidi
        self._crop_buffer: list[tuple[np.ndarray, float, float]] = []
        self._buffer_lock = threading.Lock()

        # Durum: [merkez_x, merkez_y, hÄ±z_x, hÄ±z_y, geniÅŸlik, yÃ¼kseklik].
        # Bu, eski "proxy" nesnesinin aksine okluzyonda gerÃ§ek konum tahmini Ã¼retir.
        cx, cy = self._center()
        self._kf = cv2.KalmanFilter(6, 4)
        self._kf.transitionMatrix = np.array([
            [1, 0, 1, 0, 0, 0], [0, 1, 0, 1, 0, 0],
            [0, 0, 1, 0, 0, 0], [0, 0, 0, 1, 0, 0],
            [0, 0, 0, 0, 1, 0], [0, 0, 0, 0, 0, 1],
        ], dtype=np.float32)
        self._kf.measurementMatrix = np.array([
            [1, 0, 0, 0, 0, 0], [0, 1, 0, 0, 0, 0],
            [0, 0, 0, 0, 1, 0], [0, 0, 0, 0, 0, 1],
        ], dtype=np.float32)
        self._kf.processNoiseCov = np.eye(6, dtype=np.float32) * KALMAN_PROCESS_NOISE
        self._kf.measurementNoiseCov = np.eye(4, dtype=np.float32) * KALMAN_MEASURE_NOISE
        self._kf.errorCovPost = np.eye(6, dtype=np.float32)
        self._kf.statePost = np.array([[cx], [cy], [0], [0], [self.bbox[2] - self.bbox[0]], [self.bbox[3] - self.bbox[1]]], dtype=np.float32)
        self._predicted_bbox = self.bbox.copy()
        self._predicted_this_frame = False
        # Kutu kaymasÄ± Ã¶nleyici EMA bbox (gÃ¶rselleÅŸtirme iÃ§in)
        self._ema_bbox: np.ndarray = self.bbox.copy()

    def merge_from(self, old: "Track"):
        self.hits = max(self.hits, old.hits)
        
        # BUG-FIX (KRÄ°TÄ°K â€” oklÃ¼zyon sonrasÄ± lag/jitter): Eski track'in Kalman
        # state'ini (statePost, errorCovPost) devral. Eskiden _kf hiÃ§ kopyalanmÄ±yordu,
        # yeni track sÄ±fÄ±r hÄ±zla baÅŸlÄ±yordu â†’ ani lag ve sÄ±Ã§rama.
        try:
            self._kf.statePost = old._kf.statePost.copy()
            self._kf.errorCovPost = old._kf.errorCovPost.copy()
            self._predicted_bbox = old._predicted_bbox.copy()
        except Exception:
            pass
        
        # [YENÄ°] Uzaktaki hedef Ã¶zelliklerini birleÅŸtir
        self.is_far_target = self.is_far_target or old.is_far_target
        self.far_target_frames = max(self.far_target_frames, old.far_target_frames)
        self.is_confirmed = self.is_confirmed or old.is_confirmed
        
        merged_classes = old._class_history + self._class_history
        self._class_history = merged_classes[-CLASS_VOTE_HISTORY:]

        self._pos_history = (old._pos_history + self._pos_history)[-20:]
        self._frame_idx = max(self._frame_idx, old._frame_idx)

        if old._ema_ready:
            self._ema_vel = old._ema_vel
            self._ema_ready = True
        if self.visual_heading is None:
            self.visual_heading = old.visual_heading

        with self._buffer_lock:
            with getattr(old, '_buffer_lock', threading.Lock()):
                self._crop_buffer = old._crop_buffer + self._crop_buffer
                self._crop_buffer = sorted(self._crop_buffer, key=lambda c: c[1], reverse=True)[:VLM_CROP_BUFFER_SIZE]
        self.last_vlm_time = max(self.last_vlm_time, old.last_vlm_time)
        self.vlm_done = self.vlm_done or old.vlm_done
        self.is_vlm_querying = self.is_vlm_querying or old.is_vlm_querying
        if old.vlm_class is not None:
            self.vlm_class = old.vlm_class

        # BUG-FIX (KRİTİK — birleşimde sonuç kayboluyordu): vlm_done yukarıda
        # taşınıyordu ama vlm_result/llm_result/vrag_matches HİÇ taşınmıyordu.
        # Sonuç: okluzyon sonrası aynı ID'ye birleşen bir track, vlm_done=True
        # (yeni VLM çağrısını engelliyor) ama vlm_result=None (LLM tetikleme
        # kapısı "vlm_done and vlm_result" hiç açılmıyor) durumuna düşüyor —
        # o track için bir daha asla VLM/LLM sonucu üretilemiyordu.
        if getattr(old, "vlm_result", None) is not None and getattr(self, "vlm_result", None) is None:
            self.vlm_result = old.vlm_result
        if getattr(old, "llm_result", None) is not None and getattr(self, "llm_result", None) is None:
            self.llm_result = old.llm_result
        if getattr(old, "vrag_matches", None) and not getattr(self, "vrag_matches", None):
            self.vrag_matches = old.vrag_matches
        if getattr(old, "last_llm_vlm_hash", None) is not None and getattr(self, "last_llm_vlm_hash", None) is None:
            self.last_llm_vlm_hash = old.last_llm_vlm_hash
        self.is_llm_querying = getattr(self, "is_llm_querying", False) or getattr(old, "is_llm_querying", False)


        self._ar_history = (old._ar_history + self._ar_history)[-15:]
        self._type_label_history = (
            getattr(old, "_type_label_history", []) + self._type_label_history
        )[-TYPE_LABEL_SMOOTH_WINDOW:]
        self.fill_ratio_history = (
            getattr(old, "fill_ratio_history", []) + self.fill_ratio_history
        )[-10:]
        self._screen_history = (
            getattr(old, "_screen_history", []) + self._screen_history
        )[-45:]
        self.edge_touch_frames = max(self.edge_touch_frames, old.edge_touch_frames)
        # Okluzyon sonrasÄ± kutu zÄ±plamasÄ±nÄ± Ã¶nle: eski EMA bbox'Ä± devral
        self._ema_bbox = old._ema_bbox.copy()

    def shift_history(self, dx: float, dy: float):
        self._pos_history = [(x + dx, y + dy, fi) for x, y, fi in self._pos_history]
        self._kf.statePost[0, 0] += dx
        self._kf.statePost[1, 0] += dy
        self._predicted_bbox[[0, 2]] += dx
        self._predicted_bbox[[1, 3]] += dy

    def predict(self) -> np.ndarray:
        if not self._predicted_this_frame:
            cx, cy, _, _, w, h = self._kf.predict().reshape(-1)
            w, h = max(1.0, float(w)), max(1.0, float(h))
            self._predicted_bbox = np.array([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], dtype=np.float32)
            self._predicted_this_frame = True
        return self._predicted_bbox

    def update(self, x1, y1, x2, y2, conf: float, cls: int, fw: int = 1920, fh: int = 1080):
        self.predict()
        self._last_fw = float(fw)
        self._last_fh = float(fh)
        self.bbox       = np.array([x1, y1, x2, y2], dtype=np.float32)
        self.confidence = float(conf)
        self.class_id   = int(cls)
        self.hits      += 1
        # BUG-FIX: gerÃ§ek bir tespit geldi â†’ coasting/suspended sayacÄ± sÄ±fÄ±rlanÄ±r.
        self.suspended_streak = 0

        # â”€â”€ Adaptive Kalman Filtresi (Manevra Stabilizasyonu) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        # Nesne ani yÃ¶n deÄŸiÅŸtirdiÄŸinde (keskin manevra) doÄŸrusal tahmin ile gerÃ§ek bbox
        # arasÄ± mesafe (residual/innovation) artar. Geleneksel sabit kovaryanslÄ± Kalman,
        # geride kalÄ±r (gecikme) veya sÄ±Ã§rar.
        # Ã‡Ã¶zÃ¼m: Innovation hatasÄ± bÃ¼yÃ¼nce hÄ±z sÃ¼reÃ§ gÃ¼rÃ¼ltÃ¼sÃ¼nÃ¼ (Q) dinamiÄŸe baÄŸlayÄ±p
        # katlayarak (35x) artÄ±r ve Ã¶lÃ§Ã¼me gÃ¼veni artÄ±r! BÃ¶ylece manevralarda anÄ±nda dÃ¶ner.
        try:
            pred_cx = float(self._kf.statePre[0, 0])
            pred_cy = float(self._kf.statePre[1, 0])
            meas_cx, meas_cy = (x1 + x2) * 0.5, (y1 + y2) * 0.5
            dist_err = float(np.hypot(meas_cx - pred_cx, meas_cy - pred_cy))
            box_max = max(10.0, float(x2 - x1), float(y2 - y1))

            # BUG-FIX (video'ya gÃ¶re deÄŸiÅŸen kutu titremesi): Eskiden TEK
            # karelik bir sapma (dist_err/box_max > 0.35) bile anÄ±nda "ani
            # manevra" moduna geÃ§ip Q'yu 35x aÃ§Ä±yor, R'yi 5x gÃ¼venilir
            # kÄ±lÄ±yordu â€” yani filtre o TEK gÃ¼rÃ¼ltÃ¼lÃ¼ Ã¶lÃ§Ã¼me neredeyse ham
            # geÃ§iÅŸ (pass-through) yapÄ±yordu. KÃ¼Ã§Ã¼k/uzak hedef kutularÄ±nda
            # birkaÃ§ pikselik YOLO gÃ¼rÃ¼ltÃ¼sÃ¼ bile kolayca %35'i aÅŸÄ±yor; bu
            # da videonun gÃ¼rÃ¼ltÃ¼ seviyesine gÃ¶re kutunun ya Ã§ok pÃ¼rÃ¼zsÃ¼z
            # (temiz video) ya da sÃ¼rekli manevra modunda titrek (gÃ¼rÃ¼ltÃ¼lÃ¼
            # video) gÃ¶rÃ¼nmesine yol aÃ§Ä±yordu.
            # Ã‡Ã–ZÃœM: (1) Mutlak piksel tabanÄ± â€” Ã§ok kÃ¼Ã§Ã¼k mutlak kaymalar
            # (gÃ¼rÃ¼ltÃ¼) asla "manevra" sayÄ±lmaz. (2) Manevra moduna giriÅŸ
            # iÃ§in 2 ardÄ±ÅŸÄ±k kare ÅŸartÄ± (debounce) â€” gerÃ§ek manevralar
            # birkaÃ§ kare sÃ¼rer, tek karelik gÃ¼rÃ¼ltÃ¼ artÄ±k tetiklemez.
            # Ã‡Ä±kÄ±ÅŸta (dÃ¼z uÃ§uÅŸa dÃ¶nÃ¼ÅŸte) hÃ¢lÃ¢ anÄ±nda normale dÃ¶nÃ¼lÃ¼r, lag
            # eklenmez.
            residual_ratio = dist_err / box_max
            is_residual_significant = residual_ratio > 0.35 and dist_err > 8.0

            self._maneuver_streak = (
                min(self._maneuver_streak + 1, 99) if is_residual_significant else 0
            )

            if self._maneuver_streak >= 2:
                # Ani manevra doÄŸrulandÄ± (2. ardÄ±ÅŸÄ±k kare) â†’ Q hÄ±z varyanslarÄ±nÄ± aÃ§
                self._kf.processNoiseCov[2, 2] = KALMAN_PROCESS_NOISE * 35.0
                self._kf.processNoiseCov[3, 3] = KALMAN_PROCESS_NOISE * 35.0
                self._kf.measurementNoiseCov = np.eye(4, dtype=np.float32) * (KALMAN_MEASURE_NOISE * 0.2)
            else:
                # DÃ¼z uÃ§uÅŸ VEYA tek karelik gÃ¼rÃ¼ltÃ¼ â†’ titreÅŸimi (jitter)
                # sÃ¶nÃ¼mlemek iÃ§in standart gÃ¼rÃ¼ltÃ¼ye dÃ¶n
                self._kf.processNoiseCov[2, 2] = KALMAN_PROCESS_NOISE
                self._kf.processNoiseCov[3, 3] = KALMAN_PROCESS_NOISE
                self._kf.measurementNoiseCov = np.eye(4, dtype=np.float32) * KALMAN_MEASURE_NOISE
        except Exception:
            pass

        self._kf.correct(np.array([[(x1 + x2) / 2], [(y1 + y2) / 2], [x2 - x1], [y2 - y1]], dtype=np.float32))
        self._predicted_bbox = self.bbox.copy()

        # â”€â”€ UyarlamalÄ± EMA bbox (gÃ¶rselleÅŸtirme) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        # Sorun: sabit Î±=0.35 â†’ ani manevrada kutu 3-5 frame geride kalÄ±r,
        #        sonra sÄ±Ã§rar. KullanÄ±cÄ± "kutu yerinde kalÄ±yor, uÃ§ak gidiyor" der.
        # Ã‡Ã¶zÃ¼m: Merkez kaymasÄ± bÃ¼yÃ¼dÃ¼kÃ§e Î± artar â†’ kutu anÄ±nda takip eder;
        #        kÃ¼Ã§Ã¼k titremeye karÅŸÄ± ise Î± kÃ¼Ã§Ã¼k kalÄ±r â†’ pÃ¼rÃ¼zsÃ¼z gÃ¶rÃ¼nÃ¼r.
        #
        # Î± eÅŸleme (60px eÅŸik tipik bir frame sÄ±Ã§ramasÄ±nÄ± kapsar):
        #   0  px kayma â†’ Î± = 0.20  (hafif jitter bastÄ±rma)
        #  30  px kayma â†’ Î± â‰ˆ 0.50  (orta tepki)
        #  60  px kayma â†’ Î± = 1.00  (anÄ±nda yapÄ±ÅŸ â€” ani manevra)
        # >60  px kayma â†’ Î± = 1.00  (hep anÄ±nda)
        _new_cx = (x1 + x2) * 0.5
        _new_cy = (y1 + y2) * 0.5
        _ema_cx = (self._ema_bbox[0] + self._ema_bbox[2]) * 0.5
        _ema_cy = (self._ema_bbox[1] + self._ema_bbox[3]) * 0.5
        _disp   = float(np.hypot(_new_cx - _ema_cx, _new_cy - _ema_cy))
        # BUG-FIX (Bbox kaymasÄ± tamamen Ã§Ã¶zÃ¼ldÃ¼): YumuÅŸatma (smoothing)
        # Ã¶zellikle hedef kÃ¼Ã§Ã¼k ve Ã§ok hÄ±zlÄ±yken bbox'Ä± 1-2 frame geride bÄ±rakÄ±yordu.
        # SavaÅŸan Ä°HA'da kutunun doÄŸruluÄŸu pÃ¼rÃ¼zsÃ¼zlÃ¼ÄŸÃ¼nden daha Ã¶nemlidir.
        # EMA tamamen iptal edildi (alfa=1.0). Kutu anÄ±nda, %100 hedefe yapÄ±ÅŸacak.
        _alpha_box = 1.0
        self._ema_bbox = _alpha_box * self.bbox + (1.0 - _alpha_box) * self._ema_bbox

        # Uzaktaki hedef tespiti â€” gerÃ§ek frame boyutunu kullan (BUG-12 dÃ¼zeltmesi)
        # Eski sabit eÅŸik (640*640*0.002=819pxÂ²) frame boyutundan baÄŸÄ±msÄ±zdÄ± (4K'da yanlÄ±ÅŸtÄ±).
        from src.config import FAR_TARGET_AREA_RATIO
        far_area_thresh = fw * fh * FAR_TARGET_AREA_RATIO
        bbox_area = (x2 - x1) * (y2 - y1)
        if bbox_area < far_area_thresh:
            self.is_far_target = True
            self.far_target_frames += 1
        else:
            self.is_far_target = False
            self.far_target_frames = 0
            
        # Kenar takÄ±lÄ± kalma kontrolÃ¼ (yaprak/dal filtresi iÃ§in)
        # fw/fh gerÃ§ek frame boyutunu kullanÄ±r â€” sabit 1920x1080 deÄŸil!
        if x1 < EDGE_MARGIN_PX or y1 < EDGE_MARGIN_PX or x2 > (fw - EDGE_MARGIN_PX) or y2 > (fh - EDGE_MARGIN_PX):
            self.edge_touch_frames += 1
        else:
            self.edge_touch_frames = 0

        # GÃ¼ven geÃ§miÅŸini gÃ¼ncelle
        self.confidence_history.append(conf)
        if len(self.confidence_history) > 10:
            self.confidence_history.pop(0)

        # Onaylama kontrolÃ¼ (basitleÅŸtirildi)
        if self.hits >= KALMAN_MIN_HITS:
            self.is_confirmed = True

        # Aspect ratio geÃ§miÅŸini gÃ¼ncelle (Kanat Ã§Ä±rpma filtresi iÃ§in)
        w = max(1.0, float(x2 - x1))
        h = max(1.0, float(y2 - y1))
        self._ar_history.append(w / h)
        if len(self._ar_history) > 15:
            self._ar_history.pop(0)

        # SÄ±nÄ±f oylamasÄ±
        if conf >= CLASS_VOTE_MIN_CONF:
            self._class_history.append((int(cls), float(conf)))
            if len(self._class_history) > CLASS_VOTE_HISTORY:
                self._class_history.pop(0)

        cx, cy = self._center()

        is_outlier_jump = False
        if self._pos_history:
            last_cx, last_cy, _ = self._pos_history[-1]
            jump = float(np.hypot(cx - last_cx, cy - last_cy))
            if jump > MAX_PLAUSIBLE_JUMP_PX:
                is_outlier_jump = True
                log.warning(
                    f"Track {self.track_id}: fiziksel olarak imkansÄ±z sÄ±Ã§rama "
                    f"({jump:.0f}px > {MAX_PLAUSIBLE_JUMP_PX:.0f}px) â€” atlandÄ±."
                )

        if not is_outlier_jump:
            self._frame_idx += 1
            self._pos_history.append((cx, cy, self._frame_idx))
            if len(self._pos_history) > 20:
                self._pos_history.pop(0)

            # Ekran konum ve boyut (scale) geÃ§miÅŸini gÃ¼ncelle
            w = max(1.0, float(x2 - x1))
            h = max(1.0, float(y2 - y1))
            self._screen_history.append((cx, cy, w, h, self._frame_idx))
            if len(self._screen_history) > 45:
                self._screen_history.pop(0)

            self._update_zigzag_score()

            raw_vel = self.smooth_velocity
            if not self._ema_ready:
                self._ema_vel   = raw_vel
                self._ema_ready = True
            else:
                alpha          = 0.25
                self._ema_vel  = alpha * raw_vel + (1.0 - alpha) * self._ema_vel

    @property
    def is_flapping(self) -> bool:
        """Kanat Ã§Ä±rpma filtresi â€” ÅŸu anda devre dÄ±ÅŸÄ± (alan mevcut).
        SavaÅŸ uÃ§aÄŸÄ±/Ä°HA manevra yaptÄ±ÄŸÄ±nda en/boy oranÄ± deÄŸiÅŸtiÄŸinden
        bu filtre gerÃ§ek uÃ§aklarÄ± hatalÄ± yere KUÅ sanÄ±p eliyordu."""
        return False

    @property
    def voted_class_id(self) -> int:
        if not self._class_history:
            return self.class_id

        weighted_totals: Dict[int, float] = {}
        total_weight = 0.0
        for cls_i, conf_i in self._class_history:
            weighted_totals[cls_i] = weighted_totals.get(cls_i, 0.0) + conf_i
            total_weight += conf_i

        if total_weight <= 0.0:
            return self.class_id

        # SÄ±nÄ±f oylamasÄ±: Modelde yalnÄ±zca ID 0,1,2 var.
        # Ä°HA (ID=2) Ã¶ncelikli AMA en az %50 aÄŸÄ±rlÄ±klÄ± oy almalÄ±.
        # DÃ¼ÅŸÃ¼k eÅŸik (eski 0.15) = 30 frame'de 2 yanlÄ±ÅŸ drone oyu bile kuÅŸu "Ä°HA" yapÄ±yordu!
        PRIORITY = [2]  # drone/uav Ã¶ncelikli, ama Ã§oÄŸunluk ÅŸartÄ±yla

        for cls in PRIORITY:
            if weighted_totals.get(cls, 0.0) / total_weight >= CLASS_PRIORITY_THRESHOLD:
                return cls

        return max(weighted_totals, key=weighted_totals.get)

    @property
    def voted_class_share(self) -> float:
        """Kazanan sÄ±nÄ±fÄ±n gÃ¼ven-aÄŸÄ±rlÄ±klÄ± zamansal oy oranÄ±."""
        if not self._class_history:
            return 0.0
        totals: Dict[int, float] = {}
        for cls_i, conf_i in self._class_history:
            totals[cls_i] = totals.get(cls_i, 0.0) + conf_i
        total = sum(totals.values())
        return float(totals.get(self.voted_class_id, 0.0) / total) if total else 0.0

    def world_path_length(self, window_s: float) -> float:
        """
        [YENÄ°] Son `window_s` saniyedeki, DÃœNYA Ã‡ERÃ‡EVESÄ°NDE (kamera
        hareketinden arÄ±ndÄ±rÄ±lmÄ±ÅŸ â€” bkz. shift_history/CameraMotionCompensator)
        TOPLAM KAT EDÄ°LEN YOLU dÃ¶ndÃ¼rÃ¼r.

        NEDEN NET YER DEÄÄ°ÅTÄ°RME DEÄÄ°L, TOPLAM YOL?
        DÃ¶nerek/manevra ederek uÃ§an gerÃ§ek bir hedef bir dairenin etrafÄ±nda
        dÃ¶nebilir ve net yer deÄŸiÅŸtirmesi kÃ¼Ã§Ã¼k Ã§Ä±kabilir â€” net mesafe onu
        yanlÄ±ÅŸlÄ±kla "hareketsiz" gÃ¶sterirdi. ArdÄ±ÅŸÄ±k kare-arasÄ± vektÃ¶rlerin
        BÃœYÃœKLÃœKLERÄ°NÄ°N toplamÄ± ise hem dÃ¼z uÃ§uÅŸta hem manevrada yÃ¼ksek
        Ã§Ä±kar, ama sabit duran bir gÃ¶kyÃ¼zÃ¼/bulut/parazit hayaletinde
        (kÃ¼Ã§Ã¼k YOLO/Kalman titremesi dÄ±ÅŸÄ±nda) dÃ¼ÅŸÃ¼k kalÄ±r.
        """
        n_window = max(2, int(round(window_s * self._fps)))
        pts_raw = self._pos_history[-n_window:]
        if len(pts_raw) < 2:
            return 0.0
        pts = [(p[0], p[1]) for p in pts_raw]
        arr = np.array(pts, dtype=np.float64)
        diffs = np.diff(arr, axis=0)
        return float(np.sum(np.linalg.norm(diffs, axis=1)))

    def classify_bird_vs_aircraft(self) -> tuple[str, float]:
        """
        [YENÄ°] KuÅŸ vs UÃ§ak/Ä°HA AkÄ±llÄ± SÄ±nÄ±flandÄ±rÄ±cÄ± (Post-Processing & GÃ¶rsel Karar)
        YOLO uzak mesafede kuÅŸlarÄ± Ä°HA/UÃ§ak ile karÄ±ÅŸtÄ±rabilir. Bu fonksiyon:
        1) VLM modelden gelen net semantik yorumu (varsa) Ã¶ncelikli alÄ±r.
        2) YOLO gÃ¼ven aÄŸÄ±rlÄ±klÄ± tarihsel oylamayÄ± sayar.
        3) Hareket, Kanat SalÄ±nÄ±mÄ± (Aspect Ratio), Dikey Dalgalanma (Bobbing) ve Dokusal DeÄŸiÅŸim ile
           kesin bir fizik, geometri ve biyoloji ayrÄ±mÄ± yapar.
        """
        if self.vlm_class and isinstance(self.vlm_class, str):
            val = self.vlm_class.lower()
            if any(w in val for w in ("sabit_kanat", "iha", "ucak", "helikopter", "hava_araci")):
                return ("UÃ‡AK / Ä°HA", 0.96)
            elif "kus" in val or "bird" in val or "kuÅŸ" in val:
                return ("KUÅ", 0.94)

        uav_votes  = sum(c for cls_i, c in self._class_history if cls_i == 2)
        bird_votes = sum(c for cls_i, c in self._class_history if cls_i == 1)

        uav_score  = float(uav_votes)
        bird_score = float(bird_votes)

        # 1. Kanat Ã‡Ä±rpma & Form SalÄ±nÄ±mÄ± (Aspect Ratio Micro-Fluctuations)
        # SavaÅŸ Ä°HA'sÄ± (TB2, UÃ§ak) sabittir. KuÅŸlar kanat vuruÅŸlarÄ±nda en-boy oranÄ±nÄ± sÃ¼rekli titreÅŸtirir.
        ar_flaps = 0
        ar_std = 0.0
        if len(self._ar_history) >= 4:
            ar_arr = np.array(self._ar_history)
            ar_std = float(np.std(ar_arr))
            diffs = np.diff(ar_arr)
            # BUG-FIX (AnlÄ±k KuÅŸ Benzetmesi): Bbox'Ä±n hafif titremesi veya uÃ§aÄŸÄ±n
            # aÃ§Ä±lÄ± dÃ¶nÃ¼ÅŸleri, kÃ¼Ã§Ã¼k sahte salÄ±nÄ±mlar yaratÄ±yordu.
            # EÅŸik 0.015 -> 0.040'a ve standart sapma 0.03 -> 0.06'ya Ã§Ä±karÄ±ldÄ±.
            ar_flaps = sum(1 for i in range(len(diffs)-1) if diffs[i] * diffs[i+1] < 0 and abs(diffs[i]) > 0.040)
            if ar_flaps >= 2 or ar_std > 0.06:
                bird_score += 3.5

        # 2. Dikey Dalgalanma ve SÃ¼zÃ¼lme (Bouyancy & Vertical Bobbing)
        # UÃ§ak ip gibi mermi rotasÄ±nda gider; kuÅŸ sÃ¼zÃ¼lÃ¼rken ve Ã§Ä±rparken y ekseninde hafif iniÅŸ Ã§Ä±kÄ±ÅŸ yapar.
        if len(self._pos_history) >= 6:
            y_coords = [p[1] for p in self._pos_history[-10:]]
            y_diffs = np.diff(y_coords)
            # BUG-FIX (AnlÄ±k KuÅŸ Benzetmesi): Kamera titremesini kuÅŸ uÃ§uÅŸu sanmasÄ±n
            # EÅŸik 0.8 -> 2.5'e Ã§Ä±karÄ±ldÄ±.
            y_bobbing = sum(1 for i in range(len(y_diffs)-1) if y_diffs[i] * y_diffs[i+1] < 0 and abs(y_diffs[i]) > 2.5)
            if y_bobbing >= 2:
                bird_score += 2.5

        # 3. GÃ¶rsel Doku ve Kontur SalÄ±nÄ±mÄ± (Frame-to-frame Crop Texture Variance)
        # Sabit kanat uÃ§aÄŸÄ±n krop dokusu deÄŸiÅŸmez; kuÅŸ gÃ¶vdesi ve kanadÄ± bÃ¼kÃ¼ldÃ¼kÃ§e dokusu fark yaratÄ±r.
        recent = self._most_recent_crops(2)
        if len(recent) >= 2:
            try:
                # recent[0] en yeni, recent[1] bir Ã¶ncekisi (ters kronolojik)
                _, _, _, (ar2, gray2) = recent[0]
                _, _, _, (ar1, gray1) = recent[1]
                vis_diff = float(np.mean((gray1 - gray2) ** 2))
                if vis_diff > 0.012:
                    bird_score += 2.0
            except Exception:
                pass

        # 4. Rijit Ä°HA/UÃ§ak Ä°mzasÄ±: SÄ±fÄ±r kanat/form salÄ±nÄ±mÄ± (SÃ¼rat yanÄ±ltmasÄ± Ã–NLENDÄ°!)
        # BUG-FIX (boÅŸluÄŸu %99 Ä°HA sanma): Bu kural eskiden SADECE "kanat
        # Ã§Ä±rpma sinyali YOK" bilgisine dayanÄ±yordu. Sorun: hareketsiz bir
        # arka plan hayaleti (bulut/parazit/yansÄ±ma) da doÄŸasÄ± gereÄŸi sÄ±fÄ±r
        # kanat salÄ±nÄ±mÄ± gÃ¶sterir â€” yani "kuÅŸ deÄŸil" ile "gerÃ§ek bir uÃ§ak"
        # birbirine karÄ±ÅŸtÄ±rÄ±lÄ±yor, ikisi de bu kuralÄ± tetikleyip %90+
        # gÃ¼venle "UÃ‡AK/Ä°HA" etiketleniyordu. ArtÄ±k bu bonus yalnÄ±zca hedef
        # GERÃ‡EKTEN (dÃ¼nya Ã§erÃ§evesinde) anlamlÄ± bir yol kat etmiÅŸse verilir
        # â€” bkz. config.py MIN_WORLD_PATH_PX_PER_S yorumu.
        _path_len = self.world_path_length(WORLD_PATH_WINDOW_S)
        _moving_enough = _path_len >= (MIN_WORLD_PATH_PX_PER_S * WORLD_PATH_WINDOW_S * 0.6)
        if len(self._ar_history) >= 5 and ar_std < 0.02 and ar_flaps == 0 and _moving_enough:
            uav_score += 4.0

        # Karar MekanizmasÄ±: KuÅŸ kinematiÄŸi gÃ¼Ã§lÃ¼ysa veya oylar kuÅŸtan yanaysa HATA YAPMA!
        # Eski koddaki YOLO oylamasÄ±na kÃ¶rÃ¼ kÃ¶rÃ¼ne tabi olan 'or self.voted_class_id == 2' bug'Ä± imha edildi.
        tot = uav_score + bird_score
        # BUG-FIX: Eskiden tot Ã§ok kÃ¼Ã§Ã¼k/sÄ±fÄ±ra yakÄ±nken bile (yani HÄ°Ã‡BÄ°R
        # gerÃ§ek kanÄ±t yokken) raw_conf min(0.60/0.65) ile taban deÄŸere
        # zorlanÄ±yordu â€” "kanÄ±t yok" durumu yanlÄ±ÅŸlÄ±kla "orta-yÃ¼ksek gÃ¼venli
        # karar" gibi gÃ¶rÃ¼nÃ¼yordu. ArtÄ±k gerÃ§ek kanÄ±t yoksa (tot Ã§ok kÃ¼Ã§Ã¼k)
        # gÃ¼ven kasÄ±tlÄ± olarak dÃ¼ÅŸÃ¼k/belirsiz tutulur; TYPE_LABEL_SMOOTH_WINDOW
        # Ã§oÄŸunluk oylamasÄ± zaten tek karelik gÃ¼rÃ¼ltÃ¼yÃ¼ sÃ¶ndÃ¼rÃ¼yor.
        has_evidence = tot > 0.5
        tot_safe = tot + 1e-5
        # BUG-FIX (KuÅŸ Benzetmesi TAMAMEN KÄ°LÄ°TLENDÄ°): SavaÅŸan Ä°HA konseptinde hedefin
        # uÃ§ak/Ä°HA olma olasÄ±lÄ±ÄŸÄ± %99'dur. YOLO yanlÄ±ÅŸlÄ±kla kuÅŸ dese bile, sistemin
        # kendi kendine "bu bir kuÅŸ" diyebilmesi iÃ§in biyolojik kanÄ±tlarÄ±n (kanat Ã§Ä±rpma vb)
        # uÃ§ak kanÄ±tlarÄ±ndan TAM 3 KAT daha fazla olmasÄ± ÅŸart koÅŸuldu. (YOLO "KuÅŸ" dediyse bile 2 kat fazla olmalÄ±).
        if bird_score > uav_score * 3.0 or (self.voted_class_id == 1 and bird_score >= uav_score * 2.0):
            raw_is_bird = True
            raw_conf = min(0.99, max(0.65, float(bird_score / tot_safe))) if has_evidence else 0.55
        else:
            raw_is_bird = False
            raw_conf = min(0.99, max(0.60, float(uav_score / tot_safe))) if has_evidence else 0.52

        # BUG-FIX (arada kuÅŸ olarak iÅŸaretleme titremesi): YukarÄ±daki karar
        # tamamen o anki (tek karelik) sinyallere dayanÄ±yor â€” Ã¶zellikle doku
        # farkÄ± (`vis_diff`) yalnÄ±zca en son 2 krop arasÄ±nda hesaplanÄ±yor ve
        # tek bulanÄ±k/motion-blur'lu bir kare bile rozeti bir anlÄ±ÄŸÄ±na
        # "KUÅ"a Ã§evirip hemen geri dÃ¶nebiliyordu (gÃ¶zle gÃ¶rÃ¼lÃ¼r titreme).
        # ArtÄ±k ham karar geÃ§miÅŸte tutulup son TYPE_LABEL_SMOOTH_WINDOW
        # karenin Ã‡OÄUNLUK oyu gÃ¶steriliyor: gerÃ§ek bir kuÅŸ/uÃ§ak geÃ§iÅŸi yine
        # birkaÃ§ kare iÃ§inde yakalanÄ±r, ama tek karelik gÃ¼rÃ¼ltÃ¼ artÄ±k
        # rozeti Ã§eviremez.
        self._type_label_history.append((raw_is_bird, raw_conf))
        if len(self._type_label_history) > TYPE_LABEL_SMOOTH_WINDOW:
            self._type_label_history.pop(0)

        bird_votes = sum(1 for is_bird, _ in self._type_label_history if is_bird)
        final_is_bird = bird_votes > (len(self._type_label_history) / 2.0)

        matching_confs = [c for is_bird, c in self._type_label_history if is_bird == final_is_bird]
        final_conf = float(np.mean(matching_confs)) if matching_confs else raw_conf

        return ("KUÅ", final_conf) if final_is_bird else ("UÃ‡AK / Ä°HA", final_conf)

    @property
    def smooth_velocity(self) -> np.ndarray:
        n = len(self._pos_history)
        if n < 4:
            return np.array([0.0, 0.0])

        # BUG-FIX (hÄ±z spike'larÄ±): Eskiden np.arange(n) ile her noktayÄ± 1 frame
        # aralÄ±klÄ± varsÄ±yÄ±yordu. OklÃ¼zyon sonrasÄ± 30 frame boÅŸluk â†’ fiziksel olarak
        # imkansÄ±z hÄ±z spike'Ä±. ArtÄ±k gerÃ§ek frame index'leri kullanÄ±lÄ±yor.
        t  = np.array([p[2] for p in self._pos_history], dtype=np.float64)
        xs = np.array([p[0] for p in self._pos_history], dtype=np.float64)
        ys = np.array([p[1] for p in self._pos_history], dtype=np.float64)

        # Zaman aralÄ±ÄŸÄ± sÄ±fÄ±rsa (tÃ¼m noktalar aynÄ± frame'de) hÄ±z hesaplanamaz
        if t[-1] - t[0] < 1e-6:
            return np.array([0.0, 0.0])

        vx_per_frame = np.polyfit(t, xs, 1)[0]
        vy_per_frame = np.polyfit(t, ys, 1)[0]

        return np.array([vx_per_frame * self._fps, vy_per_frame * self._fps])

    def _update_zigzag_score(self):
        """
        BUG-FIX: zigzag_score alanÄ± __init__'te 0.0 ile baÅŸlatÄ±lÄ±yordu ama
        hiÃ§bir yerde gÃ¼ncellenmiyordu â€” HUD'da ve VLM prompt'una "gerÃ§ek bir
        manevra sinyali" gibi gÃ¶nderilen alan aslÄ±nda her zaman sabit 0.0
        kalÄ±yordu. ArtÄ±k pozisyon geÃ§miÅŸindeki ardÄ±ÅŸÄ±k hareket vektÃ¶rleri
        arasÄ±ndaki yÃ¶n deÄŸiÅŸim aÃ§Ä±sÄ±na (radyan) dayalÄ± gerÃ§ek bir skor
        hesaplanÄ±yor: dÃ¼z uÃ§uÅŸta â‰ˆ0, sÄ±k yÃ¶n deÄŸiÅŸtiren (kuÅŸ/manevra) bir
        hedefte belirgin ÅŸekilde yÃ¼ksek Ã§Ä±kar.
        """
        n = len(self._pos_history)
        if n < 4:
            self.zigzag_score = 0.0
            return

        pts = np.array([(p[0], p[1]) for p in self._pos_history[-8:]], dtype=np.float64)
        vecs = np.diff(pts, axis=0)
        norms = np.linalg.norm(vecs, axis=1)

        angle_changes = []
        for i in range(len(vecs) - 1):
            n1, n2 = norms[i], norms[i + 1]
            if n1 < 1e-3 or n2 < 1e-3:
                continue
            cos_ang = float(np.dot(vecs[i], vecs[i + 1]) / (n1 * n2))
            cos_ang = max(-1.0, min(1.0, cos_ang))
            angle_changes.append(np.arccos(cos_ang))

        self.zigzag_score = float(np.mean(angle_changes)) if angle_changes else 0.0

    @property
    def display_confidence(self) -> float:
        """
        BUG-FIX (kutu titreyip kayboluyor / VLM tetiklenmiyor): GÃ¶rÃ¼ntÃ¼leme
        ve VLM tetikleme kararlarÄ± eskiden self.confidence'Ä±n (o ANKÄ° TEK
        karenin ham YOLO gÃ¼veni) doÄŸrudan eÅŸikle karÅŸÄ±laÅŸtÄ±rÄ±lmasÄ±na
        dayanÄ±yordu. Track zaten ByteTrack tarafÄ±ndan eÅŸleÅŸtiriliyor
        (suspended DEÄÄ°L) olsa bile, tek bir gÃ¼rÃ¼ltÃ¼lÃ¼/dÃ¼ÅŸÃ¼k-conf kare
        DISPLAY_MIN_CONF/VLM_MIN_TRACK_CONF eÅŸiÄŸinin altÄ±na dÃ¼ÅŸÃ¼nce kutu
        anÄ±nda kayboluyor, sonraki karede tekrar beliriyordu.
        Ã‡Ã¶zÃ¼m: son birkaÃ§ karenin EN YÃœKSEK gÃ¼venini kullan â€” track gerÃ§ekten
        orada olduÄŸunu birkaÃ§ kare Ã¶nce kanÄ±tladÄ±ysa, tek karelik bir dip
        onu gÃ¶rÃ¼ntÃ¼den silmemeli. confidence_history zaten Track.update()
        iÃ§inde her karede tutuluyor, ek maliyet yok.
        """
        if not self.confidence_history:
            return self.confidence
        return max(max(self.confidence_history[-5:]), self.confidence)

    @property
    def speed_px_s(self) -> float:
        return float(np.linalg.norm(self._ema_vel))
        
    @property
    def is_screen_static(self) -> bool:
        """HUD grafikleri, SaÄŸ alt Watermark'lar ve Lense yapÄ±ÅŸmÄ±ÅŸ lekeleri KUSURSUZ tespit eder.
        Kurallar: 
        1. Ekranda yer deÄŸiÅŸtirmemeli (kutu x,y titremesi hariÃ§).
        2. Kutu alanÄ± (BÃ¼yÃ¼klÃ¼ÄŸÃ¼) zamanla deÄŸiÅŸmemeli. (GerÃ§ek dalÄ±ÅŸ yapan uÃ§aÄŸÄ±n alanÄ± katlanarak artar!)
        """
        from src.config import HUD_STATIC_MAX_MOVEMENT_PX, HUD_STATIC_WINDOW_S, HUD_STATIC_MAX_AREA_CHANGE
        n = len(self._screen_history)
        if n < 15: # En az yarÄ±m saniye (30fps iÃ§in) veri lazÄ±m
            return False
            
        current_frame = self._screen_history[-1][4]
        window_frames = int(HUD_STATIC_WINDOW_S * self._fps)
        
        start_idx = 0
        for i in range(n-1, -1, -1):
            if current_frame - self._screen_history[i][4] > window_frames:
                start_idx = i
                break
                
        # En az yarÄ±m saniyelik geriye dÃ¶nÃ¼k veri
        if current_frame - self._screen_history[start_idx][4] < (window_frames / 2):
            return False
            
        history = self._screen_history[start_idx:]
        
        # --- 1. KONUM TESTÄ° ---
        pts = np.array([(h[0], h[1]) for h in history], dtype=np.float64)
        min_x, min_y = np.min(pts, axis=0)
        max_x, max_y = np.max(pts, axis=0)
        max_movement = float(np.hypot(max_x - min_x, max_y - min_y))
        
        w = max(1.0, float(self.bbox[2] - self.bbox[0]))
        h = max(1.0, float(self.bbox[3] - self.bbox[1]))
        dynamic_move_limit = max(HUD_STATIC_MAX_MOVEMENT_PX, min(w, h) * 0.15)
        
        if max_movement >= dynamic_move_limit:
            return False # Ekranda hareket ediyor, HUD olamaz!
            
        # --- 2. ALAN/BOYUT DEÄÄ°ÅÄ°MÄ° TESTÄ° ---
        areas = np.array([(h[2] * h[3]) for h in history], dtype=np.float64)
        min_area = float(np.min(areas))
        max_area = float(np.max(areas))
        
        # Bbox titremesi alanÄ± %10-%20 deÄŸiÅŸtirebilir. Ancak gerÃ§ek uÃ§ak yaklaÅŸtÄ±ÄŸÄ±nda alan 2-3 katÄ±na (Ratio > 1.0) Ã§Ä±kar.
        area_change_ratio = (max_area - min_area) / max(1.0, min_area)
        
        # EÄŸer konumu sabit VE alanÄ± da hiÃ§ bÃ¼yÃ¼mÃ¼yorsa/kÃ¼Ã§Ã¼lmÃ¼yorsa, KESÄ°NLÄ°KLE SABÄ°T BÄ°R YAZIDIR/GRAFÄ°KTÄ°R!
        if area_change_ratio < HUD_STATIC_MAX_AREA_CHANGE:
            return True
            
        return False

    @property
    def current_fill_ratio(self) -> float:
        """Hedefin Bounding Box iÃ§erisindeki solid (katÄ± gÃ¶vde) doluluk oranÄ±nÄ±n ortalamasÄ±nÄ± dÃ¶ndÃ¼rÃ¼r.
        HUD yazÄ±larÄ± veya teller %1-%3 civarÄ±ndayken, gerÃ§ek Ä°HA'lar %10-%80 arasÄ±dÄ±r."""
        if not self.fill_ratio_history:
            return 1.0 # EÄŸer veri yoksa varsayÄ±lan olarak uÃ§aÄŸÄ± silme! (KatÄ± kabul et)
        return float(np.mean(self.fill_ratio_history))

    @property
    def velocity(self) -> np.ndarray:
        return self._ema_vel

    def update_visual_heading(self, crop_bgr: np.ndarray):
        """
        Ok yÃ¶nÃ¼nÃ¼ son pozisyon geÃ§miÅŸinden kÄ±sa pencereyle hesaplar.

        KÃ–K NEDEN (eski hata):
          smooth_velocity = np.polyfit(t, xs, 1) Ã¼zerinden SON 20 POZÄ°SYONun
          tamamÄ±na bakÄ±yordu. Ani manevrada 17 eski + 3 yeni nokta polyfit'i
          domine eder â†’ heading 15+ frame boyunca eski yÃ¶nÃ¼ gÃ¶sterir â†’ ok
          titrer/saplar. alpha=0.20 EMA bu kadar bÃ¼yÃ¼k lagÄ± telafi edemiyordu.

        Ã‡Ã–ZÃœM:
          Son 4 pozisyondan (yaklaÅŸÄ±k 0.13s) doÄŸrudan fark vektÃ¶rÃ¼ al.
          Maneuver anÄ±nda hemen yeni yÃ¶ne dÃ¶ner.
          alpha=0.30 ile YOLO bbox jitterini yeterince bastÄ±rÄ±r.
        """
        n = len(self._pos_history)
        if n < 2:
            if self.visual_heading is None:
                self.visual_heading = np.array([0.0, -1.0])
            return

        # Son 4 frame'lik pencere (veya elimizde kaÃ§ varsa)
        lookback = min(n - 1, 3)
        p_old = self._pos_history[-(lookback + 1)]
        p_new = self._pos_history[-1]
        dx = p_new[0] - p_old[0]
        dy = p_new[1] - p_old[1]
        raw_speed = float(np.hypot(dx, dy))

        if raw_speed < 2.0:
            # Ã‡ok yavaÅŸ / yerinde: eski heading koru (flip-flop Ã¶nle)
            if self.visual_heading is None:
                self.visual_heading = np.array([0.0, -1.0])
            return

        target = np.array([dx / raw_speed, dy / raw_speed])

        if self.visual_heading is None:
            self.visual_heading = target.copy()
        else:
            # alpha=0.30: ani maneuver ~2 frame'de yakalar,
            # kÃ¼Ã§Ã¼k YOLO jitterini bastÄ±rÄ±r
            new_h = 0.30 * target + 0.70 * self.visual_heading
            norm = float(np.linalg.norm(new_h))
            if norm > 1e-6:
                self.visual_heading = new_h / norm


    @staticmethod
    def _estimate_object_coverage(gray: np.ndarray) -> tuple[float, bool]:
        """
        Basit Otsu eÅŸikleme ile nesnenin (uÃ§ak) bu crop iÃ§inde kabaca ne kadar
        yer kapladÄ±ÄŸÄ±nÄ± tahmin eder. Kameradan/Ã§Ã¶zÃ¼nÃ¼rlÃ¼kten baÄŸÄ±msÄ±z Ã§alÄ±ÅŸÄ±r.

        DÃ¶ner:
          fill_ratio   : en bÃ¼yÃ¼k konturun crop alanÄ±na oranÄ± (0..1)
          touches_edge : en bÃ¼yÃ¼k kontur crop kenarÄ±na deÄŸiyor mu
                         (nesnenin bir kÄ±smÄ± muhtemelen kadraj dÄ±ÅŸÄ±nda kalmÄ±ÅŸ)
        """
        try:
            h, w = gray.shape[:2]
            _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

            # Nesne arka plana gÃ¶re koyu ya da aÃ§Ä±k olabilir; iki polariteyi de
            # dene ve kadrajÄ±n DAHA AZINI kaplayan konturu seÃ§ â€” arka plan
            # genelde kadrajÄ±n Ã§oÄŸunluÄŸunu kaplar, nesne ise azÄ±nlÄ±ÄŸÄ±.
            def _best(mask: np.ndarray) -> tuple[float, bool]:
                contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                if not contours:
                    return 0.0, False
                c = max(contours, key=cv2.contourArea)
                area = cv2.contourArea(c)
                x, y, cw, ch = cv2.boundingRect(c)
                touches = (x <= 2 or y <= 2 or (x + cw) >= (w - 2) or (y + ch) >= (h - 2))
                return float(area) / max(1.0, float(w * h)), touches

            ratio_a, touch_a = _best(th)
            ratio_b, touch_b = _best(255 - th)
            return (ratio_a, touch_a) if ratio_a <= ratio_b else (ratio_b, touch_b)
        except Exception:
            return 0.0, False

    def update_crop_buffer(self, crop_bgr: np.ndarray, min_size: int = 15,
                            is_clipped: bool = False, area_ratio: float = 0.0,
                            conf: float | None = None):
        """
        [YENÄ°] Basit ve Etkili Kare SeÃ§im HattÄ± (2 Temel Kural):
        0.5s'lik kÄ±sa pencerelerde sÄ±fÄ±r ek yÃ¼k ve yÃ¼ksek netlikle en iyi fotoÄŸrafÄ± seÃ§er.

        is_clipped  : Tespit kutusu kare kenarÄ±na deÄŸiyor mu (uÃ§aÄŸÄ±n bir kÄ±smÄ±
                      gÃ¶rÃ¼ntÃ¼ dÄ±ÅŸÄ±nda kalmÄ±ÅŸ olabilir â†’ muhtemelen eksik/parÃ§a gÃ¶rÃ¼nÃ¼m).
        area_ratio  : Kutunun kare alanÄ±na oranÄ± (Ã§ok bÃ¼yÃ¼kse aÅŸÄ±rÄ± yakÄ±n Ã§ekim,
                      genelde sadece gÃ¶vdenin bir parÃ§asÄ± â€” kuyruk/kanat ucu vb. â€” gÃ¶rÃ¼nÃ¼r).
        conf        : BUG-FIX (VLM pipeline tetiklenmiyordu â€” YARIÅ DURUMU): Bu
                      fonksiyon eskiden `self.confidence`'Ä± (Track'in O ANKÄ°
                      canlÄ±/mutable durumu) okuyordu. Fonksiyon _crop_pool
                      Ã¼zerinden ASENKRON Ã§aÄŸrÄ±ldÄ±ÄŸÄ± iÃ§in (yalnÄ±zca 2 worker),
                      kuyruk biriktiÄŸinde worker bu kareyi iÅŸlediÄŸinde
                      self.confidence Ã§oktan SONRAKÄ° bir karenin deÄŸerine
                      gÃ¼ncellenmiÅŸ oluyordu â€” yani kabul/red kararÄ±, o karenin
                      GERÃ‡EK gÃ¼veniyle deÄŸil, tesadÃ¼fen o an track'te duran
                      deÄŸerle veriliyordu. ArtÄ±k Ã§aÄŸÄ±ran taraf
                      (MultiTargetTracker.update), kareyi yakaladÄ±ÄŸÄ± ANDAKÄ°
                      gÃ¼veni burada donduruyor (snapshot). conf=None geriye
                      dÃ¶nÃ¼k uyumluluk iÃ§in eski davranÄ±ÅŸa (self.confidence) dÃ¼ÅŸer.
        """
        eff_conf = self.confidence if conf is None else conf
        if eff_conf < VLM_CROP_MIN_CONF:
            return
            
        h, w = crop_bgr.shape[:2]
        if h < min_size or w < min_size:
            return

        gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
        # BUG-FIX: Sentetik grafikler (beyaz arkaplan Ã¼stÃ¼ne siyah yazÄ±lar vb.)
        # aÅŸÄ±rÄ± yÃ¼ksek (>2000) Laplacian verir ve gerÃ§ek uÃ§aklarÄ±n Ã¶nÃ¼ne geÃ§er.
        # Laplacian (keskinlik) skoru 800.0 ile sÄ±nÄ±rlandÄ±.
        lap_var = float(cv2.Laplacian(gray, cv2.CV_32F).var())  # CV_64F yerine CV_32F: aynı sonuç, daha az bellek/işlem
        lap_var_clipped = min(800.0, lap_var)

        # BUG-FIX: GÃ¶kyÃ¼zÃ¼nde net bir silÃ¼et olsa bile, arkaplan Ã§ok homojen olduÄŸu iÃ§in
        # genel varyans Ã§ok dÃ¼ÅŸÃ¼k Ã§Ä±kabiliyordu. EÅŸik 20.0'den 2.0'a Ã§ekildi.
        if lap_var < 2.0:
            log.warning(f"[CROP-IQA] Track {self.track_id} REDDEDÄ°LDÄ°: BulanÄ±klÄ±k (lap_var={lap_var:.1f} < 2.0)")
            return

        # Prensip 3 (Keskinlik ve Ã‡Ã¶zÃ¼nÃ¼rlÃ¼k Optimizasyonu): KÃ¶ÅŸe netliÄŸi (laplacian) + Kontrast (std) skoru
        contrast = float(gray.std())

        # BUG-FIX (yanlÄ±ÅŸ kare seÃ§imi): Eskiden skor `* np.sqrt(h * w)` ile
        # Ã‡ARPILIYORDU. Bu, boyutu salt netlikten Ã§ok daha baskÄ±n kÄ±lÄ±yordu:
        # Ã¶rn. 400x300'lÃ¼k bir kare (sqrt=346) ile 60x40'lÄ±k bir kare (sqrt=49)
        # arasÄ±nda NETLÄ°KTEN BAÄIMSIZ ~7 kat'lÄ±k bir skor farkÄ± oluÅŸuyordu.
        # SonuÃ§: uÃ§ak kameraya yaklaÅŸÄ±p kutusu bÃ¼yÃ¼dÃ¼ÄŸÃ¼ an (genelde arkadan/
        # kuyruktan en kÃ¶tÃ¼ aÃ§Ä±), o kare buffer'Ä±n tepesine kilitleniyor ve
        # sonra gelen Ã§ok daha net/iyi aÃ§Ä±lÄ± ama biraz daha kÃ¼Ã§Ã¼k kareler
        # (yan silÃ¼et vb.) bunu bir daha asla geÃ§emiyordu â€” VLM_RECALL_IQA_GAIN
        # (%10 Ã¼stÃ¼nlÃ¼k ÅŸartÄ±) da bu ÅŸiÅŸirilmiÅŸ skoru yakalayamÄ±yordu.
        # Yeni kural: Büyük (yakın) uçak kareleri her zaman uzaktaki ufak lekelere karşı kazanmalı.
        size_bonus = np.sqrt(h * w) / 200.0   # Boyuta göre lineer büyüme
        quality_score = float(lap_var_clipped * 1.5 + contrast * 2.0) * (1.0 + size_bonus)

        # BUG-FIX (en kÃ¶tÃ¼ aÃ§Ä± sorunu, 3. deneme): area_ratio (kutu / TAM VÄ°DEO
        # KARESÄ°) Ã§oÄŸu videoda Ã§ok kÃ¼Ã§Ã¼k kalÄ±yor Ã§Ã¼nkÃ¼ video karesi uÃ§aktan
        # kat kat bÃ¼yÃ¼k â€” uÃ§ak kendi crop'u iÃ§inde ekranÄ± doldursa bile
        # tam-kare oranÄ± 0.35 eÅŸiÄŸine hiÃ§ yaklaÅŸmÄ±yordu, ceza tetiklenmiyordu.
        # Bunun yerine NESNENÄ°N BU CROP Ä°Ã‡Ä°NDEKÄ° GERÃ‡EK KAPLAMA ORANINI
        # doÄŸrudan gÃ¶rÃ¼ntÃ¼ iÃ§eriÄŸinden (Otsu eÅŸikleme + en bÃ¼yÃ¼k kontur)
        # tahmin ediyoruz â€” Ã§Ã¶zÃ¼nÃ¼rlÃ¼kten/kameradan baÄŸÄ±msÄ±z, gÃ¼venilir bir sinyal:
        #   fill_ratio    Ã§ok kÃ¼Ã§Ã¼kse (<%8)  â†’ nesne muhtemelen Ã§ok uzak/belirsiz
        #   fill_ratio    Ã§ok bÃ¼yÃ¼kse (>%55) â†’ aÅŸÄ±rÄ± yakÄ±n, muhtemelen sadece
        #                                       gÃ¶vdenin bir parÃ§asÄ± (kuyruk/kanat)
        #   touches_edge  â†’ en bÃ¼yÃ¼k kontur crop kenarÄ±na deÄŸiyor â†’ nesne
        #                    kadraj dÄ±ÅŸÄ±na taÅŸmÄ±ÅŸ, parÃ§a gÃ¶rÃ¼nÃ¼m ihtimali yÃ¼ksek
        fill_ratio, touches_edge = self._estimate_object_coverage(gray)
        
        # Solid-Body geÃ§miÅŸini gÃ¼ncelle (bilgi amaÃ§lÄ±)
        self.fill_ratio_history.append(fill_ratio)
        if len(self.fill_ratio_history) > 10:
            self.fill_ratio_history.pop(0)

        if touches_edge:
            quality_score *= 0.35
        if fill_ratio > 0.75:
            # BUG-FIX (VLM en kÃ¶tÃ¼ fotoÄŸraf seÃ§imi): Eski eÅŸik 0.55 idi â€” uÃ§ak crop'u
            # tam doldurduÄŸunda Otsu kendi detaylarÄ±nÄ± segmentleyip fill_ratio>0.55
            # Ã§Ä±karÄ±yor, mÃ¼kemmel yakÄ±n Ã§ekim cezalanÄ±yordu. 0.75'e yÃ¼kseltildi,
            # ceza katsayÄ±sÄ± yumuÅŸatÄ±ldÄ± (0.6â†’0.75).
            over = (fill_ratio - 0.75) / 0.15
            quality_score *= max(0.25, 0.75 ** over)
        elif fill_ratio < 0.08 and fill_ratio > 0.0:
            # Nesne kadrajÄ±n %8'inden azÄ±nÄ± kaplÄ±yorsa (Ã§ok uzak/kÃ¼Ã§Ã¼k) hafif ceza â€”
            # tamamen elemiyoruz Ã§Ã¼nkÃ¼ lap_var eÅŸiÄŸi zaten en bulanÄ±klarÄ± eliyor.
            quality_score *= 0.6

        # Eski frame-bazlÄ± sinyaller (tracker.py'de zaten hesaplanÄ±yorsa) hÃ¢lÃ¢
        # ek bir gÃ¼venlik katmanÄ± olarak korunuyor.
        if is_clipped:
            quality_score *= 0.5
        if area_ratio > 0.35:
            closeness_penalty = max(0.25, 1.0 - (area_ratio - 0.35) * 2.0)
            quality_score *= closeness_penalty

        current_time = time.time()

        log.debug(
            f"[CROP-IQA] Track {self.track_id}: q={quality_score:.1f} "
            f"lap={lap_var:.1f} contrast={contrast:.1f} fill={fill_ratio:.2f} "
            f"edge={touches_edge} size={w}x{h} conf={eff_conf:.2f}"
        )
        
        ar = float(w) / max(1.0, float(h))
        small_gray = cv2.resize(gray, (16, 16), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
        signature = (ar, small_gray)

        # Thread-Safe olarak en yÃ¼ksek kaliteli kÄ±sÄ±mlarÄ± hafÄ±zada koru
        with self._buffer_lock:
            # BUG-FIX (debounce bozuk): Eskiden self._crop_buffer[-1] "en son
            # eklenen" sanÄ±lÄ±yordu ama buffer dolduktan sonra min_idx pozisyonuna
            # yazÄ±lÄ±yor â†’ [-1] rastgele eski bir kare. ArtÄ±k buffer'daki en yeni
            # zaman damgasÄ±na gÃ¶re debounce yapÄ±lÄ±yor.
            latest_time = max((c[2] for c in self._crop_buffer), default=0.0) if self._crop_buffer else 0.0
            if len(self._crop_buffer) < VLM_CROP_BUFFER_SIZE:
                if (current_time - latest_time) > 0.02:
                    self._crop_buffer.append((crop_bgr.copy(), quality_score, current_time, signature))
            else:
                min_idx = min(range(VLM_CROP_BUFFER_SIZE), key=lambda i: self._crop_buffer[i][1])
                if quality_score > self._crop_buffer[min_idx][1]:
                    if (current_time - latest_time) > 0.02:
                        self._crop_buffer[min_idx] = (crop_bgr.copy(), quality_score, current_time, signature)

    def _most_recent_crops(self, n: int) -> list[tuple]:
        """
        BUG-FIX: _crop_buffer[-1]/[-2] eskiden "en yeni kare" sanÄ±lÄ±yordu, ama
        update_crop_buffer() buffer dolduktan sonra SIRALI EKLEME yapmÄ±yor â€”
        en dÃ¼ÅŸÃ¼k kaliteli slotun (min_idx) Ã¼zerine yazÄ±yor. Yani buffer'Ä±n son
        elemanÄ± Ã§oÄŸu zaman en yeni deÄŸil, rastgele bir konumdaki bir karedir.
        Bu, hem classify_bird_vs_aircraft() iÃ§indeki doku-salÄ±nÄ±m kontrolÃ¼nÃ¼
        hem de okluzyon-sonrasÄ± kimlik eÅŸleÅŸtirmesindeki (appearance re-id)
        gÃ¶rsel farkÄ± bozuyordu. Bu yardÄ±mcÄ±, zaman damgasÄ±na (index 2) gÃ¶re
        gerÃ§ekten en yeni N kareyi dÃ¶ndÃ¼rÃ¼r.
        """
        with self._buffer_lock:
            if not self._crop_buffer:
                return []
            return sorted(self._crop_buffer, key=lambda c: c[2], reverse=True)[:n]

    def get_best_crops(self, max_crops: int = 2) -> list[np.ndarray]:
        """
        [YENÄ°] Prensip 3 (Highest Quality): Elenmeyen kareler arasÄ±ndan, matematiksel olarak
        kontrastÄ± ve kÃ¶ÅŸe netliÄŸi en yÃ¼ksek olan EN Ä°YÄ° 1 VEYA 2 KAREYÄ° seÃ§.
        """
        with self._buffer_lock:
            if not self._crop_buffer:
                return []
            
            # KontrastÄ± ve kÃ¶ÅŸe netliÄŸi en yÃ¼ksek olan adaylarÄ± sÄ±rala
            sorted_cands = sorted(self._crop_buffer, key=lambda x: x[1], reverse=True)
            
            # En Ã¼stÃ¼n kaliteli 1 veya en fazla 2 kareyi al
            selected = sorted_cands[:max_crops]
            selected.sort(key=lambda x: x[2])  # Zamansal akÄ±ÅŸ sÄ±rasÄ±
            return [crop for crop, score, t, *rest in selected]

    def kalman_bbox(self) -> np.ndarray:
        """GÃ¶rselleÅŸtirme iÃ§in bbox dÃ¶ndÃ¼rÃ¼r.

        - Suspended (okluzyonda): statePre â€” Kalman'Ä±n ileriye dÃ¶nÃ¼k konum tahmini.
        - Aktif               : statePost â€” Ã¶lÃ§Ã¼m + hÄ±z modeli fÃ¼zyonu (optimal tahmin).

        NEDEN EMA DEÄÄ°L statePost?
        â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
        â”‚ EMA (eski)     â”‚ tamamen reaktif, hÄ±z modeli YOK        â”‚
        â”‚                â”‚ sabit hÄ±zda bile kalÄ±cÄ± lag Ã¼retir     â”‚
        â”‚                â”‚ hÄ±zlanmada lag birikir â†’ aniden sÄ±Ã§rar â”‚
        â”œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¤
        â”‚ statePost(yeni)â”‚ Ã¶nceki (vx,vy) hÄ±z tahmini dahil fÃ¼zyonâ”‚
        â”‚                â”‚ sabit hÄ±zda steady-state lag â‰ˆ 0       â”‚
        â”‚                â”‚ hÄ±zlanmada yumuÅŸak yakÄ±nsama (no jerk) â”‚
        â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜

        Kalman state: [cx, cy, vx, vy, w, h]
        statePost her frame update() â†’ correct() ile gÃ¼ncellenir.
        Tespit yok (suspended) ise: predict() â†’ statePre ile ileriye tahmin.
        """
        if self.suspended:
            return self._clamp_box(self._predicted_bbox.copy())

        try:
            s   = self._kf.statePost.reshape(-1)
            cx  = float(s[0])
            cy  = float(s[1])
            # w ve h negatif veya sÄ±fÄ±r olursa (KF sapmasÄ±) gÃ¼venli alt sÄ±nÄ±r
            w   = max(4.0, abs(float(s[4])))
            h   = max(4.0, abs(float(s[5])))
            box = np.array([cx - w/2, cy - h/2, cx + w/2, cy + h/2], dtype=np.float32)
            return self._clamp_box(box)
        except Exception:
            # KF sayÄ±sal sapmasÄ± (Ã§ok nadir) â†’ EMA fallback
            return self._clamp_box(self._ema_bbox.copy())

    def _clamp_box(self, box: np.ndarray) -> np.ndarray:
        """
        BUG-FIX (KRÄ°TÄ°K â€” "dev kutu" / ekranÄ± kaplayan hayalet kutu, SON
        SAVUNMA KATMANI): slicer.py artÄ±k geometrik olarak saÃ§ma birleÅŸik
        kutularÄ± kaynaÄŸÄ±nda reddediyor (bkz. _merge_aircraft_fragments), AMA
        bir Kalman/appearance-re-id sapmasÄ± (Ã¶r. okluzyon sonrasÄ± kimlik
        eÅŸleÅŸmesinin yanlÄ±ÅŸlÄ±kla Ã§ok uzak/Ã§ok farklÄ± boyutlu bir track'i
        birleÅŸtirmesi) yine de statePost'u anormal bÃ¼yÃ¼tebilir. Bu fonksiyon
        Ã§izim/VLM'e giden HER kutuyu, kaynaÄŸÄ± ne olursa olsun, son bilinen
        gerÃ§ek frame alanÄ±nÄ±n MAX_OBJECT_AREA_RATIO'sunu aÅŸmayacak ÅŸekilde
        merkez etrafÄ±nda kÃ¼Ã§Ã¼ltÃ¼r â€” hedefin gerÃ§ek/onaylÄ± boyutu ne olursa
        olsun ekranÄ± kaplayan bir kutu ASLA Ã§izilmez/gÃ¶sterilmez.
        """
        fw, fh = self._last_fw, self._last_fh
        if fw <= 1.0 or fh <= 1.0:
            return box
        x1, y1, x2, y2 = box
        w = max(1.0, float(x2 - x1))
        h = max(1.0, float(y2 - y1))
        max_area = MAX_OBJECT_AREA_RATIO * fw * fh
        area = w * h
        if area <= max_area:
            return box
        scale = float(np.sqrt(max_area / area))
        cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        new_w, new_h = w * scale, h * scale
        return np.array(
            [cx - new_w / 2, cy - new_h / 2, cx + new_w / 2, cy + new_h / 2],
            dtype=np.float32,
        )


    def _center(self) -> tuple[float, float]:
        return (
            float((self.bbox[0] + self.bbox[2]) / 2),
            float((self.bbox[1] + self.bbox[3]) / 2),
        )

    class _KalmanProxy:
        def __init__(self, outer):
            self._outer = outer

        @property
        def position(self) -> np.ndarray:
            box = self._outer._predicted_bbox
            return np.array([(box[0] + box[2]) / 2, (box[1] + box[3]) / 2])

        @property
        def velocity(self) -> np.ndarray:
            return self._outer.smooth_velocity

    @property
    def kalman(self):
        return self._KalmanProxy(self)

    @property
    def velocity(self) -> np.ndarray:
        return self.smooth_velocity

    @property
    def position(self) -> np.ndarray:
        cx, cy = self._center()
        return np.array([cx, cy])


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Ã‡OKLU HEDEF TAKÄ°P YÃ–NETÄ°CÄ°SÄ° (GÃœNCELLENMÄ°Å)
