# -*- coding: utf-8 -*-
"""VRAG backend (FastAPI) â€” YOLO tespit+takip + VRAG model tanÄ±ma.

UÃ§lar:
  POST /oturum/baslat {video_yolu}  â†’ video iÅŸlemeyi baÅŸlat (arka plan thread)
  POST /oturum/durdur               â†’ durdur
  GET  /durum                       â†’ oturum durumu
  GET  /video                       â†’ MJPEG (kutulu kare akÄ±ÅŸÄ±)
  WS   /hedefler                    â†’ canlÄ± hedef JSON'u (C# panelleri)
  POST /tani  (dosya)               â†’ tek gÃ¶rselde VRAG (model + adaylar)
  GET  /meta                        â†’ model/Ã¼lke/rol listeleri
  GET  /gecmis?adet=N               â†’ tespit geÃ§miÅŸi (log)
"""
import asyncio
import json
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

import cv2
import numpy as np
from fastapi import FastAPI, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

import ayarlar
from pipeline_adapter import PipelineAdapter


class Durum:
    def __init__(self):
        self.fuzyon: PipelineAdapter | None = None
        self.calisiyor = False
        self.son_kare: bytes | None = None
        self.son_hedefler: list = []
        self.frame_no = 0
        self.kaynak = ""
        self.kilit = threading.Lock()
        # BUG-FIX (çifte pipeline / VRAG kilit çakışması): "Başlat"a art arda
        # basılırsa (ör. çift tıklama, hızlı yeniden deneme) iki ayrı
        # _video_dongu thread'i aynı anda "durum.fuzyon is None mı?" kontrolünü
        # geçip İKİ AYRI PipelineAdapter (ve dolayısıyla iki VRAGEngine/Qdrant
        # bağlantısı) oluşturmaya çalışabiliyordu. İkincisi, Qdrant'ın yerel
        # veritabanı dosyasını kilitli bulup VRAG'ı hiç başlatamıyordu — sonuç:
        # VRAG'dan hiç cevap gelmiyor, VLM de desteksiz kalıp "Bilinmiyor"
        # döndürüyordu. Bu kilit, pipeline oluşturma/sıfırlama bloğunun aynı
        # anda yalnızca bir thread tarafından çalıştırılmasını garanti eder.
        self.pipeline_kilit = threading.Lock()
        self.thread: threading.Thread | None = None
        self.meta_cache: dict = {}


durum = Durum()


import queue
import subprocess
import sys

llm_process = None

def _meta_tara() -> dict:
    """VRAG-final/veriler metadata'sından model/ülke/rol listelerini çıkarır."""
    kok = ayarlar.VRAG_DIZINI / "veriler"
    modeller, ulkeler, roller = set(), set(), set()
    for mp in kok.rglob("metadata.json"):
        try:
            m = json.loads(mp.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if m.get("model"):
            modeller.add(m["model"])
        if m.get("ulke"):
            ulkeler.add(str(m["ulke"]))
        if m.get("rol"):
            roller.add(str(m["rol"]))
    return {"model_sayisi": len(modeller), "ulkeler": sorted(ulkeler),
            "roller": sorted(roller)}


@asynccontextmanager
async def lifespan(app: FastAPI):
    global llm_process
    print("Modeller video başlatıldığında kendi iş parçacığında (thread) yüklenecek...", flush=True)
    durum.meta_cache = _meta_tara()
    
    # LLM Modülünü Başlat
    llm_dir = str((Path(__file__).resolve().parent.parent.parent / "LLM"))
    print(f"[BACKEND] LLM API başlatılıyor... ({llm_dir})", flush=True)
    try:
        # LLM'i ana ortamın Python'u ile başlat (Kullanıcının .venv'si)
        # Kopyalanmış bozuk .venv sorununu aşmak için sys.executable zorunlu kılındı.
        llm_process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "operational_decision.api.main:app", "--app-dir", "src", "--host", "127.0.0.1", "--port", "8001"],
            cwd=llm_dir
        )
    except Exception as e:
        print(f"[BACKEND] LLM başlatılırken hata: {e}")
        
    print(f"Hazır. {durum.meta_cache['model_sayisi']} model indeksli.", flush=True)
    yield
    if durum.fuzyon:
        durum.fuzyon.kapat()
    if llm_process:
        llm_process.terminate()

app = FastAPI(title="VRAG Backend", lifespan=lifespan)
app.mount("/goruntule", StaticFiles(directory=str(Path(__file__).parent.parent / "web"), html=True), name="goruntule")

