# ============================================================
# slicer.py — Akıllı Üç Geçişli SAHI Motoru
# ============================================================
# Teknofest Savaşan İHA yarışmasına uygun, uzak/küçük hedefleri
# kaçırmayan, yakın hedeflerde sahte pozitif üretmeyen tespit motoru.
#
# ÜÇ GEÇİŞLİ MİMARİ:
#   Pass-1 : Hızlı ön tarama (düşük çözünürlük, düşük conf)
#   Pass-2 : ROI'ler üzerinde yüksek çözünürlüklü SAHI
#   Fallback: Pass-1 + hint boş dönerse tam frame grid tarama
#
# ÇÖZÜLEN SORUNLAR:
#   1. Pass-1 boşsa frame tamamen atlanıyordu → Fallback eklendi
#   2. _batch_infer CONFIDENCE ile çalışıyordu → FAR_TARGET_MIN_CONF
#   3. Varyans filtresi uzak hedefleri siliyordu → Eşik düşürüldü
# ============================================================

import cv2
import logging
import numpy as np
from ultralytics import YOLO
from dataclasses import dataclass
from src.config import (
    SLICE_H, SLICE_W, OVERLAP, NMS_IOU, BATCH_SIZE,
    VARIANCE_THRESHOLD, PASS1_SIZE, PASS1_CONF, PASS1_EXPAND_PX,
    ROI_EXPAND, CONFIDENCE, DEVICE,
    FAR_TARGET_MIN_CONF, FAR_TARGET_AREA_RATIO,
    MIN_OBJECT_PX, MAX_OBJECT_AREA_RATIO, ASPECT_RATIO_MIN, ASPECT_RATIO_MAX,
    FULLSCAN_FALLBACK, FULLSCAN_STRIDE, FULLSCAN_ALWAYS, FULLSCAN_SKIP_FRAMES,
    FRAGMENT_MERGE_GAP_RATIO, FRAGMENT_MERGE_MAX_GAP_PX, FRAGMENT_MAX_MERGE_INPUT_PX,
)

log = logging.getLogger(__name__)


@dataclass
class RawDetection:
    """Tek bir YOLO tespiti: koordinatlar + güven + sınıf."""
    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float
    class_id: int

    @property
    def cx(self) -> float: return (self.x1 + self.x2) / 2
    @property
    def cy(self) -> float: return (self.y1 + self.y2) / 2
    @property
    def w(self) -> float: return self.x2 - self.x1
    @property
    def h(self) -> float: return self.y2 - self.y1
    @property
    def area(self) -> float: return self.w * self.h

    def is_valid_geometry(self, frame_w: int, frame_h: int) -> bool:
        """Geometrik olarak mantıklı bir tespit mi?"""
        if self.w < MIN_OBJECT_PX or self.h < MIN_OBJECT_PX:
            return False
        if self.area / (frame_w * frame_h) > MAX_OBJECT_AREA_RATIO:
            return False
        aspect = self.w / max(self.h, 1e-6)
        
        # BUG-FIX: Eskiden uzak/yakın hedefler için ayrı ayrı ve hardcoded olarak
        # 0.5 - 7.0 ile ASPECT_RATIO_MIN - 3.5 sınırları kullanılıyordu. Bu da dikey
        # dalış yapan (kılıç şeklindeki) İHA'ların (ör. aspect ratio 0.15) elenmesine
        # sebep oluyordu. Artık config'teki devasa sınırlarla (0.10 - 10.0)
        # hem yakın hem uzak hedefler toleranslı şekilde geçiyor!
        if aspect < ASPECT_RATIO_MIN or aspect > ASPECT_RATIO_MAX:
            return False
                
        return True

    def is_far_target(self, frame_w: int, frame_h: int) -> bool:
        """Frame alanına göre uzak hedef mi?"""
        return self.area / (frame_w * frame_h) < FAR_TARGET_AREA_RATIO


