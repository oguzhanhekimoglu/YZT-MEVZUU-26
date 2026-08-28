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
from src.tracking.track_state import Track
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
class MultiTargetTracker:
    def __init__(self, fps: float = 30.0):
        # BUG-FIX: fps artÄ±k run.py'nin algÄ±ladÄ±ÄŸÄ± gerÃ§ek kaynak FPS'i â€”
        # sabit 30 deÄŸil. ByteTrack'in track_buffer/frame_rate hesaplarÄ± ve
        # her yeni Track'in hÄ±z hesabÄ± (smooth_velocity) bunu kullanÄ±r.
        self._fps = max(1.0, float(fps))
        self._init_bytetrack()
        self._states: dict[int, Track] = {}
        self.tracks: list[Track]           = []
        self.suspended_tracks: list[Track] = []
        self.cmc = CameraMotionCompensator()
        self._frame_count = 0
        # reset() sonrasi track ID'leri sifirdan yeniden verilir; tuketiciler
        # (bkz. backend/pipeline_adapter.py) bu sayaci izleyerek eski bir
        # track_id'ye ait onbellek verisini yeni (farkli fiziksel nesneye ait)
        # ayni ID'li track'e yanlislikla tasimadigini garanti edebilir.
        self.reset_generation = 0
        # Prensip 1: GÃ¶rÃ¼ntÃ¼ yakalama ve netlik hesaplama iÅŸlemleri ana dÃ¶ngÃ¼yÃ¼ (main thread) asla bloke etmez!
        self._crop_pool = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="CropPool")

    def _async_process_crop(self, track_id: int, crop: np.ndarray,
                             is_clipped: bool = False, area_ratio: float = 0.0,
                             conf: float | None = None):
        track = self._states.get(track_id)
        if track is not None:
            try:
                track.update_visual_heading(crop)
                track.update_crop_buffer(crop, is_clipped=is_clipped,
                                          area_ratio=area_ratio, conf=conf)
            except Exception as e:
                import traceback
                log.error(f"[TRACKER-CROP] HATA track {track_id}: {e}\n{traceback.format_exc()}")

    def _init_bytetrack(self):
        try:
            # BoxMOT 19.x - 22.x (En GÃ¼ncel SÃ¼rÃ¼m)
            from boxmot.trackers.bbox.bytetrack import ByteTrack as _ByteTrack
        except ImportError:
            try:
                # BoxMOT 12.x
                from boxmot.trackers.bytetrack.bytetrack import ByteTrack as _ByteTrack
            except ImportError:
                try:
                    # BoxMOT 10.x
                    from boxmot.trackers.bbox.bytetrack.bytetrack import ByteTrack as _ByteTrack
                except ImportError:
                    # Fallback
                    from boxmot.trackers import ByteTrack as _ByteTrack
        try:
            self._bt = _ByteTrack(
                min_conf      = BYTETRACK_MIN_CONF,
                track_thresh  = BYTETRACK_TRACK_THRESH,
                match_thresh  = BYTETRACK_MATCH_THRESH,
                track_buffer  = KALMAN_MAX_AGE,
                frame_rate    = int(round(self._fps)),
            )
            log.info(
                f"ByteTrack baÅŸlatÄ±ldÄ± â€” min_conf={BYTETRACK_MIN_CONF}, "
                f"track_thresh={BYTETRACK_TRACK_THRESH}, "
                f"match_thresh={BYTETRACK_MATCH_THRESH}"
            )
        except ImportError as e:
            log.error(f"boxmot kÃ¼tÃ¼phanesi bulunamadÄ±: {e}")
            raise

    def reset(self):
        # BUG-FIX (çözünürlük değişimi çökmesi): reset() eskiden CMC'yi
        # (CameraMotionCompensator) hiç sıfırlamıyordu — önceki videodan kalan
        # prev_gray/prev_pts farklı çözünürlüklü yeni bir videoda boyut
        # uyuşmazlığıyla çöküyordu. Artık her reset() ile CMC de temiz baştan.
        self._states.clear()
        self.tracks.clear()
        self.suspended_tracks.clear()
        self._init_bytetrack()
        self.cmc = CameraMotionCompensator()
        self.reset_generation += 1
        log.info("Tracker sÄ±fÄ±rlandÄ± (CMC dahil).")

    def close(self):
        """
        BUG-FIX: _crop_pool (CropPool ThreadPoolExecutor) hiÃ§bir yerde
        kapatÄ±lmÄ±yordu. Pipeline.release() sadece kendi VLMPool'unu
        (self.executor) shutdown ediyordu; tracker'Ä±n kendi havuzu process
        sonlanana kadar arka planda aÃ§Ä±k kalÄ±yordu (kaynak sÄ±zÄ±ntÄ±sÄ±, ve
        script'in dÃ¼zgÃ¼n Ã§Ä±kÄ±ÅŸÄ±nÄ± geciktirebiliyordu). ArtÄ±k pipeline.release()
        bu metodu da Ã§aÄŸÄ±rÄ±yor.
        """
        try:
            self._crop_pool.shutdown(wait=True)
        except Exception as e:
            log.warning(f"CropPool kapatma hatasÄ±: {e}")

    def update(self, detections: list[RawDetection], frame: np.ndarray = None) -> list[Track]:
        if frame is None:
            frame = np.zeros((64, 64, 3), dtype=np.uint8)

        self._frame_count += 1
        for track in self._states.values():
            track._predicted_this_frame = False

        # Tespit listesini ByteTrack formatÄ±na Ã§evir
        if detections:
            dets_np = np.array(
                [[d.x1, d.y1, d.x2, d.y2, d.confidence, d.class_id]
                 for d in detections],
                dtype=np.float32,
            )
        else:
            dets_np = np.empty((0, 6), dtype=np.float32)

        # [YENÄ°] ByteTrack eÅŸiklerini dinamik gÃ¼ncelle
        # ByteTrack gÃ¼ncelle
        try:
            raw_tracks = self._bt.update(dets_np, frame)
        except Exception as e:
            log.warning(f"ByteTrack.update hatasÄ±: {e}")
            raw_tracks = np.empty((0, 8), dtype=np.float32)

        active_ids: set[int] = set()

        # Kamera Hareketi Ä°ptali (CMC)
        if frame is not None:
            exclude_bboxes = [r[:4] for r in raw_tracks]
            bg_dx, bg_dy = self.cmc.update(frame, exclude_bboxes)
            if abs(bg_dx) > 0.1 or abs(bg_dy) > 0.1:
                for track in self._states.values():
                    track.shift_history(bg_dx, bg_dy)

        # Aktif track'leri iÅŸle
        fh_fr, fw_fr = frame.shape[:2] if frame is not None and frame.ndim == 3 else (1080, 1920)
        for row in raw_tracks:
            x1, y1, x2, y2 = float(row[0]), float(row[1]), float(row[2]), float(row[3])
            track_id        = int(row[4])
            conf            = float(row[5])
            cls             = int(row[6])

            if not _is_sane_detection(x1, y1, x2, y2, conf, cls):
                log.warning(f"ByteTrack track_id={track_id}: geÃ§ersiz satÄ±r atlandÄ±.")
                if track_id in self._states:
                    active_ids.add(track_id)
                continue

            active_ids.add(track_id)

            if track_id in self._states:
                self._states[track_id].update(x1, y1, x2, y2, conf, cls, fw_fr, fh_fr)
                self._states[track_id].suspended = False
            else:
                self._states[track_id] = Track(track_id, x1, y1, x2, y2, conf, cls, fps=self._fps)
                
            # GÃ¶rsel YÃ¶n ve Crop GÃ¼ncellemesi
            if frame is not None and frame.shape[0] > 64:
                try:
                    fh, fw = frame.shape[:2]
                    bw, bh = x2 - x1, y2 - y1
                    # Hedefi sadece kutu kadar kesmek VLM'e ÅŸekil/kanat baÄŸlamÄ±
                    # bÄ±rakmÄ±yordu. OrantÄ±lÄ± ve kÃ¼Ã§Ã¼k hedeflerde piksel tabanlÄ±
                    # boÅŸluk ekleyerek hedefin tamamÄ±nÄ± ve yakÄ±n Ã§evresini koru.
                    pad_x = max(14.0, bw * VLM_CROP_CONTEXT_RATIO)
                    pad_y = max(14.0, bh * VLM_CROP_CONTEXT_RATIO)
                    
                    # Kolaj karesi (384x384) kare olduÄŸu iÃ§in aÅŸÄ±rÄ± geniÅŸ/ince kutularda (120x44 gibi)
                    # alt ve Ã¼stte devasa koyu gri boÅŸluklar oluÅŸuyor ve VLM'in uÃ§aÄŸÄ± net gÃ¶rmesi engelleniyordu.
                    # KÄ±rpma alanÄ±nÄ± 1.5:1 (3:2) en/boy dengesine yaklaÅŸtÄ±rÄ±p resmin ekrana tam doldurmasÄ± saÄŸlandÄ±:
                    tot_w, tot_h = bw + 2 * pad_x, bh + 2 * pad_y
                    if tot_w > 1.5 * tot_h:
                        pad_y += (tot_w / 1.5 - tot_h) / 2.0
                    elif tot_h > 1.5 * tot_w:
                        pad_x += (tot_h / 1.5 - tot_w) / 2.0
                    
                    cx1, cy1 = max(0, int(x1 - pad_x)), max(0, int(y1 - pad_y))
                    cx2, cy2 = min(fw, int(x2 + pad_x)), min(fh, int(y2 + pad_y))
                    
                    if cx2 > cx1 and cy2 > cy1:
                        # BUG-FIX (en kÃ¶tÃ¼ aÃ§Ä± sorunu, devam): Boyut skorunu Ã¼st
                        # sÄ±nÄ±rladÄ±ktan sonra bile, kamera aÅŸÄ±rÄ± yakÄ±nlaÅŸtÄ±ÄŸÄ±nda
                        # (Ã¶r. sadece kuyruk kaplamasÄ± ekranÄ± doldurduÄŸunda) o
                        # bÃ¶lgenin yazÄ±/dekal dokusu Laplacian/kontrastÄ± Ã§ok
                        # yÃ¼ksek Ã§Ä±kÄ±yor ve skor yine kazanÄ±yor â€” ama o kare
                        # uÃ§aÄŸÄ±n SADECE bir parÃ§asÄ±nÄ± (kuyruk vb.) gÃ¶steriyor,
                        # tÃ¼m gÃ¶vdeyi deÄŸil. Bunu yakalamak iÃ§in iki sinyal
                        # hesaplayÄ±p crop buffer'a iletiyoruz:
                        #   is_clipped  â†’ tespit kutusu kare kenarÄ±na deÄŸiyor mu
                        #                 (uÃ§aÄŸÄ±n bir kÄ±smÄ± gÃ¶rÃ¼ntÃ¼ dÄ±ÅŸÄ±nda kaldÄ±)
                        #   area_ratio  â†’ kutu, kare alanÄ±nÄ±n ne kadarÄ±nÄ± kaplÄ±yor
                        #                 (Ã§ok bÃ¼yÃ¼kse = aÅŸÄ±rÄ± yakÄ±n/kÄ±rpÄ±lmÄ±ÅŸ olabilir)
                        is_clipped = (
                            x1 <= EDGE_MARGIN_PX or y1 <= EDGE_MARGIN_PX or
                            x2 >= (fw - EDGE_MARGIN_PX) or y2 >= (fh - EDGE_MARGIN_PX)
                        )
                        area_ratio = float((bw * bh) / max(1.0, fw * fh))

                        # Prensip 1 (Maximum Speed): Kesme iÅŸlemini ve netlik testini main thread'i engellemeden asenkron havuza at!
                        crop = frame[cy1:cy2, cx1:cx2].copy()
                        # BUG-FIX: 'conf' burada o KAREYE ait ByteTrack gÃ¼veni
                        # (yukarÄ±da row[5]'ten alÄ±ndÄ±) â€” async worker'Ä±n
                        # ileride okuyacaÄŸÄ±, o sÄ±rada deÄŸiÅŸmiÅŸ olabilecek
                        # self.confidence yerine bu anlÄ±k deÄŸer donduruluyor.
                        self._crop_pool.submit(
                            self._async_process_crop, track_id, crop,
                            is_clipped, area_ratio, conf
                        )
                except Exception:
                    pass

        # Oklusyon kurtarma
        lost_stracks = getattr(self._bt, 'lost_stracks', [])
        coasting_ids: set[int] = set()

        for strack in lost_stracks:
            tid = int(getattr(strack, 'id', strack.track_id))
            if tid == 0:
                continue
            
            # [DEÄÄ°ÅT] SUSPENDED_AGE kullan (MAX_AGE deÄŸil)
            if strack.time_since_update > KALMAN_SUSPENDED_AGE:
                continue

            coasting_ids.add(tid)

            if tid in self._states:
                try:
                    xyxy = strack.xyxy
                    self._states[tid].bbox = np.array(
                        [float(xyxy[0]), float(xyxy[1]),
                         float(xyxy[2]), float(xyxy[3])],
                        dtype=np.float32
                    )
                    self._states[tid].suspended = True
                    self._states[tid].suspended_streak += 1
                    # BUG-FIX (kutu havada geziniyor): tespit kaybolduÄŸunda
                    # KF'in DOÄRUSAL HIZ MODELÄ° hedef gerÃ§ekte manevra/dÃ¶nÃ¼ÅŸ
                    # yapÄ±yorsa gerÃ§ek konumdan hÄ±zla sapar ("uÃ§aÄŸÄ±n gittiÄŸi
                    # yerle alakasÄ± yok" gÃ¶rÃ¼ntÃ¼sÃ¼). Coasting sÃ¼rdÃ¼kÃ§e hÄ±z
                    # tahmini kademeli sÃ¶nÃ¼mlenir â€” yeniden tespit gelmezse
                    # kutu sonsuza dek bir yÃ¶ne "kaÃ§mak" yerine yavaÅŸÃ§a durur.
                    _kf = self._states[tid]._kf
                    _kf.statePost[2, 0] *= 0.85
                    _kf.statePost[3, 0] *= 0.85
                    self._states[tid].predict()
                    active_ids.add(tid)
                except Exception:
                    pass

        # Ã–lÃ¼ track'leri temizle
        dead_ids = set(self._states.keys()) - active_ids
        for tid in dead_ids:
            del self._states[tid]

        # Hayalet kutu Ã¶nleme + DEEPSORT TARZI KÄ°MLÄ°K & GÃ–RÃœNÃœM DEVRÄ°
        # Ani manevra veya 0.5s+ kesinti anÄ±nda nesne ekranda uzaÄŸa kayabilir. SÄ±rf mesafeye (200px)
        # bakarsak baÄŸ kayarak yeni kutu aÃ§Ä±lÄ±r. 16x16 gÃ¶rsel imza (appearance embedding)
        # ve kinematik tahmini birleÅŸtirerek 450px mesafeye kadar kimlik bÃ¼tÃ¼nlÃ¼ÄŸÃ¼nÃ¼ koruruz.
        active_only_ids = active_ids - coasting_ids
        for coast_tid in list(coasting_ids):
            if coast_tid not in self._states:
                continue
            coast_track = self._states[coast_tid]
            coast_pos = coast_track.position

            best_tid = None
            best_score = float("inf")
            
            for act_tid in active_only_ids:
                if act_tid not in self._states:
                    continue
                act_track = self._states[act_tid]
                act_pos = act_track.position
                
                dist = float(np.linalg.norm(coast_pos - act_pos))
                if dist > 450.0:
                    continue

                # BUG-FIX (KRÄ°TÄ°K â€” "dev kutu" / uzak-farklÄ±-boyuttaki iki
                # tespitin yanlÄ±ÅŸlÄ±kla birleÅŸmesi): Eskiden yalnÄ±zca mesafe +
                # gÃ¶rsel imza + en/boy farkÄ±na bakÄ±lÄ±yordu â€” kutularÄ±n
                # BOYUTU hiÃ§ karÅŸÄ±laÅŸtÄ±rÄ±lmÄ±yordu. Split-screen/kolaj gibi
                # aynÄ± gÃ¶rsel iÃ§eriÄŸin tekrarlandÄ±ÄŸÄ± (Ã¶r. iki ayrÄ± kadranda
                # aynÄ± pilot fotoÄŸrafÄ±) sahnelerde gÃ¶rsel imza yanÄ±ltÄ±cÄ±
                # biÃ§imde birbirine Ã§ok benzer Ã§Ä±kabiliyor, ve <1.5sn'lik
                # okluzyon penceresinde gerÃ§ek bir hedefin gÃ¶rÃ¼nÃ¼r boyutu bu
                # kadar keskin deÄŸiÅŸmez. Boyutu (alanÄ±) 3 kattan fazla farklÄ±
                # olan iki track artÄ±k ASLA birleÅŸtirilmiyor â€” bu, yanlÄ±ÅŸlÄ±kla
                # kÃ¼Ã§Ã¼k bir track'in Ã§ok bÃ¼yÃ¼k bir track'e "yapÄ±ÅŸÄ±p" onun
                # dev kutusunu devralmasÄ±nÄ± (merge_from â†’ _ema_bbox devri)
                # engeller.
                coast_area = max(1.0, float(np.prod(coast_track.bbox[2:4] - coast_track.bbox[0:2])))
                act_area = max(1.0, float(np.prod(act_track.bbox[2:4] - act_track.bbox[0:2])))
                area_ratio = max(coast_area, act_area) / min(coast_area, act_area)
                if area_ratio > 3.0:
                    continue

                vis_diff = dist * 0.3
                ar_diff = 0.0
                coast_recent = coast_track._most_recent_crops(1)
                act_recent = act_track._most_recent_crops(1)
                if coast_recent and act_recent:
                    try:
                        _, _, _, (old_ar, old_gray) = coast_recent[0]
                        _, _, _, (new_ar, new_gray) = act_recent[0]
                        vis_diff = float(np.sqrt(np.mean((old_gray - new_gray) ** 2))) * 220.0
                        ar_diff = abs(old_ar - new_ar) / max(0.1, old_ar, new_ar) * 40.0
                    except Exception:
                        pass
                
                total_cost = dist * 0.4 + vis_diff + ar_diff
                if total_cost < best_score and total_cost < 280.0:
                    best_score = total_cost
                    best_tid = act_tid

            if best_tid is not None:
                self._states[best_tid].merge_from(self._states[coast_tid])
                del self._states[coast_tid]
                coasting_ids.discard(coast_tid)

        # Bir sonraki karede slicer'a verilecek ROI ipuÃ§larÄ± bir kare ileri
        # Kalman tahmininden gelsin; yalnÄ±z son gÃ¶zlenen kutu kullanÄ±lmasÄ±n.
        for track in self._states.values():
            track.predict()

        # Pipeline hint sistemleri iÃ§in listeleri gÃ¼ncelle
        self.tracks = list(self._states.values())
        self.suspended_tracks = [
            self._states[tid] for tid in coasting_ids
            if tid in self._states
        ]

        # â”€â”€ FÄ°LTRELEME â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        # AmaÃ§: Ne Ã§ok katÄ± (gerÃ§ek uÃ§aÄŸÄ± kaÃ§Ä±rma) ne Ã§ok gevÅŸek (yaprak geÃ§irme)
        valid: list[Track] = []
        for track in self._states.values():

            # 1. OnaylanmamÄ±ÅŸ track: henÃ¼z KALMAN_MIN_HITS kadar gÃ¶rÃ¼lmemiÅŸ â†’ geÃ§
            if not track.is_confirmed:
                continue
                
            # 1.5 VLM Kesin Reddi: EÄŸer VLM bunun kask, kokpit, insan veya yazÄ± olduÄŸunu 
            # kesin olarak sÃ¶ylediyse (veya gÃ¶rsel olarak anladÄ±ysa), bu track kesinlikle 
            # bir false-positive'dir. AnÄ±nda sil/gÃ¶rmezden gel.
            if track.vlm_class and isinstance(track.vlm_class, str):
                val = track.vlm_class.lower()
                is_false_positive = any(w in val for w in ("kask", "insan", "kokpit", "yazi", "ui", "hud", "bulut"))
                if is_false_positive:
                    continue

            # 2. HÄ±z filtresi: MIN_SPEED_CHECK_HITS frame sonra devreye girer.
            #    YavaÅŸ hareket = yaprak/leke olabilir.
            #    Ä°stisna: Uzakta, uzun sÃ¼redir takip edilen â†’ hovering Ä°HA olabilir.
            # BUG-FIX (boÅŸluÄŸu uzun sÃ¼re Ä°HA sanma): Eskiden "uzak hedef +
            # >10 hit" TEK BAÅINA yeterliydi ve anlÄ±k hÄ±z filtresini (
            # MIN_SPEED_PX_S) TAMAMEN atlÄ±yordu. Bu, sabit duran bir gÃ¶kyÃ¼zÃ¼/
            # bulut/parazit hayaletinin "uzak + uzun sÃ¼redir gÃ¶rÃ¼lÃ¼yor"
            # ÅŸartÄ±nÄ± (10 kareden sonra) kolayca saÄŸlayÄ±p sÃ¼resiz biÃ§imde
            # ekranda kalmasÄ±na izin veriyordu. ArtÄ±k istisna yalnÄ±zca hedef
            # GERÃ‡EKTEN dÃ¼nya Ã§erÃ§evesinde anlamlÄ± bir yol kat etmiÅŸse
            # (dÃ¶nerek/manevra ederek de olsa) VEYA VLM baÄŸÄ±msÄ±z olarak hava
            # aracÄ± olduÄŸunu onaylamÄ±ÅŸsa geÃ§erli sayÄ±lÄ±r.
            if track.hits > MIN_SPEED_CHECK_HITS and track.speed_px_s < MIN_SPEED_PX_S:
                path_len = track.world_path_length(WORLD_PATH_WINDOW_S)
                vlm_confirmed_aircraft = (
                    isinstance(track.vlm_class, str) and
                    any(w in track.vlm_class.lower()
                        for w in ("sabit_kanat", "iha", "ucak", "helikopter", "hava_araci"))
                )
                really_moving = path_len >= (MIN_WORLD_PATH_PX_PER_S * WORLD_PATH_WINDOW_S)
                if track.is_far_target and track.hits > 10 and (really_moving or vlm_confirmed_aircraft):
                    pass   # GerÃ§ekten hareket ettiÄŸi doÄŸrulanmÄ±ÅŸ (veya VLM onaylÄ±) hovering hedef â†’ koru
                else:
                    continue

            valid.append(track)

        return valid
