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

## TEKNOFEST TYDA 3. Senaryo Uyumu

Bu proje, Bilişim Vadisi tarafından TEKNOFEST kapsamında düzenlenen **Türkçe Yapay Zeka Dil Ajanları Yarışması, 3. Senaryo**'ya girmektedir. Senaryonun temel beklentisi — video/görüntü girdisinden yapılandırılmış, Türkçe bir karar-destek çıktısı üreten bir ajan — sistemde şu somut karşılıklarla sağlanıyor:

- **Zaman damgalı olay günlüğü + özet + risk + aksiyon önerisi:** `karar_servisi/src/operational_decision/decision/video_summary.py` her video oturumu için gerçek zaman damgalı, deterministik bir olay listesi, genel risk seviyesi ve önerilen aksiyonları üretir (`/video/ozet`, `/api/v1/videos/{video_id}/summary`).
- **Deterministik, denetlenebilir risk değerlendirmesi:** Risk seviyesi bir LLM'in serbest yorumuna değil, `karar_servisi/data/rules/risk_rules.yaml`'daki öncelik sıralı kural tablosuna dayanır (envanter durumu, izin/uçuş planı/NOTAM kontrolleri, görsel doğrulama tutarlılığı gibi doğrulanmış gerçeklerden) — "yalnızca kural tabanlı statik çözüm" riskine karşı, kurallar VRAG/VLM'in **çok modlu, canlı** çıktısını girdi olarak kullanır ve otonom şekilde (insan müdahalesi olmadan) her hedef için uçtan uca çalışır.
- **Çoklu araç/model orkestrasyonu:** SAHI+YOLO (tespit) → ByteTrack (takip) → VRAG/SigLIP2 (retrieval ile kimlik) → VLM (bağımsız görsel doğrulama) → LLM (risk + Türkçe rapor, Platform Registry/Türkiye Envanteri/izin/uçuş planı/NOTAM araçlarıyla) — birden fazla farklı modelin/aracın birbirini doğruladığı, tek bir modele bağımlı olmayan bir zincir.
- **Kendi tanımladığımız KPI'lar, canlı ölçülüp raporlanıyor:** Arayüzdeki "Kalite KPI'ları" paneli (`frontend/src/features/system-performance/`) olay tespit doğruluğu, kritik olay yakalama oranı, özet kalitesi ve aksiyon doğruluğunu; "Hedef Kalite Skorları" ise seçili hedef için YOLO güveni, takip kararlılığı, VRAG/SigLIP benzerliği ve kimlik güvenini ayrı ayrı gösterir — güven sayıları gerçek altta yatan sinyallerden (ör. VRAG oy oranı) türetilir, tek bir "genel güven" sayısına indirgenmez.
- **Girdi esnekliği:** Sunucudaki bir video dosyasını seçmek, kendi videonuzu sürükle-bırakla yüklemek veya backend'in çalıştığı makinedeki **canlı kamerayı** doğrudan açmak — üçü de aynı algı/karar hattından geçer.

**Bilinen kısıt:** VLM/LLM çıkarımı ve metin gömme artık yerel değil, TEKNOFEST'in sağladığı EVREN altyapısı (`evren-llmapi`, `evren-vektor`) üzerinden çalışıyor — sistem sürekli internet bağlantısı gerektiriyor, tamamen offline çalışmıyor. Algı hattı (YOLO/SAHI/ByteTrack/VRAG) tamamen yerelde ve GPU'suz çalışabiliyor.

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
| `docker/` | Tek container'da (Dockerfile + docker-compose.yml) çalıştırma — kuruluma gerek kalmadan Windows/macOS/Linux'ta aynı imaj |

## Ön Koşullar (her iki platform için)

