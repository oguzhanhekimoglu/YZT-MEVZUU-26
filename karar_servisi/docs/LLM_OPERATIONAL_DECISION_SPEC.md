# LLM ve Operasyonel Karar Alt Sistemi

> **Güncel runtime otoritesi (kapanış sürümü):** Registry 98 toplam / 97 aktif gerçek platformdan oluşur; allowlist 97 ve DEMO Inventory 22 kayıttır. Demo kataloğu SCN-01–SCN-23 kapsamındadır. `DEMO`, `DEMO_MOCK` seedleri ve `raw_vlm_context_routes` kullanabilir; `PRODUCTION` ayrı veritabanları ve gerçek upstream video/track/context ister, demo seedlerini yüklemez. Askerî + başarılı Inventory `NOT_LISTED` dalında operational araçlar `UNREGISTERED_MILITARY_POLICY` nedeniyle atlanır. LLM yalnız açıklama, özet ve öneri üretir; deterministic verification, risk, decision, human-review ve policy/reason kodlarını değiştiremez. Aşağıdaki eski tasarım örnekleriyle çelişen yerlerde bu bölüm ve çalışan contract/policy kodu geçerlidir.

## Coding Agent İçin Nihai Uygulama Spesifikasyonu

**Belge sürümü:** 2.1  
**Durum:** Uygulamaya hazır / source of truth  
**Hedef ortam:** Windows 10/11, NVIDIA GPU 8 GB VRAM, tamamen yerel çalışma  
**Dil:** Python 3.11.x  
**Ana karar modeli:** `Qwen3-4B-Instruct-2507` — Ollama `Q4_K_M`  
**Text embedding modeli:** `Qwen3-Embedding-0.6B`  
**Görsel katman:** Bu dokümanın kapsamı dışındadır; yalnızca JSON çıktısı tüketilir.

---

# 0. Coding agent için bağlayıcı talimat

Bu dosya projenin **ana teknik kaynağıdır**. Kodlama sırasında aşağıdaki kurallar bağlayıcıdır:

1. Bu dokümanda tanımlanan mimariyi değiştirme.
2. Dokümanda seçimi kesinleştirilmiş model, servis, veri tabanı veya kütüphane yerine kendiliğinden alternatif seçme.
3. Görsel pipeline, YOLO, tracking, crop selection, VLM veya Visual RAG kodu yazma.
4. Dış API, bulut LLM veya internet tabanlı runtime servisi ekleme.
5. Tüm çalışma zamanı bileşenleri yerel olmalıdır.
6. LLM’e serbest tool çağırma yetkisi verme.
7. Risk kararını yalnızca LLM’e bırakma.
8. `execution_status` ile operasyonel/domain durumunu birbirine karıştırma.
9. Uçuş planını uçuş izni olarak yorumlama.
10. Görsel benzerliği kesin platform kimliği olarak ifade etme.
11. `TODO`, `pass`, `NotImplementedError`, sahte başarı cevabı veya sessiz fallback bırakma.
12. Her modülde type hint, docstring, Pydantic doğrulaması ve test bulunmalıdır.
13. İş mantığını FastAPI route dosyalarına yazma.
14. Önce contracts ve testleri, sonra implementasyonu oluştur.
15. Her faz sonunda testleri çalıştır ve başarısız test bırakma.
16. Çelişki varsa bu dokümanın daha özel ve daha aşağıdaki hükmü önceliklidir.
17. Dokümanda açıkça tanımlanmayan kritik davranış için varsayım yapma; `docs/OPEN_DECISIONS.md` içine kayıt oluştur.
18. Mock kayıtları gerçek kayıt gibi sunma. Tüm sentetik kayıtları `DEMO_MOCK` olarak işaretle.
19. Mevzuat dokümanları runtime sırasında internetten indirilmemelidir.
20. Model ağırlıkları Git deposuna eklenmemelidir.

---

# 1. Projenin amacı

Bu alt sistem, upstream görsel analiz katmanından gelen yapılandırılmış hava aracı hipotezini yerel operasyonel kayıtlarla karşılaştırarak:

- operasyon bağlamını çözer,
- platform kayıtlarını sorgular,
- uçuş izni ve uçuş planı kayıtlarını sorgular,
- ilgili NOTAM kayıtlarını sorgular,
- kayıtların tutarlılığını belirler,
- deterministik minimum risk üretir,
- gerektiğinde mevzuat Text RAG çalıştırır,
- hazırlanmış kanıt paketini yerel LLM’e gönderir,
- Türkçe karar destek raporu üretir,
- LLM çıktısını güvenlik ve tutarlılık kurallarıyla denetler,
- nihai JSON çıktısını üretir,
- tüm karar zincirini event-scoped SQLite memory içinde saklar.

Sistem bir **otonom silah sistemi değildir**. Çıktılar karar destek amacı taşır. `HIGH`, `CRITICAL`, `UNKNOWN`, `INDETERMINATE` veya zorunlu insan incelemesi bulunan olaylarda nihai operasyonel yetki insandadır.

---

# 2. Kapsam sınırı ve ekipler arası sorumluluk

## 2.1 Upstream görsel ekip tarafından üretilecek bölüm

```text
Video
  ↓
Detection / YOLO
  ↓
Tracking
  ↓
Crop Extraction
  ↓
Crop Quality ve Selection
  ↓
Visual Retrieval / Visual RAG
  ↓
VLM Candidate Verification
  ↓
Visual Evidence Fusion
  ↓
Visual Uncertainty
  ↓
Final Visual Evidence JSON
```

Bu doküman yukarıdaki işlemleri **uygulamaz**.

## 2.2 Bu alt sistemin başlangıç noktası

```text
Final Visual Evidence JSON
  ↓
Visual Input Adapter
  ↓
Pydantic Validation
  ↓
Operational Context Resolver
  ↓
Event Memory
  ↓
Controlled Decision Orchestrator
  ↓
Operational Tools
  ↓
Verification
  ↓
Risk Advisor
  ↓
Conditional Text RAG
  ↓
Evidence Builder
  ↓
Local LLM Decision Agent
  ↓
Output Guard
  ↓
Final JSON + Türkçe Rapor
```

## 2.3 Kesinlikle uygulanmayacak bileşenler

- YOLO
- SAHI / SmartSlicer
- ByteTrack / DeepSORT
- Kalman Filter
- Crop extraction
- Crop quality scoring
- Crop selection
- DINOv2 / SigLIP visual embedding
- Visual FAISS / Qdrant retrieval
- Visual RAG aggregation
- VLM vision inference
- Visual evidence fusion algoritması
- Visual uncertainty algoritması
- Geofence Tool
- Gerçek EAD/Eurocontrol runtime entegrasyonu
- Bulut LLM
- Bulut embedding servisi

---

# 3. Kilitlenmiş teknoloji kararları

| Alan | Nihai seçim | Not |
|---|---|---|
| İşletim sistemi | Windows 10/11 x86-64 | Native çalışma |
| GPU | NVIDIA, 8 GB VRAM | VLM ve LLM aynı anda çalışmayacak |
| Python | 3.11.x | Sanal ortam zorunlu |
| API | FastAPI | Yalnızca adapter katmanı |
| Veri doğrulama | Pydantic v2 | Bütün modüller arası sözleşmeler |
| Ayarlar | `pydantic-settings` + YAML | Hardcode yasak |
| LLM sunumu | Ollama native Windows | vLLM kullanılmayacak |
| Decision LLM | `Qwen3-4B-Instruct-2507` | Non-thinking |
| Ollama etiketi | `qwen3:4b-instruct-2507-q4_K_M` | Q4_K_M |
| LLM structured output | Ollama JSON Schema | Pydantic JSON Schema |
| Text embedding | `Qwen/Qwen3-Embedding-0.6B` | CPU |
| Embedding framework | Sentence Transformers | Local model cache |
| Embedding dimension | 1024 | Normalize edilmiş |
| Vector index | FAISS CPU `IndexFlatIP` | Exact inner product |
| Benzerlik | Normalize embeddings + inner product | Cosine eşdeğeri |
| PDF extraction | `pypdf` | OCR yok |
| DOCX extraction | `python-docx` | Sadece gerektiğinde |
| Runtime DB | SQLite + `aiosqlite` | İki ayrı DB |
| Tool orchestration | Python async orchestrator | LLM tool çağırmaz |
| Risk | YAML tabanlı deterministik kurallar | LLM riski seçmez |
| Test | Pytest | Unit + integration + scenario |
| Runtime internet | Yasak | İlk kurulum hariç offline |
| Reranker | V1’de yok | Benchmark sonrası değerlendirilebilir |
| BM25/hybrid | V1’de yok | Benchmark sonrası değerlendirilebilir |
| OCR | Yok | Metni çıkarılamayan belge hata verir |

---

# 4. Model ve lisans kararları

## 4.1 Decision LLM

**Model:** `Qwen/Qwen3-4B-Instruct-2507`  
**Ollama:** `qwen3:4b-instruct-2507-q4_K_M`  
**Lisans:** Apache-2.0  
**Çalışma modu:** Non-thinking  
**Görev:** Hazırlanmış kanıt paketini yorumlamak, karar kodu seçmek, Türkçe rapor üretmek ve katalogdan aksiyonları önceliklendirmek.

Model:

- görsel analiz yapmaz,
- veritabanı sorgulamaz,
- tool çağırmaz,
- minimum risk belirlemez,
- mevzuat kaynağı icat etmez.

### Ollama çalışma ayarları

```yaml
llm:
  backend: ollama
  model: qwen3:4b-instruct-2507-q4_K_M
  base_url: http://127.0.0.1:11434
  endpoint: /api/chat

  stream: false
  think: false
  structured_output: true

  num_ctx: 8192
  num_predict: 1200
  temperature: 0.1
  top_p: 0.8
  seed: 42

  request_timeout_seconds: 60
  repair_attempts: 1
  keep_alive_during_batch: 2m
  unload_after_batch: true
```


um_ctx` değeri 8192 olarak sınırlandırılacaktır. Modelin daha uzun bağlam desteklemesi bu projede daha uzun bağlam kullanılacağı anlamına gelmez.

## 4.2 Text embedding modeli

**Model:** `Qwen/Qwen3-Embedding-0.6B`  
**Lisans:** Apache-2.0  
**Cihaz:** CPU  
**Boyut:** 1024  
**Normalization:** Açık  
**Runtime:** Sentence Transformers

```yaml
embedding:
  provider: sentence_transformers
  model_id: Qwen/Qwen3-Embedding-0.6B
  local_model_path: data/models/qwen3-embedding-0.6b
  device: cpu
  dimension: 1024
  normalize_embeddings: true
  max_sequence_length: 2048
  batch_size: 8
  trust_remote_code: false
```

Embedding modeli runtime sırasında Hugging Face’e bağlanmamalıdır. İlk kurulumda indirilip yerel dizine kaydedilecektir.

## 4.3 Üçüncü taraf lisans kaydı

Repo içinde aşağıdaki dosyalar zorunludur:

```text
licenses/
├── MODEL_LICENSES.md
├── THIRD_PARTY_LICENSES.md
├── qwen3-4b-instruct-2507-apache-2.0.txt
└── qwen3-embedding-0.6b-apache-2.0.txt
```

`MODEL_LICENSES.md` en az şu alanları içermelidir:

```text
model_id
local_runtime_name
model_version
license
official_source
used_by
download_date
checksum_or_revision
```

---

# 5. Windows ve GPU çalışma düzeni

## 5.1 Sequential GPU policy

VLM ve Decision LLM aynı anda GPU’da tutulmayacaktır.

```text
Upstream VLM tamamlanır
  ↓
Upstream GPU kaynaklarını serbest bırakır
  ↓
Final Visual Evidence JSON hazır sinyali oluşur
  ↓
Decision batch başlar
  ↓
Qwen3-4B Ollama üzerinden yüklenir
  ↓
Aynı videoya ait olaylar sırayla işlenir
  ↓
Decision batch biter
  ↓
Ollama modeli keep_alive=0 ile boşaltılır
  ↓
Bir sonraki görsel batch başlayabilir
```

## 5.2 Sorumluluk sınırı

Bu alt sistem upstream VLM sürecini zorla kapatmaz. Upstream entegrasyon sözleşmesi:

```json
{
  "visual_pipeline_status": "COMPLETED",
  "gpu_release_status": "RELEASED",
  "result_count": 1
}
```

`gpu_release_status != RELEASED` ise Decision LLM başlatılmaz ve:

```text
event_status = WAITING_FOR_GPU_HANDOFF
```

kullanılır.

Demo entegrasyonu henüz hazır değilse `gpu_release_status` request içinde geçici olarak `RELEASED` gönderilebilir.

## 5.3 Ollama unload

Batch sonunda Ollama `/api/chat` veya `/api/generate` çağrısında:

```json
{
  "model": "qwen3:4b-instruct-2507-q4_K_M",
  "keep_alive": 0
}
```

kullanılmalı veya eşdeğer unload çağrısı yapılmalıdır.

---

# 6. Uçtan uca mimari

```text
Canonical JSON veya Raw VLM Adapter
↓
Schema Validation
↓
Event Memory / Idempotency
↓
Operational Context Resolver
↓
Platform Registry
↓
Turkey Inventory
↓
Operational Eligibility
├── Platform unresolved / context incomplete
│   └── Permission, Flight Plan, NOTAM: SKIPPED
└── Eligible
    ├── Permission + Flight Plan
    └── NOTAM
