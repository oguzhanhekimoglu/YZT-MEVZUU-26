# -*- coding: utf-8 -*-
"""VRAG backend (FastAPI) — YOLO tespit+takip + VRAG model tanıma.

Uçlar:
  POST /oturum/baslat {video_yolu}  → video işlemeyi başlat (arka plan thread)
  POST /oturum/durdur               → durdur
  GET  /durum                       → oturum durumu
  GET  /video                       → MJPEG (kutulu kare akışı)
  WS   /hedefler                    → canlı hedef JSON'u (web arayüzü)
  POST /tani  (dosya)               → tek görselde VRAG (model + adaylar)
  GET  /meta                        → model/ülke/rol listeleri
  GET  /gecmis?adet=N               → tespit geçmişi (log)
"""
import asyncio
import json
import logging
import threading
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np
import requests
from fastapi import FastAPI, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

# BUG-FIX (INFO logları görünmüyordu): main.py hiç logging.basicConfig
# çağırmıyordu, kök logger uvicorn'un kendi ayarına rağmen varsayılan WARNING
# seviyesinde kalıyordu — pipeline.py/vlm/engine.py'deki TÜM log.info()
# çağrıları ([VLM BEKLEMEDE], [LLM] Karar alındı, [VRAG] Embedder hazır vb.)
# sessizce kayboluyordu. force=True, uvicorn'un kendi handler'ı zaten
# ayarlanmış olsa bile seviyeyi INFO'ya zorluyor.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    force=True,
)

import ayarlar
from pipeline_adapter import PipelineAdapter


class Durum:
    def __init__(self):
        self.fuzyon: PipelineAdapter | None = None
        self.calisiyor = False
        self.son_kare: bytes | None = None
        self.son_hedefler: list = []
        # BUG-FIX ("bbox eskisi gibi kare içine almıyor"): frontend'in kutu
        # konumlandırma çerçevesi, gerçekten yayınlanan (resize sonrası)
        # karenin en-boy oranını bilmeli. <img onLoad> ile tahmin MJPEG
        # multipart akışlarında güvenilir değil - bu yüzden backend'in kendi
        # bildiği piksel boyutunu doğrudan /durum ile bildiriyoruz.
        self.kare_genislik = 0
        self.kare_yukseklik = 0
        self.frame_no = 0
        self.kaynak = ""
        self.fps = 0.0
        self.sure_saniye = 0.0
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
        # BUG-FIX: ayni video_id (dosya adi) farkli oturumlarda tekrar tekrar
        # test edildiginde, karar_servisi'ndeki event_memory.db onceki
        # oturumlarin kayitlarini hic silmiyor - video-geneli ozet bunlari da
        # dahil edip "eski ciktilari baz alarak cevap uretiyor"du. Bu, mevcut
        # oturumun BASLANGIC zamanini tutar; /video/ozet bunu karar_servisi'ne
        # `since` olarak gecerek onceki oturumlari tamamen disarida birakir.
        self.oturum_baslangic_utc: datetime | None = None


durum = Durum()


import queue
import subprocess
import sys

llm_process = None

def _meta_tara() -> dict:
    """VRAG-final/data/referans metadata'sından model/ülke/rol listelerini çıkarır."""
    kok = ayarlar.VRAG_DIZINI / "data" / "referans"
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
    llm_dir = str((Path(__file__).resolve().parent.parent / "karar_servisi"))
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
app.mount("/goruntule", StaticFiles(directory=str(Path(__file__).parent / "web"), html=True), name="goruntule")

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
            # BUG-FIX: pipeline_adapter.py artık track_id başına VLM/LLM önbelleği
            # tutuyor ve tracker.reset() (yukarıda çağrıldı) her seferinde
            # tracker.reset_generation'ı artırıyor — PipelineAdapter.isle() bu
            # sayaç değiştiğinde önbelleği kendiliğinden temizliyor, burada
            # elle temizlemeye gerek yok (bkz. backend/pipeline_adapter.py).

    # Video-geneli özet (karar_servisi tarafında video_id'ye göre gruplanıyor)
    # gerçek videoyla eşleşsin diye pipeline'a bu oturumun video adını bildiriyoruz.
    durum.fuzyon.pipeline.video_id = Path(video_yolu).name

    cap = cv2.VideoCapture(video_yolu)
    if not cap.isOpened():
        durum.calisiyor = False
        print(f"Kaynak açılamadı: {video_yolu}", flush=True)
        return

    # Arayüzdeki süre göstergesi videonun gerçek süresiyle eşleşsin: fps ve
    # toplam kare sayısı OpenCV'den okunur, /durum bu ikisinden hesaplanan
    # toplam süreyi ve (frame_no/fps ile) o ana kadar geçen süreyi döndürür.
    okunan_fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    toplam_kare = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
    with durum.kilit:
        durum.fps = okunan_fps
        durum.sure_saniye = (toplam_kare / okunan_fps) if okunan_fps > 0 else 0.0

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
                durum.kare_yukseklik, durum.kare_genislik = annotated.shape[:2]
                
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
        durum.fps = 0.0
        durum.sure_saniye = 0.0
        durum.kare_genislik = 0
        durum.kare_yukseklik = 0
    durum.calisiyor = True
    durum.kaynak = yol
    durum.oturum_baslangic_utc = datetime.now(UTC)
    durum.thread = threading.Thread(target=_video_dongu, args=(yol,), daemon=True)
    durum.thread.start()
    return {"ok": True, "kaynak": yol}


