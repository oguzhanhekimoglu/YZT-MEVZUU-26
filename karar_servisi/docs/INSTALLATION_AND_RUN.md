# Kurulum ve Çalıştırma

## Ön koşullar

- Windows (PowerShell) veya macOS/Linux (bash/zsh)
- CPython 3.11
- EVREN erişimi (TEKNOFEST TYDA — SSB'nin sağladığı OpenAI-uyumlu çıkarım servisi, `OPERATIONAL_DECISION_VLLM_API_KEY` ile yapılandırılır, bkz. `.env.example`)
- `OPERATIONAL_DECISION_DECISION_MODEL` ile yapılandırılan model alias'ı (varsayılan: `llm-fast`)
- Repodaki yerel `data/models/qwen3-embedding-0.6b` embedding modeli

Runtime karar/rapor üretimi için internet ve EVREN erişimi gerekir (yerel Ollama artık kullanılmıyor). Kabul scripti model indirmez.

Not: `.venv` platforma özeldir (Windows venv macOS'ta, macOS venv Windows'ta çalışmaz). Platform değiştirdiğinizde `.venv` dizinini silip `uv sync` ile yeniden oluşturun.

## Ortam

Windows:

```powershell
uv sync --extra dev
.venv\Scripts\python.exe --version
```

macOS/Linux:

```bash
uv sync --extra dev
.venv/bin/python --version
```

Beklenen Python ana/minör sürümü `3.11`'dir.

## Çalışma modu

Varsayılan yerel geliştirme modu `DEMO`dur. Bu mod demo scenario endpointini, Developer/Demo UI bölümünü, `raw_vlm_context_routes` eşlemesini ve `DEMO_MOCK` seedlerini kullanır.

`PRODUCTION` için `OPERATIONAL_DECISION_RUNTIME_MODE=PRODUCTION` ayarlayın ve demo varsayılanlarından farklı, birbirinden ayrı `OPERATIONAL_DECISION_OPERATIONAL_DB_PATH` ile `OPERATIONAL_DECISION_EVENT_DB_PATH` sağlayın. Production bootstrap demo seedlerini yüklemez; demo verisi bulunan operational DB dosyasını reddeder. Gerçek video/track/context upstream kaynaktan gelmelidir; platformdan context, sentetik timestamp veya sabit görsel güven değeri türetilmez.

## Veri ve indeks doğrulaması

Windows:

```powershell
.venv\Scripts\python.exe scripts\validate_documents.py
.venv\Scripts\python.exe scripts\initialize_databases.py
.venv\Scripts\python.exe scripts\seed_demo_data.py
.venv\Scripts\python.exe scripts\validate_platform_registry.py
.venv\Scripts\python.exe scripts\build_text_rag_index.py
.venv\Scripts\python.exe scripts\benchmark_pipeline.py
```

macOS/Linux:

```bash
.venv/bin/python scripts/validate_documents.py
.venv/bin/python scripts/initialize_databases.py
.venv/bin/python scripts/seed_demo_data.py
.venv/bin/python scripts/validate_platform_registry.py
.venv/bin/python scripts/build_text_rag_index.py
.venv/bin/python scripts/benchmark_pipeline.py
```

`build_text_rag_index.py`, sağlıklı ve manifestle uyumlu mevcut indeksi yeniden oluşturmaz. Reference-only belgeler indekslenmez.

## API

Windows:

```powershell
.venv\Scripts\uvicorn.exe operational_decision.api.main:app --host 127.0.0.1 --port 8000
```

macOS/Linux:

```bash
.venv/bin/uvicorn operational_decision.api.main:app --host 127.0.0.1 --port 8000
```

Sağlık kontrolü — Windows:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod 'http://127.0.0.1:8000/health?deep=true'
```

Sağlık kontrolü — macOS/Linux:

```bash
curl http://127.0.0.1:8000/health
curl 'http://127.0.0.1:8000/health?deep=true'
```

`deep=false` model generation çağrısı yapmaz. Operational DB, event DB veya RAG manifest/index uyumsuzluğu health sonucunu `FAILED` ve HTTP `503` yapar. Canonical Ollama modelinin bulunmaması `DEGRADED` ve HTTP `200` üretir.

## Kabul

Windows:

```powershell
.venv\Scripts\python.exe scripts\final_acceptance.py
```

macOS/Linux:

```bash
.venv/bin/python scripts/final_acceptance.py
```

Çıktılar `reports/coverage.json`, `reports/coverage_summary.json`, `reports/final_acceptance_commands.json` ve `data/rag/index/final_benchmark_report.json` dosyalarına yazılır.
Tam test suite içindeki test sayısı geliştirme boyunca değişebilir. Sabit bir toplam test sayısı kabul ölçütü değildir; komutun setup error veya test failure olmadan tamamlanması ve tanımlı kalite eşiklerinin sağlanması gerekir.

## Troubleshooting / Sorun Giderme

### Health FAILED

Operational DB ve event DB yollarını, dosya erişimini, Türkiye Inventory registry yükleme durumunu ve `data/rag/index/index_manifest.json` ile `document_manifest.yaml` checksum uyumunu kontrol edin (macOS/Linux'ta `.venv\Scripts\python.exe` yerine `.venv/bin/python`):

```powershell
.venv\Scripts\python.exe scripts\validate_documents.py
.venv\Scripts\python.exe scripts\validate_platform_registry.py
.venv\Scripts\python.exe scripts\build_text_rag_index.py
```

Registry veya index doğrulama hatasında sessiz fallback beklenmez; health sonucu hatayı açıkça göstermelidir.

### Health DEGRADED

EVREN erişilebilir fakat canonical model yoksa veya optional model probe başarısızsa beklenen sonuç `DEGRADED` ve HTTP `200`'dür — `/durum` (health) çıktısındaki `"ollama"` anahtarı (isim tarihsel, sözleşme aynı kalsın diye korunuyor — bkz. `bootstrap.py: _vllm_probes`) bunu gösterir.

### WAITING_FOR_GPU_HANDOFF

Aynı request payload'ını `gpu_release_status=RELEASED` ile yeniden gönderin. Fingerprint alanlarını değiştirmeyin; aksi halde aynı event sürdürülemez.

### RAG index veya benchmark hatası

`data/rag/index/final_benchmark_report.json` içindeki query satırlarını inceleyin. Beklentileri hatalı retrieval sonucuna göre gevşetmeyin. Manifest/index uyuşmazlığı varsa indexi canonical manifestten yeniden oluşturun.

```powershell
.venv\Scripts\python.exe scripts\validate_documents.py
.venv\Scripts\python.exe scripts\build_text_rag_index.py
.venv\Scripts\python.exe scripts\benchmark_pipeline.py
```

macOS/Linux: aynı script'ler `.venv/bin/python` ile.

Reference-only belgeler indexe alınmamalıdır.

### Coverage veya test hatası

Windows:

```powershell
.venv\Scripts\ruff.exe check .
.venv\Scripts\mypy.exe src
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe scripts\final_acceptance.py
```

macOS/Linux:

```bash
.venv/bin/ruff check .
.venv/bin/mypy src
.venv/bin/python -m pytest -q
.venv/bin/python scripts/final_acceptance.py
```

Coverage hatasında `reports/coverage_summary.json` içindeki katman eşiğini inceleyin. Omit listesini genişletmeyin; eksik hata ve branch yollarına test ekleyin.

### Windows pytest tmp/ACL erişim hatası

Test bootstrap'ı pytest `tmp_path`, `tmpdir` ve cache davranışını repo altındaki yazılabilir, oturuma özel bir çalışma dizinine yönlendirir. Her run process ID ve benzersiz kimlik içeren ayrı bir alt dizin kullanır; paralel veya art arda çalıştırmalar çakışmaz. Oturum sonunda yalnız kendi oluşturduğu geçici içerik güvenli şekilde temizlenir.

Yönetici yetkisi kullanmayın ve ACL-kısıtlı eski pytest klasörlerine müdahale etmeyin. Komutları repo kökünden çalıştırın:

```powershell
.venv\Scripts\python.exe -m pytest -q
```

Yeni oturum yine erişim hatası verirse repo kökünün yazılabilir olduğunu ve test bootstrap'ının etkin yüklendiğini doğrulayın; testleri `skip`/`xfail` yapmayın ve assertion'ları gevşetmeyin.