# -*- coding: utf-8 -*-
"""Tam hat testi: bir videoda YOLO + VRAG; annotated kareler + tanınan modeller."""
import sys
import time
from collections import defaultdict
from pathlib import Path

import cv2
from PIL import Image

from fuzyon import Fuzyon

VID = sys.argv[1] if len(sys.argv) > 1 else \
    r"C:\Users\oguz\AppData\Local\Temp\claude\C--Users-oguz-Desktop-VRAG-0\1bb01467-d139-4565-b628-6cd113404c89\scratchpad\test_videolar\f16_test.webm"
OUT = Path(r"C:\Users\oguz\AppData\Local\Temp\claude\C--Users-oguz-Desktop-VRAG-0\1bb01467-d139-4565-b628-6cd113404c89\scratchpad\kokpit_test2")
OUT.mkdir(exist_ok=True)

print("Fuzyon yükleniyor...", flush=True)
f = Fuzyon(source_fps=25.0)
cap = cv2.VideoCapture(VID)
n = 0
kayitli = []
modeller = defaultdict(float)
sinif_say = defaultdict(int)
tespit = 0
t0 = time.time()
while True:
    ret, frame = cap.read()
    if not ret:
        break
    annotated, hedefler = f.isle(frame)
    if hedefler:
        tespit += 1
        for h in hedefler:
            sinif_say[h["sinif"]] += 1
            if h.get("model"):
                modeller[h["model"]] = max(modeller[h["model"]], h.get("model_skor") or 0)
        if len(kayitli) < 9 and n % 15 == 0:
            p = OUT / f"kare_{n:04d}.jpg"
            cv2.imwrite(str(p), annotated)
            kayitli.append(p)
    n += 1
# worker'ın son sonuçları cache'lemesi için kısa bekle
time.sleep(2.5)
cap.release()
sure = time.time() - t0
f.kapat()

print(f"\n=== SONUÇ ===", flush=True)
print(f"kare: {n} | tespitli: {tespit} | süre {sure:.1f}s (~{n/max(sure,1):.1f}/sn)", flush=True)
print(f"sınıf: {dict(sinif_say)}", flush=True)
print("VRAG tanınan (en iyi skor):", flush=True)
for m, s in sorted(modeller.items(), key=lambda x: -x[1]):
    print(f"   {s:.3f}  {m}", flush=True)

if kayitli:
    ims = [Image.open(p).convert("RGB") for p in kayitli]
    w, h = ims[0].size
    cols = 3
    rows = (len(ims) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * w, rows * h), "black")
    for i, im in enumerate(ims):
        sheet.paste(im, ((i % cols) * w, (i // cols) * h))
    mp = OUT / "montaj.jpg"
    sheet.save(mp, quality=88)
    print(f"\nMontaj: {mp} ({len(kayitli)} kare)", flush=True)
else:
    print("\nTespitli kare yok.", flush=True)
