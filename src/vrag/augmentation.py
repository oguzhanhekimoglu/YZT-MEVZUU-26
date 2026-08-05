import cv2
import numpy as np
from PIL import Image, ImageFilter
from src.config import DONME_ACILARI, OLCEK_FAKTORLERI, BULANIKLIK_YARICAPI, PERSPEKTIF_AKTIF

def perspective_tilt(img: Image.Image) -> Image.Image:
    """Simulates a perspective tilt (e.g. drone looking from an angle)"""
    cv_img = np.array(img)
    h, w = cv_img.shape[:2]
    # Tilt so the top is 20% narrower
    m = 0.2
    pts1 = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    pts2 = np.float32([[w * m, h * m], [w * (1 - m), h * m], [w, h], [0, h]])
    
    matrix = cv2.getPerspectiveTransform(pts1, pts2)
    # Use borderMode CONSTANT with black padding
    warped = cv2.warpPerspective(cv_img, matrix, (w, h), borderValue=(0, 0, 0))
    return Image.fromarray(warped)

def scale_image(img: Image.Image, scale_factor: float) -> Image.Image:
    """Scales the image down and pads with black to keep original size"""
    w, h = img.size
    nw, nh = int(w * scale_factor), int(h * scale_factor)
    if nw == 0 or nh == 0:
        return img
    scaled = img.resize((nw, nh), resample=Image.BILINEAR)
    new_img = Image.new("RGB", (w, h), (0, 0, 0))
    new_img.paste(scaled, ((w - nw) // 2, (h - nh) // 2))
    return new_img

def varyasyonlar_uret(img: Image.Image) -> list[Image.Image]:
    """
    1 orijinal + 2 döndürme + 1 ölçek + 1 blur + 1 perspektif = 6 varyasyon üretir.
    Drones/UAVs appear small, blurry, and from weird angles.
    """
    variations = []
    
    # 1. Orijinal
    variations.append(img)
    
    # 2. Döndürme 1 (Negatif açı)
    variations.append(img.rotate(DONME_ACILARI[0], resample=Image.BILINEAR, expand=False, fillcolor=(0,0,0)))
    
    # 3. Döndürme 2 (Pozitif açı)
    variations.append(img.rotate(DONME_ACILARI[1], resample=Image.BILINEAR, expand=False, fillcolor=(0,0,0)))
    
    # 4. Ölçek (Uzaklaşma)
    for scale in OLCEK_FAKTORLERI:
        variations.append(scale_image(img, scale))
        
    # 5. Bulanık (Gaussian Blur)
    variations.append(img.filter(ImageFilter.GaussianBlur(radius=BULANIKLIK_YARICAPI)))
    
    # 6. Perspektif (Eğim)
    if PERSPEKTIF_AKTIF:
        variations.append(perspective_tilt(img))
        
    return variations
