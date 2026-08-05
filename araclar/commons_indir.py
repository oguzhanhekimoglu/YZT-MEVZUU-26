# -*- coding: utf-8 -*-
"""Wikimedia Commons'tan lisans-temiz uçak fotoğrafı indirir (atıflı).

Commons yalnızca özgür-lisanslı/kamu-malı içerik barındırır -> atıf vererek
kullanılır. Her indirmede kaynak sayfa + lisans + yazar `kaynak_atif.json`e yazılır.

Kullanım:
    python araclar/commons_indir.py "<arama>" <hedef_klasor> [adet=6]
"""
import json
import ssl
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://commons.wikimedia.org/w/api.php"
UA = "VRAG-Teknofest/1.0 (aircraft recognition research; educational)"

# Yerel CA deposu eski olabiliyor -> certifi'nin güncel paketini kullan.
try:
    import certifi
    _CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _CTX = ssl.create_default_context()


def _ac(url: str):
    return urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": UA}), timeout=45, context=_CTX)


def indir(sorgu: str, hedef: Path, adet: int = 6):
    params = {
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": sorgu, "gsrnamespace": "6", "gsrlimit": str(adet * 4),
        "prop": "imageinfo", "iiprop": "url|extmetadata|mime", "iiurlwidth": "1024",
    }
    url = API + "?" + urllib.parse.urlencode(params)
    data = json.load(_ac(url))
    pages = list(data.get("query", {}).get("pages", {}).values())
    pages.sort(key=lambda p: p.get("index", 999))  # arama sırasını koru
    hedef.mkdir(parents=True, exist_ok=True)

    atif, n = [], 0
    for pg in pages:
        if n >= adet:
            break
        ii = (pg.get("imageinfo") or [{}])[0]
        mime = ii.get("mime", "")
        if mime not in ("image/jpeg", "image/png"):
            continue  # SVG/diyagram/logo atla
        turl = ii.get("thumburl") or ii.get("url")
        if not turl:
            continue
        em = ii.get("extmetadata", {})
        lisans = em.get("LicenseShortName", {}).get("value", "?")
        yazar = em.get("Artist", {}).get("value", "?")
        ext = ".jpg" if mime == "image/jpeg" else ".png"
        dosya = hedef / f"commons_{n+1}{ext}"
        time.sleep(2.0)  # Wikimedia robot politikası: yavaş/nazik indir (429 önle)
        try:
            with _ac(turl) as resp, open(dosya, "wb") as f:
                f.write(resp.read())
        except Exception as e:
            print(f"  indirilemedi ({pg.get('title')}): {e}")
            continue
        atif.append({"dosya": dosya.name, "sayfa": pg.get("title"),
                     "lisans": lisans, "yazar": yazar, "kaynak_url": turl})
        print(f"  [{n+1}] {pg.get('title')}  ·  {lisans}")
        n += 1

    (hedef / "kaynak_atif.json").write_text(
        json.dumps(atif, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"BİTTİ: {n} foto -> {hedef}  (atıf: kaynak_atif.json)")
    return atif


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    adet = int(sys.argv[3]) if len(sys.argv) > 3 else 6
    indir(sys.argv[1], Path(sys.argv[2]), adet)
