# -*- coding: utf-8 -*-
import sys, os, json
sys.path.insert(0, r"C:\Users\oguz\Desktop\VRAG-Kokpit-Tam\vrag")
os.environ["HF_HUB_OFFLINE"]="1"; os.environ["TRANSFORMERS_OFFLINE"]="1"
from pathlib import Path
from collections import Counter
from vrag import config
from vrag.arama import ara
from vrag.degerlendirme import _gorseller, _haric
from vrag.vektor_deposu import VektorDeposu

VERI = config.VERI_DIZINI
depo = VektorDeposu()
hedefler = ["F-16 Fighting Falcon","F-35A Lightning II","F-4E Phantom II",
            "Bayraktar Kızılelma","Tusaş Hürjet"]
folders = {}
for mp in VERI.rglob("metadata.json"):
    try: m = json.loads(mp.read_text(encoding="utf-8")).get("model")
    except Exception: continue
    if m in hedefler and m not in folders: folders[m] = mp.parent
print("Leave-one-out (kendi fotosunu hariç tutarak):\n")
for model in hedefler:
    f = folders.get(model)
    if not f: print(f"  {model}: klasör yok"); continue
    gs = _gorseller(f); d=0; t3=0; conf=Counter()
    for g in gs:
        ad = ara(g, topk=3, depo=depo, haric_yollar=_haric(g))
        if ad and ad[0].model==model: d+=1
        if any(a.model==model for a in ad[:3]): t3+=1
        if ad and ad[0].model!=model: conf[ad[0].model]+=1
    print(f"  {model[:24]:24s}: {len(gs):2d} foto | top1 %{100*d//len(gs):3d} | top3 %{100*t3//len(gs):3d} | karıştırdığı: {dict(conf.most_common(2))}")
depo.kapat()