# ──────────────────────────────────────────────────────────────
# YARDIMCI: IoU ve NMS
# ──────────────────────────────────────────────────────────────
def _compute_iou(box: np.ndarray, boxes: np.ndarray) -> np.ndarray:
    ix1 = np.maximum(box[0], boxes[:, 0])
    iy1 = np.maximum(box[1], boxes[:, 1])
    ix2 = np.minimum(box[2], boxes[:, 2])
    iy2 = np.minimum(box[3], boxes[:, 3])
    inter = np.maximum(0, ix2 - ix1) * np.maximum(0, iy2 - iy1)
    area_box   = (box[2] - box[0]) * (box[3] - box[1])
    area_boxes = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
    union = area_box + area_boxes - inter
    return inter / (union + 1e-6)


def _nms(detections: list[RawDetection], iou_thr: float, ioa_thr: float = 0.40) -> list[RawDetection]:
    """Sınıf-agnostik Non-Maximum Suppression + İç İçe Geçme (IoA) Engeli."""
    if not detections:
        return []
    boxes  = np.array([[d.x1, d.y1, d.x2, d.y2] for d in detections])
    scores = np.array([d.confidence for d in detections])
    order  = np.argsort(scores)[::-1]
    keep   = []
    while order.size > 0:
        i = order[0]
        
        # --- V3 Center-in-Box Koruması (Küçük kutunun merkezi büyük kutunun içindeyse acımasızca yut) ---
        is_i_suppressed = False
        suppress_center = np.zeros(order.size - 1, dtype=bool)
        
        cx_i = (boxes[i, 0] + boxes[i, 2]) / 2.0
        cy_i = (boxes[i, 1] + boxes[i, 3]) / 2.0
        area_box = (boxes[i, 2] - boxes[i, 0]) * (boxes[i, 3] - boxes[i, 1])
        
        if order.size > 1:
            for j_idx, j in enumerate(order[1:]):
                cx_j = (boxes[j, 0] + boxes[j, 2]) / 2.0
                cy_j = (boxes[j, 1] + boxes[j, 3]) / 2.0
                area_j = (boxes[j, 2] - boxes[j, 0]) * (boxes[j, 3] - boxes[j, 1])
                
                i_in_j = (boxes[j, 0] <= cx_i <= boxes[j, 2]) and (boxes[j, 1] <= cy_i <= boxes[j, 3])
                j_in_i = (boxes[i, 0] <= cx_j <= boxes[i, 2]) and (boxes[i, 1] <= cy_j <= boxes[i, 3])
                
                if j_in_i and area_j <= area_box:
                    suppress_center[j_idx] = True
                elif i_in_j and area_box <= area_j:
                    is_i_suppressed = True
                    break
                    
        if is_i_suppressed:
            # BUG-FIX: i'yi suppress eden j kutusunu garanti koru.
            # Eskiden j hiçbir listeye eklenmeden i siliniyordu —
            # j de sonra suppress edilebiliyordu ve her iki tespit kayboluyordu.
            keep.append(j)
            # j'yi ve i'yi order'dan çıkar (tekrar işlenmesin)
            mask = np.ones(order.size, dtype=bool)
            mask[0] = False  # i'yi çıkar
            for k_idx in range(1, order.size):
                if order[k_idx] == j:
                    mask[k_idx] = False
                    break
            order = order[mask]
            continue
        # --- V3 Center-in-Box Koruması Bitişi ---
        
        keep.append(i)
        if order.size == 1:
            break
            
        ix1 = np.maximum(boxes[i, 0], boxes[order[1:], 0])
        iy1 = np.maximum(boxes[i, 1], boxes[order[1:], 1])
        ix2 = np.minimum(boxes[i, 2], boxes[order[1:], 2])
        iy2 = np.minimum(boxes[i, 3], boxes[order[1:], 3])
        inter = np.maximum(0, ix2 - ix1) * np.maximum(0, iy2 - iy1)
        
        area_boxes = (boxes[order[1:], 2] - boxes[order[1:], 0]) * (boxes[order[1:], 3] - boxes[order[1:], 1])
        union = area_box + area_boxes - inter
        
        ious  = inter / (union + 1e-6)
        
        # İç içe geçme kontrolü (IoA): Kesişim alanı, KÜÇÜK olanın alanına bölünür.
        min_areas = np.minimum(area_box, area_boxes)
        max_areas = np.maximum(area_box, area_boxes)
        ioas = inter / (min_areas + 1e-6)
        
        # KORUMA: Eğer küçük kutu (ör. uzak gerçek uçak), büyük kutunun (ör. devasa 
        # UI halüsinasyonu) %1'inden bile küçükse, IoA bastırmasını UYGULAMA! 
        area_ratios = min_areas / (max_areas + 1e-6)
        suppress_ioa = (ioas > ioa_thr) & (area_ratios > 0.01)
        
        # Eğer IoU eşiği aşılırsa VEYA korumalı IoA şartı sağlanırsa VEYA merkez-içinde kuralı varsa yoksay.
        suppress = (ious > iou_thr) | suppress_ioa | suppress_center
        order = order[np.where(~suppress)[0] + 1]
    return [detections[k] for k in keep]