↓
Operational Consistency
↓
Verification
↓
Risk
↓
Conditional RAG
↓
Decision
↓
Output Guard
↓
Finalizer
↓
Final JSON + Türkçe Rapor
```

Operational eligibility; platformun çözülmüş olması, context'in `COMPLETE` olması ve gerekli zaman/bölge bilgilerinin bulunmasıyla belirlenir. Inventory sonucu eligibility girdisi değildir.

---

# 7. Uçtan uca işlem sırası

1. API request alınır.
2. `request_id` ve `event_id` oluşturulur.
3. Minimal request envelope doğrulanır.
4. Audit amaçlı event kaydı açılır.
5. Ham visual payload `VisualInputAdapter` tarafından canonical modele dönüştürülür.
6. Canonical payload Pydantic ile doğrulanır.
7. Geçersiz payload durumunda event `REJECTED_INVALID_INPUT` yapılır ve güvenli çıktı döndürülür.
8. `video_id` ile Operational Context Resolver çalışır.
9. `observation_time_utc` hesaplanır.
10. Event fingerprint hesaplanır; daha önce sonuçlandırılmış aynı event varsa idempotent sonuç döndürülür.
11. Context validation gate çalışır.
12. Strong non-aircraft erken çıkışı değerlendirilir.
13. Platform Registry exact alias/candidate üzerinden platformu çözer.
14. Çözülen `platform_id` ile Türkiye Inventory lookup yapılır; sonuç bağımsız evidence olarak saklanır.
15. Operational eligibility platform resolution, complete context ve gerekli zaman/bölge bilgileri üzerinden hesaplanır.
16. Eligible durumda Permission & Flight Plan Tool ile NOTAM Tool Inventory sonucundan bağımsız çalışır.
17. Platform unresolved, strong non-aircraft, incomplete context veya gerekli zaman/bölge bilgisi eksikse ilgili downstream araçlar `SKIPPED` ve `data=null` olur.
18. Tool envelope’ları Pydantic ile doğrulanır.
19. Operational Consistency Checker çalışır.
20. Operational Verification Checker çalışır.
21. Risk Advisor deterministik minimum riski üretir.
22. Text RAG çağrı politikası değerlendirilir ve gerekliyse RAG çalışır.
23. Evidence Package Builder LLM için kompakt paket üretir.
24. Decision LLM JSON Schema ile cevap üretir.
25. Parse başarısızsa yalnızca bir repair denemesi yapılır.
26. Output Guard çelişkileri, kaynakları ve aksiyon kodlarını denetler.
27. Finalizer Decision Policy ile Risk Advisor sonuçlarını korur.
28. Nihai JSON ve Türkçe rapor üretilir.
29. Tüm event trace SQLite’a kaydedilir ve event `FINALIZED` yapılır.
30. Batch bitmişse Ollama modeli GPU’dan boşaltılır.

---

# 8. API request sözleşmesi

## 8.1 AnalyzeEventRequest

```json
{
  "video_id": "VIDEO_001",
  "explanation_requested": false,
  "gpu_handoff": {
    "visual_pipeline_status": "COMPLETED",
    "gpu_release_status": "RELEASED"
  },
  "visual_evidence": {}
}
```

### Alan kuralları

| Alan | Zorunlu | Açıklama |
|---|---:|---|
| `video_id` | Evet | Context Resolver anahtarı |
| `explanation_requested` | Hayır | Ayrıntılı mevzuat açıklaması isteniyorsa `true` |
| `gpu_handoff` | Evet | Sequential çalışma güvenliği |
| `visual_evidence` | Evet | Upstream payload |
| `request_metadata` | Hayır | Audit amaçlı |

---

# 9. Upstream VLM çıktısı ve canonical entegrasyon sözleşmesi

Arkadaşların tarafından üretilen VLM JSON'u doğrudan operasyonel tool'lara, Risk Advisor'a
veya Decision LLM'e gönderilmez. Ham VLM sonucu önce ayrı bir `UpstreamVLMOutput`
sözleşmesiyle doğrulanır, ardından `UpstreamVLMAdapter` tarafından canonical
`FinalVisualEvidencePackage` yapısına dönüştürülür.

Bu ayrım zorunludur:

```text
Arkadaşların VLM JSON'u
  ↓
UpstreamVLMOutput validation
  ↓
UpstreamVLMAdapter
  ↓
FinalVisualEvidencePackage
  ↓
Operational decision subsystem
```

## 9.1 Arkadaşların mevcut ham VLM JSON şeması

Bu şema **ham model tahmini** olarak korunabilir:

```json
{
  "arac_sinifi": "SAVAS_UCAGI",
  "tehdit_seviyesi": "YUKSEK",
  "tahmini_hedef_tipi": "MUHARIP_JET",
  "ulke_orjini": "ABD",
  "hedef_modeli": "F-16",
  "gidis_yeri": null,
  "gorsel_analiz": "Görüntüde tek motorlu, kanat altı yük istasyonları bulunan savaş uçağı benzeri bir platform görülmektedir.",
  "guven_skoru": 85
}
```

## 9.2 Ham VLM alanlarının güvenlik anlamı

| Ham alan | Kullanım | Operasyonel karara etkisi |
|---|---|---|
| `arac_sinifi` | Canonical `visual_class` için adapter girdisi | Yalnızca sınıf eşleme |
| `hedef_modeli` | `final_visual_hypothesis` için aday metin | Kesin kimlik değildir |
| `guven_skoru` | `vlm_confidence = guven_skoru / 100` | Kalibre edilmiş doğruluk değildir |
| `tahmini_hedef_tipi` | Audit ve açıklayıcı subtype | Tool sorgusunun anahtarı değildir |
| `gorsel_analiz` | Audit ve LLM'e kompakt görsel özet | Tool sonucunun yerini tutmaz |
| `ulke_orjini` | Yalnızca advisory/audit | Platform DB doğrulaması olmadan gerçek kabul edilmez |
| `tehdit_seviyesi` | Yalnızca ham VLM görüşü | **Risk Advisor tarafından tamamen yok sayılır** |
| `gidis_yeri` | Deprecated advisory alan | Operasyonel kararda kullanılmaz |

### Kritik kurallar

1. `tehdit_seviyesi` nihai `risk_level` değildir.
2. Nihai risk yalnızca deterministik `RiskAdvisor` tarafından üretilir.
3. `gidis_yeri`, tek görüntüden güvenilir biçimde çıkarılamaz.
4. Gerçek rota bilgisi gerekiyorsa tracking ekibi ayrı bir
   `estimated_motion_direction` veya `trajectory_hypothesis` alanı üretmelidir.
5. `ulke_orjini`, platform üreticisi veya görsel stil üzerinden yapılan tahmin olabilir;
   izin/NOTAM doğrulamasında doğrudan kullanılmaz.
6. `hedef_modeli` her zaman `-like` / “benzeri” hipotez diline dönüştürülür.
7. Ham VLM çıktısı event audit kaydında saklanabilir ancak final raporda gerçek kayıt gibi
   sunulamaz.

## 9.3 UpstreamVLMOutput Pydantic sözleşmesi

**Dosya:** `src/operational_decision/contracts/upstream_vlm.py`

```python
class UpstreamVLMOutput(BaseModel):
    schema_version: Literal["upstream-vlm/1.0"] = "upstream-vlm/1.0"

    arac_sinifi: str = Field(min_length=1, max_length=100)
    tehdit_seviyesi: str | None = Field(default=None, max_length=50)
    tahmini_hedef_tipi: str | None = Field(default=None, max_length=100)
    ulke_orjini: str | None = Field(default=None, max_length=100)
    hedef_modeli: str | None = Field(default=None, max_length=150)
    gidis_yeri: str | None = Field(default=None, max_length=250)
    gorsel_analiz: str = Field(min_length=1, max_length=4000)
    guven_skoru: int = Field(ge=0, le=100)
```

JSON Schema ayrıca şu dosyaya export edilmelidir:

```text
data/schemas/upstream_vlm_output.schema.json
```

## 9.4 Ham VLM çıktısı tek başına neden yeterli değildir?

Mevcut ham JSON aşağıdaki zorunlu entegrasyon alanlarını içermemektedir:

- `track_id`
- `first_seen_offset_seconds`
- `last_seen_offset_seconds`
- `visual_evidence_status`
- `uncertainty_level`
- `human_visual_review_required`
- visual pipeline sürümü
- evidence source mode
- candidate listesi
- GPU handoff durumu

Bu nedenle arkadaşların VLM çıktısı final entegrasyonda bir **wrapper** içinde
gönderilmelidir.

## 9.5 Entegrasyonda kullanılacak nihai upstream wrapper

Arkadaşlarınızla birleştirme sırasında API'ye gönderilecek `visual_evidence` alanı aşağıdaki
biçimde olmalıdır:

```json
{
  "schema_version": "visual-evidence/1.1",
  "evidence_source_mode": "VLM_ONLY",
  "track_id": "TRK_001",

  "visual_class": "FIGHTER_JET",
  "final_visual_hypothesis": "F-16-like",
  "candidate_matches": [],

  "visual_evidence_status": "PARTIALLY_SUPPORTED",
  "visual_confidence": 0.85,
  "confidence_origin": "VLM_SELF_REPORTED",

  "uncertainty_level": "MEDIUM",
  "uncertainty_flags": [
    "VLM_ONLY_NO_RETRIEVAL_CONFIRMATION"
  ],
  "human_visual_review_required": true,

  "track_metrics": {
    "track_duration_seconds": 7.4,
    "track_stability": 0.84,
    "detection_count": 26,
    "average_detection_confidence": 0.76
  },

  "crop_evidence_summary": {
    "selected_crop_count": 3,
    "selected_crop_refs": [
      "TRK_001_CROP_01",
      "TRK_001_CROP_02",
      "TRK_001_CROP_03"
    ],
    "crop_quality_scores": [0.81, 0.76, 0.73],
    "average_crop_quality": 0.767,
    "view_diversity_score": 0.68
  },

  "timing": {
    "first_seen_offset_seconds": 8.2,
    "last_seen_offset_seconds": 15.6
  },

  "upstream_vlm_output": {
    "schema_version": "upstream-vlm/1.0",
    "arac_sinifi": "SAVAS_UCAGI",
    "tehdit_seviyesi": "YUKSEK",
    "tahmini_hedef_tipi": "MUHARIP_JET",
    "ulke_orjini": "ABD",
    "hedef_modeli": "F-16",
    "gidis_yeri": null,
    "gorsel_analiz": "Görüntüde F-16 benzeri bir muharip jet görülmektedir.",
    "guven_skoru": 85
  },

  "producer_metadata": {
    "visual_pipeline_version": "temporary-contract/1.1",
    "vlm_model": "UPSTREAM_PROVIDED",
    "retrieval_model": null,
    "created_at_utc": "2026-08-10T11:20:08Z"
  }
}
```

## 9.6 EvidenceSourceMode

```text
VLM_ONLY
VLM_PLUS_RETRIEVAL
FUSED
```

### VLM_ONLY güvenlik politikası

`evidence_source_mode = VLM_ONLY` ise:

- `visual_evidence_status` en fazla `PARTIALLY_SUPPORTED` olabilir.
- `uncertainty_level = LOW` kabul edilmez; en az `MEDIUM` olmalıdır.
- `human_visual_review_required = true` zorunludur.
- `candidate_matches` boş olabilir.
- `visual_confidence`, `guven_skoru / 100` olarak eşlenebilir.
- `confidence_origin = VLM_SELF_REPORTED` olmak zorundadır.
- Ham `tehdit_seviyesi` Risk Advisor'a aktarılmaz.

### VLM_PLUS_RETRIEVAL politikası

- Retrieval sonucu ayrıca upstream tarafından sağlanmalıdır.
- `candidate_matches` boş olamaz.
- `visual_evidence_status` upstream fusion/verification kuralıyla üretilmelidir.
- `confidence_origin = UPSTREAM_FUSION` kullanılmalıdır.
- LOW uncertainty ancak VLM/retrieval uyumu ve upstream güvenlik kuralı ile gönderilebilir.

### FUSED politikası

- Arkadaşların nihai Visual RAG + VLM + fusion çıktısıdır.
- Canonical alanların tamamı upstream tarafından üretilir.
- Adapter yalnızca isim/enum normalizasyonu yapar.
- Risk sistemi yine ham `tehdit_seviyesi` alanını kullanmaz.

## 9.7 Alan eşleme tablosu

| Ham VLM alanı | Canonical alan | Eşleme |
|---|---|---|
| `arac_sinifi` | `visual_class` | `config/visual_adapter.yaml` enum mapping |
| `hedef_modeli` | `final_visual_hypothesis` | Normalize + `-like` |
| `guven_skoru` | `visual_confidence` | `/ 100`, yalnızca `VLM_ONLY` compatibility |
| `guven_skoru` | `confidence_origin` | `VLM_SELF_REPORTED` |
| `gorsel_analiz` | `upstream_analysis_text` | Metin temizleme ve max-length |
| `tahmini_hedef_tipi` | `visual_subtype` | Opsiyonel audit |
| `ulke_orjini` | `origin_hypothesis` | Opsiyonel advisory |
| `tehdit_seviyesi` | `upstream_threat_advisory` | Audit only; Risk Advisor'a gönderilmez |
| `gidis_yeri` | `deprecated_destination_hypothesis` | Audit only; decision dışı |

## 9.8 Adapter fonksiyonları

**Dosya:** `src/operational_decision/input/upstream_vlm_adapter.py`

```python
def validate_upstream_vlm_payload(
    raw_payload: dict[str, object],
) -> UpstreamVLMOutput:
    ...
```

```python
def map_upstream_vlm_to_canonical(
    *,
    raw_vlm: UpstreamVLMOutput,
    track_context: UpstreamTrackContext,
    producer_metadata: ProducerMetadata,
) -> FinalVisualEvidencePackage:
    ...
```

```python
def normalize_vlm_model_hypothesis(value: str | None) -> str | None:
    ...
```

```python
def map_vlm_vehicle_class(value: str) -> VisualClass:
    ...
```

```python
def convert_percentage_confidence(value: int) -> float:
    return round(value / 100.0, 4)
