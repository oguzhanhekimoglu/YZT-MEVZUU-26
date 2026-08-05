# Yerel Video Tabanlı Operasyonel Karar Destek Sistemi

TEKNOFEST 3. Senaryo için geliştirilen bu proje; ham VLM çıktısını yerel veri kaynakları, deterministik operasyon politikaları ve kontrollü bir yerel LLM açıklama katmanıyla birleştirir. Sistem karar desteği sağlar; otonom karar veya silah sistemi değildir.

## Güncel kapsam

| Bileşen | Durum |
|---|---:|
| Platform Registry | 98 toplam / 97 aktif gerçek platform |
| Master allowlist | 97 canonical platform |
| Exact alias | 489 |
| DEMO Turkey Inventory | 22 kayıt |
| DEMO video context | 111 kayıt |
| DEMO Permission / Flight Plan / NOTAM | 51 / 53 / 12 kayıt (6 canonical + 6 davranış fixture) |
| DEMO raw VLM route | 94 platform route |
| Kabul senaryoları | SCN-01–SCN-23 |
| Çalışma biçimi | Yerel: FastAPI, Streamlit, SQLite, FAISS ve Ollama |

## Mimari akış

```text
Ham VLM JSON / Hazır Demo / Streamlit
→ FastAPI
→ Canonical Validation
→ Operational Context Resolver
→ Decision Orchestrator
→ Platform Registry
→ Turkey Inventory
→ Permission + Flight Plan
→ NOTAM
→ Operational Consistency
→ Operational Verification
→ Risk Advisor
→ Koşullu Text RAG
→ Evidence Package
→ Local LLM Decision Agent
→ LLM Output Guard
→ Output Finalizer
→ Canonical JSON + TEKNOFEST UI
```

### Sorumluluk sınırları

- Platform Registry kimlik, alias ve taxonomy bilgisinin canonical kaynağıdır.
- Tool katmanı yalnız veri, execution durumu ve kanıt sağlar; karar üretmez.
- Consistency ve Verification, operasyonel kayıtların kullanılabilirliğini ve uyumunu deterministik olarak değerlendirir.
- Risk Advisor risk seviyesini, gerekçeleri ve insan inceleme gereksinimini policy kurallarından üretir.
- Decision Policy canonical kararı belirler.
- Text RAG yalnız gerekli dallarda açıklayıcı mevzuat bağlamı sağlar; risk veya kararı değiştirmez.
- Yerel LLM yalnız doğrulanmış evidence paketini Türkçe özet, açıklama ve aksiyon metnine dönüştürür.
- Guard ve Finalizer; verification, risk, decision, human-review ve policy/reason kodlarını LLM sonucundan bağımsız korur.
- UI kısa operasyonel sonucu öne çıkarır; Registry, tool, RAG, guard ve tam JSON ayrıntılarını açılabilir bölümde tutar.

Permission/Flight Plan ile NOTAM, gate uygulanmayan dallarda paralel çalışır. RAG çağrısı mevcut deterministic query policy tarafından koşullu olarak belirlenir.

## Çalışma modları

| Özellik | DEMO | PRODUCTION |
|---|---|---|
| DEMO_MOCK Inventory ve operational seedler | Kullanılır | Yüklenmez |
| `raw_vlm_context_routes` | Kullanılabilir | Kullanılmaz |
| Demo scenario endpoint'i | Açık | `404 DEMO_ENDPOINT_DISABLED` |
| Developer / Demo UI | Görünür | Gizli |
| Operational ve event DB | Yerel demo yolları | Ayrı ve açıkça yapılandırılmış yollar zorunlu |
| Video/track/context | Demo paketi veya route | Upstream sistemden gerçek değerler |
| Timestamp ve visual confidence | Demo fixture sağlayabilir | Uydurulmaz; upstream değer beklenir |

Production yeni bir haricî provider uygulamaz. Gerçek Inventory ve operasyonel kayıt sağlayıcısı bağlanana kadar demo verisi production kararına sızdırılmaz; gerekli context yoksa açık `CONTEXT_MISSING` davranışı korunur.

