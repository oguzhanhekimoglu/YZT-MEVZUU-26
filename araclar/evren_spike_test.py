"""EVREN spike testi — TrackEvidenceBuilder/video-kaniti mimarisine baslamadan
once iki dogrulanmamis varsayimi ucuza test eder:

  1) "vlm" modeli gercekten video kabul ediyor mu? (dokumantasyon iddia ediyor,
     hic denenmedi - "vlm" tek gorseli 400 ile reddettigini zaten dogruladik)
  2) "llm-fast" (reasoning modeli) "chat_template_kwargs": {"enable_thinking":
     False} ile "dusunmeyi" kapatip dogrudan cevap veriyor mu? (verirse, VLM_
     NUM_PREDICT'i 4096'ya cikararak cozdugumuz token-israfi sorununu daha
     temiz/ucuz cozer)

Kullanim:
    export VLM_API_KEY=...   (ayni terminalde, backend'i baslattigin gibi)
    python araclar/evren_spike_test.py [video_dosyasi.mp4]

Hicbir seyi projeye kalici olarak baglamiyor - sadece ham API cevaplarini
yazdirir, yorumu sana birakir.
"""
import base64
import os
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.vlm.prompts import generate_vlm_prompt  # noqa: E402

API_URL = os.environ.get("VLM_API_URL") or "https://evren-llmapi.ssyz.org.tr/v1/chat/completions"
API_KEY = os.environ.get("VLM_API_KEY") or ""
DEFAULT_VIDEO = Path(__file__).resolve().parent.parent / "data" / "videos" / "00.mp4"


def _post(payload: dict) -> None:
    headers = {"Authorization": f"Bearer {API_KEY}"} if API_KEY else None
    try:
        resp = requests.post(API_URL, json=payload, headers=headers, timeout=120.0)
    except requests.exceptions.RequestException as exc:
        print(f"  -> ISTEK HATASI: {exc}")
        return
    print(f"  -> HTTP {resp.status_code}")
    try:
        body = resp.json()
    except ValueError:
        print(f"  -> JSON DEGIL, ham govde (ilk 500 karakter): {resp.text[:500]}")
        return
    if resp.status_code != 200:
        print(f"  -> HATA GOVDESI: {body}")
        return
    choice = (body.get("choices") or [{}])[0]
    message = choice.get("message", {})
    print(f"  -> finish_reason: {choice.get('finish_reason')}")
    print(f"  -> reasoning_content uzunlugu: {len(message.get('reasoning_content') or '')}")
    print(f"  -> content: {message.get('content')!r}")
    print(f"  -> usage: {body.get('usage')}")


def test_video_kabulu(video_path: Path) -> None:
    print("\n=== TEST 1: 'vlm' modeli video kabul ediyor mu? ===")
    if not video_path.is_file():
        print(f"  -> Video bulunamadi: {video_path} (arg olarak baska bir dosya ver)")
        return
    size_mb = video_path.stat().st_size / 1024 / 1024
    print(f"  -> Video: {video_path.name} ({size_mb:.1f} MB)")
    if size_mb > 20:
        print("  -> UYARI: buyukce bir dosya, base64 + agla gonderim yavas olabilir.")
    video_b64 = base64.b64encode(video_path.read_bytes()).decode("ascii")
    payload = {
        "model": "vlm",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Bu videoda ne goruyorsun? Kisaca Turkce anlat."},
                    {"type": "video_url", "video_url": {"url": f"data:video/mp4;base64,{video_b64}"}},
                ],
            }
        ],
        "temperature": 0.0,
        "max_tokens": 512,
    }
    _post(payload)