```

## 9.9 TrackContext sözleşmesi

Ham VLM JSON'da bulunmayan alanlar tracking/orchestrator tarafından sağlanır:

```json
{
  "track_id": "TRK_001",
  "first_seen_offset_seconds": 8.2,
  "last_seen_offset_seconds": 15.6,
  "track_duration_seconds": 7.4,
  "track_stability": 0.84,
  "detection_count": 26,
  "average_detection_confidence": 0.76
}
```

Bu alanlar VLM tarafından tahmin edilmez.

## 9.10 FinalVisualEvidencePackage zorunlu alanları

- `schema_version`
- `evidence_source_mode`
- `track_id`
- `visual_class`
- `visual_evidence_status`
- `visual_confidence`
- `confidence_origin`
- `uncertainty_level`
- `human_visual_review_required`
- `timing.first_seen_offset_seconds`
- `timing.last_seen_offset_seconds`
- `producer_metadata`
- `upstream_vlm_output`

`final_visual_hypothesis`, yalnızca `visual_class != NON_AIRCRAFT` olduğunda zorunludur.

## 9.11 Adapter'ın uyduramayacağı alanlar

Adapter aşağıdakileri rastgele veya örtük varsayımla üretmez:

- `track_id`
- tracking zamanları
- track stability
- crop quality
- fusion confidence
- `FUSED` evidence status
- LOW uncertainty
- insan incelemesini kaldıran karar
- platform kayıt durumu
- permission durumu
- NOTAM durumu
- operasyonel risk

## 9.12 Entegrasyon testleri

Aşağıdaki fixture'lar zorunludur:

```text
tests/fixtures/upstream_vlm/valid_vlm_only.json
tests/fixtures/upstream_vlm/invalid_confidence.json
tests/fixtures/upstream_vlm/missing_analysis.json
tests/fixtures/upstream_vlm/legacy_turkish_keys.json
tests/fixtures/visual_packages/valid_wrapper_v1_1.json
```

Zorunlu testler:

1. `guven_skoru=85` → `visual_confidence=0.85`
2. `tehdit_seviyesi=YUKSEK` → Risk Advisor girdisine taşınmaz
3. `gidis_yeri` → final kararda kullanılmaz
4. `hedef_modeli=F-16` → `F-16-like`
5. `VLM_ONLY + LOW uncertainty` → validation hatası
6. `VLM_ONLY + human_review=false` → validation hatası
7. `guven_skoru=101` → validation hatası
8. Eksik `track_id` → wrapper validation hatası
9. Fused paket raw VLM audit alanını korur
10. Arkadaşların legacy JSON'u adapter ile canonical pakete dönüşür

---

# 10. Canonical enum’lar

## 10.1 VisualClass

```text
FIGHTER_JET
UAV
UCAV
HELICOPTER
TRANSPORT_AIRCRAFT
CIVILIAN_AIRCRAFT
MICRO_DRONE
UNKNOWN_AIRCRAFT
NON_AIRCRAFT
```

## 10.2 VisualEvidenceStatus

```text
SUPPORTED
PARTIALLY_SUPPORTED
WEAK
CONFLICTING
INSUFFICIENT
```

## 10.3 UncertaintyLevel

```text
LOW
MEDIUM
HIGH
```

## 10.3.1 EvidenceSourceMode

```text
VLM_ONLY
VLM_PLUS_RETRIEVAL
FUSED
```

## 10.3.2 ConfidenceOrigin

```text
VLM_SELF_REPORTED
UPSTREAM_RETRIEVAL
UPSTREAM_FUSION
CALIBRATED_UPSTREAM
```

## 10.4 ContextStatus

```text
COMPLETE
PARTIAL
MISSING
INVALID
INACTIVE
```

## 10.5 ToolExecutionStatus

```text
SUCCESS
INVALID_INPUT
TIMEOUT
ERROR
SKIPPED
```

## 10.6 PlatformStatus

```text
EXPECTED
NOT_EXPECTED
UNKNOWN
AMBIGUOUS
NON_AIRCRAFT
```

## 10.7 PermissionStatus

```text
VALID
NOT_FOUND
EXPIRED
NOT_YET_VALID
REVOKED
AMBIGUOUS
CONFLICTING
NOT_APPLICABLE
```

## 10.8 FlightPlanStatus

```text
FILED
NOT_FOUND
EXPIRED
NOT_YET_ACTIVE
CANCELLED
AMBIGUOUS
CONFLICTING
NOT_APPLICABLE
```

## 10.9 RecordConsistency

```text
CONSISTENT
PARTIAL
CONFLICTING
UNKNOWN
NOT_APPLICABLE
```

## 10.10 NotamStatus

```text
ACTIVE_RELEVANT
ACTIVE_NOT_RELEVANT
NONE_ACTIVE
EXPIRED_ONLY
NOT_YET_ACTIVE
AMBIGUOUS
CONFLICTING
```

## 10.11 NotamOperationEffect

```text
NO_EFFECT
INFORMATIONAL
REQUIRES_ADDITIONAL_CHECK
RESTRICTS_OPERATION
PROHIBITS_OPERATION
CONFLICTS_WITH_PERMISSION
UNKNOWN
```

## 10.12 VerificationStatus

```text
VERIFIED
PARTIALLY_VERIFIED
UNVERIFIED
INDETERMINATE
NOT_APPLICABLE
```

## 10.13 ToolHealthStatus

```text
HEALTHY
DEGRADED
FAILED
```

## 10.14 RiskLevel

```text
LOW
MEDIUM
HIGH
CRITICAL
UNKNOWN
```

## 10.15 DecisionCode

```text
AUTHORIZED_OPERATIONAL_MATCH
PARTIALLY_VERIFIED_OPERATION
UNVERIFIED_AIRCRAFT
UNEXPECTED_PLATFORM
EXPIRED_OR_INVALID_PERMISSION
CONFLICTING_OPERATIONAL_RECORDS
PLATFORM_UNRESOLVED
NON_AIRCRAFT
INDETERMINATE
```

---

# 11. Modül: Input Adapterları

Aktif giriş sınırı `raw_vlm_adapter.py` ile `upstream_vlm_adapter.py` dosyalarındadır. Ham Türkçe VLM payloadu strict canonical isteğe dönüştürülür; video event projection yalnız `video_event_adapter.py` üzerinden taşınır. `config/visual_adapter.yaml` teknik sınıf eşlemelerinin korunan kaynağıdır. Production görsel güven ve zaman değerlerini uydurmaz.

---

# 12. Modül: Input Validation ve invalid audit

**Dosyalar:**

```text
src/operational_decision/contracts/visual.py
src/operational_decision/contracts/request.py
src/operational_decision/validation/input_validator.py
```

```python
def build_invalid_input_output(
    event_id: str,
    request_id: str,
    errors: list[ValidationIssue],
) -> FinalDecisionOutput:
    ...
```

## Kontroller

- Desteklenen `schema_version`
- Boş olmayan `track_id`
- Confidence alanları 0–1
- `last_seen_offset_seconds >= first_seen_offset_seconds`
- Offset değerleri negatif değil
- Candidate rank tekrar etmiyor
- Candidate score 0–1
- Crop ref ve score sayıları uyumlu
- `NON_AIRCRAFT` değilse hypothesis mevcut
- `visual_evidence_status=SUPPORTED` ve `uncertainty_level=HIGH` kombinasyonu kabul edilir; otomatik değiştirilmez
- Timestamp UTC-aware
- Naive datetime reddedilir

## Invalid input davranışı

Audit yaklaşımı kullanılacaktır:

1. `event_id = evt_<uuid4hex>` oluşturulur.
2. Event kaydı `CREATED` olur.
3. Sanitized raw payload audit tablosuna yazılır.
4. Validation başarısızsa event `REJECTED_INVALID_INPUT` olur.
5. HTTP response 422 döner.
6. Response body içinde güvenli `FinalDecisionOutput` bulunur.
7. LLM ve tool’lar çağrılmaz.

---

# 13. Operational Context Resolver

**Dosyalar:**

```text
src/operational_decision/context/context_repository.py
src/operational_decision/context/context_resolver.py
src/operational_decision/contracts/context.py
```

## Context kaydı

```json
{
  "video_id": "VIDEO_001",
  "camera_id": "CAM_01",
  "context_id": "DEMO_CONTEXT_A",
  "operational_area_id": "AREA_001",
  "scenario_id": "SCN_001",
  "video_start_time_utc": "2026-08-10T11:20:00Z",
  "description": "Beklenen platform ve geçerli izin senaryosu",
  "environment": "DEMO",
  "status": "ACTIVE"
}
```

## Fonksiyonlar

```python
async def get_video_context(video_id: str) -> VideoContextRecord | None:
    ...
```

```python
def calculate_observation_time(
    video_start_time_utc: datetime,
    first_seen_offset_seconds: float,
) -> datetime:
    ...
```

```python
def calculate_observation_end_time(
    video_start_time_utc: datetime,
    last_seen_offset_seconds: float,
) -> datetime:
    ...
```

```python
async def resolve_context(
    video_id: str,
    first_seen_offset_seconds: float,
    last_seen_offset_seconds: float,
) -> ContextResolution:
    ...
```

## Kural

```text
observation_time_utc =
video_start_time_utc + first_seen_offset_seconds
```

## Context gate

| Context | Platform Tool | NOTAM Tool | Permission Tool |
|---|---:|---:|---:|
| COMPLETE | Çalışır | Çalışır | Platform çözülürse çalışır |
| PARTIAL | Çalışır | SKIPPED | SKIPPED |
| MISSING | Çalışır | SKIPPED | SKIPPED |
| INVALID | Çalışır | SKIPPED | SKIPPED |
| INACTIVE | Çalışır | SKIPPED | SKIPPED |

---

# 14. Event Manager ve SQLite Event Memory

## 14.1 Event ID

```python
event_id = f"evt_{uuid.uuid4().hex}"
request_id = f"req_{uuid.uuid4().hex}"
```

## 14.2 Fingerprint

```python
def generate_event_fingerprint(
    video_id: str,
    track_id: str,
    first_seen_offset_seconds: float,
) -> str:
    canonical = f"{video_id}|{track_id}|{first_seen_offset_seconds:.3f}"
    return sha256(canonical.encode("utf-8")).hexdigest()
```

## 14.3 Idempotency

- Aynı fingerprint ile `FINALIZED` event varsa mevcut sonuç döndürülür.
- Aynı fingerprint `FAILED` ise yeni event açılabilir; önceki event `retry_of_event_id` ile bağlanır.
- Aynı fingerprint `PROCESSING` ise HTTP 409 döner.
- Fingerprint unique index ile korunur.

## 14.4 Event lifecycle

```text
CREATED
INPUT_VALIDATED
CONTEXT_RESOLVED
WAITING_FOR_GPU_HANDOFF
TOOLS_RUNNING
TOOLS_COMPLETED
VERIFICATION_COMPLETED
RISK_ASSESSED
RAG_COMPLETED
LLM_COMPLETED
FINALIZED
FAILED
REJECTED_INVALID_INPUT
```

## 14.5 Fonksiyonlar

```python
async def create_event(...) -> EventRecord:
    ...
```

```python
async def update_event_status(event_id: str, status: EventStatus) -> None:
    ...
```

```python
async def record_event_step(...) -> None:
    ...
```

```python
async def record_tool_execution(...) -> None:
    ...
```

```python
async def store_final_output(...) -> None:
    ...
```

```python
async def get_event_trace(event_id: str) -> dict[str, Any]:
    ...
```

```python
async def mark_event_failed(...) -> None:
    ...
```

---

# 15. Ortak Tool altyapısı

**Dosyalar:**

```text
src/operational_decision/tools/base.py
src/operational_decision/contracts/tools.py
```

## Tool envelope

```json
{
  "tool_name": "permission_flight_plan_tool",
  "tool_version": "1.0.0",
  "event_id": "evt_x",
  "request_id": "req_x",
  "execution_status": "SUCCESS",
  "started_at_utc": "2026-08-10T11:20:09.120Z",
  "finished_at_utc": "2026-08-10T11:20:09.132Z",
  "latency_ms": 12,
  "data": {},
  "warnings": [],
  "error": null,
  "source_refs": []
}
```

## Kritik ayrım

Doğru:

```json
{
  "execution_status": "SUCCESS",
  "data": {
    "permission_status": "NOT_FOUND"
  }
}
```

Yanlış:

```json
{
  "execution_status": "NOT_FOUND"
}
```

## Base Tool

```python
class BaseTool(Generic[RequestT, DataT], ABC):
    async def execute(
        self,
        request: RequestT,
        *,
        timeout_seconds: float,
    ) -> ToolResponseEnvelope[DataT]:
        ...

    def validate_request(self, request: RequestT) -> None:
        ...

    @abstractmethod
    async def execute_internal(self, request: RequestT) -> DataT:
        ...
```

Base class:

- request validation,
- timer,
- timeout,
- known exception mapping,
- envelope creation,
- log,
- retry policy hook

işlemlerini gerçekleştirir.

## Retry

- `INVALID_INPUT`: retry yok
- `NOT_FOUND`: retry yok
- `SQLITE_BUSY` / `SQLITE_LOCKED`: en fazla 1 retry
- `TIMEOUT`: tool’a göre 0 veya 1
- LLM parse hatası: 1 repair
- RAG `NO_RELEVANT_CONTEXT`: retry yok

---

# 16. Platform DB Tool

**Dosyalar:**

```text
src/operational_decision/tools/platform_tool.py
src/operational_decision/platform/platform_registry.py
src/operational_decision/contracts/platform.py
```

## Veri kaynakları

```text
data/platforms/platform_registry.json
data/platforms/platform_aliases.json
```

## Matching politikası V1

Fuzzy matching kullanılmayacaktır.

1. `visual_class=NON_AIRCRAFT` → `NON_AIRCRAFT`
2. `final_visual_hypothesis` normalize edilir.
3. Exact alias tek bir platforma eşleşirse platform çözülür.
4. Exact alias yoksa `candidate_matches` alias tablosunda aranır.
5. Candidate’lar yalnızca bir unique `platform_id` üretiyorsa platform çözülür.
6. Birden fazla unique platform oluşursa `AMBIGUOUS`.
7. Hiç platform oluşmazsa `UNKNOWN`.
8. Upstream score, eşleşme kararı için yeni bir eşik icat edilerek kullanılmaz.
9. Platform çözüldüğünde context override ile `EXPECTED` veya `NOT_EXPECTED` belirlenir.

## Platform registry örneği

```json
{
  "platform_id": "PLT_F16",
  "canonical_name": "F-16 Fighting Falcon",
  "aliases": ["F-16", "F16", "F-16-like"],
  "category": "FIGHTER_JET",
  "default_expectation": "EXPECTED",
  "context_overrides": {
    "DEMO_CONTEXT_B": "NOT_EXPECTED"
  },
  "active": true,
  "source_type": "DEMO_MOCK"
}
```

## Fonksiyonlar

```python
def load_platform_registry(path: Path) -> PlatformRegistry:
    ...
```

```python
def normalize_platform_alias(value: str) -> str:
    ...
```

```python
def find_exact_match(value: str) -> PlatformRecord | None:
    ...
```

```python
def resolve_candidates(
    candidates: list[VisualCandidate],
) -> list[PlatformRecord]:
    ...
```

```python
def resolve_context_expectation(
    platform: PlatformRecord,
    context_id: str | None,
) -> PlatformStatus:
    ...
