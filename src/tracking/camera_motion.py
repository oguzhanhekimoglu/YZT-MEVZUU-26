import cv2
import numpy as np
import logging

log = logging.getLogger(__name__)

try:
    from src.config import CMC_MIN_RELIABLE_POINTS, CMC_MAX_SHIFT_PX
except ImportError:
    CMC_MIN_RELIABLE_POINTS = 15
    CMC_MAX_SHIFT_PX        = 80.0

class CameraMotionCompensator:
    """
    Arka plan piksellerini izleyerek kameranın kendi hareketini (Ego-Motion) hesaplar.
    MultiTargetTracker bunu kullanarak hedeflerin kutu hareketinden kamera hareketini çıkarır,
    böylece uçağın dünyadaki gerçek fiziksel hız vektörünü (True World Velocity) bulur.
    """
    def __init__(self, max_corners=150, quality_level=0.1, min_distance=10,
                 min_reliable_points=CMC_MIN_RELIABLE_POINTS, max_shift_px=CMC_MAX_SHIFT_PX):
        self.max_corners = max_corners
        self.quality_level = quality_level
        self.min_distance = min_distance
        # BUG-FIX: bkz. config.py CMC_MIN_RELIABLE_POINTS / CMC_MAX_SHIFT_PX yorumu.
        self.min_reliable_points = min_reliable_points
        self.max_shift_px = max_shift_px

        self.prev_gray = None
        self.prev_pts = None

    def update(self, frame_bgr: np.ndarray, exclude_bboxes: list) -> tuple[float, float]:
        """
        frame_bgr: Mevcut kare.
        exclude_bboxes: Arka planı izlerken hareketli hedefleri izlememek için dışlanacak kutular.
                        List of [x1, y1, x2, y2].
        Returns:
            (dx, dy): Arka planın piksellerinin görüntü içindeki yer değiştirme miktarı.
        """
        if frame_bgr is None:
            return 0.0, 0.0

        curr_gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        dx, dy = 0.0, 0.0

        # BUG-FIX (çözünürlük değişimi çökmesi): CameraMotionCompensator, tracker
        # ile birlikte oturumlar arası yeniden kullanılıyor. Yeni video önceki
        # videodan farklı çözünürlükteyse prev_gray boyutu uyuşmuyor ve
        # cv2.calcOpticalFlowPyrLK piramit boyutu hatasıyla çöküyordu — ilk kare
        # gibi davranıp noktaları yeniden tespit et.
        if self.prev_gray is not None and self.prev_gray.shape != curr_gray.shape:
            self.prev_gray = None
            self.prev_pts = None

        # Eğer ilk kare ise noktaları bul ve çık
        if self.prev_gray is None:
            self._detect_new_features(curr_gray, exclude_bboxes)
            self.prev_gray = curr_gray
            return 0.0, 0.0

        # Takip edilecek nokta yoksa yeniden bul
        if self.prev_pts is None or len(self.prev_pts) < 10:
            self._detect_new_features(self.prev_gray, exclude_bboxes)
            
        if self.prev_pts is not None and len(self.prev_pts) >= 10:
            # Optik akış ile eski noktaların yeni karedeki yerini bul
            curr_pts, status, _ = cv2.calcOpticalFlowPyrLK(
                self.prev_gray, curr_gray, self.prev_pts, None,
                winSize=(15, 15), maxLevel=2,
                criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03)
            )

            # Geçerli noktaları seç
            good_old = self.prev_pts[status == 1]
            good_new = curr_pts[status == 1]

            # BUG-FIX (videoya göre değişen kutu titremesi): Eskiden yalnızca
            # >=5 eşleşen nokta yeterliydi ve medyan doğrudan güveniliyordu.
            # Düşük dokulu (örn. açık gökyüzü ağırlıklı) arka planlarda hem
            # nokta sayısı azalıyor hem kalanlar gürültülü/kararsız oluyor —
            # birkaç kötü nokta medyanı kaydırıp bunu shift_history() ile
            # HER TRACK'in Kalman durumuna hatalı bir kayma olarak
            # enjekte ediyordu. Artık: (1) minimum nokta sayısı yükseltildi,
            # (2) medyandan önce MAD (medyan mutlak sapma) ile aykırı
            # noktalar atılıyor, (3) sonuç fiziksel olarak mantıklı bir üst
            # sınırla kelepçeleniyor — aşan bir kayma güvenilmez sayılıp bu
            # karede UYGULANMIYOR (0,0 = "kamera sabit" varsayımına düşülür,
            # yanlış bir kaymayı tüm track'lere yaymaktan çok daha güvenlidir).
            if len(good_new) >= self.min_reliable_points:
                diffs = good_new - good_old

                median_diff = np.median(diffs, axis=0)
                abs_dev = np.abs(diffs - median_diff)
                mad = np.median(abs_dev, axis=0)

                if mad[0] > 1e-3 or mad[1] > 1e-3:
                    # ~3.5*MAD, Gauss dağılımında yaklaşık 2.5 sigma'ya denk gelir
                    thresh = np.maximum(mad * 3.5, 1.0)
                    inlier_mask = np.all(abs_dev <= thresh, axis=1)
                    if int(inlier_mask.sum()) >= self.min_reliable_points:
                        diffs = diffs[inlier_mask]

                cand_dx, cand_dy = np.median(diffs, axis=0)

                if abs(float(cand_dx)) <= self.max_shift_px and abs(float(cand_dy)) <= self.max_shift_px:
                    dx, dy = float(cand_dx), float(cand_dy)
                else:
                    log.debug(
                        f"[CMC] Güvenilmez kayma reddedildi: "
                        f"({cand_dx:.1f}, {cand_dy:.1f})px > sınır {self.max_shift_px}px"
                    )

            # Gelecek frame için güncel noktaları al
            self.prev_pts = good_new.reshape(-1, 1, 2)
            
            # Zamanla noktalar azalırsa tazele
            if len(self.prev_pts) < 40:
                self._detect_new_features(curr_gray, exclude_bboxes)
        
        self.prev_gray = curr_gray
        return float(dx), float(dy)

    def _detect_new_features(self, gray: np.ndarray, exclude_bboxes: list):
        """Arka plandan izlenecek güçlü köşeleri (köşe, ufuk çizgisi vb.) bulur."""
        # Hedeflerin olduğu bölgeleri maskele (Siyah yap ki oradan nokta seçmesin)
        mask = np.ones_like(gray, dtype=np.uint8) * 255
        
        h, w = gray.shape[:2]
        # BUG-FIX: exclude_bboxes bu projede HER ZAMAN tracker'daki gerçek hedef
        # kutularıdır (sallanan dal/yaprak gibi genel bir "arka plan nesnesi"
        # değil — bkz. tracker.py: exclude_bboxes = [r[:4] for r in raw_tracks]).
        # Eskiden kenara değen kutular kasıtlı olarak maskeleme dışı bırakılıyordu
        # ("mükemmel arka plan referansı olabilir" varsayımıyla). Ama bu durumda
        # maskelenmeyen bölge bir dal değil, hedefin (uçak/kuş) kendisidir —
        # hedef ekran kenarına yaklaştığında optik akış onun üzerinden köşe
        # noktaları toplar ve bu noktalar "arka plan" sanılıp ego-motion
        # tahminine (bg_dx, bg_dy) karışır → hedef kutusu titrer/kayar.
        # Artık konumdan bağımsız olarak TÜM hedef kutuları maskeleniyor.
        for bbox in exclude_bboxes:
            x1, y1, x2, y2 = map(int, bbox)
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            mask[y1:y2, x1:x2] = 0

        pts = cv2.goodFeaturesToTrack(
            gray, 
            mask=mask,
            maxCorners=self.max_corners, 
            qualityLevel=self.quality_level, 
            minDistance=self.min_distance,
            blockSize=7
        )
        
        if pts is not None:
            self.prev_pts = pts
        else:
            # BUG-11 Düzeltmesi: np.array([]) yerine None kullan.
            # np.array([]) shape'i (0,) olur, cv2.calcOpticalFlowPyrLK (N,1,2) bekliyor.
            self.prev_pts = None