- **EVREN erişimi** (TEKNOFEST TYDA — SSB'nin sağladığı OpenAI-uyumlu çıkarım servisi, https://evren-teknofest.ssyz.org.tr). E-postayla **iki** anahtar geliyor: LLM/VLM/embedding anahtarı (`sk-evren-teamNN-...`) ve ayrı bir Qdrant anahtarı (`qdr-teamNN-...`, metin RAG'ın vektör deposu için). `.env` dosyaları bunları **otomatik okumuyor** — ikisi de gerçek kabuk ortam değişkeni olarak `export` edilmeli, aşağıdaki kurulum adımlarında detaylı.
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
5. **EVREN anahtarlarınızı girin** (e-postayla gelen iki takım anahtarı — `karar_servisi/.env`'e yazmak yetmiyor, gerçek ortam değişkeni olmalı):
   ```powershell
   $env:VLM_API_KEY = "sk-evren-teamNN-XXXXXXXX"
   $env:OPERATIONAL_DECISION_VLLM_API_KEY = "sk-evren-teamNN-XXXXXXXX"
   $env:OPERATIONAL_DECISION_QDRANT_API_KEY = "qdr-teamNN-XXXXXXXX"
   $env:OPERATIONAL_DECISION_QDRANT_COLLECTION_PREFIX = "teamNN"
   ```
6. **Backend'i başlatın:**
   ```powershell
   cd backend
   ..\karar_servisi\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
   ```
   `Hazır. N model indeksli.` yazısını görünce hazırdır.

   💡 Adım 6 yerine kök dizindeki `Sistemi_Baslat.bat`'a çift tıklayarak backend'i başlatıp tarayıcıyı otomatik açtırabilirsiniz.
7. **Arayüzü açın:** Tarayıcıda **http://127.0.0.1:8000/goruntule/** açın.
8. **Video başlatın** — üç yoldan biriyle:
   - Üstteki çubuktan **sunucudaki mevcut bir videoyu seçin** (`data/videos/`),
   - **"Video Yükle / Sürükle"** ile bilgisayarınızdan bir video dosyası sürükleyip bırakın (ya da tıklayıp seçin),
   - **"Canlı Kamera Aç"**'a tıklayarak backend'in çalıştığı makinedeki kamerayı doğrudan başlatın (dosya seçimi gerekmez).

   İlk iki yolda seçim sonrası **Başlat**'a basmanız gerekir; kamera doğrudan başlar. Alternatif olarak `http://127.0.0.1:8000/docs` üzerinden `POST /oturum/baslat` (`video_yolu`), `POST /video/yukle` (dosya) veya `POST /kamera/baslat` (`index`) uçlarını da doğrudan çağırabilirsiniz.

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
5. **EVREN anahtarlarınızı girin** (e-postayla gelen iki takım anahtarı — `karar_servisi/.env`'e yazmak yetmiyor, gerçek ortam değişkeni olmalı):
   ```bash
   export VLM_API_KEY="sk-evren-teamNN-XXXXXXXX"
   export OPERATIONAL_DECISION_VLLM_API_KEY="sk-evren-teamNN-XXXXXXXX"
   export OPERATIONAL_DECISION_QDRANT_API_KEY="qdr-teamNN-XXXXXXXX"
   export OPERATIONAL_DECISION_QDRANT_COLLECTION_PREFIX="teamNN"
   ```
6. **Backend'i başlatın:**
   ```bash
   cd backend
   ../karar_servisi/.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000
   ```
   `Hazır. N model indeksli.` yazısını görünce hazırdır.
7. **Arayüzü açın:** Tarayıcıda **http://127.0.0.1:8000/goruntule/** açın — aynı backend'den servis edilen, canlı video akışını ve VRAG/VLM/LLM sonuçlarını sırayla gösteren web arayüzü.
8. **Video başlatın** — üç yoldan biriyle:
   - Üstteki çubuktan **sunucudaki mevcut bir videoyu seçin** (`data/videos/`),
   - **"Video Yükle / Sürükle"** ile bilgisayarınızdan bir video dosyası sürükleyip bırakın (ya da tıklayıp seçin),
   - **"Canlı Kamera Aç"**'a tıklayarak backend'in çalıştığı makinedeki kamerayı doğrudan başlatın (dosya seçimi gerekmez).

   İlk iki yolda seçim sonrası **Başlat**'a basmanız gerekir; kamera doğrudan başlar. Ya da doğrudan curl ile:
   ```bash
   curl -X POST http://127.0.0.1:8000/oturum/baslat \
     -H "Content-Type: application/json" \
     -d '{"video_yolu": "/tam/yol/video.mp4"}'
   ```

---

## Kurulum ve Çalıştırma — Docker (Windows / macOS / Linux)

Kurulum adımlarının hiçbirini elle yapmadan (Python, `uv`, venv, bağımlılıklar dahil) tek imajla çalıştırma. Algı hattı GPU olmadan (CPU'da) tam olarak çalışır — Mac'te NVIDIA GPU pass-through zaten mümkün değildir, bu yüzden varsayılan kurulum her platformda aynıdır.

1. **Docker Desktop'ı kurun** ([Windows](https://docs.docker.com/desktop/install/windows-install/) — WSL2 backend'i otomatik kullanır, ayrıca bir şey kurmanıza gerek yok / [macOS](https://docs.docker.com/desktop/install/mac-install/)) ve açık olduğundan emin olun.
2. **Git LFS ile depoyu klonlayın** (Windows/macOS için yukarıdaki adım 1 ve 3'teki komutlarla aynı).
3. **EVREN anahtarlarınızı girin** — burada `export`/`$env:` değil, bir dosyaya yazılıyor (container bunu okuyor):
   ```bash
   cd docker
   cp .env.example .env
   ```
   `docker/.env` içindeki 4 değeri (`VLM_API_KEY`, `OPERATIONAL_DECISION_VLLM_API_KEY`, `OPERATIONAL_DECISION_QDRANT_API_KEY`, `OPERATIONAL_DECISION_QDRANT_COLLECTION_PREFIX`) gerçek takım anahtarlarınızla doldurun. Bu dosya `.gitignore`'da — asla commit edilmez.
4. **Build edip başlatın:**
   ```bash
   docker compose up -d --build
   ```
   İlk build birkaç dakika sürer (bağımlılıklar + SigLIP2 modeli indirilir). `docker compose logs -f app` ile ilerlemeyi izleyebilirsiniz; `Hazır. N model indeksli.` satırını görünce hazırdır.
5. **Arayüzü açın:** **http://localhost:8000/goruntule/**
6. **Durdurma:** `docker compose down` (veriler `../output`, `../models`, `../data`, `../karar_servisi/data` bind-mount olduğu için container silinse de kaybolmaz).

**NVIDIA GPU ile hızlandırma (isteğe bağlı — sadece Windows/Linux, NVIDIA sürücü + [nvidia-container-toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) kuruluysa):**
```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
```
Bu sadece YOLO/SAHI tespitini hızlandırır — VRAG bilinçli olarak her zaman CPU'da çalışır (`src/config.py: VRAG_DEVICE`), VLM/LLM zaten uzaktaki EVREN'de çalıştığı için ikisi de etkilenmez.

**VRAG referans veri setini genişletmek** için `data/` klasörü zaten bind-mount edildiğinden, aşağıdaki "VRAG Referans Verisini Genişletme" adımlarını container **içinde** çalıştırın:
```bash
docker compose exec app /app/karar_servisi/.venv/bin/python -m src.vrag.ingest --img_dir /app/data/referans
```
(İndeksleme sırasında `docker compose stop app` ile önce container'ı durdurun — aynı Qdrant dosyasını aynı anda iki süreç açamaz.)

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

MIT — bkz. [`LICENSE`](LICENSE).