## Temel karar politikaları

### Askerî ve Türkiye Inventory dışında

Aşağıdaki kesin koşul sağlandığında özel gate uygulanır:

```text
platform_usage_domain == MILITARY
AND inventory execution == SUCCESS
AND inventory_status == NOT_LISTED
```

Bu dalda Permission, Flight Plan ve NOTAM `UNREGISTERED_MILITARY_POLICY` nedeniyle `SKIPPED` olur. Bu sonuç tool failure değildir. Mevcut deterministic politika `UNVERIFIED / HIGH / UNREGISTERED_MILITARY_AIRCRAFT` üretir ve insan incelemesi ister.

CIVIL, DUAL_USE ve UNKNOWN kullanım alanlarında veya Inventory `UNKNOWN`, error ya da timeout olduğunda bu gate uygulanmaz. Sivil bir platform Inventory dışında olsa bile Permission, Flight Plan ve NOTAM normal şekilde çalışabilir.

### NOTAM etkileri

- `INFORMATIONAL`: yalnız bilgi sağlar; riski otomatik yükseltmez.
- `RESTRICTS_OPERATION`: eşleşen zaman, alan ve irtifa kapsamında operasyonu kısıtlar.
- `PROHIBITS_OPERATION`: ciddi operasyonel uyumsuzluk üretir; mevcut policy ile `CRITICAL / ACTIVE_NOTAM_PROHIBITION` korunur.
- `CONFLICTS_WITH_PERMISSION`: geçerli izin ile daha dar veya güncel NOTAM kısıtı arasındaki çelişkiyi gösterir.

NOTAM tek başına düşman unsur veya kesin hukuki ihlal kanıtı değildir. NOTAM geçerlilik zamanı video içi event timestamp'i olarak kullanılmaz.

## Girdi ve çıktı

Desteklenen girişler:

1. Hazır DEMO senaryo paketi
2. Canonical `AnalyzeEventRequest`
3. Türkçe ham VLM JSON
4. Gelecekteki video olay modülü için `video_event_adapter` projection'ı

Ham VLM platform kimliği yalnız VLM model hipotezi ile Registry exact alias çözümünden gelir. Görsel sınıf, hedef tipi veya serbest metinden askerî/sivil kullanım alanı tahmin edilmez.

Timestamp bulunmuyorsa:

- `timestamped_events=[]`
- `timestamps_available=false`
- `event_extraction_status=PENDING_VIDEO_EVENT_INTEGRATION`

Zamansız görsel değerlendirme ayrı taşınır ve kritik zaman damgalı olay gibi sunulmaz.

Ana kullanıcı çıktısı şu sıradadır:

1. Durum kartı
2. En fazla dört cümlelik operasyonel özet
3. Doğrulanmış risk gerekçeleri
4. En fazla üç önerilen aksiyon
5. Açılabilir teknik ayrıntılar ve tam JSON

## Veri kaynakları

| Kaynak | Dosya | Rol |
|---|---|---|
| Master platform kapsamı | `data/platforms/platform_allowlist.json` | Yeni aktif gerçek platformlar için allowlist |
| Platform Registry | `data/platforms/platform_registry.json` | Canonical kimlik ve taxonomy |
| Alias tablosu | `data/platforms/platform_aliases.json` | Exact/normalize platform çözümleme |
| Turkey Inventory | `data/inventory/turkey_inventory.json` | DEMO_MOCK Türkiye envanter kanıtı |
| Context route | `data/seeds/raw_vlm_context_routes.json` | Yalnız DEMO ham VLM yönlendirmesi |
| Operational seedler | `data/seeds/` | Context, izin, uçuş planı, NOTAM ve senaryolar |
| Risk ve aksiyon kuralları | `data/rules/` | Deterministik risk/action policy |
| RAG kaynakları | `data/rag/` | Yerel, kontrollü mevzuat bağlamı |

