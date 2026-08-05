# Database Schema

Canonical migrationlar `migrations/operational/001_initial.sql` ve `migrations/event_memory/001_initial.sql` dosyalarıdır. DB adları `operational.db` ve `event_memory.db` olarak sabittir.

Operational DB video context, permission, flight plan ve NOTAM kayıtlarını bağımsız tablolarda tutar. Uçuş planı izin değildir. Seed kayıtları `DEMO_MOCK` provenance taşır.

Event Memory DB raw audit, lifecycle step, tool execution denemeleri ve final output'u saklar. Fingerprint idempotency için kullanılır. Her SQLite retry ayrı tool execution kaydıdır. Final output yalnız finalized akışta persist edilir; GPU waiting durumunda yeni finalized event oluşturulmaz.