@app.post("/oturum/durdur")
def oturum_durdur():
    durum.calisiyor = False
    return {"ok": True}


@app.get("/durum")
def durum_al():
    gecen_saniye = (durum.frame_no / durum.fps) if durum.fps > 0 else 0.0
    # BUG-FIX (mimari değişiklik): FPS/Slicer/Tracker gibi canlı performans
    # telemetrisi eskiden yalnızca video karesine yakılan yeşil HUD metniydi
    # (bkz. visualizer.py). Artık burada döndürülüyor - frontend'in "Canlı
    # Performans" paneli bunu okuyor, video karesi artık temiz.
    performans = durum.fuzyon.pipeline.performans if durum.fuzyon is not None else {}
    return {"calisiyor": durum.calisiyor, "kaynak": durum.kaynak,
            "frame_no": durum.frame_no, "hedef_sayisi": len(durum.son_hedefler),
            "model_sayisi": durum.meta_cache.get("model_sayisi", 0),
            "sure_saniye": durum.sure_saniye, "gecen_saniye": gecen_saniye,
            "performans": performans,
            "kare_genislik": durum.kare_genislik, "kare_yukseklik": durum.kare_yukseklik}


@app.get("/video/ozet")
def video_ozet():
    """Bu oturumun videosuna ait, karar_servisi'nde zaten biriken hedef-bazlı
    nihai kararlardan sentezlenmiş video-geneli özeti döner (bkz. TYDA
    şartnamesi: genel video özeti + olaylar + risk + aksiyonlar). video_id,
    pipeline.py'nin _async_llm_task'ta kullandığı Path(video_yolu).name ile
    birebir aynı normalize edilmiş biçimde hesaplanır."""
    if not durum.kaynak:
        return {"status": "pending", "summary": "", "events": [], "risk": "bilinmiyor", "actions": []}
    video_id = Path(durum.kaynak).name
    parametreler = {}
    if durum.oturum_baslangic_utc is not None:
        # BUG-FIX: ayni video_id onceki oturumlarda da test edilmis olabilir -
        # `since` ile karar_servisi'ne sadece MEVCUT oturumun kayitlarina
        # bakmasini soyluyoruz (bkz. Durum.oturum_baslangic_utc yorumu).
        parametreler["since"] = durum.oturum_baslangic_utc.isoformat()
    try:
        yanit = requests.get(
            f"http://127.0.0.1:8001/api/v1/videos/{video_id}/summary",
            params=parametreler,
            timeout=120.0,
        )
        yanit.raise_for_status()
        return yanit.json()
    except requests.exceptions.RequestException as e:
        print(f"[VIDEO-OZET] karar_servisi'ne erişilemedi: {e}", flush=True)
        return JSONResponse(
            {"status": "partial", "summary": "Karar servisine erişilemedi.", "events": [], "risk": "bilinmiyor", "actions": []},
            status_code=502,
        )


@app.get("/videolar")
def videolar():
    """data/videos/ altındaki mevcut test videolarını listeler (arayüzde seçim için)."""
    video_dizini = ayarlar.VRAG_DIZINI / "data" / "videos"
    if not video_dizini.exists():
        return {"videolar": []}
    uzantilar = {".mp4", ".mov", ".avi", ".mkv"}
    dosyalar = sorted(
        (p for p in video_dizini.iterdir() if p.is_file() and p.suffix.lower() in uzantilar),
        key=lambda p: p.name.lower(),
    )
    return {"videolar": [{"ad": p.name, "yol": str(p)} for p in dosyalar]}


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
    # Not directly supported in simple adapter yet
    return {"model": None, "adaylar": []}


@app.get("/meta")
def meta():
    return durum.meta_cache


_referans_yollari: dict[str, str] = {}


def _referans_bul(model: str):
    if model in _referans_yollari:
        return _referans_yollari[model]
        
    target_lower = model.lower().strip()
    
    for mp in (ayarlar.VRAG_DIZINI / "data" / "referans").rglob("metadata.json"):
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
    # Not directly supported in simple adapter yet (kayit.py kaldırıldı — kullanılmıyordu).
    return {"kayitlar": []}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=ayarlar.HOST, port=ayarlar.PORT)