## Aktif Platform Registry

Aşağıdaki 97 platform allowlist ile birebir eşleşen aktif kapsamdır. `PLT_INACTIVE_DEMO`, gerçek platform kapsam sayımına dahil olmayan tek pasif test kaydıdır.

<details>
<summary>97 aktif platformu göster</summary>
### Türkiye öncelikli İHA / SİHA (11)

| platform_id | Canonical ad |
|---|---|
| `PLT_BAYRAKTAR_TB2` | Bayraktar TB2 |
| `PLT_BAYRAKTAR_TB3` | Bayraktar TB3 |
| `PLT_BAYRAKTAR_AKINCI` | Bayraktar AKINCI |
| `PLT_TUSAS_ANKA` | TUSAŞ ANKA |
| `PLT_TUSAS_AKSUNGUR` | TUSAŞ AKSUNGUR |
| `PLT_TUSAS_SIMSEK` | TUSAŞ ŞİMŞEK |
| `PLT_TUSAS_SUPER_SIMSEK` | TUSAŞ SÜPER ŞİMŞEK |
| `PLT_VESTEL_KARAYEL` | Vestel KARAYEL |
| `PLT_STM_KARGU` | STM KARGU |
| `PLT_STM_ALPAGU` | STM ALPAGU |
| `PLT_STM_TOGAN` | STM TOGAN |

### Türkiye bağlamlı insanlı hava araçları (6)

| platform_id | Canonical ad |
|---|---|
| `PLT_F16` | F-16 Fighting Falcon |
| `PLT_F4E_2020` | F-4E 2020 Terminator |
| `PLT_HURKUS` | TUSAŞ HÜRKUŞ |
| `PLT_F5_FREEDOM_FIGHTER` | F-5 Freedom Fighter |
| `PLT_NF5_TURK_YILDIZLARI` | NF-5 Türk Yıldızları |
| `PLT_T38_TALON` | T-38 Talon |

### Yabancı savaş uçakları (23)

| platform_id | Canonical ad |
|---|---|
| `PLT_F35_GENERIC` | F-35 Lightning II (varyant belirsiz aile kaydı) |
| `PLT_F35A` | F-35A Lightning II |
| `PLT_F35B` | F-35B Lightning II |
| `PLT_F35C` | F-35C Lightning II |
| `PLT_F22_RAPTOR` | F-22 Raptor |
| `PLT_FA18EF_SUPER_HORNET` | F/A-18E/F Super Hornet |
| `PLT_F15_EAGLE` | F-15 Eagle |
| `PLT_F15EX_EAGLE_II` | F-15EX Eagle II |
| `PLT_A10_THUNDERBOLT_II` | A-10 Thunderbolt II |
| `PLT_EUROFIGHTER_TYPHOON` | Eurofighter Typhoon |
| `PLT_RAFALE` | Dassault Rafale |
| `PLT_JAS39_GRIPEN` | Saab JAS 39 Gripen |
| `PLT_MIRAGE_2000` | Mirage 2000 |
| `PLT_MIG29` | Mikoyan MiG-29 |
| `PLT_MIG35` | Mikoyan MiG-35 |
| `PLT_SU27` | Sukhoi Su-27 Flanker |
| `PLT_SU30` | Sukhoi Su-30 |
| `PLT_SU35` | Sukhoi Su-35 |
| `PLT_SU57` | Sukhoi Su-57 |
| `PLT_J10` | Chengdu J-10 |
| `PLT_J20` | Chengdu J-20 |
| `PLT_JF17_THUNDER` | JF-17 Thunder |
| `PLT_TEJAS` | HAL Tejas |

### Askerî nakliye, tanker ve özel görev (10)

