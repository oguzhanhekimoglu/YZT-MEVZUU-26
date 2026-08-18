# API Kullanımı

Base URL: `http://127.0.0.1:8000`

## Event analizi

```powershell
$body = Get-Content examples\analyze_event_request.json -Raw
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/events/analyze -ContentType application/json -Body $body
```

Durumlar:

- `200`: Finalized sonuç veya aynı fingerprint için önceden finalized sonuç
- `202`: `WAITING_FOR_GPU_HANDOFF`; aynı payload `gpu_release_status=RELEASED` ile tekrar gönderilerek aynı event sürdürülür
- `409`: Aynı fingerprint için waiting dışında aktif işlem vardır
- `422`: Canonical input geçersizdir; sanitized raw audit ve rejected event yine saklanır

GPU hazır değilken yeni finalized event oluşturulmaz ve LLM başlatılmaz.

## Event ve trace

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/events/EVENT_ID
Invoke-RestMethod http://127.0.0.1:8000/api/v1/events/EVENT_ID/trace
```

Trace; lifecycle step'lerini, tool execution denemelerini, raw audit kaydını ve persisted final output'u içerir.

Final output içindeki `inventory_status`, execution durumu ve policy reason birlikte okunmalıdır. Yalnız `usage_domain=MILITARY` + Inventory execution `SUCCESS` + `NOT_LISTED` koşulunda Permission, Flight Plan ve NOTAM `UNREGISTERED_MILITARY_POLICY` nedeniyle atlanır. Sivil `NOT_LISTED` platformlarda operational araçlar normal çalışabilir ve `VALID + FILED + NO_EFFECT` sonucu `VERIFIED / LOW / AUTHORIZED_OPERATIONAL_MATCH` olabilir. Platform unresolved, strong `NON_AIRCRAFT` veya incomplete context durumlarında mevcut güvenli skip davranışı korunur.

Ham VLM adapter'ın `tehdit_seviyesi` ve `ulke_orjini` metadata alanları Risk, Inventory veya Decision için doğrudan kanıt değildir. Platform Registry origin ve taxonomy metadata'sı da karar girdisi olarak kullanılmaz.

## Katalog ve health

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/demo/scenarios
Invoke-RestMethod http://127.0.0.1:8000/api/v1/rag/status
Invoke-RestMethod http://127.0.0.1:8000/health
```

API içindeki karar mantığı route katmanında değildir; route'lar transport ve serialization sınırıdır.


## Çalışma modu sınırı

`DEMO` modunda `/api/v1/demo/scenarios` erişilebilir ve demo seedleri kullanılabilir. `PRODUCTION` modunda endpoint `404 DEMO_ENDPOINT_DISABLED` döndürür; `/api/v1/analyze/raw-vlm` demo Inventory dosyasını değerlendirmez. Production tam analiz için upstream video/track/context alanlarını bekler.
