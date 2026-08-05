# Operational Decision Demo UI

Bu Streamlit uygulaması yalnız mevcut FastAPI endpointlerinin manuel test istemcisidir. Frontend içinde karar, risk, verification, RAG veya operational tool mantığı uygulanmaz; SQLite'a doğrudan erişilmez.

Ham VLM ekranında `VLM Çıktısını Analiz Et` ayrıntılı canonical operasyonel sonucu, `TEKNOFEST Şartname` ise aynı canonical karardan türetilen kısa sunumu gösterir. Hazır demo sekmesindeki format seçimi test amacıyla korunur; backend canonical karar kaydı değiştirilmez.

## Kurulum

```bash
uv sync --extra dev --extra demo-ui
```

## Çalıştırma

Backend — Windows:

```powershell
.venv\Scripts\uvicorn.exe operational_decision.api.main:app --host 127.0.0.1 --port 8000
```

Backend — macOS/Linux:

```bash
.venv/bin/uvicorn operational_decision.api.main:app --host 127.0.0.1 --port 8000
```

UI — Windows:

```powershell
.venv\Scripts\streamlit.exe run apps/demo_ui/app.py
```

UI — macOS/Linux:

```bash
.venv/bin/streamlit run apps/demo_ui/app.py
```

Repo kökünden çalıştırılmalıdır; `app.py` `apps/` paketini bulmak için repo kökünü otomatik olarak `sys.path`'e ekler.

Test — Windows:

```powershell
.venv\Scripts\pytest.exe tests/unit/test_demo_ui_api_client.py -q
```

Test — macOS/Linux:

```bash
.venv/bin/pytest tests/unit/test_demo_ui_api_client.py -q
```

## Backend scenario sözleşmesi

`GET /api/v1/demo/scenarios`, SCN-01–SCN-23 için ad, açıklama, beklenen verification/risk ve canonical `request_payload` döndürür. SCN-13, Boeing 747 için Inventory `NOT_LISTED` kalırken geçerli Permission ve Flight Plan ile doğrulanan operasyonu gösterir. SCN-14 kullanıcıya dönük listede Bayraktar TB2 SİHA, SCN-15 Bayraktar AKINCI Ağır sınıf SİHA, SCN-16 TUSAŞ ANKA Orta irtifa uzun havada kalışlı İHA, SCN-17 F-35A Lightning II savaş uçağı ve SCN-18 MQ-9 Reaper Orta irtifa uzun havada kalışlı SİHA olarak görünür. SCN-17 ve SCN-18, Inventory `NOT_LISTED` askerî platform politikası gereği downstream araçların SKIPPED olduğu ve `UNVERIFIED / HIGH / UNREGISTERED_MILITARY_AIRCRAFT` ürettiği kontrollü örneklerdir. Ham VLM sekmesindeki örnek `examples/raw_vlm_mq9_reaper.json` dosyasından yüklenir; `tehdit_seviyesi` ve `ulke_orjini` karar kanıtı değildir. UI senaryo payload'ını üretmez veya tamamlamaz; backend'in verdiği nesneyi değiştirmeden analyze endpointine gönderir. Eksik payload yine `SCENARIO_REQUEST_PAYLOAD_MISSING` olarak görünür ve sahte fallback üretilmez.

Final output içindeki mevcut diagnostic veriler kaybolmadan gösterilir:

- Risk Advisor tarafından üretilen `matched_rule_ids`.
- Tool envelope tarafından üretilen `ToolExecutionSummaryItem.warnings`.

Bilinçli sözleşme sınırları:

- `SourceReference` excerpt veya runtime/reference rolü içermez. Reference-only sızıntı uyarısı canonical manifestteki document ID listesiyle yalnız sunum amaçlı kontrol edilir; sonuç değiştirilmez.
- `RecommendedAction` yalnız `action_code`, `priority` ve `reason_tr` içerir. Aksiyon başlığı ve aksiyon-bazlı human approval uydurulmaz; final genel `human_approval_required` ayrıca gösterilir.

## Güvenlik sınırları

Kayıtlar `DEMO_MOCK`'tur. PDF'ler operasyonel kayıt değildir. RAG karar vermez. Uçuş planı izin değildir. Görsel hipotez kesin kimlik değildir. Sistem gerçek operasyonel otoritenin yerini almaz.