```

---

# 17. Permission & Flight Plan Tool

Tek tool, iki ayrı repository ve iki ayrı domain sonucu kullanır.

**Dosyalar:**

```text
src/operational_decision/tools/permission_flight_plan_tool.py
src/operational_decision/operational/permission_repository.py
src/operational_decision/operational/flight_plan_repository.py
src/operational_decision/contracts/permission.py
```

## Çağrı politikası

Tool yalnızca:

```text
platform_id mevcut
AND platform execution SUCCESS
AND platform_status ∈ {EXPECTED, NOT_EXPECTED}
AND context_status = COMPLETE
```

ise çağrılır.

Diğer durumlarda:

```json
{
  "execution_status": "SKIPPED",
  "data": {
    "skip_reason": "PLATFORM_UNRESOLVED"
  }
}
```

## Permission kuralları

- Aktif ve zaman aralığına uyan tek kayıt → `VALID`
- Kayıt yok → `NOT_FOUND`
- Sadece süresi geçmiş kayıt → `EXPIRED`
- Sadece gelecekte başlayan kayıt → `NOT_YET_VALID`
- Revoked kayıt → `REVOKED`
- Aynı anda birden fazla uyumsuz aktif kayıt → `CONFLICTING`
- Aynı anda birden fazla eşdeğer kayıt → `AMBIGUOUS`

## Flight plan kuralları

- Gözlem zamanıyla uyumlu filed/active kayıt → `FILED`
- Kayıt yok → `NOT_FOUND`
- Süresi geçmiş → `EXPIRED`
- Henüz aktif değil → `NOT_YET_ACTIVE`
- İptal → `CANCELLED`
- Uyumsuz birden fazla kayıt → `CONFLICTING`
- Birden fazla eşdeğer kayıt → `AMBIGUOUS`

## Uçuş planı izin değildir

```text
flight_plan_status = FILED
permission_status = NOT_FOUND
```

sonucu hiçbir koşulda geçerli izin gibi yorumlanmaz.

## Record consistency

| Permission | Flight plan | Consistency |
|---|---|---|
| VALID | FILED | CONSISTENT |
| VALID | NOT_FOUND | PARTIAL |
| NOT_FOUND | FILED | PARTIAL |
| VALID | CANCELLED | CONFLICTING |
| EXPIRED | FILED | CONFLICTING |
| CONFLICTING | Herhangi | CONFLICTING |
| NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE |

---

# 18. NOTAM Tool

**Dosyalar:**

```text
src/operational_decision/tools/notam_tool.py
src/operational_decision/operational/notam_repository.py
src/operational_decision/contracts/notam.py
```

## Girdi

```text
context_id
operational_area_id
scenario_id
observation_time_utc
visual_class
platform_id (opsiyonel)
```

## Akış

1. `operational_area_id` + zaman aralığı ile kayıtlar çekilir.
2. Aktif kayıtlar belirlenir.
3. Relevance metadata üzerinden hesaplanır.
4. LLM relevance belirlemez.
5. Operation effect kaydın kontrollü enum alanından alınır.
6. Birbiriyle uyumsuz eşzamanlı kayıtlar `CONFLICTING` yapar.

## Relevance alanları

- `context_id`
- `scenario_id`
- `relevance_tags`
- `affected_platform_categories`
- `affected_platform_ids`
- `operational_area_id`

## NOTAM sonucu

```json
{
  "notam_status": "ACTIVE_RELEVANT",
  "operation_effect": "RESTRICTS_OPERATION",
  "active_notams": [
    {
      "notam_id": "DEMO_NOTAM_SCN_05",
      "summary_tr": "Demo operasyon alanında belirli uçuşlar sınırlandırılmıştır."
    }
  ]
}
```

Aktif NOTAM tek başına otomatik HIGH değildir; `operation_effect` risk kuralını belirler.

---

# 19. Operational Verification Checker

**Dosya:** `src/operational_decision/decision/verification_checker.py`

Bu katman risk üretmez.

## Tool health

- Bütün gerekli tool’lar `SUCCESS` veya gerekçeli `SKIPPED` → `HEALTHY`
- Kararı tamamen engellemeyen bir tool `TIMEOUT/ERROR` → `DEGRADED`
- Kritik context/platform/permission doğrulaması yapılamıyor → `FAILED`

## Precedence kuralları

Aşağıdaki sıra bağlayıcıdır:

1. Strong non-aircraft → `NOT_APPLICABLE`
2. Context `MISSING/INVALID/INACTIVE` → `INDETERMINATE`
3. Tool health `FAILED` → `INDETERMINATE`
4. Platform `UNKNOWN/AMBIGUOUS` → `INDETERMINATE`
5. Permission veya flight plan `CONFLICTING` → `UNVERIFIED`
6. NOTAM effect `CONFLICTS_WITH_PERMISSION/PROHIBITS_OPERATION` → `UNVERIFIED`
7. Permission `EXPIRED/REVOKED/NOT_YET_VALID/NOT_FOUND` → `UNVERIFIED`
8. Platform `EXPECTED` + permission `VALID` + plan `FILED` + no restricting conflict → `VERIFIED`
9. Platform `EXPECTED` + permission `VALID` + plan `NOT_FOUND` → `PARTIALLY_VERIFIED`
10. Platform `NOT_EXPECTED` + permission `VALID` + plan `FILED` → `PARTIALLY_VERIFIED`
11. Geri kalan eksik ama kısmen doğrulanmış durum → `PARTIALLY_VERIFIED`
12. Güvenli şekilde sınıflandırılamayan durum → `INDETERMINATE`

## Reason codes

En az şu kodlar desteklenmelidir:

```text
PLATFORM_EXPECTED
PLATFORM_NOT_EXPECTED
PLATFORM_UNKNOWN
PLATFORM_AMBIGUOUS
PERMISSION_VALID
PERMISSION_NOT_FOUND
PERMISSION_EXPIRED
PERMISSION_NOT_YET_VALID
PERMISSION_REVOKED
PERMISSION_CONFLICTING
FLIGHT_PLAN_FILED
FLIGHT_PLAN_NOT_FOUND
FLIGHT_PLAN_CANCELLED
FLIGHT_PLAN_WITHOUT_PERMISSION
NOTAM_ACTIVE_RELEVANT
NOTAM_RESTRICTS_OPERATION
NOTAM_PROHIBITS_OPERATION
NOTAM_CONFLICTS_WITH_PERMISSION
NOTAM_NONE_ACTIVE
NOTAM_CONFLICTING
CONTEXT_COMPLETE
CONTEXT_PARTIAL
CONTEXT_MISSING
CONTEXT_INVALID
CONTEXT_INACTIVE
PLATFORM_TOOL_ERROR
PERMISSION_TOOL_ERROR
NOTAM_TOOL_ERROR
TOOL_TIMEOUT
VISUAL_EVIDENCE_CONFLICTING
VISUAL_UNCERTAINTY_HIGH
NON_AIRCRAFT
```

---

# 20. Risk Advisor

**Dosyalar:**

```text
src/operational_decision/decision/risk_advisor.py
src/operational_decision/contracts/risk.py
data/rules/risk_rules.yaml
```

Risk Advisor deterministiktir. LLM risk seviyesini seçmez.

## Risk birleştirme

1. Context eksikliği veya kritik tool failure varsa final risk `UNKNOWN`.
2. Aksi durumda `LOW < MEDIUM < HIGH < CRITICAL` sıralamasındaki en yüksek minimum risk seçilir.
3. Human review bütün kaynaklardan OR ile birleştirilir.
4. `UNKNOWN` hiçbir zaman LOW’a çevrilmez.
5. Risk kuralı yoksa `UNKNOWN + human review`.

## Zorunlu temel kurallar

```yaml
rules:
  - id: RULE_CONTEXT_UNAVAILABLE
    priority: 1000
    when:
      context_status:
        in: [MISSING, INVALID, INACTIVE]
    minimum_risk: UNKNOWN
    human_review: true

  - id: RULE_CRITICAL_TOOL_FAILURE
    priority: 1000
    when:
      tool_health_status: FAILED
    minimum_risk: UNKNOWN
    human_review: true

  - id: RULE_NOTAM_PROHIBITS_OPERATION
    priority: 950
    when:
      notam_operation_effect: PROHIBITS_OPERATION
    minimum_risk: CRITICAL
    human_review: true

  - id: RULE_NOTAM_PERMISSION_CONFLICT
    priority: 900
    when:
      notam_operation_effect: CONFLICTS_WITH_PERMISSION
    minimum_risk: HIGH
    human_review: true

  - id: RULE_CONFLICTING_RECORDS
    priority: 900
    when:
      record_consistency: CONFLICTING
    minimum_risk: HIGH
    human_review: true

  - id: RULE_PERMISSION_REVOKED
    priority: 900
    when:
      permission_status: REVOKED
    minimum_risk: HIGH
    human_review: true

  - id: RULE_PERMISSION_EXPIRED
    priority: 850
    when:
      permission_status: EXPIRED
    minimum_risk: HIGH
    human_review: true

  - id: RULE_NOT_EXPECTED_NO_PERMISSION
    priority: 800
    when:
      platform_status: NOT_EXPECTED
      permission_status: NOT_FOUND
    minimum_risk: HIGH
    human_review: true

  - id: RULE_EXPECTED_NO_PERMISSION
    priority: 600
    when:
      platform_status: EXPECTED
      permission_status: NOT_FOUND
    minimum_risk: MEDIUM
    human_review: true

  - id: RULE_NOT_EXPECTED_VALID_PERMISSION
    priority: 550
    when:
      platform_status: NOT_EXPECTED
      permission_status: VALID
    minimum_risk: MEDIUM
    human_review: true

  - id: RULE_HIGH_VISUAL_UNCERTAINTY
    priority: 500
    when:
      uncertainty_level: HIGH
    minimum_risk: MEDIUM
    human_review: true

  - id: RULE_VERIFIED_OPERATION
    priority: 100
    when:
      verification_status: VERIFIED
      uncertainty_level:
        in: [LOW, MEDIUM]
    minimum_risk: LOW
    human_review: false

  - id: RULE_NON_AIRCRAFT
    priority: 100
    when:
      verification_status: NOT_APPLICABLE
    minimum_risk: LOW
    human_review: false
```

---

# 21. Confidence ve kalite göstergeleri

Bu değerler **istatistiksel doğruluk olasılığı değildir**. İç sistem kalite göstergesidir. Alan adları buna göre kullanılacaktır:

- `evidence_quality_score`
- `risk_assessment_confidence`
- `decision_confidence`

## 21.1 Tool coverage score

```text
tool_coverage =
başarılı gerekli tool sayısı / gerekli tool sayısı
```

Kontrollü `SKIPPED`:

- `NOT_APPLICABLE` nedeniyle ise denominator’a girmez.
- Eksik context/platform nedeniyle ise gerekli ama çalıştırılamamış sayılır ve 0 katkı verir.

## 21.2 Context score

| Context | Score |
|---|---:|
| COMPLETE | 1.00 |
| PARTIAL | 0.60 |
| INACTIVE | 0.20 |
| MISSING | 0.00 |
| INVALID | 0.00 |

## 21.3 Verification determinacy score

| Verification | Score |
|---|---:|
| VERIFIED | 1.00 |
| UNVERIFIED | 1.00 |
| NOT_APPLICABLE | 1.00 |
| PARTIALLY_VERIFIED | 0.70 |
| INDETERMINATE | 0.30 |

## 21.4 Evidence quality formula

```python
evidence_quality_score = round(
    0.45 * visual.visual_confidence
    + 0.25 * tool_coverage_score
    + 0.20 * context_score
    + 0.10 * verification_determinacy_score,
    3,
)
```

## 21.5 Risk assessment confidence

```text
exact multi-field rule matched → specificity 1.00
exact single-field rule matched → specificity 0.85
fallback/unknown rule → specificity 0.50
```

```python
risk_assessment_confidence = round(
    evidence_quality_score * rule_specificity,
    3,
)
```

`risk_level=UNKNOWN` olduğunda confidence en fazla `0.50` olmalıdır.

## 21.6 Decision confidence

LLM self-report kullanılmaz.

```python
decision_confidence = round(
    min(evidence_quality_score, risk_assessment_confidence),
    3,
)
```

---

# 22. Strong non-aircraft early exit

```python
def should_early_exit_non_aircraft(
    visual: FinalVisualEvidencePackage,
    threshold: float,
) -> bool:
    return (
        visual.visual_class == VisualClass.NON_AIRCRAFT
        and visual.visual_evidence_status == VisualEvidenceStatus.SUPPORTED
        and visual.uncertainty_level == UncertaintyLevel.LOW
        and visual.visual_confidence >= threshold
    )
```

Config:

```yaml
early_exit:
  non_aircraft_enabled: true
  non_aircraft_visual_confidence_threshold: 0.85
  call_llm_for_non_aircraft: false
```

Erken çıkış:

```text
verification_status = NOT_APPLICABLE
risk_level = LOW
decision = NON_AIRCRAFT
Text RAG = SKIPPED
LLM = SKIPPED
```

`NON_AIRCRAFT + HIGH uncertainty` erken çıkmaz.

---

# 23. Text RAG kaynakları

## Runtime temel kaynakları

```text
LT_GEN_1_2_en.pdf
SHT-IHA_Rev-05.pdf
LT_GEN_3_1_en.pdf
LT_ENR_1_10_en.pdf
```

## Opsiyonel destek

```text
LT_GEN_3_3_en.pdf
LT_GEN_1_6_en.pdf
```

## Runtime RAG’e alınmayacak

```text
ucus_izni_talep_formu.docx
ucus_izinlerine_iliskin_el_kitabi.pdf
Sistem Mimarisi + Görevler.pdf
TEKNOFEST şartnamesi
```

## Kullanım rolleri

### `LT_GEN_1_2_en.pdf`

- uçuş izni gerekliliği,
- izin başvuru bilgileri,
- uçuş planı ile izin ayrımı,
- izin geçerliliği,
- izinsiz uçuş bağlamı.

### `SHT-IHA_Rev-05.pdf`

- sivil İHA kapsamı,
- kayıt/tescil,
- uçuş izni,
- hava sahası kullanımı,
- risk değerlendirmesi,
- insan/yapı ve diğer hava araçları riski.

Bu belge sivil İHA içindir. Askeri/devlet platformlarına otomatik uygulanmaz.

### `LT_GEN_3_1_en.pdf`

- AIS/AIM,
- NOF,
- FIC,
- NOTAM,
- NOTAM serileri,
- PIB,
- uçuş öncesi bilgi hizmetleri.

### `LT_ENR_1_10_en.pdf`

- uçuş planı prosedürleri,
- plan sunulması,
- flight plan kayıtlarının anlamı.

### `ucus_izni_talep_formu.docx`

Sadece DB alanlarını anlamak için reference-only kullanılır. Runtime retrieval’a girmez.

### EAD / Eurocontrol

Yalnızca veri hazırlama sırasında referans olabilir. Runtime bağlantısı yasaktır.

---

# 24. Document manifest

**Dosya:** `data/rag/document_manifest.yaml`

Her kayıt:

```yaml
documents:
  - document_id: LT_GEN_1_2
    filename: LT_GEN_1_2_en.pdf
    authority: DHMI_AIP
    document_type: AIP_GEN
    language: en
    topics:
      - flight_permission
      - permission_application
      - flight_plan_permission_distinction
    source_priority: 100
    authoritative: true
    runtime_rag: true
    revision_date: null
    effective_date: null
    sha256: REPLACE_WITH_REAL_CHECKSUM

  - document_id: SHT_IHA_REV_05
    filename: SHT-IHA_Rev-05.pdf
    authority: SHGM
    document_type: INSTRUCTION
    language: tr
    topics:
      - civil_uav
      - uav_permission
      - uav_risk
    source_priority: 95
    authoritative: true
    runtime_rag: true
    revision_date: null
    effective_date: null
    sha256: REPLACE_WITH_REAL_CHECKSUM