def _merge_aircraft_fragments(
    detections: list[RawDetection], frame_w: int, frame_h: int
) -> list[RawDetection]:
    """Aynı hedefin birbirine yakın gövde/kanat kutularını tek kutuda birleştir.

    Birleştirme yalnız uçak/drone sınıfları ve yakın, aynı eksendeki kutular için
    yapılır; uzaktaki iki bağımsız hedefin yanlışlıkla birleşmesini önler.

    BUG-FIX (arada 2-3 kutu + anlık "KUŞ" etiketi): SAHI patch sınırları aynı
    fiziksel hedefi (uçak/İHA) ikiye bölebiliyor; komşu patch'ler bu parçaları
    FARKLI sınıflarla etiketleyebiliyor (örn. kanadın bir kısmı class_3/İHA,
    gövdenin bir kısmı yanlışlıkla class_1/kuş çıkabiliyor — kuşa benzeyen
    kısmi siluet). Eski kod yalnızca class_id==2 olan kutuları birbirine
    birleştirmeye çalışıyordu: {2} kümesi dışındaki (örn. kuş) parça anında
    "merged" listesine ekleniyor, hiç birleşme denenmiyordu. Sonuç: AYNI
    hedef için biri "İHA", biri "KUŞ" etiketli, birbirine yakın İKİ AYRI ham
    tespit NMS'e (IoU eşiği düşük kalabiliyor çünkü fiziksel olarak
    çakışmayan komşu parçalar) hayalet ikinci bir track ve anlık "KUŞ"
    rozeti olarak sızıyordu.
    Artık kuş(1) ve İHA(2) parçaları BİRLİKTE değerlendiriliyor, ama
    kuş+kuş (iki ayrı gerçek kuş) asla birleştirilmiyor — yalnızca
    grupta en az bir İHA(2) parçası varsa birleşme denenir. Birleşen
    kutunun sınıfı, en yüksek güvenli parçanın sınıfını korur (aşağıdaki
    `remaining` zaten güvene göre azalan sırada, `base` her zaman o anki
    en yüksek güvenli parça).

    BUG-FIX (KRİTİK — "dev kutu" / ekranı kaplayan hayalet kutu): Eskiden
    birleştirme kararı SADECE oransal boşluğa (FRAGMENT_MERGE_GAP_RATIO)
    bakıyordu. Parçalardan biri zaten büyükse, bu oran yüzlerce piksellik
    bir boşluğu bile "yakın" sayabiliyordu. Çoklu-panel / split-screen /
    kolaj görüntülerde (ör. 2x2 kokpit ızgarası, üst üste yayın grafikleri)
    komşu panolar TAM OLARAK bitişiktir (gap≈0) ve her ikisinde de benzer
    şekiller yanlış pozitif üretebiliyor — birbirinden tamamen bağımsız iki
    tespit, sırf x/y hizalı ve "oransal olarak yakın" sayıldığı için TEK,
    DEV bir kutuya (ör. ekranın iki kadranını birden kaplayan kutu)
    birleştiriliyordu. Artık İKİ ek güvenlik katmanı var:
      1. Mutlak piksel tavanı (FRAGMENT_MERGE_MAX_GAP_PX) — gövde/kanat
         parçaları gerçekte birkaç on piksel arayla bulunur, asla yüzlerce
         piksel değil. Oran VE mutlak tavan AYNI ANDA sağlanmalı.
      2. Birleşim SONRASI geometri doğrulaması — aday birleşik kutu
         is_valid_geometry() (MAX_OBJECT_AREA_RATIO, ASPECT_RATIO_MIN/MAX)
         ile tekrar kontrol edilir. Doğrulamayı geçemezse birleştirme iptal
         edilir, iki parça birbirinden AYRI tespit olarak kalır — hiçbir
         zaman ekranı kaplayan saçma bir kutu üretilmez.
    """
    remaining = sorted(detections, key=lambda d: d.confidence, reverse=True)
    merged: list[RawDetection] = []
    # BUG-6 Düzeltmesi: Model yalnızca 3 sınıf üretiyor (0=kite, 1=bird, 2=drone/uav).
    # {2,3,4} kümesindeki 3 ve 4 hiçbir zaman eşleşmiyordu.
    mergeable_classes = {1, 2}
    while remaining:
        base = remaining.pop(0)
        if base.class_id not in mergeable_classes:
            merged.append(base)
            continue
        keep: list[RawDetection] = []
        for other in remaining:
            if other.class_id not in mergeable_classes:
                keep.append(other)
                continue
            # İki ayrı gerçek kuş (class 1 + class 1) asla birleştirilmez —
            # yalnızca en az bir taraf class 2 (İHA/drone) ise parça sayılır.
            if base.class_id == 1 and other.class_id == 1:
                keep.append(other)
                continue
            # BUG-FIX (KRİTİK — "dev kutu", 2. katman): iki bitişik panel/
            # kadran arasında gap fiziksel olarak 0 olabileceğinden, gap
            # tavanı tek başına yetmez. Parçalardan biri zaten büyükse
            # (bir "parça" olamayacak kadar büyük — bkz. config.py
            # FRAGMENT_MAX_MERGE_INPUT_PX yorumu) birleştirmeye aday bile
            # sayılmaz.
            if (base.w > FRAGMENT_MAX_MERGE_INPUT_PX or base.h > FRAGMENT_MAX_MERGE_INPUT_PX or
                    other.w > FRAGMENT_MAX_MERGE_INPUT_PX or other.h > FRAGMENT_MAX_MERGE_INPUT_PX):
                keep.append(other)
                continue
            horizontal_gap = max(0.0, max(base.x1, other.x1) - min(base.x2, other.x2))
            vertical_gap = max(0.0, max(base.y1, other.y1) - min(base.y2, other.y2))
            x_aligned = abs(base.cx - other.cx) <= max(base.w, other.w) * FRAGMENT_MERGE_GAP_RATIO
            y_aligned = abs(base.cy - other.cy) <= max(base.h, other.h) * FRAGMENT_MERGE_GAP_RATIO
            near_horizontal = (
                horizontal_gap <= max(base.w, other.w) * FRAGMENT_MERGE_GAP_RATIO
                and horizontal_gap <= FRAGMENT_MERGE_MAX_GAP_PX
                and y_aligned
            )
            near_vertical = (
                vertical_gap <= max(base.h, other.h) * FRAGMENT_MERGE_GAP_RATIO
                and vertical_gap <= FRAGMENT_MERGE_MAX_GAP_PX
                and x_aligned
            )
            if near_horizontal or near_vertical:
                candidate = RawDetection(
                    min(base.x1, other.x1), min(base.y1, other.y1),
                    max(base.x2, other.x2), max(base.y2, other.y2),
                    max(base.confidence, other.confidence), base.class_id,
                )
                # Birleşim sonrası geometri sağlıklı değilse (ör. dev/saçma
                # bir kutu doğurmuşsa) birleştirmeyi iptal et — parçalar
                # ayrı ayrı kalsın, "en kötü ihtimalde" ikinci bir kutu
                # görürüz, ASLA ekranı kaplayan hayalet bir kutu değil.
                if candidate.is_valid_geometry(frame_w, frame_h):
                    base = candidate
                else:
                    keep.append(other)
            else:
                keep.append(other)
        remaining = keep
        merged.append(base)
    return merged


