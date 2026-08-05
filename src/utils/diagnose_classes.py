"""
Tanı scripti: raw YOLO çıktısını logla.
Ne zaman kus ID=2 (drone) alıyor görelim.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import cv2
import numpy as np
from collections import defaultdict

PYTHONPATH = r"C:\Users\BERAT\Desktop\DATASET\.venv\Lib\site-packages"
sys.path.insert(0, PYTHONPATH)

from ultralytics import YOLO

MODEL = r"C:\Users\BERAT\Desktop\DATASET\UAV-VRAG\models\best.pt"
VIDEO = r"C:\Users\BERAT\Desktop\DATASET\UAV-VRAG\data\videos\test.mp4"

CLASS_NAMES = {0: "kite", 1: "bird", 2: "IHA/drone(class_3)"}

model = YOLO(MODEL)
cap = cv2.VideoCapture(VIDEO)

class_counts = defaultdict(int)
class2_confs = []
frame_idx = 0

print(f"Video: {VIDEO}")
print(f"Toplam sınıf sayısı (modelin .names): {model.names}")
print("="*60)

while True:
    ret, frame = cap.read()
    if not ret or frame_idx > 300:
        break
    frame_idx += 1

    results = model.predict(frame, conf=0.15, verbose=False, device="cuda:0")
    for r in results:
        if r.boxes is None:
            continue
        for box in r.boxes:
            cls = int(box.cls[0])
            conf = float(box.conf[0])
            class_counts[cls] += 1
            if cls == 2:
                class2_confs.append(conf)
                if len(class2_confs) <= 20:
                    x1,y1,x2,y2 = [int(v) for v in box.xyxy[0]]
                    area = (x2-x1)*(y2-y1)
                    fh, fw = frame.shape[:2]
                    print(f"  Frame {frame_idx:03d}: cls=2(IHA) conf={conf:.2f} bbox=({x1},{y1},{x2},{y2}) area_ratio={area/(fw*fh):.4f}")

cap.release()
print("="*60)
print("ÖZET (300 frame):")
total = sum(class_counts.values())
for cls_id, cnt in sorted(class_counts.items()):
    pct = cnt / total * 100 if total else 0
    print(f"  {CLASS_NAMES.get(cls_id, str(cls_id))}: {cnt} tespit ({pct:.1f}%)")

if class2_confs:
    print(f"\nclass_3/IHA tespitlerinin güven istatistikleri:")
    print(f"  Ortalama conf: {np.mean(class2_confs):.3f}")
    print(f"  Min conf:      {min(class2_confs):.3f}")
    print(f"  Max conf:      {max(class2_confs):.3f}")
    print(f"  >0.50 conf:    {sum(1 for c in class2_confs if c > 0.50)} adet")
    print(f"  >0.30 conf:    {sum(1 for c in class2_confs if c > 0.30)} adet")