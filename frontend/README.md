# MEVZUU — Hava Sahası Karar Destek Sistemi — Operatör Arayüzü

TEKNOFEST Yapay Zeka Dil Ajanları Yarışması, 3. Senaryo kapsamında geliştirilen operatör konsolu frontend'idir. `YZT-MEVZUU-26` ana projesindeki gerçek backend'e bağlanacak, tamamen çevrimdışı çalışabilen bağımsız bir React + TypeScript + Vite uygulamasıdır.

## Çalıştırma

```bash
npm install
npm run dev                    # Vite geliştirme sunucusu (gerçek backend adapter'ı kullanır)
npm run build                  # tsc -b && vite build
npm run build:backend          # tsc -b && vite build --mode backend (.env.backend — aynı origin/production dağıtımı)
npm run lint                   # eslint .
npm test                       # vitest run
npm run test:watch             # vitest (watch modu)
npm run test:e2e:backend       # playwright.backend.config.ts — gerçek backend adaptör akışı (tek e2e suite)
npm run serve:e2e              # dist/ çıktısını e2e-backend için sunar
```

Veri kaynağı `VITE_DATA_SOURCE` ortam değişkeniyle seçilir (`backend` | `planned-backend`); bkz. `.env.example` (yerel geliştirme) ve `.env.backend` (aynı origin production dağıtımı). Uygulamada seçilebilir bir mock/sahte veri kaynağı yoktur.

## Mimari

```
UI → State → Backend Adapter → YZT-MEVZUU-26 Backend
```

UI bileşenleri hiçbir zaman `fetch`/`WebSocket` çağırmaz veya test verisi import etmez; tamamı tek bir `OperatorDataSource` arayüzü (`src/services/contracts.ts`) üzerinden `useOperatorDataSource()` ile konuşur. Bu arayüzün somut implementasyonu (`backend` | `planned-backend`) `src/services/data-source.ts` içinde ortam değişkenine göre seçilir. Bileşen testlerinde kullanılan sahte veri kaynağı (`src/test/`) yalnızca test amaçlıdır ve production seçeneklerinden biri değildir.

**Frontend operasyonel karar üretmez.** Risk seviyesi, tehdit hipotezi, envanter/izin/NOTAM durumu ve önerilen aksiyonlar dahil tüm karar çıktıları backend'den gelir; arayüz yalnızca bu sonuçları görselleştirir ve operatöre sunar.

## Backend Entegrasyonu

Ana backend referansı: `YZT-MEVZUU-26/entegrasyon/backend/main.py` (FastAPI, port 8000).

`src/services/existing-backend-adapter.ts` şu an desteklenen gerçek endpoint/akışları kullanır:

- `GET /durum` — oturum durumu, 1.5 sn periyotla poll edilir
- `WS /hedefler` — canlı hedef/analiz verisi akışı
- `GET /video` — MJPEG video akışı
- `POST /oturum/durdur` — oturumu durdurma
- `GET /referans?model=` — VRAG referans görselleri

Backend'in Türkçe alan adları (`sinif`, `guven`, `vlm.gercek_tahmin`, `llm.risk` vb.) `src/services/backend-parser.ts` içinde kanonik frontend veri modeline (`src/types/operator.ts`) çevrilir; backend'in henüz sağlamadığı alanlar uydurulmadan `undefined`/`"pending"`/`"unknown"` olarak bırakılır.

> **Not:** `POST /oturum/baslat` backend'de sunucu tarafında bir dosya yolu (`video_yolu`) bekler. Tarayıcıdan seçilen bir dosya bu yolu sağlayamadığı için mevcut adapter yeni oturum başlatmayı desteklemez (`start`/`pause`/`resume`/`restart` `unsupported` döner); frontend yalnızca zaten backend'de başlatılmış bir oturumu izleyip durdurabilir. **Yeni oturum başlatma entegrasyonu final birleşimde çözülmelidir.**

## Şartname Uyumu

Arayüz, backend'den gelen aşağıdaki çıktıları göstermek üzere tasarlanmıştır:

- hedef/platform kimliği
- güven bilgisi
- analiz aşamaları (tespit, VRAG, VLM, LLM)
- zaman damgalı olaylar
- risk/değerlendirme
- nihai analiz sonucu
- önerilen aksiyon
- operatör doğrulaması gereken durumlar

Tam şartname detayı için `FRONTEND_SPEC.md` kaynak alınmalıdır; bu README yalnızca arayüzün hangi çıktı kategorilerini göstermek üzere tasarlandığını özetler, tam şartname uyumluluğunu garanti etmez.

## Birleştirme Notları

- Production'da `npm run build:backend` (veya `VITE_DATA_SOURCE=backend` ile `npm run build`) kullanılmalı.
- Mevcut backend adapter (`existing-backend-adapter.ts`) korunmalı; yeni contract/endpoint uydurulmamalı.
- Frontend'e karar/analiz mantığı eklenmemeli — tüm karar çıktıları backend'den gelmeli.
- `POST /oturum/baslat` (sunucu taraflı `video_yolu`) ile yeni oturum başlatma akışı final entegrasyonda çözülmelidir.
- `VITE_API_BASE_URL` / `VITE_WS_BASE_URL` deployment'a göre ayarlanmalıdır; backend aynı origin'den `/goruntule/` altında servis edildiğinde bu değerler boş bırakılabilir.
