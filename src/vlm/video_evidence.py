# ============================================================
# video_evidence.py — Video-kanıtı (TrackEvidenceBuilder-lite, MVP)
# ============================================================
# Belgede tarif edilen tam TrackEvidenceBuilder'ın (histerezisli pencere,
# Kalman fallback, WAITING/READY/ANALYZED state machine) basitleştirilmiş
# ilk sürümü: sabit boyutlu, basit bir kırpma penceresi kullanır, track
# başına en fazla bir kez tetiklenir. spike testiyle (araclar/evren_spike_
# test.py) hem hazır video hem de OpenCV'yle anlık encode edilmiş klibin
# EVREN'in "vlm" modeli tarafından kabul edildiği doğrulandıktan sonra
# yazıldı.
#
# Track nesnesine gömülmez — pipeline.py, her track_id için ayrı bir
# TrackVideoBuffer tutar (bkz. TeknoFestPipeline._video_buffers).
import base64
import json
import logging
import re
import tempfile
import threading
from pathlib import Path

import cv2
import numpy as np
import requests

from src.config import VLM_API_URL, VLM_API_KEY, VLM_TIMEOUT_S

log = logging.getLogger(__name__)

VIDEO_CLIP_FPS = 10.0          # kaydedilen klip fps'i (kaynak fps'ten düşük - boyut/hız için)
VIDEO_CLIP_DURATION_S = 2.0    # klip süresi
VIDEO_CLIP_CANVAS = 480        # letterbox hedef kare boyutu (kare, sabit)
VIDEO_MAX_CONCURRENT = 2       # eş zamanlı video-VLM çağrısı limiti (image VLM'den AYRI)

# Image path (ThreadPoolExecutor max_workers=4) ile aynı kaynağı paylaşmasın
# diye ayrı bir sayaç — video çağrıları çok daha ağır (encode + büyük upload).
_video_semaphore = threading.Semaphore(VIDEO_MAX_CONCURRENT)


class TrackVideoBuffer:
    """Tek bir track için son birkaç saniyenin kırpılmış karelerini tutar.

    MVP kısıtı: histerezisli pencere/Kalman fallback YOK — her karede
    track'in o anki (ham) bbox'ı, biraz payla kırpılır. Hedef ekrandan
    kısa süre çıkarsa/tekrar girerse klip biraz tutarsızlaşabilir; bu
    kabul edilebilir bir MVP kısıtı, tam TrackEvidenceBuilder'da düzelir.
    """

    def __init__(self, fps: float):
        # BUG-FIX: max_frames kaynak fps'e göre hesaplanıyordu ama tampona
        # sadece ÖRNEKLENMİŞ (her _every_n karede bir) kareler giriyor - bu
        # yüzden "2 saniyelik" hedef aslında ~4 saniye gerçek zaman
        # gerektiriyordu (25fps kaynak, 10fps hedefte 2'de 1 örnekleme).
        # max_frames artık hedef encode fps'ine göre (örneklenmiş kare
        # sayısı), gerçek zaman ~VIDEO_CLIP_DURATION_S'e yakınsıyor.
        self._every_n = max(1, int(round(fps / VIDEO_CLIP_FPS)))
        self.max_frames = max(1, int(round(VIDEO_CLIP_DURATION_S * VIDEO_CLIP_FPS)))
        self._tick = 0
        self.frames: list[np.ndarray] = []
        self.sent_once: bool = False  # MVP: track başına en fazla 1 video-VLM çağrısı

    def add(self, crop_bgr: np.ndarray) -> None:
        self._tick += 1
        if crop_bgr.size == 0 or (self._tick % self._every_n) != 0:
            return
        self.frames.append(crop_bgr.copy())
        if len(self.frames) > self.max_frames:
            self.frames.pop(0)

    @property
    def ready(self) -> bool:
        return len(self.frames) >= self.max_frames


def _letterbox(frame: np.ndarray, target: int) -> np.ndarray:
    h, w = frame.shape[:2]
    scale = target / max(h, w)
    nh, nw = max(1, int(round(h * scale))), max(1, int(round(w * scale)))
    resized = cv2.resize(frame, (nw, nh))
    canvas = np.full((target, target, 3), 30, dtype=np.uint8)
    y0, x0 = (target - nh) // 2, (target - nw) // 2
    canvas[y0:y0 + nh, x0:x0 + nw] = resized
    return canvas


