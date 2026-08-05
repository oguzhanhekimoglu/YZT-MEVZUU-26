# Demo Senaryoları

SCN-01–SCN-23, `data/seeds/demo_scenarios.json` içindeki deterministik kabul kataloğudur. İlişkili operational tool kayıtlarının tamamı `DEMO_MOCK`'tur; gerçek izin, uçuş planı veya NOTAM değildir.

`GET /api/v1/demo/scenarios` her kayıt için `scenario_id`, `name`, `description`, `expected_verification_status`, `expected_risk_level`, `source_type` ve canonical `AnalyzeEventRequest` uyumlu `request_payload` döndürür. Payload frontend tarafından üretilmez; seed katalog metadatası ile `examples/analyze_event_request.json` tabanından deterministik oluşturulur.

| Senaryo | Verification | Risk |
|---|---|---|
| SCN-01 | VERIFIED | LOW |
| SCN-02 | UNVERIFIED | MEDIUM |
| SCN-03 | UNVERIFIED | HIGH |
| SCN-04 | UNVERIFIED | HIGH |
| SCN-05 | UNVERIFIED | HIGH |
| SCN-06 | INDETERMINATE | UNKNOWN |
| SCN-07 | INDETERMINATE | UNKNOWN |
| SCN-08 | NOT_APPLICABLE | LOW |
| SCN-09 | UNVERIFIED | HIGH |
| SCN-10 | INDETERMINATE | UNKNOWN |
| SCN-11 | UNVERIFIED | CRITICAL |
| SCN-12 | PARTIALLY_VERIFIED | MEDIUM |
| SCN-13 | VERIFIED | LOW |
| SCN-14 | VERIFIED | LOW |
| SCN-15 | UNVERIFIED | MEDIUM |
| SCN-16 | UNVERIFIED | HIGH |
| SCN-17 | UNVERIFIED | HIGH |
| SCN-18 | UNVERIFIED | HIGH |
| SCN-19 | UNVERIFIED | HIGH |
| SCN-20 | UNVERIFIED | HIGH |
| SCN-21 | UNVERIFIED | CRITICAL |
| SCN-22 | UNVERIFIED | HIGH |
| SCN-23 | UNVERIFIED | HIGH |

SCN-13, `Boeing 747` exact aliasını `PLT_BOEING_747` olarak çözer. Platform DEMO_MOCK Turkey Inventory veri setine bilerek eklenmemiştir ve Inventory `NOT_LISTED` kalır. Operational eligibility sağlandığı için Permission `VALID`, Flight Plan `FILED` ve NOTAM `NONE_ACTIVE / NO_EFFECT` gerçekten değerlendirilir; sonuç consistency `CONSISTENT`, Verification `VERIFIED`, Risk `LOW`, karar `AUTHORIZED_OPERATIONAL_MATCH`, human review `false` ve RAG `SKIPPED` olur. Bu sonuç Boeing 747'nin Türkiye Inventory içinde olduğunu, yabancı bir operatöre ait olduğunu veya tehdit olup olmadığını iddia etmez.

SCN-14, kullanıcıya dönük etikette **Bayraktar TB2 SİHA** olarak sunulur. `Bayraktar TB2` exact aliası `PLT_BAYRAKTAR_TB2` kaydına çözülür; DEMO_MOCK Turkey Inventory sonucu `CONFIRMED`, Permission `VALID`, Flight Plan `FILED`, NOTAM `NONE_ACTIVE / NO_EFFECT`, Verification `VERIFIED`, Risk `LOW` ve karar `AUTHORIZED_OPERATIONAL_MATCH` olur. Bu demo kaydı gerçek sahiplik, güncel operatör aidiyeti veya gerçek uçuş izni kanıtı değildir; `DOMESTIC_ORIGIN / TR` yalnız model ve üretici metadata'sıdır.