def _dedupe_overlapping_targets(detections: list[RawDetection], ioa_thr: float = 0.55) -> list[RawDetection]:
    """
    BUG-FIX (KRİTİK — aynı uçağa 2 kalıcı kutu/ID): _nms()'teki merkez-içi
    koruma ve _merge_aircraft_fragments()'teki FRAGMENT_MAX_MERGE_INPUT_PX
    (150px) boyut tavanı, YAKIN PLANDA çekilmiş büyük uçak kutularını
    (genişlik/yükseklik kolayca 150px'i aşıyor) birleştirme adaylığından
    TAMAMEN dışlıyordu. Model aynı fiziksel uçak üzerinde "tüm gövde"
    (büyük) ve "kokpit/burun" (küçük, kısmen taşan) gibi iki ayrı ham
    tespit ürettiğinde — bu ikisi boyut farkı yüzünden IoU eşiğini
    (NMS_IOU=0.20) geçemiyor VE küçük kutunun merkezi büyük kutunun
    tam içinde olmayabiliyor (taşma payı) — hem NMS hem parça-birleştirme
    atlanıyor, sonuç iki ayrı, kalıcı ByteTrack ID'si (ekranda iki kutu)
    oluyordu. Bu son, boyut sınırı OLMAKSIZIN çalışan katman, yalnızca
    "küçük kutu ne kadar diğerinin içine gömülü" (IoA = kesişim / küçük
    kutunun alanı) sorusuna bakar; eşik aşılırsa küçük/düşük-güvenli kutu
    elenir. Sınıf farkı (kuş/İHA) kasıtlı olarak ÖNEMSENMİYOR çünkü aynı
    uçağın bir parçası bazen yanlışlıkla farklı sınıfa da düşebiliyordu.
    """
    if len(detections) < 2:
        return detections
    ordered = sorted(detections, key=lambda d: (d.area, d.confidence), reverse=True)
    keep: list[RawDetection] = []
    for cand in ordered:
        dropped = False
        for kept in keep:
            ix1 = max(cand.x1, kept.x1)
            iy1 = max(cand.y1, kept.y1)
            ix2 = min(cand.x2, kept.x2)
            iy2 = min(cand.y2, kept.y2)
            inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
            if inter <= 0.0:
                continue
            ioa = inter / max(1.0, min(cand.area, kept.area))
            if ioa >= ioa_thr:
                dropped = True
                break
        if not dropped:
            keep.append(cand)
    return keep


