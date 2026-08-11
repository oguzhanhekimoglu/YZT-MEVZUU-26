# Hava Sahası Gözetleme ve İHA Tehdit Tespit Sistemi

Video/kamera görüntüsünden hava araçlarını (uçak, İHA/SİHA, helikopter) tespit eden, tam olarak hangi model olduğunu tanıyan, bağımsız bir görsel dil modeliyle doğrulayan ve son olarak bir LLM karar destek katmanıyla risk değerlendirmesi + Türkçe rapor üreten, **tamamen yerel (offline)** çalışan bir sistem.

TEKNOFEST Türkçe Yapay Zeka Dil Ajanları Yarışması (3. Senaryo) kapsamında geliştirilmiştir.

## Sistem Mimarisi

```
Video Girdisi
     ↓
Görüntü İyileştirme + SAHI ile Kare Dilimleme     (src/detection, src/utils/enhancer.py)
     ↓
YOLO ile Nesne Tespiti                             (src/detection/slicer.py, models/best.pt)
     ↓
ByteTrack ile Takip                                (src/tracking/tracker.py)
     ↓
Hedefin Kırpılması (Crop)
     ↓
Model Tanıma (VRAG) + Görsel Doğrulama (VLM)       (src/vrag/, src/vlm/ — SigLIP2+Qdrant / Ollama)
     ↓
Karar Destek (LLM — risk + Türkçe rapor)           (LLM/ — ayrı FastAPI servisi)
     ↓
Web Arayüzü (Windows ve macOS'ta aynı şekilde)      (entegrasyon/)
     ↓
Operatör
```

**Neden VLM değil VRAG kimlik için birincil kaynak:** VLM'i model tanıma zincirine sokmak (retrieval + VLM birlikte) doğruluğu düşürdü (top-1 %88.9 → %64.4, benchmark verisiyle). Bu yüzden model kimliği VRAG'ın retrieval sonucuna dayanır; VLM bağımsız bir ikinci göz olarak tehdit değerlendirmesi ve doğrulama yapar, kimlik kararını değiştirmez.

## Klasör Yapısı

| Klasör | İçerik |
|---|---|
| `src/` | Ana algı hattı: SAHI+YOLO tespiti, ByteTrack takibi, VRAG (model tanıma), VLM entegrasyonu |
| `veriler/` | VRAG referans veri seti — `<kategori>/<model>/*.jpg` + `metadata.json` (ülke/üretici/rol) |
| `models/best.pt` | YOLO ağırlıkları |
| `output/qdrant_db/` | VRAG'ın indekslenmiş vektör veritabanı (Qdrant, embedded/local mod) |
| `LLM/` | Karar destek sistemi — ayrı bir FastAPI servisi (Platform Registry, Türkiye Envanteri, izin/uçuş planı/NOTAM kontrolleri, LLM ile Türkçe rapor) |
| `entegrasyon/` | Algı hattını (src/) ve karar destek sistemini (LLM/) kullanıcı arayüzüne bağlayan katman |
| `entegrasyon/backend/` | FastAPI backend — `src/core/pipeline.py`'yi çalıştırır, video akışı + hedef verisi sunar |
| `entegrasyon/web/` | Tek, platform bağımsız arayüz — tarayıcıdan açılır, Windows ve macOS'ta aynı şekilde çalışır |

## Ön Koşullar (her iki platform için)