```

Checksum placeholder bırakılabilir ancak index oluşturulmadan önce script gerçek checksum üretip manifesti güncellemelidir.

## Kaynak önceliği

```text
Güncel resmi AIP / resmi talimat
  ↓
Güncel resmi rehber
  ↓
Resmi form
  ↓
Eski açıklayıcı el kitabı
  ↓
Proje notları
```

---

# 25. Text RAG ingestion

**Dosyalar:**

```text
src/operational_decision/rag/document_catalog.py
src/operational_decision/rag/document_loader.py
src/operational_decision/rag/chunker.py
src/operational_decision/rag/embedding_provider.py
src/operational_decision/rag/faiss_store.py
src/operational_decision/rag/index_builder.py
```

## Extractor

- PDF: `pypdf`
- DOCX: `python-docx`
- OCR: yok
- Metin çıkarılamazsa doküman `EXTRACTION_FAILED`
- Sayfa bilgisi korunur
- Header/footer tekrarları basit deterministik temizleme ile kaldırılabilir
- Anlamlı madde numaraları korunur

## Chunking

```yaml
chunking:
  target_tokens: 600
  max_tokens: 750
  overlap_tokens: 100
  preserve_page_number: true
  preserve_section_title: true
  split_on_heading_first: true
  split_on_paragraph_second: true
```

Chunk iki sayfaya taşıyorsa:

```text
page_start
page_end
```

alanları tutulur.

## Chunk metadata

```text
chunk_id
document_id
filename
language
page_start
page_end
section_title
content
topics
source_priority
authoritative
revision_date
effective_date
document_sha256
chunk_sha256
```

## Index

```python
index = faiss.IndexFlatIP(1024)
```

Index yalnızca normalize edilmiş `float32` embedding kabul eder.

Dosyalar:

```text
data/rag/index/text.index
data/rag/index/chunk_metadata.jsonl
data/rag/index/index_manifest.json
```

`index_manifest.json`:

```json
{
  "embedding_model": "Qwen/Qwen3-Embedding-0.6B",
  "dimension": 1024,
  "normalized": true,
  "document_manifest_sha256": "...",
  "chunk_count": 0,
  "built_at_utc": "..."
}
```

Runtime başlangıcında index ve manifest uyumu doğrulanır.

---

# 26. Text RAG retrieval

## V1 ayarları

```yaml
retrieval:
  candidate_top_k: 8
  final_top_k: 4
  max_chunks_per_document: 2
  deduplicate_adjacent_chunks: true
  reranker_enabled: false
  hybrid_search_enabled: false
  minimum_similarity: null
```

İlk sürümde keyfi similarity threshold kullanılmaz. Benchmark sonrasında threshold eklenebilir.

## Akış

1. Verification/risk üzerinden query template seç.
2. Document/topic filtresi oluştur.
3. Query instruction’ı İngilizce ekle.
4. Query embedding üret.
5. Filterlenmiş adaylar üzerinde exact search yap.
6. Top-8 al.
7. Aynı veya komşu tekrar chunk’ları temizle.
8. Doküman başına en fazla 2 chunk tut.
9. Final Top-4 üret.
10. Source references oluştur.

## Query instruction

```text
Retrieve authoritative aviation regulation passages relevant to the
Turkish operational verification question. Prefer exact legal and
procedural context in Turkish or English.
```

## Query templates

### Permission not found

```text
Türk hava sahasında uçuş planı mevcut olsa bile geçerli uçuş izni kaydı
bulunmayan operasyonların izin bağlamı nedir?
```

Filter:

```text
LT_GEN_1_2
LT_ENR_1_10
```

### Permission expired

```text
Gözlem zamanında geçerlilik süresi sona ermiş uçuş izninin operasyonel
değerlendirmesi nedir?
```

Filter:

```text
LT_GEN_1_2
```

### Civil UAV

```text
Sivil İHA operasyonlarında uçuş izni, hava sahası kullanımı ve risk
değerlendirmesi hangi kurallara tabidir?
```

Filter:

```text
SHT_IHA_REV_05
```

### Active NOTAM

```text
Aktif ve operasyonla ilgili NOTAM bildiriminin uçuş operasyonu ve
havacılık bilgi hizmetleri açısından anlamı nedir?
```

Filter:

```text
LT_GEN_3_1
```

### Flight plan without permission

```text
Uçuş planının bulunması, uçuş izninin bulunduğu anlamına gelir mi?
```

Filter:

```text
LT_GEN_1_2
LT_ENR_1_10
```

---

# 27. Text RAG çağrı politikası

RAG, Risk Advisor’dan sonra çalışır.

## RAG çağrılmaz

Aşağıdakilerin tamamı doğruysa:

```text
verification_status = VERIFIED
risk_level = LOW
tool_health_status = HEALTHY
explanation_requested = false
```

Strong non-aircraft erken çıkışında da çağrılmaz.

## RAG çağrılır

Aşağıdakilerden biri doğruysa:

- `explanation_requested=true`
- `verification_status != VERIFIED`
- `risk_level ∈ {MEDIUM, HIGH, CRITICAL, UNKNOWN}`
- permission `NOT_FOUND/EXPIRED/CONFLICTING/AMBIGUOUS/REVOKED`
- flight plan `NOT_FOUND/CANCELLED/CONFLICTING/AMBIGUOUS`
- NOTAM `ACTIVE_RELEVANT/CONFLICTING/AMBIGUOUS`
- platform `NOT_EXPECTED/UNKNOWN/AMBIGUOUS`
- context `MISSING/PARTIAL/INVALID/INACTIVE`

RAG karar vermez. Yalnızca kaynak bağlamı sağlar.

---

# 28. Evidence Package Builder

**Dosya:** `src/operational_decision/decision/evidence_builder.py`

LLM’e ham DB satırları ve crop dosyaları gönderilmez.

## Paket

### Legacy 2.0 örneği — yalnız tarihsel referans

Aşağıdaki paket eski `llm-evidence/2.0` biçimini gösterir. Yeni evidence üretiminde canonical değildir ve 2.1 Inventory/Consistency alanlarıyla karıştırılmaz.

```json
{
  "schema_version": "llm-evidence/2.0",
  "event": {
    "event_id": "evt_x",
    "track_id": "TRK_001",
    "observation_time_utc": "2026-08-10T11:20:08.200Z"
  },
  "visual_evidence": {},
  "operational_context": {},
  "platform_result": {},
  "permission_flight_plan_result": {},
  "notam_result": {},
  "verification_result": {},
  "risk_result": {},
  "rag_context": [],
  "constraints": {
    "minimum_risk_level": "HIGH",
    "human_review_required": true,
    "visual_identity_is_hypothesis": true,
    "allowed_decision_codes": [],
    "allowed_action_codes": [],
    "available_source_ids": []
  }
}
```

### Canonical LLMEvidencePackage 2.1

Yeni paket `schema_version="llm-evidence/2.1"` kullanır ve legacy gövdeye aşağıdaki deterministic alanları ekler:

```json
{
  "schema_version": "llm-evidence/2.1",
  "inventory_status": "CONFIRMED",
  "inventory_record_id": "INV_TR_F16_DEMO",
  "inventory_country_code": "TR",
  "inventory_operator_name": "DEMO_OPERATOR",
  "inventory_service_status": "ACTIVE",
  "inventory_dataset_id": "turkey_inventory_demo",
  "inventory_dataset_version": "1.0.0",
  "inventory_source_type": "DEMO_MOCK",
  "inventory_reason_codes": ["INVENTORY_SCOPE_CONFIRMED"],
  "operational_consistency_status": "CONSISTENT",
  "operational_consistency_flags": ["INVENTORY_SCOPE_CONFIRMED"]
}
```

Bu compact alanlar deterministic tool/checker sonuçlarından gelir; LLM üretmez. Ham Inventory registry satırı evidence paketine konmaz.

## Token budget

- Evidence package hedef: en fazla 5000 input token
- RAG chunk: en fazla 4
- Her chunk content: en fazla 750 token
- Tekrarlanan tool envelope metadata LLM’e gönderilmez
- Request ID, timing ve internal errors yalnızca gerektiğinde özetlenir

---

# 29. Local LLM Decision Agent

**Dosyalar:**

```text
src/operational_decision/llm/base_client.py
src/operational_decision/llm/ollama_client.py
src/operational_decision/llm/prompt_builder.py
src/operational_decision/llm/response_parser.py
src/operational_decision/contracts/llm.py
```

Yalnızca `OllamaLLMClient` uygulanacaktır. vLLM/OpenAI adapter yazılmayacaktır.

## LLM’in görevleri

- İzin verilen karar kodları arasından seçim yapmak
- Türkçe özet yazmak
- Kanıtları kısa ve açık biçimde açıklamak
- Belirsizlikleri belirtmek
- Aksiyon kataloğundan aksiyonları önceliklendirmek
- Retrieval kaynağı varsa geçerli source ID kullanmak

## LLM’in yapamayacakları

- Risk seviyesi seçmek veya düşürmek
- Tool sonucunu değiştirmek
- `NOT_FOUND` sonucunu `VALID` saymak
- `ERROR` sonucunu kayıt yok gibi yorumlamak
- Uçuş planını izin saymak
- Görsel benzerliği kesin kimlik olarak sunmak
- Kaynaklarda olmayan mevzuat oluşturmak
- Yeni NOTAM/izin kaydı uydurmak
- Tanımsız aksiyon üretmek
- Retrieval’da bulunmayan source ID kullanmak

## LLMDecision şeması

```json
{
  "decision_code": "UNVERIFIED_AIRCRAFT",
  "summary_tr": "string",
  "evidence_summary": [
    "string"
  ],
  "recommended_actions": [
    {
      "action_code": "REQUEST_OPERATOR_REVIEW",
      "priority": 1,
      "reason_tr": "string"
    }
  ],
  "uncertainty_notes": [
    "string"
  ],
  "source_ids": [
    "LT_GEN_1_2_P1_C03"
  ]
}
```

LLM response içinde `risk_level`, `decision_confidence`, `permission_status`, 
otam_status` bulunmaz. Bu alanlar deterministik katmanlardan gelir.

## Ollama request

```python
payload = {
    "model": settings.llm.model,
    "messages": messages,
    "stream": False,
    "think": False,
    "format": LLMDecision.model_json_schema(),
    "keep_alive": settings.llm.keep_alive_during_batch,
    "options": {
        "num_ctx": 8192,
        "num_predict": 1200,
        "temperature": 0.1,
        "top_p": 0.8,
        "seed": 42,
    },
}
```

## Repair

1. İlk cevap Pydantic ile parse edilir.
2. Başarısızsa hata listesiyle tek repair çağrısı yapılır.
3. İkinci cevap başarısızsa safe fallback.
4. Repair promptuna yeni evidence eklenmez.
5. Repair yalnızca JSON/schema düzeltmesi ister.

---

# 30. Allowed decision policy

Output Guard’a verilen `allowed_decision_codes` deterministik oluşturulur.

| Verification / Ana neden | İzin verilen karar |
|---|---|
| NOT_APPLICABLE | NON_AIRCRAFT |
| VERIFIED | AUTHORIZED_OPERATIONAL_MATCH |
| PARTIALLY_VERIFIED | PARTIALLY_VERIFIED_OPERATION |
| UNVERIFIED + NOT_EXPECTED | UNEXPECTED_PLATFORM |
| UNVERIFIED + EXPIRED/REVOKED | EXPIRED_OR_INVALID_PERMISSION |
| UNVERIFIED + CONFLICTING | CONFLICTING_OPERATIONAL_RECORDS |
| UNVERIFIED diğer | UNVERIFIED_AIRCRAFT |
| INDETERMINATE + platform unresolved | PLATFORM_UNRESOLVED |
| INDETERMINATE diğer | INDETERMINATE |

LLM farklı bir karar seçerse Guard düzeltir ve correction log oluşturur.

---

# 31. Aksiyon kataloğu

**Dosya:** `data/rules/action_catalog.yaml`

```yaml
actions:
  - code: CONTINUE_TRACKING
    title_tr: Takibi sürdür
    allowed_risks: [LOW, MEDIUM, HIGH, CRITICAL, UNKNOWN]

  - code: REQUEST_OPERATOR_REVIEW
    title_tr: Operatör incelemesi iste
    allowed_risks: [MEDIUM, HIGH, CRITICAL, UNKNOWN]

  - code: VERIFY_PLATFORM_MANUALLY
    title_tr: Platform hipotezini manuel doğrula
    allowed_risks: [MEDIUM, HIGH, CRITICAL, UNKNOWN]

  - code: CHECK_PERMISSION_RECORDS
    title_tr: Uçuş izni kayıtlarını kontrol et
    allowed_risks: [MEDIUM, HIGH, CRITICAL, UNKNOWN]

  - code: CHECK_FLIGHT_PLAN_RECORDS
    title_tr: Uçuş planı kayıtlarını kontrol et
    allowed_risks: [MEDIUM, HIGH, CRITICAL, UNKNOWN]

  - code: REVIEW_ACTIVE_NOTAM
    title_tr: Aktif NOTAM ayrıntılarını incele
    allowed_risks: [MEDIUM, HIGH, CRITICAL, UNKNOWN]

  - code: REQUEST_ADDITIONAL_VISUAL_EVIDENCE
    title_tr: Ek görsel kanıt iste
    allowed_risks: [MEDIUM, HIGH, UNKNOWN]

  - code: ESCALATE_TO_AUTHORIZED_UNIT
    title_tr: Yetkili birime ilet
    allowed_risks: [HIGH, CRITICAL]

  - code: MARK_AS_NON_AIRCRAFT
    title_tr: Hava aracı olmayan hedef olarak işaretle
    allowed_risks: [LOW]

  - code: LOG_AND_CLOSE_EVENT
    title_tr: Olayı kaydet ve kapat
    allowed_risks: [LOW]
```

Guard:

- kod var mı,
- risk ile uyumlu mu,
- priority unique ve 1’den başlıyor mu

kontrol eder.

---

# 32. Output Guard

**Dosya:** `src/operational_decision/finalizer/output_guard.py`

## Kontroller

1. Pydantic schema
2. Allowed decision
3. Action catalog
4. Action-risk compatibility
5. Source ID existence
6. Tool contradiction
7. Görsel overclaim
8. Human review preservation
9. Safe wording
10. Empty summary
11. Duplicate actions
12. Risked event için yetersiz aksiyon

