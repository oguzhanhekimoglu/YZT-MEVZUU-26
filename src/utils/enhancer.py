# ============================================================
# enhancer.py - GPU-Destekli Görüntü İyileştirme Modülü
# ============================================================
# NEDEN BU MODÜL VAR?
# SAHI + ByteTrack bize hedefin koordinatlarını verir. O koordinatta
# kırpılan (Crop edilen) resim; uzak mesafe, sis, hareket bulanıklığı
# (motion blur) nedeniyle çoğunlukla pis ve net değildir.
# VLM (Vision Language Model) net olmayan görüntülerde halüsinasyon
# (saçmalama) yapar ve yanlış karar verir.
# Bu modül, o ufacık kırpılmış kareyi mümkün olduğunca pırıl pırıl
# hale getirir — ama VLM'in doğal doku algısını bozmadan.
#
# GPU YOLU (CUDA + cv2.cuda):
#   CLAHE (clip=1.5, tile=16×16) → bilateral denoising → cubic upscale
# CPU FALLBACK:
#   gray-world + cubic upscale + bilateral (cv2.cuda yoksa/CUDA yoksa)
#
# NEDEN SERT FİLTRELER YOK?
#   - Unsharp mask      → ringing artefakları → VLM halüsinasyonu
#   - CLAHE clip > 2.0  → sahte kontrast bantları → VLM yanılır
#   - Lanczos4          → keskin yapay kenarlar → VLM kuyruk/kanat sanır
# ============================================================

import cv2
import numpy as np
import logging

log = logging.getLogger(__name__)

try:
    from src.config import (
        CLAHE_CLIP, CLAHE_GRID, SHARPEN_STRENGTH, MIN_CROP_SIZE,
        USE_GPU_ENHANCE, CLAHE_CLIP_GPU, CLAHE_GRID_GPU, ENHANCE_GAMMA,
    )
except ImportError:
    CLAHE_CLIP       = 2.0
    CLAHE_GRID       = (8, 8)
    SHARPEN_STRENGTH = 1.5
    MIN_CROP_SIZE    = 8
    USE_GPU_ENHANCE  = True
    CLAHE_CLIP_GPU   = 1.5
    CLAHE_GRID_GPU   = (16, 16)
    ENHANCE_GAMMA    = 1.1


def _check_gpu_available() -> bool:
    """cv2.cuda gerçekten kullanılabilir mi? Runtime'da kontrol et."""
    try:
        count = cv2.cuda.getCudaEnabledDeviceCount()
        return count > 0
    except (cv2.error, AttributeError):
        return False