- **[Ollama](https://ollama.com)** kurulu ve çalışıyor olmalı, şu modeller çekili olmalı:
  ```
  ollama pull qwen2.5vl:7b   # VLM — görsel istihbarat/doğrulama
  ollama pull llama3.2:1b    # LLM karar destek — Türkçe rapor üretimi
  ```
- Python'un kendisini elle kurmanıza gerek yok — aşağıdaki `uv sync` adımı, projenin istediği **Python 3.11**'i sizin için otomatik indirip kuruyor.
- İlk çalıştırmada **internet gerekir** — VRAG'ın görsel gömme modeli (`google/siglip2-so400m-patch14-384`) Hugging Face'ten otomatik indirilir (~3-4 GB, bir kerelik). Sonrasında sistem tamamen yerel/offline çalışır.

---

## Kurulum ve Çalıştırma — Windows

1. **Git LFS'i kurun** (büyük dosyalar — görseller, VRAG indeksi, model ağırlıkları — bununla gelir):
   ```powershell
   winget install GitHub.GitLFS
   git lfs install
   ```
2. **uv'yi kurun** (Python paket yöneticisi):
   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```
3. **Depoyu klonlayın:**
   ```powershell
   git clone https://github.com/uludagai-club/YZT-MEVZUU-26.git
   cd YZT-MEVZUU-26
   git lfs pull
   ```
4. **Ortak sanal ortamı kurun** (hem algı hattı hem LLM karar destek sistemi için TEK venv — backend ikisini de bu venv'in Python'uyla çalıştırıyor):
   ```powershell
   cd LLM
   uv sync
   uv pip install --python .venv\Scripts\python.exe ultralytics opencv-python qdrant-client requests python-multipart boxmot
   cd ..
   ```
5. **Backend'i başlatın:**
   ```powershell
   cd entegrasyon\backend
   ..\..\LLM\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
   ```
   `Hazır. N model indeksli.` yazısını görünce hazırdır.

   💡 Adım 5 yerine kök dizindeki `Sistemi_Baslat.bat`'a çift tıklayarak backend'i başlatıp tarayıcıyı otomatik açtırabilirsiniz.
6. **Arayüzü açın:** Tarayıcıda **http://127.0.0.1:8000/goruntule/** açın.
7. **Video başlatın:** Arayüzdeki kutuya videonun tam yolunu yazıp **Başlat**'a basın; ya da tarayıcıda `http://127.0.0.1:8000/docs` → `POST /oturum/baslat` → `video_yolu` alanına tam dosya yolunu yazıp Execute'a basın.

---

## Kurulum ve Çalıştırma — macOS

1. **Git LFS'i kurun:**
   ```bash
   brew install git-lfs
   git lfs install
   ```
2. **uv'yi kurun:**
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
3. **Depoyu klonlayın:**
   ```bash
   git clone https://github.com/uludagai-club/YZT-MEVZUU-26.git
   cd YZT-MEVZUU-26
   git lfs pull
   ```
4. **Ortak sanal ortamı kurun** (hem algı hattı hem LLM karar destek sistemi için TEK venv):
   ```bash
   cd LLM
   uv sync
   uv pip install --python .venv/bin/python ultralytics opencv-python qdrant-client requests python-multipart boxmot
   cd ..
   ```
5. **Backend'i başlatın:**
   ```bash
   cd entegrasyon/backend
   ../../LLM/.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000
   ```
   `Hazır. N model indeksli.` yazısını görünce hazırdır.
6. **Arayüzü açın:** Tarayıcıda **http://127.0.0.1:8000/goruntule/** açın — aynı backend'den servis edilen, canlı video akışını ve VRAG/VLM/LLM sonuçlarını sırayla gösteren web arayüzü.
7. **Video başlatın:** Arayüzdeki kutuya videonun tam yolunu yazıp **Başlat**'a basın; ya da:
   ```bash
   curl -X POST http://127.0.0.1:8000/oturum/baslat \
     -H "Content-Type: application/json" \
     -d '{"video_yolu": "/tam/yol/video.mp4"}'
   ```

---

Her iki platformda da: farklı bir video denemek için backend'i yeniden başlatmanıza gerek yok — `/oturum/baslat`'ı tekrar çağırmanız (ya da arayüzden tekrar Başlat'a basmanız) yeterli, sistem farklı çözünürlükteki videolar arasında otomatik olarak temiz bir başlangıç yapar.

## VRAG Referans Verisini Genişletme

Yeni model/görsel eklemek için:

1. `veriler/<kategori>/<model>/` altına görselleri koyun (var olan bir modelse mevcut klasöre, **dosya adları çakışmasın**; yeni bir modelse yeni klasör + diğerleri gibi bir `metadata.json` — `model`, `kategori`, `ulke`, `uretici`, `rol` alanlarıyla).
2. İndeksleyin — proje kök dizininden (`YZT-MEVZUU-26/`):

   Windows:
   ```powershell
   LLM\.venv\Scripts\python.exe -m src.vrag.ingest --img_dir veriler
   ```

   macOS:
   ```bash
   LLM/.venv/bin/python -m src.vrag.ingest --img_dir veriler
   ```

Script **güvenli şekilde senkronize eder**: `veriler/`'in tamamını her seferinde verebilirsiniz — zaten indekslenmiş görselleri atlar (tekrar eklemez), sadece gerçekten yeni olanları işler, ve `veriler/`'den kaldırılmış görselleri de indeksten otomatik siler. Yani indeks her zaman diskteki `veriler/` klasörüyle bire bir eşleşir.

⚠️ İndeksleme sırasında backend'in **kapalı olması gerekir** (ikisi aynı Qdrant veritabanı dosyasını kilitler — aynı anda açık olamazlar).

⚠️ `--img_dir` **mutlaka belirtin** (varsayılan `data/knowledge_base`'dir, `veriler/` değil) — yanlışlıkla varsayılanla çalıştırmak, script'in "diskte artık yok" sanıp `veriler/`'deki tüm mevcut kayıtları indeksten **silmesine** yol açar.

### Güven Göstergeleri

- **Düşük güven ⚠️ işareti:** VRAG'ın en iyi eşleşmesi ya `VRAG_MIN_SCORE` (0.65) altındaysa ya da onu ondan **farklı bir modelden** ayıran fark belirsizse (`VRAG_MARGIN_ESIGI`, 0.015), sonuç yine gösterilir ama bu etiketle işaretlenir — sistem "eminim" demek yerine belirsizliğini dürüstçe bildirir.
- **Zamansal oylama:** VRAG'ın bağımsız canlı araması track başına ~saniyede bir çalışır; tek bir karenin sonucu titreyebileceği için (aynı hedef için art arda farklı model önerileri), son `VRAG_VOTE_WINDOW` (5) aramanın en sık tekrar eden modeli gösterilir.
- **VLM debug kolaj kaydı** (`src/config.py: VLM_DEBUG_SAVE_IMAGES`) varsayılan olarak **kapalı** — üretimde gereksiz CPU/disk işini önler. VLM'e giden görselleri manuel incelemek isterseniz `True` yapıp `output/debug_vlm/`'e bakabilirsiniz.

## Sık Karşılaşılan Sorunlar

**"Storage folder ... already accessed by another instance" hatası:** Backend hâlâ açık, önce onu durdurun (`Ctrl+C` veya süreci `kill` edin), sonra ingest'i çalıştırın.

**VLM/LLM'den hiç cevap gelmiyor, `ProxyError` / `Unable to connect to proxy`:** Sistem genelinde bir proxy (GoodbyeDPI vb. DPI-bypass araçları dahil) `localhost`'u istisna listesine almadan aktifse, yerel Ollama çağrıları da o proxy'ye yönlendirilip başarısız olur. Proxy'yi kapatın (Ayarlar → Ağ → Proxy) ve backend'i **yeniden başlatın** (süreç açıkken proxy ayarı değişse bile eski durumu tutabiliyor).

**Farklı çözünürlüklü bir videoya geçince çöküyor:** Bu sorun çözüldü — her yeni oturumda tracker + kamera hareketi kompanzasyonu otomatik sıfırlanıyor. Hâlâ oluyorsa güncel kodda olduğunuzdan emin olun.

**Hepsi birlikte (YOLO+VRAG+VLM+LLM) çalışınca VLM/Ollama yanıt vermiyor / donanım yetmiyor gibi görünüyor:** VRAM tıkanıklığı — VRAG bilinçli olarak CPU'da çalışacak şekilde ayarlı (`src/config.py: VRAG_DEVICE = "cpu"`), bunu değiştirmeyin. VRAG ve VLM artık **ayrı kilitlere** sahip (`pipeline.py: self._vrag_gate`, `self._vlm_gate`) — VLM'in Ollama çağrısı (120 saniyeye kadar sürebilir) sırasında VRAG'ın kendi bağımsız aramaları artık bloklanmıyor; eskiden tek bir ortak kilit (`_ai_gate`) ikisini birden sıraya alıyordu ve VLM meşgulken VRAG tamamen donabiliyordu.

**Ollama modelleri VRAM'e sığmıyor:** `src/config.py`'de `VLM_MODEL_NAME`'i daha küçük bir modelle değiştirebilirsiniz (örn. `minicpm-v4.6:1b`), doğruluktan biraz ödün verip VRAM kazanırsınız.

## Lisans

Bu proje açık kaynak kodlu olarak geliştirilmiştir.