## Tool contradiction örnekleri

- permission `NOT_FOUND`, özet “geçerli izin var”
- platform `UNKNOWN`, özet “kesin F-16”
- tool health `FAILED`, karar `AUTHORIZED_OPERATIONAL_MATCH`
- NOTAM `PROHIBITS_OPERATION`, özet “operasyon serbest”
- flight plan `FILED`, permission `NOT_FOUND`, özet “izin ve plan mevcut”

## Visual overclaim

İzin verilmeyen kalıplar:

```text
kesin olarak
kesinlikle
tartışmasız
%100
doğrulanmış F-16
```

Görsel kimlik dili:

```text
F-16 benzeri
F-16 ile görsel benzerlik gösteren
görsel hipotez
platform benzerliği
```

## Correction log

```json
{
  "field": "decision_code",
  "llm_value": "AUTHORIZED_OPERATIONAL_MATCH",
  "final_value": "UNVERIFIED_AIRCRAFT",
  "reason": "DECISION_NOT_ALLOWED_BY_VERIFICATION"
}
```

Metin çelişkisi otomatik güvenli şablonla değiştirilir; belirsiz serbest rewrite yapılmaz.

---

# 33. Output Finalizer

**Dosya:** `src/operational_decision/finalizer/output_finalizer.py`

Finalizer:

- risk seviyesini Risk Advisor’dan alır,
- decision confidence’ı deterministik hesaplar,
- human review OR kuralını uygular,
- Guard corrections ekler,
- final JSON oluşturur,
- event memory’ye kaydeder.

## Safe fallback

LLM veya Guard başarısızsa:

```text
decision = INDETERMINATE
risk_level = Risk Advisor UNKNOWN ise UNKNOWN,
             aksi durumda minimum_risk_level
human_approval_required = true
summary_tr = "Karar ajanı geçerli ve tutarlı bir çıktı üretemedi. Yapılandırılmış
kayıtlar operatör incelemesine aktarılmıştır."
recommended_actions = [REQUEST_OPERATOR_REVIEW]
```

Structured tool ve risk sonuçları kaybedilmez.

---

# 34. Nihai output şeması

## Legacy final-output/2.0 örneği — geriye dönük okuma

Aşağıdaki tam örnek saklanmış `final-output/2.0` kayıtlarının biçimini belgelendirir. Yeni final kayıtlar için canonical sürüm değildir.

```json
{
  "schema_version": "final-output/2.0",
  "event_id": "evt_x",
  "request_id": "req_x",
  "event_status": "FINALIZED",

  "video_id": "VIDEO_001",
  "camera_id": "CAM_01",
  "context_id": "DEMO_CONTEXT_A",
  "operational_area_id": "AREA_001",
  "scenario_id": "SCN_001",

  "track_id": "TRK_001",
  "observation_time_utc": "2026-08-10T11:20:08.200Z",
  "observation_end_time_utc": "2026-08-10T11:20:15.600Z",

  "visual_class": "FIGHTER_JET",
  "visual_hypothesis": "F-16-like",
  "visual_evidence_status": "SUPPORTED",
  "visual_confidence": 0.72,
  "uncertainty_level": "MEDIUM",
  "uncertainty_flags": ["LIMITED_VIEW_ANGLE"],

  "platform_status": "EXPECTED",
  "matched_platform": "F-16 Fighting Falcon",

  "permission_status": "VALID",
  "flight_plan_status": "FILED",
  "record_consistency": "CONSISTENT",

  "notam_status": "NONE_ACTIVE",
  "notam_operation_effect": "NO_EFFECT",

  "context_status": "COMPLETE",

  "verification_status": "VERIFIED",
  "verification_reason_codes": [
    "PLATFORM_EXPECTED",
    "PERMISSION_VALID",
    "FLIGHT_PLAN_FILED",
    "NOTAM_NONE_ACTIVE",
    "CONTEXT_COMPLETE"
  ],
  "tool_health_status": "HEALTHY",

  "decision": "AUTHORIZED_OPERATIONAL_MATCH",
  "decision_confidence": 0.81,

  "risk_level": "LOW",
  "minimum_risk_level": "LOW",
  "risk_assessment_confidence": 0.81,
  "evidence_quality_score": 0.81,

  "summary_tr": "F-16 benzeri bir hava aracı tespit edilmiştir...",
  "evidence_summary": [],
  "recommended_actions": [],

  "human_approval_required": false,
  "uncertainty_notes": [],

  "sources": [],
  "tool_execution_summary": {},
  "guard_corrections": [],

  "processing_latency_ms": 2840,
  "model_versions": {
    "decision_llm": "qwen3:4b-instruct-2507-q4_K_M",
    "text_embedding": "Qwen/Qwen3-Embedding-0.6B",
    "visual_pipeline": "UPSTREAM_PROVIDED"
  }
}
```

## Canonical FinalDecisionOutput 2.1

Yeni final çıktılar `schema_version="final-output/2.1"` kullanır. Legacy gövde korunur ve aşağıdaki Inventory/Consistency alanları canonical final JSON'a eklenir:

```json
{
  "schema_version": "final-output/2.1",
  "inventory_status": "CONFIRMED",
  "inventory_record_id": "INV_TR_F16_DEMO",
  "inventory_country_code": "TR",
  "inventory_operator_name": "DEMO_OPERATOR",
  "inventory_service_status": "ACTIVE",
  "inventory_dataset_id": "turkey_inventory_demo",
  "inventory_dataset_version": "1.0.0",
  "inventory_source_type": "DEMO_MOCK",
  "inventory_reason_codes": ["INVENTORY_SCOPE_CONFIRMED"],
  "operational_consistency_status": "CONSISTENT",
  "operational_consistency_flags": ["INVENTORY_SCOPE_CONFIRMED"]
}
```

`tool_execution_summary` içinde `turkey_inventory_tool` ayrı yer alır. Inventory ve consistency alanları LLM'den değil orchestrator/evidence sonuçlarından alınır; safe fallback aynı deterministic değerleri korur. Saklanmış `final-output/2.0` kayıtları okunabilir kalır ve okuma sırasında uydurma Inventory veya consistency gerçeği üretilmez.
---

# 35. SQLite şemaları

İki DB:

```text
data/databases/operational.db
data/databases/event_memory.db
```

## 35.1 Operational DB

### video_contexts

```sql
CREATE TABLE video_contexts (
    video_id TEXT PRIMARY KEY,
    camera_id TEXT NOT NULL,
    context_id TEXT NOT NULL,
    operational_area_id TEXT NOT NULL,
    scenario_id TEXT NOT NULL,
    video_start_time_utc TEXT NOT NULL,
    description TEXT,
    environment TEXT NOT NULL DEFAULT 'DEMO',
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    source_type TEXT NOT NULL DEFAULT 'DEMO_MOCK'
);
```

### permissions

```sql
CREATE TABLE permissions (
    permission_id TEXT PRIMARY KEY,
    platform_id TEXT NOT NULL,
    registration_mark TEXT,
    operator_name TEXT,
    context_id TEXT NOT NULL,
    operational_area_id TEXT,
    scenario_id TEXT,
    flight_purpose TEXT,
    flight_type TEXT,
    valid_from_utc TEXT NOT NULL,
    valid_to_utc TEXT NOT NULL,
    altitude_ft_msl INTEGER,
    departure_aerodrome TEXT,
    arrival_aerodrome TEXT,
    permission_status TEXT NOT NULL,
    issued_at_utc TEXT,
    source_type TEXT NOT NULL DEFAULT 'DEMO_MOCK',
    notes TEXT
);
```

```sql
CREATE INDEX idx_permissions_lookup
ON permissions (
    platform_id,
    context_id,
    valid_from_utc,
    valid_to_utc
);
```

### flight_plans

```sql
CREATE TABLE flight_plans (
    flight_plan_id TEXT PRIMARY KEY,
    platform_id TEXT NOT NULL,
    registration_mark TEXT,
    callsign TEXT,
    context_id TEXT NOT NULL,
    operational_area_id TEXT,
    scenario_id TEXT,
    departure_aerodrome TEXT,
    arrival_aerodrome TEXT,
    planned_departure_utc TEXT NOT NULL,
    planned_arrival_utc TEXT,
    route_or_area TEXT,
    flight_plan_status TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'DEMO_MOCK',
    notes TEXT
);
```

```sql
CREATE INDEX idx_flight_plans_lookup
ON flight_plans (
    platform_id,
    context_id,
    planned_departure_utc
);
```

### notams

```sql
CREATE TABLE notams (
    notam_id TEXT PRIMARY KEY,
    series TEXT,
    notam_number TEXT,
    context_id TEXT,
    operational_area_id TEXT NOT NULL,
    valid_from_utc TEXT NOT NULL,
    valid_to_utc TEXT NOT NULL,
    notam_status TEXT NOT NULL,
    restriction_type TEXT,
    operation_effect TEXT NOT NULL,
    relevance_tags_json TEXT,
    affected_platform_categories_json TEXT,
    affected_platform_ids_json TEXT,
    summary_tr TEXT NOT NULL,
    source_reference TEXT,
    scenario_id TEXT,
    source_type TEXT NOT NULL DEFAULT 'DEMO_MOCK'
);
```

```sql
CREATE INDEX idx_notams_lookup
ON notams (
    operational_area_id,
    valid_from_utc,
    valid_to_utc
);
```

## 35.2 Event Memory DB

### events

```sql
CREATE TABLE events (
    event_id TEXT PRIMARY KEY,
    request_id TEXT UNIQUE NOT NULL,
    event_fingerprint TEXT,
    retry_of_event_id TEXT,
    video_id TEXT,
    camera_id TEXT,
    context_id TEXT,
    track_id TEXT,
    observation_time_utc TEXT,
    event_status TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    completed_at_utc TEXT,
    error_code TEXT,
    error_message TEXT
);
```

Finalized fingerprint için partial unique index uygulama katmanında veya uygun SQLite migration ile korunmalıdır.

### event_steps

```sql
CREATE TABLE event_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL,
    step_name TEXT NOT NULL,
    step_status TEXT NOT NULL,
    payload_json TEXT,
    created_at_utc TEXT NOT NULL,
    FOREIGN KEY(event_id) REFERENCES events(event_id)
);
```

### tool_executions

```sql
CREATE TABLE tool_executions (
    request_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    execution_status TEXT NOT NULL,
    domain_status TEXT,
    request_json TEXT,
    response_json TEXT,
    latency_ms INTEGER,
    error_code TEXT,
    created_at_utc TEXT NOT NULL,
    FOREIGN KEY(event_id) REFERENCES events(event_id)
);
```

### final_outputs

```sql
CREATE TABLE final_outputs (
    event_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    output_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    FOREIGN KEY(event_id) REFERENCES events(event_id)
);
```

### raw_inputs

```sql
CREATE TABLE raw_inputs (
    event_id TEXT PRIMARY KEY,
    sanitized_request_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    FOREIGN KEY(event_id) REFERENCES events(event_id)
);
```

## PRAGMA

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 3000;
```

---

# 36. FastAPI tasarımı

Core logic FastAPI’ye bağımlı olmayacaktır.

## Endpoint’ler

```http
POST /api/v1/events/analyze
```

```http
GET /api/v1/events/{event_id}
```

```http
GET /api/v1/events/{event_id}/trace
```

```http
GET /api/v1/demo/scenarios
```

```http
GET /api/v1/rag/status
```

```http
GET /health
```

## Health bileşenleri

```json
{
  "status": "HEALTHY",
  "components": {
    "operational_db": "HEALTHY",
    "event_memory_db": "HEALTHY",
    "platform_registry": "HEALTHY",
    "rag_index": "HEALTHY",
    "embedding_model": "HEALTHY",
    "ollama": "HEALTHY",
    "decision_model": "AVAILABLE"
  }
}
```

Health endpoint model generate çağrısı yapmamalı; ayrı `deep=true` parametresi verilirse küçük inference testi yapılabilir.

---

# 37. Timeout ve retry

```yaml
timeouts:
  platform_tool_seconds: 0.2
  permission_tool_seconds: 0.5
  notam_tool_seconds: 0.5
  text_rag_seconds: 5.0
  ollama_seconds: 60.0

retries:
  sqlite_transient: 1
  platform_tool: 0
  permission_tool: 1
  notam_tool: 1
  text_rag: 0
  llm_json_repair: 1