def test_canli_encode_kabulu(video_path: Path) -> None:
    """TrackEvidenceBuilder'ın gerçekte yapacağı şeyi taklit eder: hazır bir
    dosyayı OLDUĞU GİBİ göndermek yerine, birkaç kareyi OpenCV ile YENİDEN
    encode edip (pipeline'ın canlı üreteceği klip gibi) gönderir. Test 1
    hazır bir dosyanın kabul edildiğini gösterdi ama pipeline kendi klibini
    anlık üretecek - farklı bir codec/konteyner EVREN tarafından reddedilebilir.
    """
    print("\n=== TEST 3: OpenCV ile YENİDEN ENCODE edilmiş klip kabul ediliyor mu? ===")
    if not video_path.is_file():
        print(f"  -> Video bulunamadi: {video_path}")
        return
    cap = cv2.VideoCapture(str(video_path))
    frames = []
    for _ in range(30):  # ~1-1.5 saniyelik klip
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(frame)
    cap.release()
    if not frames:
        print("  -> Videodan kare okunamadi.")
        return
    h, w = frames[0].shape[:2]

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(tmp_path), fourcc, 25.0, (w, h))
    for f in frames:
        writer.write(f)
    writer.release()

    size_kb = tmp_path.stat().st_size / 1024
    print(f"  -> {len(frames)} kare, mp4v codec, {w}x{h}, {size_kb:.0f} KB olarak encode edildi")
    clip_b64 = base64.b64encode(tmp_path.read_bytes()).decode("ascii")
    tmp_path.unlink(missing_ok=True)

    payload = {
        "model": "vlm",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Bu kisa klipte ne goruyorsun? Kisaca Turkce anlat."},
                    {"type": "video_url", "video_url": {"url": f"data:video/mp4;base64,{clip_b64}"}},
                ],
            }
        ],
        "temperature": 0.0,
        "max_tokens": 512,
    }
    _post(payload)


def test_thinking_kapatma() -> None:
    print("\n=== TEST 2: 'llm-fast' + chat_template_kwargs.enable_thinking=False ===")
    prompt = "1 ile 10 arasinda asal sayilari virgulle ayirarak yaz. Sadece sayilari yaz, baska hicbir sey yazma."

    print("-- 2a) kontrol (flag YOK, mevcut davranis) --")
    _post({
        "model": "llm-fast",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "max_tokens": 300,
    })

    print("-- 2b) chat_template_kwargs ile dusunme kapatilmaya calisiliyor --")
    _post({
        "model": "llm-fast",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "max_tokens": 300,
        "chat_template_kwargs": {"enable_thinking": False},
    })


def test_thinking_kapatma_gercek_prompt(video_path: Path) -> None:
    """Test 2, basit bir soruyla yapilmisti - reasoning hic tetiklenmedigi
    icin flag'in gercek etkisi hic gorulemedi. Burada image-VLM'in gercekte
    kullandigi UZUN, karmasik prompt + gercek bir goruntuyle deniyoruz -
    canli testte tam bu tur promptlarda reasoning 4096 token'i tuketip
    content:None dondurmustu (iki kez gozlemlendi)."""
    print("\n=== TEST 4: Gercek image-VLM prompt'uyla 'llm-fast' thinking kapatma ===")
    if not video_path.is_file():
        print(f"  -> Video bulunamadi: {video_path}")
        return
    cap = cv2.VideoCapture(str(video_path))
    ok, frame = cap.read()
    cap.release()
    if not ok:
        print("  -> Videodan kare okunamadi.")
        return
    ok, buf = cv2.imencode(".jpg", frame)
    img_b64 = base64.b64encode(buf.tobytes()).decode("ascii")

    prompt = generate_vlm_prompt(
        speed=49.5, zigzag=0.08, threat=0.6,
        yolo_class="hava_araci (ucak, iha veya helikopter)", yolo_conf=0.78,
        n_crops=1,
        vrag_context="1. Vestel KARAYEL (Sinif: 1. Turkiye oncelikli IHA, Ulke: Bilinmiyor, Benzerlik: 88%)\n"
                     "2. F-35a lightning ii (Sinif: 3. Yabanci savas ucaklari, Ulke: Bilinmiyor, Benzerlik: 86%)",
    )

    def _payload(extra: dict) -> dict:
        base = {
            "model": "llm-fast",
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                ],
            }],
            "temperature": 0.0,
            "top_p": 1.0,
            "max_tokens": 4096,
            "response_format": {"type": "json_object"},
        }
        base.update(extra)
        return base

    print("-- 4a) kontrol (flag YOK, canli testteki gercek davranis) --")
    _post(_payload({}))

    print("-- 4b) chat_template_kwargs ile dusunme kapatilmaya calisiliyor --")
    _post(_payload({"chat_template_kwargs": {"enable_thinking": False}}))


if __name__ == "__main__":
    if not API_KEY:
        print("HATA: VLM_API_KEY ortam degiskeni bos. Once export et.")
        sys.exit(1)
    video_arg = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_VIDEO
    test_video_kabulu(video_arg)
    test_canli_encode_kabulu(video_arg)
    test_thinking_kapatma()
    test_thinking_kapatma_gercek_prompt(video_arg)