| platform_id | Canonical ad |
|---|---|
| `PLT_A400M` | Airbus A400M Atlas |
| `PLT_C130` | C-130 Hercules |
| `PLT_C17_GLOBEMASTER_III` | C-17 Globemaster III |
| `PLT_CN235` | CASA CN-235 |
| `PLT_C295W` | Airbus C-295W |
| `PLT_BOEING_E7` | Boeing E-7 |
| `PLT_A330_243_MRTT` | Airbus A330-243 MRTT |
| `PLT_P8A_POSEIDON` | Boeing P-8A Poseidon |
| `PLT_V22_OSPREY` | Bell Boeing V-22 Osprey |
| `PLT_AN124_RUSLAN` | Antonov An-124 Ruslan |

### Sivil hava araçları (13)

| platform_id | Canonical ad |
|---|---|
| `PLT_BOEING_737_NG` | Boeing 737 NG |
| `PLT_BOEING_737_MAX` | Boeing 737 MAX |
| `PLT_BOEING_747` | Boeing 747 |
| `PLT_BOEING_777` | Boeing 777 |
| `PLT_BOEING_787` | Boeing 787 Dreamliner |
| `PLT_AIRBUS_A320` | Airbus A320 |
| `PLT_AIRBUS_A321` | Airbus A321 |
| `PLT_AIRBUS_A330` | Airbus A330 |
| `PLT_AIRBUS_A350` | Airbus A350 |
| `PLT_AIRBUS_A380` | Airbus A380 |
| `PLT_ATR72` | ATR 72 |
| `PLT_CESSNA_172` | Cessna 172 Skyhawk |
| `PLT_PIPER_PA28` | Piper PA-28 Cherokee |

### Döner kanatlılar (9)

| platform_id | Canonical ad |
|---|---|
| `PLT_T129_ATAK` | T129 ATAK |
| `PLT_T625_GOKBEY` | T625 GÖKBEY |
| `PLT_SIKORSKY_S70` | Sikorsky S-70 Black Hawk |
| `PLT_CH47F_CHINOOK` | Boeing CH-47F Chinook |
| `PLT_AS532_COUGAR` | Airbus AS532 Cougar |
| `PLT_UH1_HUEY` | Bell UH-1 Huey |
| `PLT_AH1_SUPER_COBRA` | Bell AH-1 Super Cobra |
| `PLT_AH64E_APACHE_GUARDIAN` | Boeing AH-64E Apache Guardian |
| `PLT_KA52_ALLIGATOR` | Kamov Ka-52 Alligator |

### Mikro, ticari ve kamikaze İHA (9)

| platform_id | Canonical ad |
|---|---|
| `PLT_DJI_MAVIC_2` | DJI Mavic 2 |
| `PLT_DJI_MAVIC_3` | DJI Mavic 3 |
| `PLT_DJI_MINI_SERIES` | DJI Mini Serisi |
| `PLT_DJI_AIR_SERIES` | DJI Air Serisi |
| `PLT_DJI_PHANTOM_SERIES` | DJI Phantom Serisi |
| `PLT_DJI_MATRICE_300` | DJI Matrice 300 |
| `PLT_DJI_MATRICE_350` | DJI Matrice 350 |
| `PLT_SHAHED136_GERAN2` | Shahed-136 / Geran-2 |
| `PLT_HAROP` | IAI Harop |

### Yabancı İHA / SİHA (14)

| platform_id | Canonical ad |
|---|---|
| `PLT_MQ9_REAPER` | MQ-9 Reaper |
| `PLT_MQ9B_SKYGUARDIAN` | MQ-9B SkyGuardian |
| `PLT_MQ1_PREDATOR` | MQ-1 Predator |
| `PLT_RQ4_GLOBAL_HAWK` | RQ-4 Global Hawk |
| `PLT_RQ170_SENTINEL` | RQ-170 Sentinel |
| `PLT_HERON_TP` | IAI Heron TP |
| `PLT_HERMES_450` | Elbit Hermes 450 |
| `PLT_HERMES_900` | Elbit Hermes 900 |
| `PLT_ORION_UAV` | Kronstadt Orion İHA |
| `PLT_FORPOST_R` | Forpost-R |
| `PLT_CH4` | CASC CH-4 |
| `PLT_WING_LOONG_I` | Wing Loong I |
| `PLT_WING_LOONG_II` | Wing Loong II |
| `PLT_WZ7_SOARING_DRAGON` | WZ-7 Soaring Dragon |