```

Windows ve ilk model yüklemesi için warm-up ayrı tutulmalıdır. İlk yükleme latency metriğine karar inference latency olarak eklenmemelidir; `model_load_latency_ms` ayrı ölçülür.

---

# 38. Loglama ve gözlemlenebilirlik

## Her log

```text
timestamp_utc
level
event_id
request_id
module
operation
status
latency_ms
error_code
```

## Loglanmayacak

- crop binary
- model ağırlığı
- gizli environment değerleri
- tam uzun RAG context
- hassas yerel path
- kişisel veri

## Metrikler

- total_event_latency_ms
- model_load_latency_ms
- llm_inference_latency_ms
- context_resolution_latency_ms
- platform_tool_latency_ms
- permission_tool_latency_ms
- notam_tool_latency_ms
- rag_retrieval_latency_ms
- output_guard_latency_ms
- tool_error_rate
- tool_timeout_rate
- rag_call_rate
- rag_no_context_rate
- early_exit_rate
- llm_repair_rate
- safe_fallback_rate
- event_success_rate
- peak_process_ram_mb
- Ollama GPU allocation gözlemi (opsiyonel script)

---

# 39. Demo seed senaryoları

Tüm kayıtlar deterministik ve `DEMO_MOCK` olmalıdır.

| Senaryo | Platform | Permission | Plan | NOTAM | Beklenen |
|---|---|---|---|---|---|
| SCN-01 | EXPECTED | VALID | FILED | NONE | VERIFIED / LOW |
| SCN-02 | EXPECTED | NOT_FOUND | FILED | NONE | UNVERIFIED / MEDIUM |
| SCN-03 | NOT_EXPECTED | NOT_FOUND | NOT_FOUND | NONE | UNVERIFIED / HIGH |
| SCN-04 | EXPECTED | EXPIRED | FILED | NONE | UNVERIFIED / HIGH |
| SCN-05 | EXPECTED | VALID | FILED | RESTRICTS | UNVERIFIED veya PARTIAL / HIGH |
| SCN-06 | UNKNOWN | SKIPPED | SKIPPED | NONE | INDETERMINATE / UNKNOWN veya MEDIUM görsel kuralı |
| SCN-07 | EXPECTED | TOOL_ERROR | UNKNOWN | NONE | INDETERMINATE / UNKNOWN |
| SCN-08 | NON_AIRCRAFT | N/A | N/A | SKIPPED | NOT_APPLICABLE / LOW |
| SCN-09 | EXPECTED | VALID | CANCELLED | NONE | UNVERIFIED / HIGH |
| SCN-10 | CONTEXT_MISSING | SKIPPED | SKIPPED | SKIPPED | INDETERMINATE / UNKNOWN |
| SCN-11 | EXPECTED | VALID | FILED | PROHIBITS | UNVERIFIED / CRITICAL |
| SCN-12 | NOT_EXPECTED | VALID | FILED | NONE | PARTIALLY_VERIFIED / MEDIUM |

---

# 40. Test planı

## Contract

- raw Turkish VLM JSON validation
- raw-to-canonical adapter mapping
- VLM_ONLY safety policy
- generated JSON Schema snapshots
- wrapper backward compatibility

## Unit

- visual adapter mapping
- invalid enum
- missing semantic field
- context time calculation
- timezone validation
- fingerprint
- idempotency
- platform exact alias
- candidate unique resolution
- candidate ambiguity
- permission validity
- expired/revoked/not-yet-valid
- flight plan status
- record consistency
- NOTAM time filter
- NOTAM relevance
- verification precedence
- tool health
- risk rule validation
- risk combination
- evidence quality formula
- RAG policy
- chunk metadata
- FAISS normalized retrieval
- LLM schema parsing
- one repair limit
- allowed decision guard
- source validation
- visual overclaim
- safe fallback

## Integration

- operational DB + repositories
- event DB lifecycle
- platform + permission + NOTAM tools
- RAG index build + retrieval
- Ollama client with stub server
- orchestrator valid flow
- orchestrator tool error
- orchestrator invalid input
- orchestrator idempotency
- output persistence
- FastAPI endpoint

## Scenario

Her SCN-01–SCN-12 ayrı test olmalıdır.

## Kritik guard testleri

1. Permission NOT_FOUND, LLM “izin var” → güvenli summary
2. Minimum risk HIGH, output LOW’a çevrilemez
3. Platform UNKNOWN, kesin kimlik → overclaim violation
4. Source ID retrieval’da yok → source kaldırılır/violation
5. Tanımsız action → reddedilir
6. LLM malformed JSON → bir repair
7. İkinci malformed JSON → safe fallback
8. Tool ERROR ile NOT_FOUND aynı sonucu üretmez
9. NOTAM PROHIBITS → CRITICAL korunur
10. Context missing → UNKNOWN korunur

---

# 41. Bağımlılıklar

`pyproject.toml` için başlangıç aralıkları:

```toml
[project]
requires-python = ">=3.11,<3.12"

dependencies = [
  "fastapi>=0.115,<1",
  "uvicorn[standard]>=0.30,<1",
  "pydantic>=2.10,<3",
  "pydantic-settings>=2.6,<3",
  "aiosqlite>=0.20,<1",
  "httpx>=0.27,<1",
  "PyYAML>=6,<7",
  "numpy>=1.26,<3",
  "faiss-cpu>=1.12,<2",
  "sentence-transformers>=3,<6",
  "transformers>=4.51,<6",
  "torch>=2.5,<3",
  "pypdf>=5,<7",
  "python-docx>=1.1,<2",
  "orjson>=3.10,<4",
  "structlog>=24,<27"
]

[project.optional-dependencies]
dev = [
  "pytest>=8,<10",
  "pytest-asyncio>=0.24,<2",
  "pytest-cov>=5,<8",
  "ruff>=0.8,<1",
  "mypy>=1.13,<2"
]
```

Lock file oluşturulmalıdır. Coding agent dependency çözümü sonunda çalışan tam sürümleri `uv.lock` veya eşdeğer lock dosyasına sabitlemelidir.

---

# 42. Windows kurulum komutları

## Ollama

```powershell
ollama pull qwen3:4b-instruct-2507-q4_K_M
ollama list
```

## Python

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

## Embedding modelini yerelleştirme

Script:

```powershell
python scripts/download_embedding_model.py
```

Runtime env:

```powershell
$env:HF_HUB_OFFLINE="1"
$env:TRANSFORMERS_OFFLINE="1"
```

## DB ve index

```powershell
python scripts/initialize_databases.py
python scripts/seed_demo_data.py
python scripts/validate_documents.py
python scripts/build_text_rag_index.py
```

## Test ve demo

```powershell
pytest -q
python scripts/run_demo_scenarios.py
uvicorn operational_decision.api.main:app --host 127.0.0.1 --port 8000
```

---

# 43. Nihai dosya yapısı

Python için gerçek `src layout` ve tek bir import namespace kullanılacaktır:
`operational_decision`.

```text
project-root/
├── pyproject.toml
├── uv.lock
├── README.md
├── .env.example
├── .gitignore
│
├── config/
│   ├── rag.yaml
│   └── visual_adapter.yaml
│
├── examples/
│   ├── upstream_vlm_payload.json
│   ├── visual_evidence_wrapper.json
│   └── analyze_event_request.json
│
├── data/
│   ├── schemas/
│   │   ├── upstream_vlm_output.schema.json
│   │   ├── final_visual_evidence.schema.json
│   │   └── final_decision_output.schema.json
│   ├── databases/
│   │   ├── operational.db
│   │   └── event_memory.db
│   ├── models/
│   │   └── qwen3-embedding-0.6b/
│   ├── platforms/
│   │   ├── platform_registry.json
│   │   └── platform_aliases.json
│   ├── rules/
│   │   ├── risk_rules.yaml
│   │   └── action_catalog.yaml
│   ├── rag/
│   │   ├── source_documents/
│   │   │   ├── LT_GEN_1_2_en.pdf
│   │   │   ├── SHT-IHA_Rev-05.pdf
│   │   │   ├── LT_GEN_3_1_en.pdf
│   │   │   ├── LT_ENR_1_10_en.pdf
│   │   │   ├── LT_GEN_3_3_en.pdf
│   │   │   └── LT_GEN_1_6_en.pdf
│   │   ├── reference_only/
│   │   │   ├── ucus_izni_talep_formu.docx
│   │   │   └── ucus_izinlerine_iliskin_el_kitabi.pdf
│   │   ├── index/
│   │   │   ├── text.index
│   │   │   ├── chunk_metadata.jsonl
│   │   │   └── index_manifest.json
│   │   └── document_manifest.yaml
│   └── seeds/
│       ├── video_contexts.json
│       ├── permissions.json
│       ├── flight_plans.json
│       ├── notams.json
│       └── demo_scenarios.json
│
├── licenses/
│   ├── MODEL_LICENSES.md
│   ├── THIRD_PARTY_LICENSES.md
│   ├── qwen3-4b-instruct-2507-apache-2.0.txt
│   └── qwen3-embedding-0.6b-apache-2.0.txt
│
├── migrations/
│   ├── operational/
│   │   └── 001_initial.sql
│   └── event_memory/
│       └── 001_initial.sql
│
├── scripts/
│   ├── setup_windows.ps1
│   ├── export_json_schemas.py
│   ├── download_embedding_model.py
│   ├── initialize_databases.py
│   ├── seed_demo_data.py
│   ├── validate_platform_registry.py
│   ├── validate_documents.py
│   ├── build_text_rag_index.py
│   ├── run_demo_scenarios.py
│   ├── benchmark_pipeline.py
│   └── unload_ollama_model.py
│
├── src/
│   └── operational_decision/
│       ├── __init__.py
│       ├── app/
│       │   ├── bootstrap.py
│       │   ├── config.py
│       │   └── lifecycle.py
│       ├── api/
│       │   ├── main.py
│       │   ├── dependencies.py
│       │   ├── error_handlers.py
│       │   ├── routes_events.py
│       │   ├── routes_health.py
│       │   └── schemas.py
│       ├── input/
│       │   ├── raw_vlm_adapter.py
│       │   └── upstream_vlm_adapter.py
│       ├── contracts/
│       │   ├── common.py
│       │   ├── request.py
│       │   ├── upstream_vlm.py
│       │   ├── visual.py
│       │   ├── context.py
│       │   ├── event.py
│       │   ├── tools.py
│       │   ├── platform.py
│       │   ├── permission.py
│       │   ├── notam.py
│       │   ├── verification.py
│       │   ├── risk.py
│       │   ├── rag.py
│       │   ├── llm.py
│       │   └── final_output.py
│       ├── validation/
│       │   └── input_validator.py
│       ├── context/
│       │   ├── context_repository.py
│       │   └── context_resolver.py
│       ├── memory/
│       │   ├── database.py
│       │   ├── event_repository.py
│       │   └── event_service.py
│       ├── platform/
│       │   └── platform_registry.py
│       ├── operational/
│       │   ├── database.py
│       │   ├── permission_repository.py
│       │   ├── flight_plan_repository.py
│       │   └── notam_repository.py
│       ├── tools/
│       │   ├── base.py
│       │   ├── platform_tool.py
│       │   ├── permission_flight_plan_tool.py
│       │   ├── notam_tool.py
│       │   └── text_rag_tool.py
│       ├── rag/
│       │   ├── document_catalog.py
│       │   ├── document_loader.py
│       │   ├── chunker.py
│       │   ├── embedding_provider.py
│       │   ├── faiss_store.py
│       │   ├── index_builder.py
│       │   └── retriever.py
│       ├── decision/
│       │   ├── orchestrator.py
│       │   ├── gpu_handoff.py
│       │   ├── verification_checker.py
│       │   ├── risk_advisor.py
│       │   ├── rag_policy.py
│       │   ├── decision_policy.py
│       │   └── evidence_builder.py
│       ├── llm/
│       │   ├── base_client.py
│       │   ├── ollama_client.py
│       │   ├── prompt_builder.py
│       │   └── response_parser.py
│       ├── finalizer/
│       │   ├── output_guard.py
│       │   └── output_finalizer.py
│       └── observability/
│           ├── logger.py
│           ├── metrics.py
│           └── timers.py
│
├── tests/
│   ├── contracts/
│   │   ├── test_upstream_vlm_contract.py
│   │   ├── test_visual_evidence_contract.py
│   │   └── test_schema_exports.py
│   ├── unit/
│   ├── integration/
│   │   └── test_upstream_vlm_integration.py
│   ├── scenarios/
│   └── fixtures/
│       ├── upstream_vlm/
│       ├── visual_packages/
│       ├── operational_records/
│       ├── rag_queries/
│       └── llm_responses/
│
└── docs/
    ├── LLM_OPERATIONAL_DECISION_SPEC.md
    ├── UPSTREAM_INTEGRATION.md
    ├── CONTRACTS.md
    ├── DATABASE_SCHEMA.md
    ├── DATA_AND_RAG_PROVENANCE.md
    ├── RISK_RULES.md
    ├── INSTALLATION_AND_RUN.md
    ├── DEMO_SCENARIOS.md
    ├── OPEN_DECISIONS.md
    ├── API_USAGE.md
    └── MODEL_AND_GPU_HANDOFF.md
```

## Profesyonel yapı kuralları

1. `src/operational_decision/` gerçek import package'dır.
2. `src` doğrudan Python package adı olarak kullanılmaz.
3. Ham upstream ve canonical contract ayrı dosyalardadır.
4. JSON Schema export'ları Git'e dahil edilir.
5. Model ağırlıkları, DB binary'leri ve FAISS index `.gitignore` içindedir.
6. Seed, migration, schema, manifest ve örnek JSON dosyaları Git'e dahil edilir.
7. API, domain logic ve persistence birbirinden ayrıdır.
8. Testler contract, unit, integration ve scenario olarak ayrılır.
9. Upstream entegrasyon için bağımsız `UPSTREAM_INTEGRATION.md` bulunur.
10. Arkadaşların JSON değişirse yalnızca contract/adapter ve contract testleri değiştirilir.

---

# 44. Uygulama fazları

Coding agent tüm projeyi tek seferde yüzeysel üretmemelidir.

## Faz 0 — Repo analizi

- Mevcut dosyaları incele
- Bu dokümanla gap analysis çıkar
- Kod yazma

## Faz 1 — Contracts

- Enum’lar
- Pydantic modelleri
- JSON örnekleri
- Contract testleri

Kabul: Tüm contract testleri geçer.

## Faz 2 — DB ve memory

- Migration
- Repository
- Event lifecycle
- Idempotency
- Audit invalid input

Kabul: DB integration testleri geçer.

## Faz 3 — Context ve operational tools

- Context Resolver
- Platform Tool
- Permission/Flight Plan Tool
- NOTAM Tool
- Tool envelope

Kabul: SCN-01–SCN-04 temel kayıt testleri geçer.

## Faz 4 — Verification ve Risk

- Precedence
- Reason codes
- YAML risk engine
- Confidence formülleri
- Action catalog

Kabul: Verification/risk scenario testleri geçer.

## Faz 5 — Text RAG

- Manifest
- Extraction
- Chunking
- Local embedding
- FAISS
- Retrieval
- RAG policy

Kabul: Gold query set üzerinde Recall@4 raporu oluşur.

## Faz 6 — LLM ve Guard

- Ollama client
- JSON Schema
- Prompt
- Parser
- Repair
- Allowed decision
- Guard
- Safe fallback

Kabul: Stub ve gerçek Ollama smoke test geçer.

## Faz 7 — Orchestrator ve API

- End-to-end orchestrator
- GPU handoff
- FastAPI
- Health
- Event trace
- Final persistence

Kabul: SCN-01–SCN-12 uçtan uca geçer.

## Faz 8 — Benchmark ve dokümantasyon

- Latency
- RAM
- model load
- RAG quality
- README
- Troubleshooting
- Licenses

---

# 45. Her coding fazının sonunda zorunlu rapor

Coding agent şu formatta cevap vermelidir:

```text
Tamamlanan faz:
Değiştirilen dosyalar:
Eklenen testler:
Çalıştırılan komutlar:
Test sonucu:
Coverage:
Bilinen sınırlamalar:
Açık kararlar:
Bir sonraki faz:
```

Başarısız test varken “tamamlandı” denmemelidir.

---

# 46. Kabul kriterleri

Proje tamamlanmış sayılmak için:

1. Windows’ta kurulabilmeli.
2. Runtime tamamen local olmalı.
3. Ollama tag doğru kullanılmalı.
4. Decision LLM structured JSON üretmeli.
5. Embedding modeli local path’ten CPU’da yüklenmeli.
6. Upstream visual JSON Pydantic ile doğrulanmalı.
7. Adapter semantik veri uydurmamalı.
8. Invalid input audit event oluşturmalı.
9. Context zamanı UTC olarak doğru hesaplanmalı.
10. Idempotency çalışmalı.
11. Platform ve NOTAM uygun durumda paralel çalışmalı.
12. Platform unresolved ise Permission Tool `SKIPPED` olmalı.
13. Tool ERROR ve domain NOT_FOUND ayrılmalı.
14. Permission ve flight plan ayrı statüler olmalı.
15. Uçuş planı izin sayılmamalı.
16. Verification Checker risk üretmemeli.
17. Risk Advisor deterministik olmalı.
18. UNKNOWN otomatik LOW olmamalı.
19. LLM risk seçmemeli.
20. LLM yalnızca allowed decision seçebilmeli.
21. LLM olmayan source ID kullanamamalı.
22. Görsel hipotezi kesin kimlik olarak sunamamalı.
23. Text RAG yalnızca policy ile çağrılmalı.
24. RAG kaynakları sayfa/chunk metadata içermeli.
25. RAG runtime internet kullanmamalı.
26. LLM ikinci geçersiz JSON’da safe fallback üretmeli.
27. Final JSON her durumda Pydantic uyumlu olmalı.
28. Event trace SQLite’dan okunabilmeli.
29. SCN-01–SCN-12 otomatik testleri geçmeli.
30. `pytest`, `ruff` ve `mypy` kritik hata vermemeli.
31. `TODO`, `pass`, sahte fallback bulunmamalı.
32. Model ve dependency lisansları dokümante edilmeli.
33. Batch sonunda Ollama unload edilebilmeli.
34. GPU handoff başarısızken LLM başlatılmamalı.
35. README tek komutlu Windows kurulumunu açıklamalı.
36. Ham VLM `tehdit_seviyesi` Risk Advisor girdisine taşınmamalı.
37. `gidis_yeri` operasyonel karar veya tool sorgusunda kullanılmamalı.
38. Legacy Türkçe VLM JSON contract testiyle doğrulanmalı.
39. Upstream JSON değişikliği yalnızca adapter/contract katmanını etkilemeli.
40. Python import namespace `operational_decision` olmalı.

---

# 47. Coding agent’ın yapmaması gerekenler

- Visual RAG yazma
- VLM yazma
- Fuzzy platform matching ekleme
- Geofence ekleme
- EAD API çağrısı ekleme
- LangChain/LlamaIndex’i zorunlu framework yapma
- Chroma/Qdrant ekleme
- Risk için LLM kullanma
- LLM’e SQL üretme
- LLM’e tool çağırma
- FastAPI içine business logic koyma
- RAG chunk’larını risk hesabına sokma
- Kaynak metnini doğrulamadan hukuk/mevzuat sonucu üretme
- Model adı veya quantization değiştirme
- Embedding modelini Ollama üzerinden servis etme
- GPU FAISS kullanma
- Reranker ekleme
- OCR ekleme
- Cloud telemetry ekleme
- Mock kayıtları gerçek veri gibi isimlendirme
- Gizli fallback ile sahte `SUCCESS` üretme

---

# 48. Resmî teknik referanslar

Bu kaynaklar model ve altyapı kararlarının doğrulanması için tutulmalıdır:

- Ollama Windows: `https://docs.ollama.com/windows`
- Ollama Chat API / JSON Schema: `https://docs.ollama.com/api/chat`
- Ollama Generate API / keep_alive: `https://docs.ollama.com/api/generate`
- Ollama model tag: `https://ollama.com/library/qwen3:4b-instruct-2507-q4_K_M`
- Qwen3-4B-Instruct-2507: `https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507`
- Qwen3-Embedding-0.6B: `https://huggingface.co/Qwen/Qwen3-Embedding-0.6B`
- FAISS install: `https://github.com/facebookresearch/faiss/blob/main/INSTALL.md`
- FAISS docs: `https://faiss.ai/`