SCN-15, kullanıcıya dönük etikette **Bayraktar AKINCI Ağır sınıf SİHA** olarak sunulur. Platform ve DEMO_MOCK Turkey Inventory kayıtları doğrulanır; Flight Plan `FILED` iken Permission `NOT_FOUND`, NOTAM `NONE_ACTIVE / NO_EFFECT`, Verification `UNVERIFIED`, Risk `MEDIUM` ve karar `UNVERIFIED_AIRCRAFT` olur. Mevcut `FLIGHT_PLAN_WITHOUT_PERMISSION` RAG template'i çağrılır. Bu kontrollü demo kaydı gerçek sahiplik, güncel operatör aidiyeti, tehdit veya kesin izinsizlik kanıtı değildir; `DOMESTIC_ORIGIN / TR` yalnız model ve üretici metadata'sıdır.

SCN-16, kullanıcıya dönük etikette **TUSAŞ ANKA Orta irtifa uzun havada kalışlı İHA** olarak sunulur. Platform ve DEMO_MOCK Turkey Inventory kayıtları doğrulanır; Permission `VALID` ve Flight Plan `FILED` olmasına rağmen aktif NOTAM `RESTRICTS_OPERATION` etkisi üretir. Sonuç Verification `UNVERIFIED`, Risk `HIGH`, karar `UNVERIFIED_AIRCRAFT` ve consistency `FLAGGED` olur. Mevcut `ACTIVE_NOTAM` RAG template'i çağrılır. NOTAM platform aidiyeti, model menşei gerçek operatör veya kesin tehdit kanıtı değildir.

SCN-17, kullanıcıya dönük etikette **F-35A Lightning II savaş uçağı** olarak sunulur. Registry exact alias çözümü başarılı, Inventory `NOT_LISTED`, askerî platform politikası gereği downstream araçlar `UNREGISTERED_MILITARY_POLICY` sebebiyle SKIPPED olur. Sonuç Verification `UNVERIFIED`, Risk `HIGH`, karar `UNREGISTERED_MILITARY_AIRCRAFT`, human review `true` (URGENT) ve `UNREGISTERED_MILITARY_AIRSPACE_CONTEXT` RAG template'i ile RAG `CALLED` olur. Registry'deki `FOREIGN_ORIGIN / US` yalnız model ve üretici metadata'sıdır; yabancı operatör, aidiyet, düşmanlık veya kesin tehdit kanıtı değildir.

SCN-18, kullanıcıya dönük etikette **MQ-9 Reaper Orta irtifa uzun havada kalışlı SİHA** olarak sunulur. `examples/raw_vlm_mq9_reaper.json` girdisi gerçek ham VLM adapter üzerinden canonical isteğe dönüştürülür; `hedef_modeli=MQ-9 Reaper` exact Registry çözümünde kullanılır. Inventory `NOT_LISTED` askerî platform politikası gereği downstream araçlar `UNREGISTERED_MILITARY_POLICY` sebebiyle SKIPPED olur. Sonuç Verification `UNVERIFIED`, Risk `HIGH`, karar `UNREGISTERED_MILITARY_AIRCRAFT`, human review `true` (URGENT) ve RAG `CALLED` olur. Ham VLM içindeki `tehdit_seviyesi=dusuk` yalnız audit metadata'sıdır; `ulke_orjini=Bilinmiyor` Inventory, Risk, Decision, gerçek aidiyet veya operatör kanıtı değildir.

SCN-19 ve SCN-20 geçersiz veya süresi dolmuş izin için `EXPIRED_OR_INVALID_PERMISSION`; SCN-21 aktif yasaklayıcı NOTAM için `ACTIVE_NOTAM_PROHIBITION`; SCN-22 izin-NOTAM çelişkisi için `CONFLICTING_OPERATIONAL_RECORDS`; SCN-23 kısıtlayıcı bakım NOTAMı için mevcut deterministic karar politikasını kullanır. LLM bu verification, risk ve karar sonuçlarını değiştirmez.

Çalıştırma:

```powershell
.venv\Scripts\python.exe scripts\run_demo_scenarios.py
```

Senaryolar gerçek context resolver, operational tools, verification, risk, orchestrator, guard, finalizer ve SQLite persistence akışını kullanır; LLM tarafı deterministik test stub'ıdır. SCN-08 strong non-aircraft early exit nedeniyle RAG ve LLM çağırmaz.