### Stratejik bombardıman uçakları (2)

| platform_id | Canonical ad |
|---|---|
| `PLT_B2_SPIRIT` | Northrop Grumman B-2 Spirit |
| `PLT_B52_STRATOFORTRESS` | Boeing B-52 Stratofortress |

</details>

## Registry kapsamı dışında tutulan platformlar

Nihai plana göre aşağıdaki platformlar prototip, test/teknoloji demonstratörü, geliştirme programı veya operasyonel hava sahasında düşük karşılaşma değeri nedeniyle Platform Registry'de bulunmaz:

- KAAN
- Bayraktar KIZILELMA
- Bayraktar KALKAN DİHA
- TUSAŞ ANKA-III
- TUSAŞ HÜRJET
- STM ALPAGU-B
- WZ-8
- Northrop Grumman X-47B
- Dassault nEUROn
- BAE Systems Taranis
- B-21 Raider

Bu adlar alias, Inventory, Permission, Flight Plan, NOTAM, context veya raw route hedefi olarak da kullanılmamalıdır.

## DEMO Turkey Inventory

Bu 22 kayıt yalnız `DEMO_MOCK` kabul ve gösterim verisidir; güncel veya resmî Türkiye envanteri beyanı değildir.

<details>
<summary>22 DEMO Inventory kaydını göster</summary>

| platform_id | Platform |
|---|---|| `PLT_F16` | F-16 Fighting Falcon |
| `PLT_BAYRAKTAR_TB2` | Bayraktar TB2 |
| `PLT_BAYRAKTAR_AKINCI` | Bayraktar AKINCI |
| `PLT_TUSAS_ANKA` | TUSAŞ ANKA |
| `PLT_T129_ATAK` | T129 ATAK |
| `PLT_T625_GOKBEY` | T625 GÖKBEY |
| `PLT_A400M` | Airbus A400M Atlas |
| `PLT_C130` | C-130 Hercules |
| `PLT_CN235` | CASA CN-235 |
| `PLT_BOEING_E7` | Boeing E-7 |
| `PLT_TUSAS_AKSUNGUR` | TUSAŞ AKSUNGUR |
| `PLT_STM_KARGU` | STM KARGU |
| `PLT_STM_TOGAN` | STM TOGAN |
| `PLT_F4E_2020` | F-4E 2020 Terminator |
| `PLT_F5_FREEDOM_FIGHTER` | F-5 Freedom Fighter |
| `PLT_NF5_TURK_YILDIZLARI` | NF-5 Türk Yıldızları |
| `PLT_T38_TALON` | T-38 Talon |
| `PLT_SIKORSKY_S70` | Sikorsky S-70 Black Hawk |
| `PLT_CH47F_CHINOOK` | Boeing CH-47F Chinook |
| `PLT_AS532_COUGAR` | Airbus AS532 Cougar |
| `PLT_UH1_HUEY` | Bell UH-1 Huey |
| `PLT_AH1_SUPER_COBRA` | Bell AH-1 Super Cobra |

</details>

## DEMO kabul senaryoları

SCN-01–SCN-23 gerçek orchestrator, tool, verification, risk, decision, guard ve finalizer akışını çalıştıran deterministik kabul kataloğudur.

<details>
<summary>23 senaryoyu göster</summary>