def _kare_okuyucu(cap, q):
    while durum.calisiyor:
        ret, frame = cap.read()
        if not ret:
            break
        try:
            q.put(frame, timeout=1.0)
        except queue.Full:
            continue
    q.put(None)

def _video_dongu(video_yolu: str):
    durum.calisiyor = True

    # BUG-FIX: bu blok (pipeline oluşturma/sıfırlama) art arda gelen iki
    # /oturum/baslat isteğinde aynı anda çalışırsa, "durum.fuzyon is None mı?"
    # kontrolünü ikisi de geçip iki ayrı PipelineAdapter (iki ayrı VRAG/Qdrant
    # bağlantısı) oluşturmaya çalışabiliyordu — bkz. Durum.pipeline_kilit
    # tanımındaki not. Kilitle bu bloğu tek seferde tek thread'e indiriyoruz.
    with durum.pipeline_kilit:
        # CUDA Thread kilitlemesini önlemek için modeli bu thread içinde yükle
        if durum.fuzyon is None:
            print("[BACKEND] Modeller belleğe alınıyor, lütfen bekleyin...", flush=True)
            from pipeline_adapter import PipelineAdapter
            durum.fuzyon = PipelineAdapter(source_fps=25.0)
        else:
            # Otomatik tam sıfırlama: farklı çözünürlükte bir video ile yeniden
            # başlatılsa bile (tracker, kamera hareketi kompanzasyonu, sahne-diff
            # önbelleği) her oturum temiz baştan başlasın — model ağırlıklarını
            # yeniden yüklemeden (~10-15sn kazanç), yalnızca çözünürlüğe bağlı
            # önbellekleri sıfırlar. Böylece video değiştirmek için backend'i
            # kapatıp açmaya gerek kalmaz.
            print("[BACKEND] Yeni oturum: tracker + kamera hareketi + VLM önbelleği sıfırlanıyor...", flush=True)
            durum.fuzyon.pipeline.tracker.reset()
            durum.fuzyon.pipeline._prev_gray = None
            # BUG-FIX: tracker.reset() ByteTrack'in ID sayacını da sıfırlıyor, yani
            # yeni videodaki ilk hedef eski videodaki aynı track_id'yi alabiliyordu.
            # VLM'in kendi önbelleği (self.vlm) ayrı bir nesne olduğu için tracker
            # sıfırlanınca otomatik temizlenmiyordu — eski videodan kalan cevap
            # (ör. "Kaan", tutarlılık 2/2) hiç yeni analiz yapılmadan gösteriliyordu.
            durum.fuzyon.pipeline.vlm.reset_all()
            # BUG-FIX: pipeline_adapter.py, henüz kendi tazesi olmayan hedefler için
            # (ör. yeni track ilk birkaç karede) en son bilinen VLM/LLM sonucunu
            # (last_vlm_payload/last_llm_payload) "hayalet" olarak gösteriyordu —
            # bunlar PipelineAdapter nesnesinde saklandığı için (oturumlar arası
            # yaşıyor) yeni video başlasa bile eski sonuç ekranda kalmaya devam
            # ediyordu. Yeni oturumda bunlar da temizlenmeli.
            durum.fuzyon.last_vlm_payload = None
            durum.fuzyon.last_llm_payload = None

    cap = cv2.VideoCapture(video_yolu)
    if not cap.isOpened():
        durum.calisiyor = False
        print(f"Kaynak açılamadı: {video_yolu}", flush=True)
        return
        
    frame_queue = queue.Queue(maxsize=30)
    reader_thread = threading.Thread(target=_kare_okuyucu, args=(cap, frame_queue), daemon=True)
    reader_thread.start()
    
    while durum.calisiyor:
        try:
            frame = frame_queue.get(timeout=0.5)
        except queue.Empty:
            continue
            
        if frame is None:
            break
            
        annotated, hedefler = durum.fuzyon.isle(frame)
        
        # MJPEG için kareyi sıkıştır
        ok, jpg = cv2.imencode(".jpg", annotated,
                               [cv2.IMWRITE_JPEG_QUALITY, ayarlar.JPEG_KALITE])
        if ok:
            with durum.kilit:
                durum.son_kare = jpg.tobytes()
                durum.son_hedefler = hedefler
                durum.frame_no += 1
                
    cap.release()
    durum.calisiyor = False
    print("Video bitti / durduruldu.", flush=True)


