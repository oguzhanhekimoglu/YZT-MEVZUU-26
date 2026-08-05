# -*- coding: utf-8 -*-
"""Kokpit backend ayarlarÄ± â€” yollar ve fÃ¼zyon parametreleri tek yerde."""
from pathlib import Path

# --- Proje yollarÄ± (klasÃ¶r-iÃ§i kopyalar; GÃ–RELÄ° â†’ klasÃ¶rÃ¼ taÅŸÄ±san da Ã§alÄ±ÅŸÄ±r) ---
_KOK = Path(__file__).resolve().parent.parent           # VRAG-Kokpit-Tam
MEVZUU_YOLO_DIZINI = _KOK / "yolo"                      # YOLO hattÄ± (klasÃ¶r iÃ§i)
VRAG_DIZINI = _KOK.parent                              # VRAG retrieval (klasÃ¶r iÃ§i)

# --- FÃ¼zyon (VRAG tetikleme) ---
VRAG_PERIYOT_SN = 2.0        # aynÄ± track iÃ§in VRAG'Ä± en fazla bu sÄ±klÄ±kta koÅŸtur (periyodik yenile)
VRAG_MIN_HITS = 3            # track bu kadar kare gÃ¶rÃ¼lmeden VRAG koÅŸma (kararlÄ±lÄ±k)
# best.pt sÄ±nÄ±flarÄ±: 0=uÃ§urtma, 1=kuÅŸ, 2=drone, 3=uÃ§ak, 4=muharip Ä°HA.
# VRAG yalnÄ±z UÃ‡AK/DRONE sÄ±nÄ±flarÄ±na (2,3,4) uygulanÄ±r; kuÅŸ/uÃ§urtmaya (0,1) uygulanmaz.
VRAG_UCAK_SINIFLARI = {2, 3, 4}
VRAG_TOPK = 5                # arayÃ¼zde gÃ¶sterilecek aday sayÄ±sÄ±

# --- Kategori filtresi: YOLO sÄ±nÄ±fÄ±na gÃ¶re VRAG'Ä± ilgili kategorilerle sÄ±nÄ±rla ---
# KAPALI: YOLO'nun kaba/kararsÄ±z sÄ±nÄ±fÄ±na gÃ¼venmiyoruz (plane<->combat_uav karÄ±ÅŸÄ±yor);
# model kararÄ± tamamen VRAG'a bÄ±rakÄ±ldÄ± (tÃ¼m kategorilerde ara).
KATEGORI_FILTRESI_AKTIF = False
SINIF_KATEGORILERI = {
    2: {"Ticari Drone", "Drone", "Ä°HA", "SÄ°HA", "Kamikaze Ä°HA"},          # normaldrone
    3: {"SavaÅŸ UÃ§aÄŸÄ±", "Yolcu UÃ§aÄŸÄ±", "Nakliye/Ã–zel GÃ¶rev UÃ§aÄŸÄ±",         # plane (insanlÄ±)
        "BombardÄ±man UÃ§aÄŸÄ±", "Hafif UÃ§ak", "Ä°ÅŸ Jeti", "EÄŸitim UÃ§aÄŸÄ±", "Helikopter"},
    4: {"SÄ°HA", "Ä°HA", "Kamikaze Ä°HA", "Drone"},                          # combat_uav
}

# --- VLM doÄŸrulayÄ±cÄ± (ollama gemma â€” VRAG'Ä±n tahminini denetler) ---
VLM_AKTIF = True
VLM_MODEL = "gemma4:12b"
VLM_API = "http://localhost:11434/api/generate"
VLM_NUM_PREDICT = 2048       # gemma4 thinking modÃ¼lÃ¼ iÃ§in (arkadaÅŸÄ±n config'i)
VLM_TIMEOUT = 300            # yavaÅŸ (CPU/kÄ±smi offload) â€” 5 dk
VLM_MIN_HITS = 5             # VLM sadece iyi oturmuÅŸ track'lerde (yavaÅŸ, boÅŸa harcama)

# --- Sunucu ---
HOST = "127.0.0.1"
PORT = 8000
JPEG_KALITE = 80             # MJPEG akÄ±ÅŸ kalitesi (1-100)

# --- KayÄ±t ---
KAYIT_DOSYASI = Path(__file__).parent / "tespit_gecmisi.jsonl"