def _encode_clip(frames: list[np.ndarray]) -> bytes:
    """spike testinde doğrulanan aynı yol: mp4v codec, kare (letterbox) kanvas."""
    target = VIDEO_CLIP_CANVAS
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        writer = cv2.VideoWriter(
            str(tmp_path), cv2.VideoWriter_fourcc(*"mp4v"), VIDEO_CLIP_FPS, (target, target)
        )
        for f in frames:
            writer.write(_letterbox(f, target))
        writer.release()
        return tmp_path.read_bytes()
    finally:
        tmp_path.unlink(missing_ok=True)


# BUG-FIX (image path'te yaşanan aynı hata): "vlm" modelinde response_format
# hiç test edilmedi (spike testi düz metin promptuyla denendi) - JSON modu
# isteyip 400/reddedilme riskine girmek yerine, image VLM'deki gibi metinden
# JSON çıkarma (regex/find) ile idare ediyoruz.
_VIDEO_PROMPT = (
    "Bu kısa video klibi, takip edilen TEK bir hava aracının son birkaç "
    "saniyesidir. SADECE gözlemsel bilgi ver - risk/tehdit/yetki/düşmanlık/"
    "kesin ülke hükmü YAZMA, bu senin görevin değil. SADECE şu JSON'u döndür, "
    "başka hiçbir şey yazma:\n"
    '{"arac_sinifi": "sabit_kanat|doner_kanat|kus|bilinmeyen", '
    '"hareket_tanimi": "kısa gözlem (örn: düz uçuş, alçalıyor, dönüyor)", '
    '"ayirt_edici_ozellik": "kısa görsel ipucu (renk, silüet, gövde şekli vb.)", '
    '"model_ipucu": "varsa düşük-öncelikli model tahmini, yoksa bilinmiyor", '
    '"gorsel_guven": 0.0 ile 1.0 arası sayı, '
    '"belirsizlik_notu": "varsa net görülemeyen şey, yoksa bos string"}'
)


def _extract_json(raw_text: str) -> dict | None:
    raw_text = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL).strip()
    start, end = raw_text.find("{"), raw_text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        return json.loads(raw_text[start:end + 1])
    except json.JSONDecodeError:
        return None


def analyze_track_video(frames: list[np.ndarray], track_id: int) -> dict | None:
    """Bir defaya mahsus, RETRY YOK senkron çağrı (bilinçli — video çağrıları
    ağır, başarısız bir denemeyi otomatik tekrarlamak kuyruğu tıkar).
    Görüntü (image) VLM'den ayrı bir eş-zamanlılık limiti kullanır."""
    if not VLM_API_KEY:
        return None
    if not _video_semaphore.acquire(timeout=0.1):
        log.info(f"[VIDEO-VLM] Track {track_id}: eş zamanlı video-VLM limiti dolu, bu tur atlanıyor.")
        return None
    try:
        clip_b64 = base64.b64encode(_encode_clip(frames)).decode("ascii")
        payload = {
            "model": "vlm",
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": _VIDEO_PROMPT},
                    {"type": "video_url", "video_url": {"url": f"data:video/mp4;base64,{clip_b64}"}},
                ],
            }],
            "temperature": 0.0,
            "max_tokens": 512,
        }
        headers = {"Authorization": f"Bearer {VLM_API_KEY}"}
        response = requests.post(VLM_API_URL, json=payload, headers=headers, timeout=VLM_TIMEOUT_S)
        response.raise_for_status()
        choices = response.json().get("choices") or []
        content = (choices[0].get("message", {}).get("content") or "").strip() if choices else ""
        if not content:
            log.warning(f"[VIDEO-VLM] Track {track_id}: boş yanıt döndü.")
            return None
        result = _extract_json(content)
        if result is None:
            log.warning(f"[VIDEO-VLM] Track {track_id}: JSON ayrıştırılamadı: {content[:200]!r}")
        return result
    except requests.exceptions.RequestException as exc:
        log.error(f"[VIDEO-VLM] Track {track_id}: API hatası → {exc}")
        return None
    finally:
        _video_semaphore.release()
