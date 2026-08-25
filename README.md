# Hava Sahası Gözetleme ve İHA Tehdit Tespit Sistemi

Video/kamera görüntüsünden hava araçlarını (uçak, İHA/SİHA, helikopter) tespit eden, tam olarak hangi model olduğunu tanıyan, bağımsız bir görsel dil modeliyle doğrulayan ve son olarak bir LLM karar destek katmanıyla risk değerlendirmesi + Türkçe rapor üreten bir sistem. Algı hattı (YOLO/SAHI/ByteTrack/VRAG) tamamen yerelde çalışır; VLM ve karar/rapor üretimi SSB'nin TEKNOFEST TYDA için sağladığı EVREN çıkarım servisi üzerinden (internet gerektirir) çalışır.

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
Model Tanıma (VRAG) + Görsel Doğrulama (VLM)       (src/vrag/, src/vlm/ — SigLIP2+Qdrant / EVREN)
     ↓
Karar Destek (LLM — risk + Türkçe rapor)           (karar_servisi/ — ayrı FastAPI servisi)
     ↓
Web Arayüzü (Windows ve macOS'ta aynı şekilde)      (backend/)
     ↓
Operatör
```

**Neden VLM değil VRAG kimlik için birincil kaynak:** VLM'i model tanıma zincirine sokmak (retrieval + VLM birlikte) doğruluğu düşürdü (top-1 %88.9 → %64.4, benchmark verisiyle). Bu yüzden model kimliği VRAG'ın retrieval sonucuna dayanır; VLM bağımsız bir ikinci göz olarak tehdit değerlendirmesi ve doğrulama yapar, kimlik kararını değiştirmez.

## Klasör Yapısı

| Klasör | İçerik |
|---|---|
| `src/` | Ana algı hattı: SAHI+YOLO tespiti, ByteTrack takibi, VRAG (model tanıma), VLM entegrasyonu |
| `data/referans/` | VRAG referans veri seti — `<kategori>/<model>/*.jpg` + `metadata.json` (ülke/üretici/rol) |
| `models/best.pt` | YOLO ağırlıkları |
| `output/qdrant_db/` | VRAG'ın indekslenmiş vektör veritabanı (Qdrant, embedded/local mod) |
| `karar_servisi/` | Karar destek sistemi — ayrı bir FastAPI servisi (Platform Registry, Türkiye Envanteri, izin/uçuş planı/NOTAM kontrolleri, LLM ile Türkçe rapor) |
| `backend/` | Algı hattını (src/) ve karar destek sistemini (karar_servisi/) kullanıcı arayüzüne bağlayan FastAPI backend — `src/core/pipeline.py`'yi çalıştırır, video akışı + hedef verisi sunar |
| `backend/web/` | Tek, platform bağımsız arayüz — tarayıcıdan açılır, Windows ve macOS'ta aynı şekilde çalışır |

## Ön Koşullar (her iki platform için)

- **EVREN erişimi** (TEKNOFEST TYDA — SSB'nin sağladığı OpenAI-uyumlu çıkarım servisi, https://evren-teknofest.ssyz.org.tr). Takım anahtarı e-postayla geliyor; `.env`'e (`karar_servisi/.env`) ve ortam değişkeni olarak (`VLM_API_KEY`) girilmesi gerekiyor — aşağıdaki kurulum adımlarında detaylı.
- İnternet bağlantısı gerekiyor — VLM ve karar/rapor üretimi artık yerel bir modelle değil, EVREN üzerinden çalışıyor.
- Python'un kendisini elle kurmanıza gerek yok — aşağıdaki `uv sync` adımı, projenin istediği **Python 3.11**'i sizin için otomatik indirip kuruyor.
- İlk çalıştırmada VRAG'ın görsel gömme modeli (`google/siglip2-so400m-patch14-384`) Hugging Face'ten otomatik indirilir (~3-4 GB, bir kerelik) — bunun için internet gerekir. Bunun ötesinde, VLM ve karar/rapor üretimi her çağrıda EVREN'e gittiği için sistem **sürekli internet bağlantısına ihtiyaç duyar**, artık offline çalışmaz.

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
   cd karar_servisi
   uv sync
   uv pip install --python .venv\Scripts\python.exe ultralytics opencv-python qdrant-client requests python-multipart boxmot
   cd ..
   ```
5. **EVREN anahtarınızı girin** (e-postayla gelen takım anahtarı):
   ```powershell
   # karar_servisi/.env içine:
   #   OPERATIONAL_DECISION_VLLM_API_KEY=sk-evren-teamNN-XXXXXXXX
   $env:VLM_API_KEY = "sk-evren-teamNN-XXXXXXXX"
   ```
6. **Backend'i başlatın:**
   ```powershell
   cd backend
   ..\karar_servisi\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
   ```
   `Hazır. N model indeksli.` yazısını görünce hazırdır.

   💡 Adım 6 yerine kök dizindeki `Sistemi_Baslat.bat`'a çift tıklayarak backend'i başlatıp tarayıcıyı otomatik açtırabilirsiniz.
7. **Arayüzü açın:** Tarayıcıda **http://127.0.0.1:8000/goruntule/** açın.
8. **Video başlatın:** Arayüzdeki kutuya videonun tam yolunu yazıp **Başlat**'a basın; ya da tarayıcıda `http://127.0.0.1:8000/docs` → `POST /oturum/baslat` → `video_yolu` alanına tam dosya yolunu yazıp Execute'a basın.

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
   cd karar_servisi
   uv sync
   uv pip install --python .venv/bin/python ultralytics opencv-python qdrant-client requests python-multipart boxmot
   cd ..
   ```
5. **EVREN anahtarınızı girin** (e-postayla gelen takım anahtarı):
   ```bash
   # karar_servisi/.env içine:
   #   OPERATIONAL_DECISION_VLLM_API_KEY=sk-evren-teamNN-XXXXXXXX
   export VLM_API_KEY="sk-evren-teamNN-XXXXXXXX"
   ```
6. **Backend'i başlatın:**
   ```bash
   cd backend
   ../karar_servisi/.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000
   ```
   `Hazır. N model indeksli.` yazısını görünce hazırdır.
7. **Arayüzü açın:** Tarayıcıda **http://127.0.0.1:8000/goruntule/** açın — aynı backend'den servis edilen, canlı video akışını ve VRAG/VLM/LLM sonuçlarını sırayla gösteren web arayüzü.
8. **Video başlatın:** Arayüzdeki kutuya videonun tam yolunu yazıp **Başlat**'a basın; ya da:
   ```bash
   curl -X POST http://127.0.0.1:8000/oturum/baslat \
     -H "Content-Type: application/json" \
     -d '{"video_yolu": "/tam/yol/video.mp4"}'
   ```

---

Her iki platformda da: farklı bir video denemek için backend'i yeniden başlatmanıza gerek yok — `/oturum/baslat`'ı tekrar çağırmanız (ya da arayüzden tekrar Başlat'a basmanız) yeterli, sistem farklı çözünürlükteki videolar arasında otomatik olarak temiz bir başlangıç yapar.

## VRAG Referans Verisini Genişletme

Yeni model/görsel eklemek için:

1. `data/referans/<kategori>/<model>/` altına görselleri koyun (var olan bir modelse mevcut klasöre, **dosya adları çakışmasın**; yeni bir modelse yeni klasör + diğerleri gibi bir `metadata.json` — `model`, `kategori`, `ulke`, `uretici`, `rol` alanlarıyla).
2. İndeksleyin — proje kök dizininden (`YZT-MEVZUU-26/`):

   Windows:
   ```powershell
   karar_servisi\.venv\Scripts\python.exe -m src.vrag.ingest --img_dir data\referans
   ```

   macOS:
   ```bash
   karar_servisi/.venv/bin/python -m src.vrag.ingest --img_dir data/referans
   ```

Script **güvenli şekilde senkronize eder**: `data/referans/`'ın tamamını her seferinde verebilirsiniz — zaten indekslenmiş görselleri atlar (tekrar eklemez), sadece gerçekten yeni olanları işler, ve `data/referans/`'dan kaldırılmış görselleri de indeksten otomatik siler. Yani indeks her zaman diskteki `data/referans/` klasörüyle bire bir eşleşir.

⚠️ İndeksleme sırasında backend'in **kapalı olması gerekir** (ikisi aynı Qdrant veritabanı dosyasını kilitler — aynı anda açık olamazlar).

⚠️ `--img_dir` **mutlaka belirtin** (varsayılan `data/knowledge_base`'dir, `data/referans/` değil) — yanlışlıkla varsayılanla çalıştırmak, script'in "diskte artık yok" sanıp `data/referans/`'daki tüm mevcut kayıtları indeksten **silmesine** yol açar.

### Güven Göstergeleri

- **Düşük güven ⚠️ işareti:** VRAG'ın en iyi eşleşmesi ya `VRAG_MIN_SCORE` (0.65) altındaysa ya da onu ondan **farklı bir modelden** ayıran fark belirsizse (`VRAG_MARGIN_ESIGI`, 0.015), sonuç yine gösterilir ama bu etiketle işaretlenir — sistem "eminim" demek yerine belirsizliğini dürüstçe bildirir.
- **Zamansal oylama:** VRAG'ın bağımsız canlı araması track başına ~saniyede bir çalışır; tek bir karenin sonucu titreyebileceği için (aynı hedef için art arda farklı model önerileri), son `VRAG_VOTE_WINDOW` (5) aramanın en sık tekrar eden modeli gösterilir.
- **VLM debug kolaj kaydı** (`src/config.py: VLM_DEBUG_SAVE_IMAGES`) varsayılan olarak **kapalı** — üretimde gereksiz CPU/disk işini önler. VLM'e giden görselleri manuel incelemek isterseniz `True` yapıp `output/debug_vlm/`'e bakabilirsiniz.

## Sık Karşılaşılan Sorunlar

**"Storage folder ... already accessed by another instance" hatası:** Backend hâlâ açık, önce onu durdurun (`Ctrl+C` veya süreci `kill` edin), sonra ingest'i çalıştırın.

**VLM/LLM'den hiç cevap gelmiyor, `ProxyError` / `Unable to connect to proxy` / bağlantı hatası:** VLM ve karar/rapor üretimi artık uzaktaki EVREN servisine gidiyor — internet bağlantınızı ve `VLM_API_KEY` / `OPERATIONAL_DECISION_VLLM_API_KEY` ortam değişkenlerinin doğru girildiğini kontrol edin. Bir proxy (GoodbyeDPI vb. DPI-bypass araçları dahil) aktifse EVREN'in host'unu (`evren-llmapi.ssyz.org.tr`) engelliyor olabilir.

**Farklı çözünürlüklü bir videoya geçince çöküyor:** Bu sorun çözüldü — her yeni oturumda tracker + kamera hareketi kompanzasyonu otomatik sıfırlanıyor. Hâlâ oluyorsa güncel kodda olduğunuzdan emin olun.

**Hepsi birlikte (YOLO+VRAG+VLM+LLM) çalışınca donanım yetmiyor gibi görünüyor:** VRAG bilinçli olarak CPU'da çalışacak şekilde ayarlı (`src/config.py: VRAG_DEVICE = "cpu"`), bunu değiştirmeyin. VLM/LLM artık uzakta (EVREN) çalıştığı için yerel GPU/VRAM'i hiç kullanmıyor — bu tıkanıklık artık sadece YOLO+VRAG'ın kendi aralarında paylaştığı yerel kaynaklarla ilgili olabilir.

## Lisans

Bu proje açık kaynak kodlu olarak geliştirilmiştir.
