# Risk Rules

Canonical kurallar `data/rules/risk_rules.yaml`, aksiyonlar `data/rules/action_catalog.yaml` içindedir. Risk Advisor priority sırasını, minimum risk korumasını ve specificity değerlerini deterministik uygular. LLM risk veya verification seçmez.

## Inventory bağımsız evidence davranışı

- Başarılı Inventory sonucu `NOT_LISTED` ve Registry kullanım alanı `MILITARY` olduğunda `UNREGISTERED_MILITARY_POLICY` gate koşulu Permission, Flight Plan ve NOTAM araçlarını policy `SKIPPED` yapar. Bu skip tool failure değildir; verification `UNVERIFIED`, risk `HIGH` ve karar `UNREGISTERED_MILITARY_AIRCRAFT` deterministic olarak üretilir. CIVIL, DUAL_USE ve UNKNOWN kullanım alanlarında normal downstream kontrolleri korunur.
- Inventory `UNKNOWN` veya Inventory Tool `ERROR`/`TIMEOUT`: verification `INDETERMINATE`, risk `UNKNOWN`, güvenli inceleme kararı ve human review `true` üretir; tool health `FAILED` olur.
- Inventory `CONFIRMED`: yalnız kullanılan DEMO_MOCK veri setindeki kaydı gösterir. Permission, flight-plan, NOTAM, platform ve consistency kuralları normal deterministic akışta ayrıca değerlendirilir; `CONFIRMED` uçuş izni değildir.
- Registry üretici ülke metadata'sından bağımsız olarak, VLM'nin ham `ulke_orjini` alanı normalize edilir (`TURKEY`/`UNKNOWN`/`FOREIGN`). `MILITARY` kullanım alanında ve Inventory `CONFIRMED` olduğunda bu kategori, platform adından bağımsız olarak tüm askerî platformlarda aynı şekilde uygulanır: `FOREIGN` en az `HIGH` risk ve `URGENT` human review üretir; `UNKNOWN` en az `MEDIUM` risk üretir ve `LOW` risk engellenir; `TURKEY` tek başına güvenli karar üretmez, mevcut Permission/Flight Plan/NOTAM sonuçlarına göre `LOW` mümkün kalır.
- Strong `NON_AIRCRAFT`: mevcut early exit ile verification `NOT_APPLICABLE` ve risk `LOW` kalır.

## Operational Consistency etkisi

- Consistency `INDETERMINATE`, verification sonucunu `INDETERMINATE` yapar.
- `REQUIRED_OPERATIONAL_CHECK_UNAVAILABLE`, riski `UNKNOWN` yapar.
- `NOTAM_PROHIBITS_OPERATION`, minimum `CRITICAL` uygular.
- `NOTAM_RESTRICTS_OPERATION` ve `NOTAM_CONFLICTS_WITH_PERMISSION`, minimum `HIGH` uygular.
- `INVENTORY_NOT_LISTED`, tehdit, düşmanlık, yabancılık veya taklit riskine dönüştürülmez.
- Platform origin ve taxonomy metadata'sı Risk veya Decision girdisi değildir.

## Permission, flight plan ve NOTAM

- `FILED` flight plan ile geçerli permission yoksa verification `UNVERIFIED` olur.
- `VALID` permission ile `CANCELLED` flight plan verification `UNVERIFIED` ve minimum `HIGH` üretir.
- `EXPIRED` veya `REVOKED` permission minimum `HIGH` üretir.
- Flight plan permission sayılmaz.
- NOTAM `PROHIBITS_OPERATION` en az `CRITICAL`; `RESTRICTS_OPERATION` veya `CONFLICTS_WITH_PERMISSION` en az `HIGH` üretir.
- `SKIPPED` execution sonucu `NOT_FOUND` veya başka bir domain sonucu olarak yorumlanmaz.

`UNKNOWN` hiçbir koşulda `LOW` yapılmaz. Human review, eşleşen kurallar ve kanıt koşullarının OR birleşimidir. Tanımsız durum `UNKNOWN` ve human review üretir.