class ImageEnhancer:
    """
    VLM'e gönderilecek hedef görüntüsünü zorlu hava şartlarına (sis, yağmur,
    ters ışık, motion blur) karşı iyileştiren sınıf.

    GPU modu (CUDA + cv2.cuda):
        LAB renk uzayında L kanalına CLAHE → GPU bilateral denoising
        → (küçükse) GPU'da cubic upscale

    CPU modu (fallback):
        Gray-world renk restorasyon → CPU bilateral → cubic upscale
    """

    def __init__(self):
        self._use_gpu = USE_GPU_ENHANCE and _check_gpu_available()

        if self._use_gpu:
            try:
                # CLAHE: L kanalına (LAB'da) uygulanır — rengi bozmaz
                self._clahe_gpu = cv2.cuda.createCLAHE(
                    clipLimit=CLAHE_CLIP_GPU,
                    tileGridSize=CLAHE_GRID_GPU,
                )
                log.info(
                    f"[Enhancer] GPU modu aktif — "
                    f"CLAHE clip={CLAHE_CLIP_GPU}, tile={CLAHE_GRID_GPU}"
                )
            except Exception as e:
                log.warning(f"[Enhancer] cv2.cuda.createCLAHE başarısız: {e} → CPU'ya düşüldü")
                self._use_gpu = False
        else:
            log.info("[Enhancer] CPU modu (CUDA bulunamadı veya devre dışı)")

    # ----------------------------------------------------------
    # YARDİMCI: Gray-World (CPU Fallback'te kullanılır)
    # ----------------------------------------------------------
    def _apply_gray_world(self, img: np.ndarray) -> np.ndarray:
        """
        Renk Restorasyonu: Sis/yağmur/akşam mavisinin yarattığı sahte renk
        perdesini siler. Gri dünya algoritması — ortam ışığının etkisini sil.
        """
        result = img.astype(np.float32)
        avg_b = np.mean(result[:, :, 0])
        avg_g = np.mean(result[:, :, 1])
        avg_r = np.mean(result[:, :, 2])
        avg_gray = (avg_b + avg_g + avg_r) / 3.0

        # Sıfıra bölme hatasını engelle
        if avg_b < 1e-3 or avg_g < 1e-3 or avg_r < 1e-3:
            return img

        result[:, :, 0] *= (avg_gray / avg_b)
        result[:, :, 1] *= (avg_gray / avg_g)
        result[:, :, 2] *= (avg_gray / avg_r)
        return np.clip(result, 0, 255).astype(np.uint8)

    # ----------------------------------------------------------
    # YARDİMCI: Gamma düzeltme (çok karanlık crop'lar için)
    # ----------------------------------------------------------
    @staticmethod
    def _apply_gamma(img: np.ndarray, gamma: float) -> np.ndarray:
        """LUT tabanlı hızlı gamma düzeltme (1.0 = değişiklik yok)."""
        if abs(gamma - 1.0) < 0.01:
            return img
        inv_gamma = 1.0 / gamma
        table = np.array(
            [(i / 255.0) ** inv_gamma * 255 for i in range(256)],
            dtype=np.uint8
        )
        return cv2.LUT(img, table)

    # ----------------------------------------------------------
    # GPU ENHANCE (CLAHE + Bilateral + Upscale)
    # ----------------------------------------------------------
    def _enhance_gpu(self, crop_bgr: np.ndarray) -> np.ndarray:
        """
        GPU yolu:
          1. Gamma düzeltme (karanlık krop açılır)
          2. LAB renk uzayında L kanalına GPU CLAHE (rengi korur)
          3. GPU bilateral filter (gürültüyü kaldırır, kenarları korur)
          4. Küçükse GPU'da INTER_CUBIC upscale
        """
        h, w = crop_bgr.shape[:2]

        # --- Adım 0: Hafif gamma düzeltme ---
        out = self._apply_gamma(crop_bgr, ENHANCE_GAMMA)

        # --- Adım 1: LAB → GPU CLAHE sadece L kanalında ---
        try:
            lab = cv2.cvtColor(out, cv2.COLOR_BGR2LAB)
            l_ch, a_ch, b_ch = cv2.split(lab)

            gpu_l = cv2.cuda_GpuMat()
            gpu_l.upload(l_ch)
            gpu_l_clahe = self._clahe_gpu.apply(gpu_l)
            l_eq = gpu_l_clahe.download()

            lab_eq = cv2.merge([l_eq, a_ch, b_ch])
            out = cv2.cvtColor(lab_eq, cv2.COLOR_LAB2BGR)
        except Exception as e:
            log.debug(f"[Enhancer GPU] CLAHE adımı başarısız: {e}")
            # CLAHE başarısız olursa önceki çıktıyla devam et

        # --- Adım 2: GPU Bilateral denoising ---
        try:
            gpu_in = cv2.cuda_GpuMat()
            gpu_in.upload(out)
            # d=5, sigmaColor=35, sigmaSpace=35 → hafif ama etkili
            gpu_out = cv2.cuda.bilateralFilter(
                gpu_in, d=5, sigmaColor=35, sigmaSpace=35,
                borderMode=cv2.BORDER_REFLECT_101
            )
            out = gpu_out.download()
        except Exception as e:
            log.debug(f"[Enhancer GPU] Bilateral başarısız: {e} → CPU fallback")
            out = cv2.bilateralFilter(out, d=5, sigmaColor=35, sigmaSpace=35)

        # --- Adım 3: GPU'da cubic upscale (sadece küçük crop'lar) ---
        if h < 150 or w < 150:
            scale = min(3.0, 256.0 / max(1, min(h, w)))
            new_w = max(64, int(w * scale))
            new_h = max(64, int(h * scale))
            try:
                gpu_small = cv2.cuda_GpuMat()
                gpu_small.upload(out)
                gpu_big = cv2.cuda.resize(
                    gpu_small, (new_w, new_h),
                    interpolation=cv2.INTER_CUBIC
                )
                out = gpu_big.download()
            except Exception as e:
                log.debug(f"[Enhancer GPU] Upscale başarısız: {e} → CPU fallback")
                out = cv2.resize(out, (new_w, new_h), interpolation=cv2.INTER_CUBIC)

        return out

    # ----------------------------------------------------------
    # CPU ENHANCE (Gray-World + Bilateral + Upscale)
    # ----------------------------------------------------------
    def _enhance_cpu(self, crop_bgr: np.ndarray) -> np.ndarray:
        """
        CPU yolu (GPU yoksa veya cv2.cuda hata verirse):
          1. Gray-world renk restorasyon (sis/pus giderici)
          2. Hafif gamma düzeltme
          3. Bilateral filter (gürültü azalt, kenar koru)
          4. Küçükse INTER_CUBIC upscale
        """
        h, w = crop_bgr.shape[:2]

        # --- Adım 1: Renk restorasyon ---
        out = self._apply_gray_world(crop_bgr)

        # --- Adım 2: Gamma ---
        out = self._apply_gamma(out, ENHANCE_GAMMA)

        # --- Adım 3: Bilateral ---
        out = cv2.bilateralFilter(out, d=5, sigmaColor=40, sigmaSpace=40)

        # --- Adım 4: Upscale ---
        if h < 150 or w < 150:
            scale = min(3.0, 256.0 / max(1, min(h, w)))
            new_w = max(64, int(w * scale))
            new_h = max(64, int(h * scale))
            out = cv2.resize(out, (new_w, new_h), interpolation=cv2.INTER_CUBIC)

        return out

    # ----------------------------------------------------------
    # ANA GİRİŞ NOKTASI
    # ----------------------------------------------------------
    def enhance(self, crop_bgr: np.ndarray) -> np.ndarray | None:
        """
        Tek bir ham crop'u VLM için iyileştirir.
        GPU varsa GPU yolunu, yoksa CPU yolunu kullanır.
        Bozuk/çok küçük/siyah dolgu varsa None döner.
        """
        if crop_bgr is None or crop_bgr.size == 0:
            return None

        h, w = crop_bgr.shape[:2]

        if h < MIN_CROP_SIZE or w < MIN_CROP_SIZE:
            return None

        # --- Siyah Dolgu Kontrolü ---
        # Patçanın kenarından kırpılan crop'lar siyah (letterbox) padding içerebilir.
        # Siyah piksel oranı çok yüksekse (%40+) VLM'e göndermek karışıklık yaratır.
        gray_check = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
        black_ratio = float(np.mean(gray_check < 10))
        if black_ratio > 0.40:
            return None

        # --- GPU veya CPU yolu ---
        try:
            if self._use_gpu:
                return self._enhance_gpu(crop_bgr)
            else:
                return self._enhance_cpu(crop_bgr)
        except Exception as e:
            log.warning(f"[Enhancer] İyileştirme hatası, ham crop döndürülüyor: {e}")
            return crop_bgr