---

# 49. Son mimari kararı

Bu projenin V1 sürümü:

```text
Windows + 8 GB NVIDIA GPU
  ↓
Upstream VLM tamamlanır ve GPU’yu bırakır
  ↓
Canonical Final Visual Evidence JSON
  ↓
Pydantic + Context + Event Memory
  ↓
Deterministik Tools + Verification + Risk
  ↓
Koşullu Qwen3-Embedding-0.6B + FAISS Text RAG
  ↓
Ollama üzerinde Qwen3-4B-Instruct-2507 Q4_K_M
  ↓
JSON Schema + Output Guard
  ↓
Final Türkçe rapor + JSON + SQLite trace
```

Bu karar seti coding agent tarafından değiştirilmeden uygulanacaktır.

---

# 47. Türkiye Inventory V1 — bağlayıcı teknik kararlar

Bu bölüm Türkiye Inventory V1 için bağlayıcıdır. Belgenin önceki bölümlerinde Platform, Permission/Flight Plan, NOTAM, Verification, evidence veya final-output akışıyla çelişen bir hüküm varsa bu bölüm önceliklidir.

## 47.1 Kapsam ve veri sahipliği

1. Türkiye Inventory, Platform Registry'den ayrı bir JSON registry'dir.
2. Registry strict doğrulanır; bilinmeyen alan, tip coercion ve bilinmeyen enum değeri reddedilir.
3. Registry açık `schema_version` ve veri `registry_version` alanlarıyla versioned tutulur.
4. V1 verisinin tamamı sentetiktir ve hem registry hem kayıt provenance'ı `DEMO_MOCK` olarak işaretlenir.
5. Platform Registry tanınabilir yerli ve yabancı platform modellerini ve alias'larını tutar. Bir platformun Platform Registry'de bulunması Türkiye envanterinde bulunduğu anlamına gelmez.
6. Inventory yalnız Türkiye envanteri kapsamındaki platform kimliklerini tutar; yabancı platform kataloğu veya genel platform tanıma sözlüğü olarak kullanılmaz.
7. Inventory lookup yalnız Platform Tool tarafından kesin olarak çözülen `platform_id` ile yapılır. Görsel hipotez, model adı, alias, ülke tahmini, serbest metin veya LLM çıktısı Inventory sorgu anahtarı olamaz.

## 47.2 Inventory sözleşmesi

Canonical `InventoryStatus` değerleri yalnız şunlardır:

```text
CONFIRMED
NOT_LISTED
UNKNOWN
NOT_APPLICABLE
```

Anlamları:

- `CONFIRMED`: Çözülen `platform_id`, aktif Inventory registry sürümünde açıkça listelenmiştir.
- `NOT_LISTED`: Çözülen `platform_id`, kullanılan registry sürümünde listelenmemiştir.
- `UNKNOWN`: Lookup güvenilir biçimde tamamlanamamış veya Inventory gerçeği belirlenememiştir.
- `NOT_APPLICABLE`: Inventory değerlendirmesi olay türü için uygulanabilir değildir; örneğin güçlü non-aircraft erken çıkışı.

`NOT_LISTED`; düşman, yabancı, ajan, taklit, tehdit veya izinsiz operasyon anlamına gelmez. Yalnız kullanılan Türkiye Inventory registry sürümünün kapsam ifadesidir.

## 47.3 Bağlayıcı orchestration ve operational eligibility sırası

Event Memory ve idempotency sırası değişmez. Mevcut event fingerprint girdileri ve hesaplama algoritması değişmez; Inventory alanı fingerprint'e eklenmez.

Operational araç sırası:

```text
Canonical JSON veya Raw VLM Adapter
↓
Schema Validation
↓
Event Memory / Idempotency
↓
Operational Context Resolver
↓
Platform Registry
↓
Turkey Inventory
↓
Operational Eligibility
├── Platform unresolved / context incomplete
│   └── Permission, Flight Plan, NOTAM: SKIPPED
└── Eligible
    ├── Permission + Flight Plan
    └── NOTAM
↓
Operational Consistency
↓
Verification
↓
Risk
↓
Conditional RAG
↓
Decision
↓
Output Guard
↓
Finalizer
↓
Final JSON + Türkçe Rapor
```

Kurallar:

1. Operational eligibility için platform resolved, Context `COMPLETE`, operational area, scenario ve geçerli observation interval gerekir.
2. Eligible durumda Permission/Flight Plan ile NOTAM, Inventory `CONFIRMED`, `NOT_LISTED`, `UNKNOWN` veya Inventory Tool `ERROR` olsa da çalışabilir. Inventory sonucu downstream çağrıyı tek başına kapatmaz.
3. Platform unresolved, strong `NON_AIRCRAFT`, incomplete context veya gerekli zaman/bölge bilgisinin eksikliği durumunda ilgili downstream araçlar `SKIPPED` olur; `data=null` korunur ve domain sonucu uydurulmaz.
4. Inventory `CONFIRMED` yalnız kullanılan DEMO_MOCK veri setindeki kaydı gösterir; otomatik izin değildir. `NOT_LISTED` otomatik izinsizlik veya kapsam dışı operasyon değildir.
5. Inventory sonucu Operational Consistency, Verification, Risk ve final çıktıya bağımsız evidence olarak taşınır.
6. Operational Consistency Checker, tool sonuçları tamamlandıktan sonra ve Verification'dan önce çalışır. Verification ve Risk yalnız consistency ile zenginleştirilmiş deterministik gerçekleri tüketir.

## 47.4 NOT_LISTED değerlendirme davranışı

Inventory `NOT_LISTED` tek başına Verification, Risk, Decision veya human-review sonucu belirlemez. Gerçek Permission, Flight Plan, NOTAM, platform expectation ve tool-health sonuçları normal deterministic politikalarla değerlendirilir. Bu nedenle `NOT_LISTED + VALID + FILED + NO_EFFECT + EXPECTED`, `VERIFIED / LOW / AUTHORIZED_OPERATIONAL_MATCH / human_review=false` üretebilir; eksik Permission ve Flight Plan ise `UNVERIFIED / MEDIUM / UNVERIFIED_AIRCRAFT / human_review=true` üretebilir.

`REJECTED_OUT_OF_SCOPE` geriye dönük contract uyumluluğu için desteklenen bir `DecisionCode` üyesidir; güncel runtime'da yalnız Inventory `NOT_LISTED` olmasından türetilmez. `EventStatus` değildir.

## 47.5 RAG ve LLM sınırı

1. Inventory gerçeği yalnız versioned registry lookup sonucudur; RAG veya LLM tarafından üretilemez, tamamlanamaz ya da değiştirilemez.
2. LLM; Inventory, Verification veya Risk alanlarının canonical değerini seçemez veya override edemez.
3. RAG çağrısı Inventory statusundan değil Permission, Flight Plan, NOTAM, Verification ve Risk için mevcut query policy'den belirlenir. İzinli `NOT_LISTED` operasyonunda RAG atlanabilir; Permission `NOT_FOUND` durumunda mevcut template ile çağrılabilir.
4. Böyle bir açıklama `NOT_LISTED` sonucuna düşmanlık, yabancılık, ajanlık, taklit, tehdit veya izinsizlik anlamı yükleyemez.
5. Output Guard ve Finalizer, Inventory sonucunu korurken Decision Policy ve Risk Advisor'ın gerçek Verification/Risk/Decision/human-review sonuçlarını da Inventory kaynaklı bir override uygulamadan korur.

## 47.6 Schema sürümü ve geriye dönük okuma

1. Yeni `LLMEvidencePackage` schema sürümü `llm-evidence/2.1` olacaktır.
2. Yeni `FinalDecisionOutput` schema sürümü `final-output/2.1` olacaktır.
3. Yeni üretilen kayıtlar 2.1 olarak yazılır.
4. Daha önce saklanmış `final-output/2.0` kayıtları geriye dönük okunabilir kalır; okuma katmanı 2.0 kayıtlarını reddetmez.
5. 2.0 kayıtların geriye dönük okunması, saklanan kaydı sessizce yeniden yazmak veya var olmayan Inventory gerçeği üretmek anlamına gelmez.
---

# 50. Operasyonel Sınırlılıklar ve Güvenlik

- Sistem gerçek operasyonel otorite, SHGM, DHMİ, AIS, FIC, ATS veya ATC yerine geçmez.
- Operational tool ve Inventory kayıtları `DEMO_MOCK`'tur; gerçek operational kayıt olarak kullanılamaz.
- Inventory `CONFIRMED`, platformun dataset kapsamında listelendiğini gösterir; uçuş izni anlamına gelmez.
- Inventory `NOT_LISTED`, yalnız platformun mevcut Türkiye Inventory veri setinde bulunmadığını gösterir. Düşman, yabancı, ajan, taklit, sahte, izinsiz veya tehdit anlamına gelmez.
- Platform Registry eşleşmesi Türkiye Inventory onayı değildir.
- RAG ve LLM Inventory gerçeği üretmez, doğrulamaz veya değiştirmez. RAG yalnız kaynak bağlamı getirir; verification, risk ve decision sonucunu değiştirmez.
- `SKIPPED` Permission, Flight Plan veya NOTAM sonucu bir domain sonucu değildir; `NOT_FOUND`, izinli, yasaklı veya benzeri bir sonuç uydurulamaz.
- Uçuş planı izin değildir.
- Görsel hipotez kesin platform kimliği değildir. Upstream contract'ta visual affiliation alanı bulunmadıkça `VISUAL_AFFILIATION_INVENTORY_MISMATCH` veya aidiyet iddiası üretilmez.
- Geofence V1 kapsamı dışındadır.
- Visual pipeline bu repoda geliştirilmez; upstream kanıtın doğruluğu ayrıca güvence altına alınmalıdır.
- Fuzzy platform matching yoktur; yalnız exact alias ve unique candidate resolution kullanılır.
- NOTAM relevance metadata tabanlıdır; canlı NOTAM servisi bağlantısı yoktur.
- PDF/DOCX kaynaklar runtime operational kayıt değildir.
- Runtime internet, cloud LLM ve otomatik model indirme yoktur; local decision modeli yalnız bounded evidence ve izin verilen constraints ile çalışır.
- LLM Inventory, consistency, verification, risk veya deterministic decision sonucunu değiştiremez ve yeni consistency flag üretemez.
- Output Guard; tool/evidence çelişkisi, Inventory overclaim, skipped-tool uydurması, kaynak uydurması ve izin verilmeyen karar/aksiyonları deterministic olarak engeller. Geçersiz LLM çıktısında güvenli fallback kullanılır.
- Inventory `NOT_LISTED` tek başına human review zorlamaz. Inventory `UNKNOWN`/tool failure, consistency `INDETERMINATE`, tool health failure ve policy tarafından işaretlenen diğer durumlarda güvenli human-review davranışı korunur.
- Platform origin ve taxonomy yalnız Registry metadata'sıdır; Risk veya Decision girdisi değildir.
- İnsan onayı gerektiren sonuçlar otomatik operational talimata dönüştürülemez.

`UNKNOWN` risk hiçbir zaman `LOW` seviyesine indirilmez. `CRITICAL` sonuç operator review ve yetkili birime escalation gerektirir.