| Senaryo | Kısa ad | Verification | Risk | Decision |
|---|---|---|---|---|
| SCN-01 | Doğrulanmış operasyon | `VERIFIED` | `LOW` | `AUTHORIZED_OPERATIONAL_MATCH` |
| SCN-02 | İzinsiz dosyalanmış uçuş planı | `UNVERIFIED` | `MEDIUM` | `OPERATIONAL_AUTHORIZATION_UNVERIFIED` |
| SCN-03 | Beklenmeyen izinsiz platform | `UNVERIFIED` | `HIGH` | `UNEXPECTED_PLATFORM` |
| SCN-04 | Süresi dolmuş izin | `UNVERIFIED` | `HIGH` | `EXPIRED_OR_INVALID_PERMISSION` |
| SCN-05 | Kısıtlayıcı NOTAM | `UNVERIFIED` | `HIGH` | `UNVERIFIED_AIRCRAFT` |
| SCN-06 | Çözümlenemeyen platform | `INDETERMINATE` | `UNKNOWN` | `PLATFORM_UNRESOLVED` |
| SCN-07 | Kritik tool hatası | `INDETERMINATE` | `UNKNOWN` | `INDETERMINATE` |
| SCN-08 | Güçlü non-aircraft | `NOT_APPLICABLE` | `LOW` | `NON_AIRCRAFT` |
| SCN-09 | İptal edilmiş uçuş planı | `UNVERIFIED` | `HIGH` | `CONFLICTING_OPERATIONAL_RECORDS` |
| SCN-10 | Kullanılamayan context | `INDETERMINATE` | `UNKNOWN` | `PLATFORM_UNRESOLVED` |
| SCN-11 | Operasyonu yasaklayan NOTAM | `UNVERIFIED` | `CRITICAL` | `ACTIVE_NOTAM_PROHIBITION` |
| SCN-12 | Beklenmeyen fakat izinli platform | `PARTIALLY_VERIFIED` | `MEDIUM` | `PARTIALLY_VERIFIED_OPERATION` |
| SCN-13 | Boeing 747 envanter dışı doğrulanmış operasyon | `VERIFIED` | `LOW` | `AUTHORIZED_OPERATIONAL_MATCH` |
| SCN-14 | Bayraktar TB2 SİHA doğrulanmış operasyon | `VERIFIED` | `LOW` | `AUTHORIZED_OPERATIONAL_MATCH` |
| SCN-15 | Bayraktar AKINCI Ağır sınıf SİHA permission bulunamadı | `UNVERIFIED` | `MEDIUM` | `OPERATIONAL_AUTHORIZATION_UNVERIFIED` |
| SCN-16 | TUSAŞ ANKA Orta irtifa uzun havada kalışlı İHA NOTAM kısıtı | `UNVERIFIED` | `HIGH` | `UNVERIFIED_AIRCRAFT` |
| SCN-17 | F-35A Lightning II savaş uçağı Inventory kapsam dışı | `UNVERIFIED` | `HIGH` | `UNREGISTERED_MILITARY_AIRCRAFT` |
| SCN-18 | MQ-9 Reaper Orta irtifa uzun havada kalışlı SİHA ham VLM | `UNVERIFIED` | `HIGH` | `UNREGISTERED_MILITARY_AIRCRAFT` |
| SCN-19 | Bayraktar AKINCI iptal edilmiş Permission | `UNVERIFIED` | `HIGH` | `EXPIRED_OR_INVALID_PERMISSION` |
| SCN-20 | Bayraktar TB2 süresi dolmuş Permission | `UNVERIFIED` | `HIGH` | `EXPIRED_OR_INVALID_PERMISSION` |
| SCN-21 | F-16 operasyonu yasaklayan NOTAM | `UNVERIFIED` | `CRITICAL` | `ACTIVE_NOTAM_PROHIBITION` |
| SCN-22 | TUSAŞ ANKA Permission ile çelişen NOTAM | `UNVERIFIED` | `HIGH` | `CONFLICTING_OPERATIONAL_RECORDS` |
| SCN-23 | Boeing 747 ILS bakım NOTAM kısıtı | `UNVERIFIED` | `HIGH` | `UNVERIFIED_AIRCRAFT` |

</details>

## API

