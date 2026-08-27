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
from pathlib import Path

import requests

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


if __name__ == "__main__":
    if not API_KEY:
        print("HATA: VLM_API_KEY ortam degiskeni bos. Once export et.")
        sys.exit(1)
    video_arg = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_VIDEO
    test_video_kabulu(video_arg)
    test_thinking_kapatma()
