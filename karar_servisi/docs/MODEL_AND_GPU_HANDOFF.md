# Model ve GPU Handoff

## Canonical Ollama modeli

```text
qwen3:4b-instruct-2507-q4_K_M
```

Canonical generation ayarları:

```text
num_ctx=8192
num_predict=1000
temperature=0.1
top_p=0.8
seed=42
stream=false
think=false
keep_alive=10m
```

LLM risk seçmez, tool sonucunu değiştirmez, olmayan source ID kullanamaz ve görsel hipotezi kesin kimlik olarak sunamaz. Parse/schema hatasında yalnız bir repair yapılır; timeout veya network hatası otomatik retry edilmez. İkinci invalid output deterministic safe fallback üretir.

## GPU teslim protokolü

`gpu_release_status != RELEASED` ise:

1. LLM başlatılmaz.
2. Event `WAITING_FOR_GPU_HANDOFF` olur.
3. Analyze endpoint HTTP `202` döner.
4. Aynı fingerprint, `RELEASED` statüsüyle yeniden gönderildiğinde aynı event devam eder.

Aynı video eventleri sequential işlenir. Farklı videolarda da LLM inference eşzamanlı çalışmaz. Event tamamlandığında aynı video için başka aktif event yoksa explicit unload çağrılır. Unload başarısızlığı final kararı değiştirmez; warning ve metric üretir.

> **GÜNCELLEME:** LLM artık yerel Ollama değil, SSB'nin TEKNOFEST TYDA için sağladığı
> EVREN çıkarım servisi (uzak, OpenAI-uyumlu) üzerinden çalışıyor — `ollama_client.py`
> ve bu sayfadaki Ollama'ya özel smoke script'i (`run_ollama_real_smoke.py`) kaldırıldı.
> Bu sayfanın geri kalanı (canonical model adı, GPU handoff protokolü), yerel GPU'yu
> YOLO ile paylaşan bir Ollama sürecine göre yazılmıştı; EVREN ayrı donanımda
> çalıştığı için bu paylaşım/handoff senaryosu artık geçerli değil ve gözden
> geçirilmeyi bekliyor.