@app.post("/oturum/baslat")
def oturum_baslat(govde: dict):
    yol = govde.get("video_yolu", "")
    if not Path(yol).exists():
        return JSONResponse({"hata": f"Video bulunamadÄ±: {yol}"}, status_code=400)
    # Ã‡alÄ±ÅŸan oturum varsa Ã¶nce DURDUR (yeni videoya sorunsuz geÃ§iÅŸ).
    if durum.calisiyor:
        durum.calisiyor = False
        eski = durum.thread
        if eski and eski.is_alive():
            eski.join(timeout=4)
    with durum.kilit:                 # eski videonun son karesini/hedeflerini temizle
        durum.son_kare = None
        durum.son_hedefler = []
        durum.frame_no = 0
    durum.calisiyor = True
    durum.kaynak = yol
    durum.thread = threading.Thread(target=_video_dongu, args=(yol,), daemon=True)
    durum.thread.start()
    return {"ok": True, "kaynak": yol}


@app.post("/oturum/durdur")
def oturum_durdur():
    durum.calisiyor = False
    return {"ok": True}


@app.get("/durum")
def durum_al():
    return {"calisiyor": durum.calisiyor, "kaynak": durum.kaynak,
            "frame_no": durum.frame_no, "hedef_sayisi": len(durum.son_hedefler),
            "model_sayisi": durum.meta_cache.get("model_sayisi", 0)}


@app.get("/video")
def video():
    def uret():
        bos = 0
        while True:
            with durum.kilit:
                kare = durum.son_kare
            if kare:
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + kare + b"\r\n")
                bos = 0
            else:
                bos += 1
                if bos > 300:      # ~10 sn hiÃ§ kare yoksa akÄ±ÅŸÄ± kapat
                    break
            time.sleep(1 / 30)
    return StreamingResponse(uret(),
                             media_type="multipart/x-mixed-replace; boundary=frame")


@app.websocket("/hedefler")
async def hedefler_ws(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            with durum.kilit:
                paket = {"frame": durum.frame_no, "hedefler": durum.son_hedefler}
            await ws.send_json(paket)
            await asyncio.sleep(0.2)
    except WebSocketDisconnect:
        pass


@app.post("/tani")
async def tani(dosya: UploadFile = File(...)):
    veri = await dosya.read()
    arr = np.frombuffer(veri, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return JSONResponse({"hata": "GÃ¶rsel Ã§Ã¶zÃ¼lemedi."}, status_code=400)
    adaylar = [] # Not directly supported in simple adapter yet
    if not adaylar:
        return {"model": None, "adaylar": []}
    from vrag_adapter import dusuk_guven, margin
    return {
        "model": adaylar[0].model, "skor": round(adaylar[0].skor, 3),
        "dusuk_guven": dusuk_guven(adaylar), "margin": round(margin(adaylar), 3),
        "ulke": adaylar[0].ulke, "uretici": adaylar[0].uretici, "rol": adaylar[0].rol,
        "adaylar": [{"model": a.model, "skor": round(a.skor, 3),
                     "ulke": a.ulke, "rol": a.rol} for a in adaylar],
    }


@app.get("/meta")
def meta():
    return durum.meta_cache


_referans_yollari: dict[str, str] = {}


def _referans_bul(model: str):
    if model in _referans_yollari:
        return _referans_yollari[model]
        
    target_lower = model.lower().strip()
    
    for mp in (ayarlar.VRAG_DIZINI / "veriler").rglob("metadata.json"):
        try:
            m_data = json.loads(mp.read_text(encoding="utf-8"))
            meta_model = m_data.get("model", "")
            folder_name = mp.parent.name
            
            if meta_model.lower().strip() == target_lower or folder_name.lower().strip() == target_lower:
                for p in sorted(mp.parent.iterdir()):
                    if p.suffix.lower() in (".jpg", ".jpeg", ".png"):
                        _referans_yollari[model] = str(p)
                        return str(p)
        except (OSError, ValueError):
            continue
    return None


@app.get("/referans")
def referans(model: str):
    """Bir modelin dataset'teki temsili fotoÄŸrafÄ±nÄ± dÃ¶ndÃ¼rÃ¼r ('iÅŸte bu X' kanÄ±tÄ±)."""
    yol = _referans_bul(model)
    if yol and Path(yol).exists():
        return FileResponse(yol)
    return JSONResponse({"hata": "referans bulunamadÄ±"}, status_code=404)


@app.get("/gecmis")
def gecmis(adet: int = 100):
    if False:
        return {"kayitlar": durum.fuzyon.kayit.son_kayitlar(adet)}
    return {"kayitlar": []}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=ayarlar.HOST, port=ayarlar.PORT)