| Metot | Endpoint | Açıklama |
|---|---|---|
| `POST` | `/api/v1/adapters/raw-vlm` | Ham VLM girdisini canonical request'e dönüştürür |
| `POST` | `/api/v1/analyze/raw-vlm` | Context üretmeden Registry ve güvenli Inventory ön değerlendirmesi yapar |
| `POST` | `/api/v1/events/analyze` | Tam operasyonel karar pipeline'ını çalıştırır |
| `GET` | `/api/v1/events/{event_id}` | Saklanan final olayı getirir |
| `GET` | `/api/v1/events/{event_id}/trace` | Audit ve tool execution trace'ini getirir |
| `GET` | `/api/v1/demo/scenarios` | Yalnız DEMO modunda senaryo kataloğunu getirir |
| `GET` | `/api/v1/rag/status` | Yerel RAG durumunu getirir |
| `GET` | `/health` | Runtime bileşen sağlığını getirir |

## Kurulum ve çalıştırma

Gereksinimler: Windows veya macOS/Linux, Python 3.11, yerel Ollama ve repository içinde hazır embedding modeli.

Windows (PowerShell):

```powershell
uv sync --extra dev --extra demo-ui
Copy-Item .env.example .env
.venv\Scripts\python.exe scripts\initialize_databases.py
.venv\Scripts\python.exe scripts\seed_demo_data.py
```

macOS/Linux (bash/zsh):

```bash
uv sync --extra dev --extra demo-ui
cp .env.example .env
.venv/bin/python scripts/initialize_databases.py
.venv/bin/python scripts/seed_demo_data.py
```

API — Windows:

```powershell
.venv\Scripts\uvicorn.exe operational_decision.api.main:app --host 127.0.0.1 --port 8000
```

API — macOS/Linux:

```bash
.venv/bin/uvicorn operational_decision.api.main:app --host 127.0.0.1 --port 8000
```

Streamlit — Windows:

```powershell
.venv\Scripts\streamlit.exe run apps\demo_ui\app.py
```

Streamlit — macOS/Linux:

```bash
.venv/bin/streamlit run apps/demo_ui/app.py
```

Production için `.env.example` içindeki mode sınırlarını izleyin; demo DB yollarını kullanmayın ve gerçek video/track/context değerlerini upstream entegrasyondan sağlayın.

## Doğrulama

Windows:

```powershell
.venv\Scripts\python.exe scripts\validate_platform_registry.py
.venv\Scripts\python.exe scripts\validate_documents.py
.venv\Scripts\python.exe scripts\run_demo_scenarios.py
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m mypy src --strict
```

macOS/Linux:

```bash
.venv/bin/python scripts/validate_platform_registry.py
.venv/bin/python scripts/validate_documents.py
.venv/bin/python scripts/run_demo_scenarios.py
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy src --strict
```

Test sayısı sabit bir kabul ölçütü değildir; tüm komutların hatasız tamamlanması beklenir.

## Proje yapısı

```text
apps/demo_ui/                 Streamlit kullanıcı arayüzü
data/platforms/              Allowlist, Registry ve alias verileri
data/inventory/              DEMO Turkey Inventory
data/seeds/                  Context ve operational demo kayıtları
data/rules/                  Risk ve aksiyon politikaları
data/rag/                    Yerel RAG manifesti ve kaynakları
migrations/                  SQLite migration'ları
src/operational_decision/    API, contract, tool, policy ve finalizer katmanları
tests/                       Unit, integration, contract ve senaryo testleri
```

Ayrıntılı teknik belgeler `docs/` dizinindedir. Özellikle `API_USAGE.md`, `UPSTREAM_INTEGRATION.md`, `RISK_RULES.md`, `DATA_AND_RAG_PROVENANCE.md` ve `DEMO_SCENARIOS.md` güncel uygulama sınırlarını açıklar.

## Veri ve kullanım notu

Repository içindeki Inventory, Permission, Flight Plan, NOTAM ve context kayıtları `DEMO_MOCK` veridir. Gerçek operasyonel otorite, güncel envanter, hukuki ihlal veya düşman unsur kanıtı olarak kullanılamaz. Nihai operasyonel yetki insan operatördedir.
