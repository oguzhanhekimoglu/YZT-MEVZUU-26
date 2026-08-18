# Veri ve RAG Provenance

Bu belge operational seed, Türkiye Inventory veri seti ve Text RAG kaynaklarının provenance sınırlarını tek yerde tanımlar.

## Operational seed kayıtları

`data/seeds/permissions.json`, `flight_plans.json`, `notams.json` ve `video_contexts.json` içindeki tool kayıtları `DEMO_MOCK`'tur. Yalnız senaryo ve yazılım doğrulaması için kullanılır; gerçek operasyonel kayıt değildir.

Permission ve flight plan ayrı domain status ve provenance ile değerlendirilir. Uçuş planı izin değildir. NOTAM relevance yalnız metadata ile belirlenir.

## Türkiye Inventory veri seti

Türkiye Inventory, Platform Registry'den ayrı, strict ve versioned bir JSON registry'dir. Yalnız Türkiye envanteri kapsamını taşır; bütün V1 demo kayıtlarında `source_type=DEMO_MOCK` olur. Dataset ID, dataset version ve timezone-aware effective timestamp yükleme ve lookup sonuçlarında korunur.

Inventory gerçeği Platform Registry, RAG veya LLM tarafından üretilmez. Platform Registry yerli ve yabancı tanınabilir modelleri tutar; platform eşleşmesi Türkiye Inventory onayı değildir. Inventory lookup yalnız çözülen `platform_id` ile yapılır.

Inventory sonucu yalnız kesin askerî gate koşulunda downstream çağrıları etkiler: Registry `usage_domain=MILITARY`, Inventory execution `SUCCESS` ve status `NOT_LISTED` ise Permission, Flight Plan ve NOTAM `UNREGISTERED_MILITARY_POLICY` nedeniyle policy `SKIPPED` olur. CIVIL, DUAL_USE, UNKNOWN, Inventory error/timeout/unknown ve `CONFIRMED` dallarında mevcut normal davranış korunur. Platform origin yalnız Registry metadata alanıdır; kullanım alanı ise bu kesin gate dışında otomatik aidiyet, tehdit veya hukuki hüküm üretmez.

## Document manifest

Canonical belge kataloğu `data/rag/document_manifest.yaml` dosyasıdır. Her belge için authority, kullanım rolü, revision/effective date ve gerçek SHA-256 tutulur. Manifest doğrulaması dosya varlığını, checksum değerlerini, metadata'yı ve runtime/reference-only ayrımını korur.

SHT-İHA kaydında resmi yayın etiketi `Rev-05`, belge içi değişiklik numarası `04` ve değişiklik tarihi `2020-07-12` ayrı metadata alanlarıdır.

## RUNTIME_RAG ve REFERENCE_ONLY

Runtime RAG belgeleri:

- `LT_GEN_1_2`
- `SHT_IHA_REV_05`
- `LT_GEN_3_1`
- `LT_ENR_1_10`
- `LT_GEN_3_3`
- `LT_GEN_1_6`

Reference-only belgeler:

- `LT_ENR_5_1`
- `LT_ENR_5_3`
- `UCUS_IZINLERINE_ILISKIN_EL_KITABI`
- `UCUS_IZNI_TALEP_FORMU`

Altı `runtime_rag=true` belge indekslenir. Dört `runtime_rag=false` belge reference-only kalır ve hiçbir koşulda FAISS indeksine alınmaz. PDF/DOCX belgeler runtime operational kayıt değildir; yalnız kontrollü metin bağlamı sağlar.

## FAISS index ve embedding modeli

Text RAG, tek global normalize `IndexFlatIP` index kullanır. Embedding modeli repodaki yerel, 1024 boyutlu Qwen modelidir. Retrieval metadata-first filtre, `candidate_top_k=8`, `final_top_k=4` ve belge başına en fazla iki chunk ile çalışır. Similarity threshold yoktur. Sağlıklı index ve geçerli filtre sonrasında aday yoksa `NO_RELEVANT_CONTEXT` üretilir.

Index manifesti document manifest ve kaynak checksum'larıyla uyumlu olmalıdır. Final 48-query benchmark metrikleri `data/rag/index/final_benchmark_report.json` dosyasındadır.

## Yetki ve karar sınırı

RAG yalnız permission, flight plan, NOTAM ve genel mevzuat açıklaması sağlar. Türkiye Inventory status değerini belgelerden doğrulamaz, üretmez veya değiştirmez. Retrieval sonucu verification, risk veya decision sonucunu değiştirmez. Inventory `NOT_LISTED` için sahte Inventory query template oluşturulmaz.
