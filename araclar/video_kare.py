# -*- coding: utf-8 -*-
"""Videodan eşit aralıklı kareler çıkarır (referans veri toplamak için).

Airshow / uçuş / drone videosundan onlarca farklı açı üretir — ekran görüntüsü
toplamaktan çok hızlı. Kareler hedef klasöre `kare_001.jpg ...` olarak yazılır;
sonra istersen 1..N yeniden adlandırıp `python -m vrag ingest` ile indekslersin.

Kullanım:
    python araclar/video_kare.py <video> <hedef_klasor> [kare_sayisi=15] [--sahne]

  --sahne : eşit aralık yerine SAHNE DEĞİŞİMİ karelerini seçer (çok kesikli
            videolarda daha çeşitli; akıcı/tek çekimlerde az kare verebilir).
"""
import subprocess
import sys
from pathlib import Path

if len(sys.argv) < 3:
    print(__doc__)
    sys.exit(1)

video = Path(sys.argv[1])
hedef = Path(sys.argv[2])
sayi = int(sys.argv[3]) if len(sys.argv) > 3 and not sys.argv[3].startswith("-") else 15
sahne = "--sahne" in sys.argv

if not video.exists():
    print(f"HATA: video yok: {video}")
    sys.exit(1)
hedef.mkdir(parents=True, exist_ok=True)


def _sure(v: Path) -> float:
    try:
        cikti = subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nokey=1:noprint_wrappers=1", str(v)],
            text=True).strip()
        return float(cikti)
    except Exception:
        return 0.0


kalip = str(hedef / "kare_%03d.jpg")
if sahne:
    # Sahne değişimi > 0.30 olan kareleri seç.
    vf = "select='gt(scene,0.30)',showinfo"
    cmd = ["ffmpeg", "-y", "-i", str(video), "-vf", vf, "-vsync", "vfr",
           "-qscale:v", "2", kalip]
else:
    sure = _sure(video)
    fps = (sayi / sure) if sure > 0 else 1.0
    # fps=sayi/süre -> yaklaşık `sayi` adet eşit aralıklı kare.
    cmd = ["ffmpeg", "-y", "-i", str(video), "-vf", f"fps={fps:.6f}",
           "-qscale:v", "2", kalip]
    print(f"video süresi ~{sure:.1f}s -> fps={fps:.4f} (~{sayi} kare)")

print("ffmpeg çalışıyor...", flush=True)
subprocess.run(cmd, check=True, stderr=subprocess.DEVNULL)
uretilen = sorted(hedef.glob("kare_*.jpg"))
print(f"BİTTİ: {len(uretilen)} kare -> {hedef}")
print("Sonra: kötü/bulanık kareleri sil, gerekirse metadata.json ekle, "
      "`python -m vrag ingest` ile indeksle.")