# ──────────────────────────────────────────────────────────────
# ANA SINIF
# ──────────────────────────────────────────────────────────────
class SmartSlicer:
    """
    Üç geçişli, varyans filtreli, çift eşikli, GPU batch destekli
    SAHI motoru. Uzak hedefleri kaçırmaz, yakın sahte pozitifleri eler.
    """

    def __init__(self, model_path: str):
        self.model = YOLO(model_path)
        self.model.to(DEVICE)
        # BUG-FIX (boşluğu uzun süre İHA sanma): FULLSCAN_ALWAYS her karede
        # tüm frame'i zayıf eşikle taradığı için, aktif takip varken bile
        # sürekli arka plan gürültüsü üretiyordu. Bu sayaç, hint varken tam
        # taramayı FULLSCAN_SKIP_FRAMES karede birine seyreltmek için kullanılır.
        self._frame_counter = 0

    # ──────────────────────────────────────────────────────────
    # ANA TESPİT FONKSİYONU
    # ──────────────────────────────────────────────────────────
    def detect(
        self,
        frame: np.ndarray,
        hint_positions: list[tuple[float, float]] = None
    ) -> list[RawDetection]:
        frame_h, frame_w = frame.shape[:2]
        self._frame_counter += 1

        # ======================================================
        # PASS-1: Hızlı düşük çözünürlüklü ön tarama
        # ======================================================
        rois = self._pass1_scan(frame, frame_w, frame_h)

        # ======================================================
        # TRACKER HINT ROI'LARI
        # Tracker'dan gelen Kalman tahmin pozisyonları etrafında ROI aç
        # ======================================================
        # Tracker'dan gelen Kalman tahmin pozisyonları etrafında ROI aç
        if hint_positions:
            HINT_ROI_PX = 200  # BUG-FIX: 150 → 200, hızlı manevra yapan hedef 150px'ten fazla kayabilir
            for (hcx, hcy) in hint_positions:
                rx1 = max(0, int(hcx - HINT_ROI_PX))
                ry1 = max(0, int(hcy - HINT_ROI_PX))
                rx2 = min(frame_w, int(hcx + HINT_ROI_PX))
                ry2 = min(frame_h, int(hcy + HINT_ROI_PX))
                if (rx2 - rx1) > 50 and (ry2 - ry1) > 50:
                    rois.append((rx1, ry1, rx2, ry2))

        # ======================================================
        # ROI BİRLEŞTİRME (PERFORMANS İÇİN)
        # ======================================================
        merged_rois = []
        for r in rois:
            x1, y1, x2, y2 = r
            merged = False
            for i, mr in enumerate(merged_rois):
                mx1, my1, mx2, my2 = mr
                # Eğer iki ROI kesişiyorsa birleştir
                if not (x2 < mx1 or x1 > mx2 or y2 < my1 or y1 > my2):
                    new_roi = (min(x1, mx1), min(y1, my1), max(x2, mx2), max(y2, my2))
                    # BUG-FIX (ROI birleştirme patlaması): Zincirleme birleşme
                    # A∩B + B∩C → tüm frame tek dev ROI yapabiliyordu.
                    # Birleşik alan, bileşenlerin en büyüğünün 3x'ini aşarsa reddet.
                    orig_area = max((x2 - x1) * (y2 - y1), (mx2 - mx1) * (my2 - my1))
                    new_area = (new_roi[2] - new_roi[0]) * (new_roi[3] - new_roi[1])
                    if new_area <= orig_area * 3.0:
                        merged_rois[i] = new_roi
                        merged = True
                        break
            if not merged:
                merged_rois.append(r)
        
        rois = merged_rois

        # ======================================================
        # FALLBACK: Pass-1 + hint boş → tam frame grid tarama
        # Bu olmadan uzak hedeflerin ilk tespiti imkansızdı!
        # ======================================================
        # Ön tarama bir yerde zayıf/yanlış bir aday bulduğunda eski akış
        # yalnız o ROI'yi inceliyordu. Yüksek çözünürlükte gerçek hedef başka
        # bir patch'te kaldığında bu doğrudan kaçırma sebebidir.
        # BUG-FIX (boşluğu uzun süre İHA sanma): Zaten takip edilen (hint
        # verilen) bir hedef varken HER karede tüm frame'i zayıf eşikle
        # tekrar taramak, arka plandaki düşük-varyanslı gürültünün sürekli
        # yeniden bulunup yeni hayalet track'ler açmasının başlıca
        # kaynağıydı. Hiç hint yokken (ilk kilitlenme öncesi, azami recall
        # şart) her karede tam tarama sürer; hint varken tam tarama yalnızca
        # her FULLSCAN_SKIP_FRAMES karede bir tekrarlanır — periyodik "başka
        # yeni hedef var mı?" kontrolü olarak görevini sürdürür.
        if FULLSCAN_ALWAYS:
            if not hint_positions or (self._frame_counter % FULLSCAN_SKIP_FRAMES == 0):
                rois.extend(self._fullscan_grid(frame_w, frame_h))
        elif not rois and FULLSCAN_FALLBACK:
            rois = self._fullscan_grid(frame_w, frame_h)

        if not rois:
            return []

        # ======================================================
        # PASS-2: ROI'ler üzerinde yüksek çözünürlüklü SAHI
        # ======================================================
        all_detections: list[RawDetection] = []
        for (rx1, ry1, rx2, ry2) in rois:
            roi_img = frame[ry1:ry2, rx1:rx2]
            roi_dets = self._sahi_on_region(roi_img, offset_x=rx1, offset_y=ry1)
            for det in roi_dets:
                if det.is_valid_geometry(frame_w, frame_h):
                    all_detections.append(det)

        # NMS uygula
        nms_dets = _merge_aircraft_fragments(_nms(all_detections, NMS_IOU), frame_w, frame_h)
        # BUG-FIX (aynı uçağa 2 kutu): boyut sınırı olmayan son temizlik katmanı.
        nms_dets = _dedupe_overlapping_targets(nms_dets)

        # ======================================================
        # ÇİFT EŞİKLİ GÜVEN FİLTRESİ
        # Uzak hedefler düşük conf ile geçer, yakın hedefler yüksek conf ister
        # ======================================================
        final_dets = []
        for det in nms_dets:
            # BUG-FIX (savunma katmanı): _merge_aircraft_fragments() artık
            # kendi içinde is_valid_geometry() ile doğruluyor, ama olası bir
            # gelecekteki değişiklik/regresyon için burada da tekrar
            if not det.is_valid_geometry(frame_w, frame_h):
                continue
            if det.is_far_target(frame_w, frame_h):
                if det.confidence >= FAR_TARGET_MIN_CONF:
                    final_dets.append(det)
            else:
                if det.confidence >= CONFIDENCE:
                    final_dets.append(det)

        return final_dets

    # ──────────────────────────────────────────────────────────
    # PASS-1: Hızlı ön tarama
    # ──────────────────────────────────────────────────────────
    def _pass1_scan(self, frame: np.ndarray, frame_w: int, frame_h: int) -> list[tuple]:
        """
        Frame'i küçültüp hızlı YOLO ile şüpheli bölgeleri bul.

        LETTERBOX (en/boy oranı korunur): Eskiden cv2.resize(frame,
        (PASS1_SIZE, PASS1_SIZE)) doğrudan kareye SIKIŞTIRIYORDU — 16:9
        veya dikey bir görüntüde bu, uçağın şeklini deforme edip YOLO'nun
        tanımasını zorlaştırıyordu. Şimdi uzun kenar PASS1_SIZE'a
        ölçeklenir, kısa kenar siyah ile doldurulur (padding), böylece
        nesnenin gerçek en/boy oranı korunur.
        """
        scale = PASS1_SIZE / max(frame_w, frame_h)
        new_w = max(1, int(round(frame_w * scale)))
        new_h = max(1, int(round(frame_h * scale)))
        resized = cv2.resize(frame, (new_w, new_h))

        pad_x = (PASS1_SIZE - new_w) // 2
        pad_y = (PASS1_SIZE - new_h) // 2
        small = np.full((PASS1_SIZE, PASS1_SIZE, 3), 114, dtype=np.uint8)
        small[pad_y:pad_y + new_h, pad_x:pad_x + new_w] = resized

        p1_results = self.model(
            small, conf=PASS1_CONF, device=DEVICE, verbose=False, imgsz=PASS1_SIZE
        )[0]

        rois = []
        if p1_results.boxes is None or len(p1_results.boxes) == 0:
            return rois

        inv_scale = 1.0 / scale
        boxes = p1_results.boxes.xyxy.cpu().numpy()

        for box in boxes:
            x1 = int(np.clip((box[0] - pad_x) * inv_scale, 0, frame_w))
            y1 = int(np.clip((box[1] - pad_y) * inv_scale, 0, frame_h))
            x2 = int(np.clip((box[2] - pad_x) * inv_scale, 0, frame_w))
            y2 = int(np.clip((box[3] - pad_y) * inv_scale, 0, frame_h))
            bw, bh = x2 - x1, y2 - y1
            if bw <= 0 or bh <= 0:
                continue
                
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2

            # ROI genişletme: Kutu oranı veya sabit px, hangisi büyükse
            expand_w = max(bw * ROI_EXPAND / 2, PASS1_EXPAND_PX)
            expand_h = max(bh * ROI_EXPAND / 2, PASS1_EXPAND_PX)
            rx1 = max(0, int(cx - expand_w))
            ry1 = max(0, int(cy - expand_h))
            rx2 = min(frame_w, int(cx + expand_w))
            ry2 = min(frame_h, int(cy + expand_h))

            if (rx2 - rx1) > 50 and (ry2 - ry1) > 50:
                rois.append((rx1, ry1, rx2, ry2))

        return rois

    # ──────────────────────────────────────────────────────────
    # FALLBACK: Tam frame grid tarama
    # ──────────────────────────────────────────────────────────
    def _fullscan_grid(self, frame_w: int, frame_h: int) -> list[tuple]:
        """
        Pass-1 hiçbir şey bulamadığında frame'i büyük ROI'lere böl.
        Bu sayede uzak hedefin İLK tespiti bile mümkün olur.
        Stride büyük tutularak (960px) performans korunur.
        """
        rois = []
        y = 0
        while y < frame_h:
            x = 0
            while x < frame_w:
                rx2 = min(x + FULLSCAN_STRIDE, frame_w)
                ry2 = min(y + FULLSCAN_STRIDE, frame_h)
                if (rx2 - x) > 50 and (ry2 - y) > 50:
                    rois.append((x, y, rx2, ry2))
                x += FULLSCAN_STRIDE
            y += FULLSCAN_STRIDE
        return rois

    # ──────────────────────────────────────────────────────────
    # BİR ROI ÜZERİNDE SAHI
    # ──────────────────────────────────────────────────────────
    def _sahi_on_region(
        self, region: np.ndarray, offset_x: int, offset_y: int
    ) -> list[RawDetection]:
        patches_data = self._generate_patches(region, offset_x, offset_y)

        # Varyans filtresi: Tamamen boş gökyüzü patçalarını atla
        filtered = [
            (patch, ox, oy)
            for patch, ox, oy in patches_data
            if self._variance_ok(patch)
        ]
        if not filtered:
            return []

        all_dets: list[RawDetection] = []
        for i in range(0, len(filtered), BATCH_SIZE):
            batch = filtered[i:i + BATCH_SIZE]
            patches = [b[0] for b in batch]
            offsets = [(b[1], b[2]) for b in batch]
            dets = self._batch_infer(patches, offsets)
            all_dets.extend(dets)

        return _nms(all_dets, NMS_IOU)

    # ──────────────────────────────────────────────────────────
    # PATÇA ÜRETİCİ
    # ──────────────────────────────────────────────────────────
    def _generate_patches(self, image: np.ndarray, offset_x: int = 0, offset_y: int = 0):
        h, w = image.shape[:2]
        
        # Eğer ROI zaten patch boyutundan küçükse tek patch üret ve çık (büyük performans artışı)
        if h <= SLICE_H and w <= SLICE_W:
            padded = np.zeros((SLICE_H, SLICE_W, 3), dtype=np.uint8)
            padded[:h, :w] = image
            return [(padded, offset_x, offset_y)]

        stride_y = max(1, int(SLICE_H * (1 - OVERLAP)))
        stride_x = max(1, int(SLICE_W * (1 - OVERLAP)))

        patches = []
        y = 0
        while y < h:
            x = 0
            while x < w:
                y2 = min(y + SLICE_H, h)
                x2 = min(x + SLICE_W, w)
                patch = image[y:y2, x:x2]

                # Kenar patçaları için padding
                if patch.shape[0] < SLICE_H or patch.shape[1] < SLICE_W:
                    padded = np.zeros((SLICE_H, SLICE_W, 3), dtype=np.uint8)
                    padded[:patch.shape[0], :patch.shape[1]] = patch
                    patch = padded

                patches.append((patch, offset_x + x, offset_y + y))
                x += stride_x
            y += stride_y

        return patches

    # ──────────────────────────────────────────────────────────
    # VARYANS FİLTRESİ
    # ──────────────────────────────────────────────────────────
    @staticmethod
    def _variance_ok(patch: np.ndarray) -> bool:
        gray = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)
        lap  = cv2.Laplacian(gray, cv2.CV_64F)
        return float(lap.var()) >= VARIANCE_THRESHOLD

    # ──────────────────────────────────────────────────────────
    # BATCH YOLO INFERENCE
    # ──────────────────────────────────────────────────────────
    def _batch_infer(
        self, patches: list[np.ndarray], offsets: list[tuple[int, int]]
    ) -> list[RawDetection]:
        # ÖNEMLİ: Burada FAR_TARGET_MIN_CONF kullanılır (0.12),
        # CONFIDENCE (0.30) değil! Böylece uzak hedef YOLO çıktısında
        # bile oluşur. Gereksiz tespitler sonradan detect() içinde
        # çift eşikli filtre ile elenir.
        results = self.model(
            patches,
            conf=FAR_TARGET_MIN_CONF,
            device=DEVICE,
            verbose=False,
            imgsz=max(SLICE_H, SLICE_W)
        )

        dets: list[RawDetection] = []
        for result, (ox, oy) in zip(results, offsets):
            if result.boxes is None:
                continue
            boxes_xyxy = result.boxes.xyxy.cpu().numpy()
            confs      = result.boxes.conf.cpu().numpy()
            classes    = result.boxes.cls.cpu().numpy().astype(int)

            for (x1, y1, x2, y2), conf, cls in zip(boxes_xyxy, confs, classes):
                dets.append(RawDetection(
                    x1=float(x1) + ox, y1=float(y1) + oy,
                    x2=float(x2) + ox, y2=float(y2) + oy,
                    confidence=float(conf), class_id=int(cls)
                ))

        return dets