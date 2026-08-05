# -*- coding: utf-8 -*-
"""VLM doğrulayıcı — VRAG'ın model tahminini gemma (ollama) ile DENETLER.

Akış: YOLO crop → VRAG modeli bulur → bu modül crop + VRAG tahminini gemma'ya
verir, gemma görüntüye bakıp 'onaylandı/şüpheli/reddedildi' der + genel istihbarat
(araç sınıfı, tehdit, görsel analiz) üretir. Ollama HTTP API (localhost:11434).
"""
import base64
import json
import re

import cv2
import requests

import ayarlar

_PROMPT = """Sen deneyimli bir askeri hava aracı görüntü analistisin. Sana bir hava
aracının kırpılmış görüntüsü veriliyor.

Bir görüntü-eşleştirme sistemi (VRAG) bu aracı şöyle tahmin etti:
- En olası model: {model}  (benzerlik %{skor})
- Diğer adaylar: {adaylar}

GÖRÜNTÜYE DİKKATLE BAK: kanat şekli (delta/süpürgeç/düz), motor sayısı ve yeri,
kuyruk tasarımı, gövde oranı, iniş takımı. SADECE GÖRDÜĞÜNÜ değerlendir; göremediğin
bir detayı UYDURMA. Emin değilsen "şüpheli"/"belirsiz" de.

Yalnızca şu JSON'u döndür (Türkçe değerler):
{{
  "dogrulama": "onaylandı" | "şüpheli" | "reddedildi",
  "gercek_tahmin": "görüntüde gördüğün en olası model (VRAG doğruysa aynısı)",
  "arac_sinifi": "Savaş Uçağı / İHA / SİHA / Helikopter / Yolcu Uçağı / Bombardıman ...",
  "tehdit_seviyesi": "Düşük" | "Orta" | "Yüksek",
  "gorsel_analiz": "1-2 cümle gerekçe (hangi görsel özelliklere dayandın)",
  "gidis_yonu": "görselden çıkarabiliyorsan yön, yoksa belirsiz"
}}"""


def _json_ayikla(metin: str):
    """gemma yanıtından ilk geçerli JSON nesnesini çıkarır."""
    try:
        return json.loads(metin)
    except (ValueError, TypeError):
        pass
    m = re.search(r"\{.*\}", metin or "", re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except ValueError:
            return None
    return None


def dogrula(bgr_crop, adaylar) -> dict | None:
    """crop (BGR) + VRAG adayları → gemma denetim JSON'u (veya None)."""
    if bgr_crop is None or bgr_crop.size == 0 or not adaylar:
        return None
    ok, buf = cv2.imencode(".jpg", bgr_crop, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        return None
    img_b64 = base64.b64encode(buf).decode("utf-8")

    a0 = adaylar[0]
    aday_metni = ", ".join(f"{a.model} (%{a.skor*100:.0f})" for a in adaylar[:4])
    prompt = _PROMPT.format(model=a0.model, skor=f"{a0.skor*100:.0f}", adaylar=aday_metni)

    payload = {
        "model": ayarlar.VLM_MODEL,
        "prompt": prompt,
        "images": [img_b64],
        "format": "json",
        "stream": False,
        "options": {"num_predict": ayarlar.VLM_NUM_PREDICT, "temperature": 0.2},
    }
    try:
        r = requests.post(ayarlar.VLM_API, json=payload, timeout=ayarlar.VLM_TIMEOUT)
        r.raise_for_status()
        cevap = r.json().get("response", "")
    except requests.RequestException:
        return None

    veri = _json_ayikla(cevap)
    if not isinstance(veri, dict):
        return None
    # alanları normalize et
    return {
        "dogrulama": str(veri.get("dogrulama", "belirsiz")),
        "gercek_tahmin": str(veri.get("gercek_tahmin", "")),
        "arac_sinifi": str(veri.get("arac_sinifi", "")),
        "tehdit_seviyesi": str(veri.get("tehdit_seviyesi", "belirsiz")),
        "gorsel_analiz": str(veri.get("gorsel_analiz", "")),
        "gidis_yonu": str(veri.get("gidis_yonu", "belirsiz")),
    }


def hazir_mi() -> bool:
    """ollama ayakta + model yüklü mü (hızlı kontrol)."""
    try:
        r = requests.get(ayarlar.VLM_API.replace("/api/generate", "/api/tags"), timeout=5)
        adlar = [m.get("name", "") for m in r.json().get("models", [])]
        return any(ayarlar.VLM_MODEL.split(":")[0] in a for a in adlar)
    except requests.RequestException:
        return False
