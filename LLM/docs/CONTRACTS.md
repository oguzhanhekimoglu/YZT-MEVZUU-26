# Veri ve Tool Sözleşmeleri

Canonical strict Pydantic sözleşmeleri `src/operational_decision/contracts/` altındadır. Bütün sözleşmeler mevcut `StrictContract` altyapısını kullanır; bilinmeyen alanlar reddedilir. Execution durumu ile domain sonucu birbirine karıştırılmaz: örneğin başarılı bir sorgu `execution_status=SUCCESS` ile domain düzeyinde `NOT_FOUND` veya `NOT_LISTED` döndürebilir.

## Ana veri sözleşmeleri

- `upstream-vlm/1.0`: upstream model çıktısı.
- `visual-evidence/1.1`: canonical görsel kanıt paketi.
- `llm-evidence/2.1`: LLM'ye verilen bounded ve deterministic evidence.
- `final-output/2.1`: yeni üretilen, persist edilen ve API'den dönen canonical final sonuç.
- `final-output/2.0`: yalnız geriye dönük okuma için desteklenen eski final kayıt sürümü.

Yeni final kayıtlar `2.1` yazılır. `2.0` kayıtların okunabilirliği korunur; eski `2.0` örnekleri canonical `2.1` örneği olarak yorumlanmaz.

## ToolResponseEnvelope

Bütün tool'lar ortak `ToolResponseEnvelope` kullanır. Envelope; tool kimliği ve sürümü, event/request kimlikleri, `execution_status`, timezone-aware başlangıç ve bitiş zamanları, latency, typed domain verisi, warnings, kontrollü error ve source references alanlarını ayrı taşır.

`SUCCESS`, `SKIPPED`, `ERROR`, `TIMEOUT` ve `INVALID_INPUT` altyapı yürütme sonucudur. Platform, Inventory, permission, flight-plan ve NOTAM domain status değerlerinin yerine geçmez. SQLite transient hata için en fazla bir retry uygulanır; timeout, invalid input ve kontrollü tool hataları sahte success üretmez.

## Operational tool sözleşmeleri

- Platform Tool: exact alias veya unique candidate çözümlemesi yapar; fuzzy matching yoktur. Platform Registry tanınabilir yerli ve yabancı modelleri kapsar.
- Permission & Flight Plan Tool: resolved platform, `ContextStatus.COMPLETE` ve gerekli context kimlikleri/zaman aralığı bulunduğunda çalışır. Inventory sonucu eligibility önkoşulu değildir. Uçuş planı izin değildir.
- NOTAM Tool: resolved platform, complete context, operational area, scenario ve observation interval bulunduğunda Inventory sonucundan bağımsız çalışır. Relevance metadata tabanlı, strongest-effect precedence deterministiktir.
- Text RAG Tool: yalnız runtime allowlist üzerinde retrieval yapar; Inventory, verification, risk veya decision üretmez ve değiştirmez.

## Türkiye Inventory V1

Inventory, Platform Registry'den ayrı, strict, versioned ve yalnız Türkiye kapsamını taşıyan `DEMO_MOCK` bir JSON veri setidir. Lookup yalnız çözülen `platform_id` ile yapılır; alias veya fuzzy matching uygulanmaz.

`TurkeyInventoryRecord` alanları:

- `inventory_record_id`
- `platform_id`
- `country_code`
- `operator_name`
- `service_status`
- `active`
- `source_type`

`TurkeyInventoryDataset` alanları:

- `schema_version`
- `dataset_id`
- `dataset_version`
- timezone-aware `effective_at_utc`
- `source_type`
- `records`

`TurkeyInventoryToolRequest`, çözülen `platform_id` ile Platform Tool execution/domain status değerlerini taşır. `TurkeyInventoryResult`; `inventory_status`, `platform_id`, opsiyonel kayıt ve dataset metadata'sı, `reason_codes`, `safe_message` ve `warnings` alanlarını taşır.

Canonical Inventory status değerleri `CONFIRMED`, `NOT_LISTED`, `UNKNOWN` ve `NOT_APPLICABLE` değerleridir. `NOT_LISTED` teknik hata değildir ve düşman, yabancı, ajan, taklit, sahte, izinsiz veya tehdit anlamına gelmez. Inventory `CONFIRMED` uçuş izni anlamına gelmez.

Inventory sonucu bağımsız evidence olarak Verification, Risk ve final çıktıya taşınır. `NOT_LISTED`, Permission/Flight Plan veya NOTAM çağrılarını kapatmaz ve tek başına verification, risk, decision ya da human-review sonucu belirlemez. Platform unresolved, strong `NON_AIRCRAFT`, incomplete context veya gerekli zaman/bölge bilgisinin eksikliği güvenli `SKIPPED` sonucunu korur; `SKIPPED` tool verisi `null` kalır ve domain sonucu uydurulmaz.

## Operational Consistency

`OperationalConsistencyInput`; context, platform, Inventory, permission/flight-plan, NOTAM, visual evidence ve bunların execution status değerlerini deterministic checker'a verir.

`OperationalConsistencyResult` alanları:

- `status`
- `flags`
- `reason_codes`
- `evidence_references`
- `human_review_required`

Status değerleri `CONSISTENT`, `FLAGGED`, `INDETERMINATE` ve `NOT_APPLICABLE` değerleridir. Flag'ler deterministic sırada ve tekrarsızdır. Her flag için tam bir reason code ve evidence reference bulunur; üç listenin uzunluğu eşittir. Checker sonucu LLM tarafından üretilmez veya değiştirilmez.

## LLMEvidencePackage 2.1

`LLMEvidencePackage`, deterministic katmanların compact sonucunu taşır. Inventory için status, record ID, country code, operator name, service status, dataset ID/version/source type ve reason code'lar; consistency için status ve flag'ler pakete eklenir. Ham Inventory registry satırı LLM'ye verilmez.

LLM; Inventory, verification, risk veya consistency sonucunu değiştiremez, yeni consistency flag üretemez ve kimlik/sürüm/source değeri uyduramaz.

## FinalDecisionOutput 2.1

Final çıktı aynı compact Inventory ve Operational Consistency alanlarını taşır; `tool_summary` içinde `turkey_inventory_tool` ayrı görünür. Bu alanlar LLM cevabından değil orchestrator/evidence sonuçlarından alınır. Safe fallback de aynı deterministic değerleri korur.

Finalizer, Inventory `NOT_LISTED` için karar veya human-review sonucu zorlamaz. Decision Policy ve Risk Advisor'ın Permission, Flight Plan, NOTAM, Verification ve platform expectation üzerinden ürettiği sonuç korunur. `REJECTED_OUT_OF_SCOPE` geriye dönük contract uyumluluğu için desteklenen bir `DecisionCode` değeridir; güncel runtime'da yalnız `NOT_LISTED` olmasından türetilmez ve `EventStatus` değildir.

## JSON Schema yolları

Export edilen canonical JSON Schema dosyaları:

- `data/schemas/upstream_vlm_output.schema.json`
- `data/schemas/final_visual_evidence.schema.json`
- `data/schemas/final_decision_output.schema.json`

Pydantic kaynakları schema exportlarının canonical tanımıdır. Inventory ve consistency sözleşmeleri `src/operational_decision/contracts/inventory.py` ve `src/operational_decision/contracts/operational_consistency.py` dosyalarındadır.
