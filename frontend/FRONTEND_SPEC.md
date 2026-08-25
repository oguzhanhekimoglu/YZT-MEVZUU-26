# MEVZUU Frontend Tasarım ve Entegrasyon Rehberi

Bu belge, MEVZUU ana operatör arayüzünün mevcut proje dizininden bağımsız bir klasörde sıfırdan geliştirilmesi ve daha sonra bu projeye sorunsuz biçimde entegre edilmesi için hazırlanmış eksiksiz devir dokümanıdır.

Yeni bir sohbette frontend geliştirmeye başlanırken bu dosyanın tamamı bağlam olarak verilmelidir. Bu belge ürün kararlarını, kullanıcı deneyimini, görsel sistemi, mock veri sözleşmesini, mevcut backend sözleşmesini ve entegrasyon sırasında backend'e eklenecek ihtiyaçları birbirinden ayırır.

## 1. Görev Tanımı

Bağımsız bir klasörde yalnızca frontend geliştirilecektir. Amaç, mevcut `entegrasyon/web/index.html` arayüzünün yerine geçecek production seviyesinde yeni bir ana operatör arayüzü hazırlamaktır.

Yeni arayüz:

- Video dosyasını bilgisayardaki klasörden seçebilmelidir.
- Video analizini başlatma, duraklatma/devam ettirme, durdurma ve başa alma kontrollerini sunmalıdır.
- Farklı video çözünürlüklerinde yerleşimi ve yazıları kaydırmamalıdır.
- Canlı video, aktif hedefler, kritik olaylar ve nihai kararı tek masaüstü ekranında göstermelidir.
- Ana kullanıcıya önce nihai sonucu göstermelidir.
- VRAG, VLM, LLM ve nesne tespiti ayrıntılarını açılabilir Analiz Süreci çekmecesinde sunmalıdır.
- Zaman damgalı olayları tıklanabilir timeline üzerinde göstermelidir.
- Şartnameye uygun genel video özeti, olaylar, risk ve aksiyonları sunmalıdır.
- Mock verilerle tamamen çalışmalı; gerçek backend'e geçerken bileşenlerin yeniden yazılmasını gerektirmemelidir.
- Tamamen yerel/offline çalışmaya uygun olmalı; harici font, ikon, analytics, CDN veya bulut servisi kullanmamalıdır.

Bu aşamada backend kodu değiştirilmemelidir. Mevcut ve planlanan backend özellikleri adaptör katmanında ayrılmalıdır.

## 2. Ürün Kimliği

Logo henüz yoktur. Yapay veya geçici bir logo üretilmemelidir.

Üst sol marka alanı:

```text
MEVZUU
Hava Sahası Karar Destek Sistemi
```

- `MEVZUU` ana ürün adıdır.
- `Hava Sahası Karar Destek Sistemi` alt başlıktır.
- `Gözcü AI` veya başka bir ürün adı kullanılmamalıdır.
- Gelecekte logo eklenecek kadar esnek bir marka bileşeni hazırlanmalıdır.
- TEKNOFEST logosu ürün logosu gibi kullanılmamalıdır.

## 3. Temel Kullanıcı Soruları

Arayüz ilk bakışta şu üç soruyu cevaplamalıdır:

1. Ne tespit edildi?
2. Risk seviyesi nedir?
3. Operatör ne yapmalıdır?

Teknik ayrıntılar ana sonucu gölgelememelidir. “Bu sonuca nasıl ulaşıldı?” sorusunun cevabı açılabilir Analiz Süreci çekmecesinde bulunmalıdır.

## 4. Terminoloji ve Kesin Kararlar

- Arayüzde “Düşünce Zinciri” denmemelidir.
- Doğru ad: `Analiz Süreci`.
- Gizli model muhakemesi veya token bazlı chain-of-thought gösterilmemelidir.
- Yalnız doğrulanabilir ara çıktılar, araç kontrolleri, model sonuçları ve karar gerekçeleri gösterilmelidir.
- Yön/gidiş yönü bilgisi hiçbir ekranda kullanılmamalıdır.
- VLM’nin değeri `Tehdit hipotezi`, LLM/operasyonel sistemin sonucu `Nihai risk` olarak adlandırılmalıdır.
- `Geçici` ve `Nihai` sonuçlar açıkça ayrılmalıdır.
- Hedef bazlı sonuç ile video geneli sonucu birbirine karıştırılmamalıdır.

## 5. Önerilen Teknoloji

Bağımsız frontend için önerilen yığın:

- React
- TypeScript
- Vite
- CSS Modules veya düzenli global token/component CSS yapısı
- Yerel SVG ikonlar veya açık kaynak ikon paketinin build içine alınan bileşenleri
- Test için Vitest ve React Testing Library
- İsteğe bağlı uçtan uca test için Playwright

Zorunlu olmayan kütüphaneler eklenmemelidir. Büyük bir UI framework’ü ancak bütün bileşenlerde tutarlı biçimde kullanılacaksa seçilmelidir. Tailwind kullanılabilir fakat şart değildir. Tasarım tokenları merkezi olarak tanımlanmalıdır.

Harici bağımlılık sınırları:

- Google Fonts/CDN kullanılmamalıdır.
- Harici görsel API kullanılmamalıdır.
- Analytics/telemetry servisi kullanılmamalıdır.
- Mock servis için uzak API kullanılmamalıdır.
- Tüm assetler ve fontlar repository içinde bulunmalıdır.

## 6. Önerilen Bağımsız Dosya Yapısı

Frontend mevcut projenin dışında örneğin `mevzuu-operator-ui/` klasöründe geliştirilebilir:

```text
mevzuu-operator-ui/
├── public/
├── src/
│   ├── app/
│   │   ├── App.tsx
│   │   └── providers.tsx
│   ├── assets/
│   │   ├── fonts/
│   │   └── icons/
│   ├── components/
│   │   ├── brand/
│   │   ├── controls/
│   │   ├── layout/
│   │   ├── status/
│   │   └── ui/
│   ├── features/
│   │   ├── analysis-process/
│   │   ├── final-result/
│   │   ├── session/
│   │   ├── targets/
│   │   ├── timeline/
│   │   └── video/
│   ├── mocks/
│   │   ├── fixtures/
│   │   ├── mock-adapter.ts
│   │   └── mock-scenario.ts
│   ├── services/
│   │   ├── contracts.ts
│   │   ├── data-source.ts
│   │   ├── existing-backend-adapter.ts
│   │   ├── planned-backend-adapter.ts
│   │   └── websocket-client.ts
│   ├── styles/
│   │   ├── reset.css
│   │   ├── tokens.css
│   │   └── globals.css
│   ├── types/
│   │   └── operator.ts
│   └── main.tsx
├── .env.example
├── index.html
├── package.json
├── tsconfig.json
└── vite.config.ts
```

Temel mimari kuralı:

```text
UI bileşenleri → DataSource arayüzü → Mock veya Backend adaptörü
```

UI doğrudan `fetch`, WebSocket veya mock JSON çağırmamalıdır. Bütün veri erişimi tek bir `OperatorDataSource` arayüzünün arkasında olmalıdır. Böylece geliştirmede mock adaptörü, entegrasyonda backend adaptörü seçilir.

Örnek ortam değişkenleri:

```env
VITE_DATA_SOURCE=mock
VITE_API_BASE_URL=http://127.0.0.1:8000
VITE_WS_BASE_URL=ws://127.0.0.1:8000
```

Production build aynı FastAPI origin’inden servis edildiğinde API adresleri göreli kullanılmalıdır.

## 7. Masaüstü Ana Yerleşim

Ana operatör ekranı standart masaüstünde sayfanın kendisini aşağı kaydırmadan `100dvh` içinde çalışmalıdır.

```text
┌─────────────────────────────────────────────────────────────────────────┐
│ MEVZUU / alt başlık │ Sistem │ Yerel │ Video │ Süre │ Hedef │ Kritik │
├─────────────────────────────────────────────────────────────────────────┤
│ Video Seç │ Başlat │ Duraklat/Devam │ Durdur │ Başa Al │ Tam Ekran    │
├──────────────────────────────────────┬──────────────────────────────────┤
│                                      │ Seçili Hedef Kimliği             │
│ Sabit 16:9 Video Alanı               │ Model · ülke · üretici · rol     │
│                                      │ Kimlik güveni · nihai risk       │
│                                      ├──────────────────────────────────┤
│                                      │ Açılabilir Analiz Süreci satırı  │
├──────────────────────────────────────┤                                  │
│ Tıklanabilir Olay Timeline’ı         │ Nihai video özeti                 │
│ Seçili olay ayrıntısı                │ Olaylar · risk · aksiyonlar       │
└──────────────────────────────────────┴──────────────────────────────────┘
```

Önerilen oranlar:

- Sol sütun yaklaşık `%62`.
- Sağ sütun yaklaşık `%38`.
- Sağ sütunun okunabilir minimum genişliği korunmalıdır.
- Grid içindeki çocuklarda `min-width: 0` kullanılmalı; uzun metin yatay taşma oluşturmamalıdır.
- Sayfa değil, yalnız gerektiğinde sağ içerik paneli veya drawer kendi içinde kaymalıdır.
- Ana kontroller tek satırda kalmalı; dar masaüstünde kontrollü şekilde sıkışmalı veya ikincil kontroller menüye alınmalıdır.

Standart hedef ekranlar:

- 1920×1080
- 1600×900
- 1440×900
- 1366×768

Bu boyutlarda ana video, nihai sonuç, kontroller ve kritik olay alanı aynı viewport içinde kalmalıdır.

## 8. Responsive Davranış

### Büyük ve standart masaüstü

- Video solda, sonuç sağda.
- Timeline video altında.
- Analiz Süreci sağdan drawer olarak açılır.
- Sayfa kaydırılmaz.

### Tablet

- Video üstte, nihai sonuç altında.
- Timeline video altında kalır.
- Drawer ekranın büyük bölümünü kaplar.
- Gerekirse sayfa dikey kaydırılabilir.

### Mobil

- Tek viewport zorunluluğu yoktur.
- Video, kimlik, risk, özet, aksiyonlar, timeline ve teknik detaylar alt alta gelir.
- Dokunma hedefleri en az yaklaşık 40-44 px olmalıdır.
- Drawer ekranın yaklaşık `%92-100` genişliğini kullanabilir.

## 9. Üst Sistem Çubuğu

Sürekli görünmesi gereken bilgiler:

- Marka adı ve alt başlık
- Backend bağlantı durumu
- Pipeline/oturum durumu
- Tamamen yerel/offline çalışma göstergesi
- Video adı
- Geçen/Toplam video süresi
- Aktif hedef sayısı
- Kritik olay sayısı

Örnek:

```text
MEVZUU                                      ● Sistem Hazır   ● Tamamen Yerel
Hava Sahası Karar Destek Sistemi            00:42 / 02:16   2 Hedef   1 Kritik
```

Olası sistem durumları:

- Hazır
- Video seçildi
- Video yükleniyor
- Modeller hazırlanıyor
- Analiz sürüyor
- Analiz duraklatıldı
- Analiz durduruldu
- Analiz tamamlandı
- Yeniden bağlanılıyor
- Hata

Bağlantı koptuğunda son veriler silinmemeli; `Son veri: 8 sn önce` benzeri güncellik bilgisi gösterilmelidir.

## 10. Video Seçme ve Oturum Kontrolleri

### Video seçilmeden önce

Sabit video alanının içinde sade bir yükleme görünümü:

```text
Video Analizi

Videoyu buraya sürükleyin
veya
[ Dosya Seç ]

MP4, MOV, AVI, MKV
```

Dosya seçildikten sonra gösterilecek bilgiler:

- Dosya adı
- Dosya boyutu
- Format
- Süre
- Çözünürlük
- Önizleme

Ana eylemler:

```text
[ Analizi Başlat ] [ Başka Video Seç ]
```

### Analiz kontrolleri

- `Video Değiştir`
- `Başlat`
- `Duraklat`
- `Devam Et`
- `Durdur`
- `Başa Al`
- `Tam Ekran`

Buton etkinlikleri duruma göre değişmelidir:

| Durum | Etkin kontroller |
|---|---|
| Video yok | Video Seç |
| Video hazır | Başlat, Video Değiştir |
| Analiz sürüyor | Duraklat, Durdur, Tam Ekran |
| Duraklatıldı | Devam Et, Durdur, Başa Al |
| Durduruldu | Başa Al, Yeni Video, Rapor varsa görüntüle |
| Tamamlandı | Başa Al, Yeni Video, JSON/Rapor indir |

Davranış tanımları:

- `Duraklat`: Konum ve sonuçlar korunur, devam edilebilir.
- `Durdur`: Oturum sonlanır, mevcut sonuçlar korunur.
- `Başa Al`: Tracker, olaylar, analiz sonuçları ve video zamanı temizlenerek aynı video için yeni oturum başlatılır.
- `Video Değiştir`: Mevcut oturum sonuçlarını koruma/temizleme konusunda kullanıcıdan onay ister.
- `Başa Al` geri döndürülemez sonuç temizliği yapacağından onay istemelidir.

## 11. Video Alanı ve Yerleşim Kararlılığı

Video çözünürlüğü hiçbir zaman layout ölçülerini belirlememelidir.

Zorunlu davranışlar:

- Video dış kutusu sabit `16:9` oranlıdır.
- Video `object-fit: contain` ile yerleşir.
- Dikey veya 4:3 videolarda koyu letterbox alanları kalır.
- Video esnetilmez veya kırpılmaz.
- Video yüklenmeden önce aynı boyutta placeholder vardır.
- Video gelince hiçbir panel ve yazı yer değiştirmez.
- Sağ panel genişliği videodan etkilenmez.
- Uzun dosya/model adları satır kırar veya ellipsis kullanır; grid’i genişletmez.
- JSON ve teknik metinler yatay taşma oluşturmaz.

Mevcut backend MJPEG akışı sunduğunda `<video>` değil `<img>` kullanılmalıdır. Mock modda normal video önizlemesi kullanılabilir; bileşen veri kaynağı türüne göre MJPEG veya yerel preview gösterebilmelidir.

## 12. Çoklu Hedef Yönetimi

Bir videoda birden fazla hedef olabilir. Sağ panel tek hedef varsayımıyla tasarlanmamalıdır.

Kompakt hedef seçici:

```text
[ Hedef #4 · F-16 · Yüksek ] [ Hedef #7 · Bilinmiyor · Orta ]
```

Analiz Süreci drawer’ında kapsam seçici:

```text
[ Video Geneli ] [ Hedef #4 ] [ Hedef #7 ]
```

- `Video Geneli`: Genel özet, olaylar, genel risk, genel aksiyonlar.
- `Hedef #N`: Nesne tespiti, VRAG, VLM ve hedefe ait LLM sonucu.

Varsayılan hedef önceliği:

1. Kritik riskli hedef
2. Yüksek riskli hedef
3. Yeni hedef
4. Kullanıcının manuel seçimi

Kullanıcı manuel hedef seçtikten sonra otomatik seçim, kritik bir kullanıcı uyarısı dışında seçimi zorla değiştirmemelidir.

`id = -1` backend tarafından hayalet/sonuç koruma hedefi olarak gelebilir. Bu kayıt normal aktif hedef kartı olarak gösterilmemelidir.

## 13. Sağ Panel: Hedef Kimliği ve Nihai Sonuç

### Hedef kimliği

İlk bakışta gösterilecekler:

- Model adı
- Ülke orijini
- Üretici
- Rol
- Araç sınıfı
- Kimlik güveni
- Takip ID’si
- Hedef risk seviyesi
- Uygunsa küçük referans görsel

Yön bilgisi gösterilmez.

Örnek:

```text
F-16 Fighting Falcon
ABD · Lockheed Martin
Çok amaçlı savaş uçağı

Kimlik güveni %91            Hedef riski ORTA
```

### Video geneli nihai sonuç

Şartname sırası korunmalıdır:

1. Genel video özeti
2. Zaman damgalı olaylar
3. Genel risk değerlendirmesi ve gerekçesi
4. Önceliklendirilmiş aksiyon önerileri

Örnek:

```text
Genel Video Özeti
Videoda F-16 Fighting Falcon olarak değerlendirilen bir hava aracı
tespit edilmiştir. Hedefin kimliği görsel analizle doğrulanmış ve
operasyonel kayıt eksikleri nedeniyle genel risk Orta belirlenmiştir.

Genel Risk: ORTA
Uçuş izni ve uçuş planı doğrulanamadığı için operatör teyidi gereklidir.

Önerilen Aksiyonlar
1. Takibi kesintisiz sürdür
2. Operatör kimlik doğrulaması gerçekleştir
3. İzin ve uçuş planı kayıtlarını kontrol et
```

- Özet 3-5 satırda kalmalıdır.
- Uzunsa `Devamını göster` ile açılmalıdır.
- Analiz sürerken `Geçici sonuç` etiketi bulunmalıdır.
- Tamamlandığında `Nihai sonuç` etiketi bulunmalıdır.
- Risk yalnız renk ile anlatılmamalı; ikon, metin ve gerekçe birlikte kullanılmalıdır.
- Ana ekran ve drawer içindeki Nihai Çıktı aynı veri nesnesini kullanmalıdır.

## 14. Analiz Süreci: Kapalı Satır

Ana ekranda kompakt bir durum satırı bulunur.

Çalışırken:

```text
◉ Analiz sürüyor · Risk ve operasyonel durum değerlendiriliyor...  Detayları Gör ›
```

Tamamlandığında:

```text
✓ Analiz tamamlandı · Nihai çıktı hazır  Detayları Gör ›
```

Uyarılı tamamlanma:

```text
⚠ Analiz tamamlandı · Kimlik doğrulamasında belirsizlik var  Detayları Gör ›
```

Aşamaya göre durum cümleleri:

- Hedefler tespit ediliyor...
- VRAG model eşleştirmesi yapılıyor...
- VLM görsel doğrulama yapıyor...
- Operasyonel kayıtlar kontrol ediliyor...
- Risk ve operasyonel durum değerlendiriliyor...
- LLM nihai karar çıktısını hazırlıyor...
- Video geneli özetleniyor...

Satır ana layout’u büyütmemelidir.

## 15. Analiz Süreci Drawer’ı

Kapalı satıra tıklanınca sağdan drawer açılır.

Özellikleri:

- Masaüstünde yaklaşık `480-520 px` genişlik.
- Ana sayfayı ve videoyu yeniden boyutlandırmaz.
- Sayfayı aşağı doğru büyütmez.
- Kendi içinde kayar.
- Üst başlığı sabit kalır.
- `Esc`, dış alana tıklama ve kapatma butonuyla kapanır.
- Video arka planda çalışmaya devam eder.
- Açıldığında odak drawer içine alınır; kapandığında tetikleyiciye geri döner.

Özet görünüm:

```text
Analiz Süreci                         Hedef #4

✓ Nesne Tespiti               Tamamlandı · 0.03 sn
  Hedef #4 · İHA · Güven %91

✓ VRAG Model Eşleştirmesi      Tamamlandı · 0.4 sn
  F-16 Fighting Falcon · %91

✓ VLM Görsel Doğrulama         Tamamlandı · 4.2 sn
  Askerî uçak · Sonuç tutarlı

◉ LLM Karar Desteği            Çalışıyor · 1.8 sn
  Risk ve operasyonel durum değerlendiriliyor...

○ Nihai Çıktı                  Bekliyor
  Önceki aşamalar bekleniyor
```

Durum ikonları:

| İkon | Durum |
|---|---|
| `○` | Bekliyor |
| `◉` | Çalışıyor |
| `✓` | Tamamlandı |
| `⚠` | Belirsiz/Uyarılı |
| `×` | Hata |

Renk tek başına anlam taşımamalıdır; ikonun yanında durum metni bulunmalıdır.

### Accordion davranışı

- Her aşama tıklanabilir.
- Tamamlanan aşamaya tıklanınca tamamlanan ayrıntılı çıktı açılır.
- Çalışan aşamaya tıklanınca biten alt adımlar ve mevcut durum gösterilir.
- Bekleyen aşama açılırsa neden beklediği gösterilir, sahte sonuç üretilmez.
- Aynı anda yalnız bir aşamanın ayrıntısı açık kalır.
- Aşama tamamlandığında açık panel kapanmadan canlı şekilde sonuç görünümüne dönüşür.
- İşlem süresi backend ölçümü veya kontrollü mock veriden gelir; frontend tahmin üretmez.
- `İşlem süresi` ile `Son güncelleme` birbirinden ayrılır.

## 16. Analiz Aşamalarının Ayrıntıları

### 16.1 Nesne Tespiti ve Takip

Gösterilecekler:

- Hedef ID
- Tespit sınıfı
- Tespit güveni
- Takip durumu
- `hits`/takip kararlılığı
- Hareket hızı
- Zigzag skoru

Yön bilgisi gösterilmez. `bbox` yalnız teknik görünümde gerekirse bulunabilir.

### 16.2 VRAG Model Eşleştirmesi

Gösterilecekler:

- Referans görsel
- En iyi model
- Benzerlik skoru
- Ülke
- Üretici
- Rol
- Kategori
- İlk 3-5 benzersiz aday
- Aday skor barları
- Düşük güven uyarısı
- İlk iki aday farkı/margin mevcutsa açıklama

Aynı model farklı referanslardan tekrar gelirse operatör görünümünde model bazında birleştirilmelidir. Teknik görünümde ham sonuç korunabilir.

### 16.3 VLM Görsel Doğrulama

Gösterilecekler:

- Görsel tahmin
- Araç türü
- Araç sınıfı
- Ülke hipotezi
- Tehdit hipotezi
- VRAG tutarlılığı
- Doğrulama/çelişki
- Görsel değerlendirme açıklaması
- İşlem süresi
- Son güncelleme

Yön bilgisi gösterilmez.

Çelişki örneği:

```text
⚠ Görsel doğrulama çelişkisi
VRAG: F-16 Fighting Falcon
VLM: F-15 Eagle
Sonuç kesin kimlik olarak değerlendirilmemelidir.
```

### 16.4 LLM Operasyonel Karar Desteği

Gösterilecekler:

- Nihai risk
- Karar durumu
- Envanter durumu
- Uçuş izni durumu
- Uçuş planı durumu
- NOTAM durumu
- Operatör teyidi gereksinimi
- Kısa operasyonel değerlendirme
- Riski artıran faktörler
- Riski azaltan faktörler
- Önceliklendirilmiş aksiyonlar
- İşlem süresi
- Son güncelleme

Uzun tek paragraf yerine yapılandırılmış bölümler kullanılmalıdır.

Çalışırken doğrulanabilir alt adımlar gösterilebilir:

```text
✓ Platform kaydı kontrol edildi
✓ Türkiye envanteri kontrol edildi
◉ Uçuş izni ve uçuş planı inceleniyor
○ NOTAM kontrolü bekliyor
○ Nihai risk değerlendirmesi bekliyor
○ Aksiyon önerileri bekliyor
```

### 16.5 Nihai Çıktı

Gösterilecekler:

- Hava aracı genel bilgileri
- Video özeti
- Zaman damgalı olaylar
- Genel risk ve gerekçesi
- Aksiyonlar
- Geçici/nihai durum
- JSON görüntüleme, kopyalama ve indirme

## 17. Timeline ve Zaman Damgalı Olaylar

Timeline video alanının altında, sabit yüksekliğe ayrılmış bölgede bulunmalıdır.

```text
00:00 ─── ● 00:18 ───── ▲ 00:42 ───── ◆ 00:51 ─── 01:10
            Bilgi           Yüksek          Kritik
```

### Timeline kuralları

- Her semantik olay zaman damgalı ve tıklanabilir olmalıdır.
- Klavye ile odaklanabilir/seçilebilir olmalıdır.
- Hover/focus tooltip’i zaman, olay ve hedefi göstermelidir.
- Seçilen olay belirginleşir, diğerleri hafifçe geri çekilir.
- Olay seçimi layout yüksekliğini değiştirmez.
- Çok sayıda olay varsa timeline kendi içinde yatay kayar veya zoom/gruplama kullanır.
- Aynı zaman çevresindeki olaylar küme olarak gösterilebilir (`3 olay`).
- Filtreler: Tümü, Kritik, Yüksek, hedef bazlı filtre.
- Her model güncellemesi olay yapılmamalıdır.

Timeline’a alınacak anlamlı olaylar:

- Hedef ilk görüldü
- Model kimliği belirlendi
- Kimlik sonucu önemli biçimde değişti
- VLM doğrulaması veya çelişkisi oluştu
- Risk seviyesi değişti
- Kritik durum oluştu
- Operatör teyidi gerekti
- Hedef kayboldu
- Analiz tamamlandı

### Olay ayrıntısı

Timeline işaretine tıklanınca aynı sabit alanın ayrıntı bölümünde gösterilecekler:

- Olay zamanı
- Başlangıç/bitiş zamanı
- Olay türü
- Türkçe açıklama
- Risk seviyesi
- İlgili hedef
- Güven skoru
- Kritik durumu
- Devam ediyor/tamamlandı durumu
- İlgili aksiyonlar
- Kritik olay karesi varsa görsel

Eylemler:

- `İlgili Hedefi Gör`
- `Analiz Ayrıntılarını Aç`
- Backend seek desteği geldiğinde `Bu Ana Git`

`Analiz Ayrıntılarını Aç`, drawer’ı açmalı; ilgili hedefi ve olayla ilişkili aşamayı otomatik seçmelidir.

MJPEG akışında doğrudan seek yapılamaz. `Bu Ana Git` özelliği backend desteği gelene kadar devre dışı veya gizli olmalıdır. Sahte seek davranışı yapılmamalıdır.

## 18. Yapılandırılmış Çıktı

Ana kullanıcı ham JSON okumaya zorlanmamalıdır. Nihai sonuçta ikincil eylemler:

- `JSON'u Görüntüle`
- `Panoya Kopyala`
- `JSON İndir`
- Daha sonra `Rapor İndir`

JSON modal veya drawer içinde formatlanmış gösterilmelidir. Şartname uyumlu üst düzey yapı:

```json
{
  "summary": "Videoda bir hava aracı tespit edilmiş ve operasyonel risk değerlendirilmiştir.",
  "aircraft": {
    "model": "F-16 Fighting Falcon",
    "country_origin": "ABD",
    "manufacturer": "Lockheed Martin",
    "role": "Çok amaçlı savaş uçağı"
  },
  "events": [
    {
      "time": "00:18",
      "event": "Hava aracı kimliği belirlendi",
      "risk": "INFO",
      "critical": false
    }
  ],
  "risk": "MEDIUM",
  "risk_reason": "Uçuş izni ve uçuş planı doğrulanamadı.",
  "actions": [
    "Takibi sürdür",
    "Operatör incelemesi iste",
    "İzin kayıtlarını kontrol et"
  ]
}
```

## 19. Görsel Tasarım Sistemi

Tasarım yönü:

> Modern, koyu, kontrollü ve teknik operasyon konsolu.

Kaçınılacaklar:

- Neon radar estetiği
- Hareketli arka plan
- Parçacık efektleri
- Ağır glassmorphism
- Her kartta gradient
- Büyük parlak gölgeler
- Sürekli yanıp sönen uyarılar
- Aşırı yuvarlak/kapsül paneller
- Gereksiz ikon yoğunluğu

### Kesin renk paleti

```text
Background          #0B0F14
Surface             #10161D
Card                #151C24
Elevated            #1A232D
Border              #26313D

Text Primary        #E7EDF4
Text Secondary      #A8B3C1
Text Muted          #758293
Text Disabled       #566273

Accent              #3CBFC4
Accent Hover        #55CED2
Information         #5595E8
Success             #49B980
Warning             #E5B454
High Risk           #EC7A5C
Critical            #F05262
Unknown             #8D99A8
```

Renkler dekorasyon için değil, anlam için kullanılmalıdır. Ana vurgu ekranın küçük bölümünde kalmalıdır.

### Risk renkleri

| Risk | Ön plan | Yumuşak arka plan |
|---|---|---|
| Düşük | `#49B980` | `rgba(73,185,128,.12)` |
| Orta | `#E5B454` | `rgba(229,180,84,.12)` |
| Yüksek | `#EC7A5C` | `rgba(236,122,92,.12)` |
| Kritik | `#F05262` | `rgba(240,82,98,.13)` |
| Bilinmiyor | `#8D99A8` | `rgba(141,153,168,.10)` |

### Analiz durum renkleri

| Durum | Renk |
|---|---|
| Bekliyor | `#667383` |
| Çalışıyor | `#3CBFC4` |
| Tamamlandı | `#49B980` |
| Uyarılı | `#E5B454` |
| Hata | `#F05262` |

### Tipografi

- Ana font: lokal `Inter Variable`.
- Sayısal/teknik font: lokal `JetBrains Mono`.
- Sistem font fallback’i tanımlanmalıdır.
- Türkçe karakter desteği doğrulanmalıdır.

Ölçek:

```text
Uçak modeli         24-28 px / 650
Nihai risk          20-24 px / 700
Sayfa başlığı       18-20 px / 650
Panel başlığı       14-16 px / 600
Ana gövde           14 px / 400
Yardımcı metin      12-13 px / 400
Teknik etiket       11-12 px / 500
```

Tamamı büyük harf yalnız kısa etiketlerde kullanılmalıdır.

### Yüzeyler ve ölçüler

```text
Ana panel radius    12 px
İç kart radius      8 px
Buton radius        8 px
Risk rozeti         6 px
Durum rozeti        999 px
Standart panel içi  16-20 px
```

- Ana kartlarda ağır gölge kullanılmaz.
- Drawer/modal için `0 20px 60px rgba(0,0,0,.38)` seviyesinde gölge kullanılabilir.
- Seçili panelde turkuaz ince sınır veya sol çizgi kullanılabilir.
- Kritik panelde kırmızı ince sol çizgi yeterlidir; tüm panel kırmızı yapılmaz.

### Spacing sistemi

```text
4, 8, 12, 16, 20, 24, 32 px
```

### Animasyon

```text
Hover              120-160 ms
Accordion          180-220 ms
Drawer             220-280 ms
Durum değişimi     yaklaşık 180 ms
```

Yalnız işlevsel animasyonlar:

- Drawer açılışı
- Accordion geçişi
- Aktif analiz ikonunda hafif pulse
- Yeni olayda tek seferlik kısa vurgu
- Progress geçişi

`prefers-reduced-motion` desteklenmelidir.

## 20. Erişilebilirlik

- Risk/durum yalnız renkle anlatılmamalıdır.
- Tüm butonlarda görünür metin veya erişilebilir ad olmalıdır.
- Drawer ve modal focus trap kullanmalıdır.
- `Esc` ile kapanmalıdır.
- Timeline olayları gerçek button semantics ile klavye erişimli olmalıdır.
- Görünür focus stilleri bulunmalıdır.
- Kontrast oranları WCAG AA hedeflemelidir.
- Canlı durum mesajları gerektiğinde ölçülü `aria-live` kullanmalıdır.
- Sürekli değişen WebSocket verileri ekran okuyucuyu spamlememelidir.
- Kritik bildirimler anlaşılır Türkçe ile sunulmalıdır.

## 21. Bütün UI Durumları

Mock geliştirmede şu durumların tamamı ayrı senaryo olarak hazırlanmalıdır:

1. İlk açılış, video yok
2. Dosya seçildi
3. Video yükleniyor
4. Modeller hazırlanıyor
5. Analiz başladı, yalnız nesne tespiti hazır
6. VRAG çalışıyor
7. VRAG tamamlandı, VLM çalışıyor
8. VLM tamamlandı, LLM çalışıyor
9. Analiz tamamlandı
10. Düşük kimlik güveni
11. VRAG/VLM çelişkisi
12. Kısmi sonuç, VLM hatası
13. LLM/operasyonel servis hatası
14. WebSocket bağlantısı koptu ve yeniden bağlanıyor
15. Analiz duraklatıldı
16. Analiz durduruldu
17. Video bitti
18. Hedef yok
19. Tek hedef
20. Çoklu hedef
21. Çok sayıda timeline olayı
22. Kritik olay seçildi
23. Uzun model adı ve uzun Türkçe özet
24. Dar ekran/1366×768

## 22. Frontend İç Veri Modeli

Aşağıdaki sözleşme frontend’in canonical iç modelidir. Backend alanları doğrudan bileşenlere verilmemeli; adaptör bu modele dönüştürmelidir.

```ts
export type ProcessStatus =
  | "waiting"
  | "running"
  | "completed"
  | "warning"
  | "error";

export type RiskLevel =
  | "info"
  | "low"
  | "medium"
  | "high"
  | "critical"
  | "unknown";

export type SessionStatus =
  | "idle"
  | "file-selected"
  | "uploading"
  | "preparing"
  | "running"
  | "paused"
  | "stopped"
  | "completed"
  | "error";

export interface AircraftCandidate {
  model: string;
  score: number;
  country?: string;
  role?: string;
  referenceImageUrl?: string;
}

export interface DetectionDetail {
  targetId: number;
  className: string;
  confidence: number;
  trackingStatus: "active" | "lost" | "completed";
  hits: number;
  speedPxS?: number;
  zigzagScore?: number;
}

export interface VragDetail {
  model?: string;
  score?: number;
  lowConfidence: boolean;
  margin?: number;
  country?: string;
  manufacturer?: string;
  role?: string;
  category?: string;
  referenceImageUrl?: string;
  candidates: AircraftCandidate[];
}

export interface VlmDetail {
  visualPrediction?: string;
  vehicleType?: string;
  vehicleClass?: string;
  countryHypothesis?: string;
  threatHypothesis?: RiskLevel;
  verification?: string;
  vragConsistency?: string;
  visualAssessment?: string;
}

export interface ActionRecommendation {
  id: string;
  label: string;
  priority: "urgent" | "high" | "normal";
  reason?: string;
  requiresConfirmation?: boolean;
}

export interface LlmDetail {
  risk: RiskLevel;
  decision?: string;
  inventoryStatus?: string;
  permissionStatus?: string;
  flightPlanStatus?: string;
  notamStatus?: string;
  humanReviewRequired?: boolean;
  summary?: string;
  riskIncreasingFactors: string[];
  riskReducingFactors: string[];
  actions: ActionRecommendation[];
}

export interface AnalysisStep<T = unknown> {
  id: "detection" | "vrag" | "vlm" | "llm" | "final";
  title: string;
  status: ProcessStatus;
  statusText: string;
  summary?: string;
  durationMs?: number;
  updatedAt?: string;
  warning?: string;
  error?: string;
  substeps?: Array<{
    id: string;
    label: string;
    status: ProcessStatus;
  }>;
  detail?: T;
}

export interface TargetAnalysis {
  id: number;
  displayName: string;
  className: string;
  detectionConfidence: number;
  risk: RiskLevel;
  selected: boolean;
  detection: AnalysisStep<DetectionDetail>;
  vrag: AnalysisStep<VragDetail>;
  vlm: AnalysisStep<VlmDetail>;
  llm: AnalysisStep<LlmDetail>;
}

export interface TimelineEvent {
  id: string;
  targetId?: number;
  timeSeconds: number;
  timeLabel: string;
  startSeconds?: number;
  endSeconds?: number;
  title: string;
  description: string;
  risk: RiskLevel;
  critical: boolean;
  confidence?: number;
  status: "active" | "completed";
  relatedStep?: AnalysisStep["id"];
  snapshotUrl?: string;
  actions?: ActionRecommendation[];
}

export interface FinalOutput {
  status: "pending" | "provisional" | "final" | "partial";
  summary: string;
  aircraft?: {
    model?: string;
    countryOrigin?: string;
    manufacturer?: string;
    role?: string;
    vehicleClass?: string;
    identityConfidence?: number;
  };
  events: TimelineEvent[];
  risk: RiskLevel;
  riskReason?: string;
  actions: ActionRecommendation[];
  generatedAt?: string;
}

export interface OperatorSession {
  id: string;
  status: SessionStatus;
  connection: "connecting" | "connected" | "reconnecting" | "disconnected";
  localMode: boolean;
  sourceName?: string;
  durationSeconds?: number;
  currentSeconds: number;
  progress?: number;
  frameNumber: number;
  activeTargetCount: number;
  criticalEventCount: number;
  streamUrl?: string;
  selectedTargetId?: number;
  targets: TargetAnalysis[];
  events: TimelineEvent[];
  finalOutput: FinalOutput;
  lastMessageAt?: string;
}
```

Alanlar eksik gelebilir. UI `null/undefined`, boş dizi, bekleyen durum ve kısmi sonuçları güvenli biçimde ele almalıdır.

## 23. Mock Veri Yaklaşımı

Mocklar yalnız statik tek JSON olmamalıdır. Pipeline’ın zaman içinde ilerlediği senaryo simülasyonu hazırlanmalıdır.

Önerilen mock akışı:

```text
0.0 sn  Oturum hazırlanıyor
0.8 sn  Video başladı
1.2 sn  Hedef #4 tespit edildi
2.0 sn  VRAG çalışıyor
2.5 sn  VRAG: F-16 Fighting Falcon %91
3.0 sn  VLM çalışıyor
7.2 sn  VLM: Askerî uçak / Sabit kanat, VRAG tutarlı
7.4 sn  LLM çalışıyor
13.3 sn LLM: Orta risk, operatör teyidi gerekli
13.6 sn Nihai çıktı hazır
```

Mock denetimleri geliştirme modunda erişilebilir olabilir:

- Senaryoyu başlat
- Sonraki aşamaya geç
- Hızlandır
- Uyarı üret
- VLM hatası üret
- WebSocket kopması simüle et
- Kritik olay ekle
- İkinci hedef ekle
- Analizi tamamla

Bu kontroller production build’de görünmemelidir.

### Projedeki mevcut bilgilere dayalı örnek mock

```ts
export const mockTarget: TargetAnalysis = {
  id: 4,
  displayName: "F-16 Fighting Falcon",
  className: "İHA",
  detectionConfidence: 0.91,
  risk: "medium",
  selected: true,
  detection: {
    id: "detection",
    title: "Nesne Tespiti",
    status: "completed",
    statusText: "Tamamlandı",
    summary: "Hedef #4 · İHA · Güven %91",
    durationMs: 30,
    detail: {
      targetId: 4,
      className: "İHA",
      confidence: 0.91,
      trackingStatus: "active",
      hits: 38,
      speedPxS: 24.7,
      zigzagScore: 0.12
    }
  },
  vrag: {
    id: "vrag",
    title: "VRAG Model Eşleştirmesi",
    status: "completed",
    statusText: "Tamamlandı",
    summary: "F-16 Fighting Falcon · Benzerlik %91",
    durationMs: 400,
    detail: {
      model: "F-16 Fighting Falcon",
      score: 0.91,
      lowConfidence: false,
      country: "ABD",
      manufacturer: "Lockheed Martin",
      role: "Çok amaçlı savaş uçağı",
      category: "Askerî uçak",
      candidates: [
        { model: "F-16 Fighting Falcon", score: 0.91, country: "ABD" },
        { model: "F-15 Eagle", score: 0.78, country: "ABD" },
        { model: "F/A-18 Hornet", score: 0.72, country: "ABD" }
      ]
    }
  },
  vlm: {
    id: "vlm",
    title: "VLM Görsel Doğrulama",
    status: "completed",
    statusText: "Tamamlandı",
    summary: "Askerî uçak · Sabit kanat · Sonuç tutarlı",
    durationMs: 4200,
    detail: {
      visualPrediction: "F-16 Fighting Falcon",
      vehicleType: "Askerî uçak",
      vehicleClass: "Sabit kanat",
      countryHypothesis: "Türkiye",
      threatHypothesis: "low",
      verification: "Onaylandı",
      vragConsistency: "Tutarlı",
      visualAssessment:
        "Görüntüde F-16 Fighting Falcon savaş uçağı görülmektedir. Görsel özellikler VRAG eşleşmesini desteklemektedir."
    }
  },
  llm: {
    id: "llm",
    title: "LLM Karar Desteği",
    status: "running",
    statusText: "Çalışıyor",
    summary: "Risk ve operasyonel durum değerlendiriliyor...",
    substeps: [
      { id: "platform", label: "Platform kaydı kontrol edildi", status: "completed" },
      { id: "inventory", label: "Türkiye envanteri kontrol edildi", status: "completed" },
      { id: "permission", label: "Uçuş izni ve uçuş planı inceleniyor", status: "running" },
      { id: "notam", label: "NOTAM kontrolü", status: "waiting" },
      { id: "risk", label: "Nihai risk değerlendirmesi", status: "waiting" }
    ],
    detail: {
      risk: "unknown",
      riskIncreasingFactors: [],
      riskReducingFactors: [],
      actions: []
    }
  }
};
```

Mock veriler gerçek sonuç iddiası değildir; yalnız UI geliştirme ve test içindir.

## 24. Mevcut Backend Sözleşmesi

Mevcut ana backend FastAPI’dir: `entegrasyon/backend/main.py`.

Mevcut frontend şu adresten servis edilir:

```text
http://127.0.0.1:8000/goruntule/
```

Mevcut endpointler:

| İşlev | Yöntem | Endpoint | Durum |
|---|---|---|---|
| Oturum başlat | POST | `/oturum/baslat` | Mevcut |
| Oturum durdur | POST | `/oturum/durdur` | Mevcut |
| Sistem durumu | GET | `/durum` | Mevcut |
| MJPEG video | GET | `/video` | Mevcut |
| Hedef WebSocket | WS | `/hedefler` | Mevcut |
| Referans görsel | GET | `/referans?model=...` | Mevcut |
| Metadata | GET | `/meta` | Mevcut |
| Tek görsel tanıma | POST | `/tani` | Endpoint var fakat işlev sınırlı |
| Geçmiş | GET | `/gecmis?adet=N` | Endpoint var fakat boş dönüyor |

### Oturum başlatma

```http
POST /oturum/baslat
Content-Type: application/json
```

```json
{
  "video_yolu": "C:\\tam\\yol\\video.mp4"
}
```

Başarılı cevap:

```json
{
  "ok": true,
  "kaynak": "C:\\tam\\yol\\video.mp4"
}
```

Bu sözleşme tarayıcı dosya seçimi için yeterli değildir. Tarayıcı gerçek yerel yolu backend’e veremez. Gerçek yükleme için planlanan endpoint gereklidir.

### Durum

```http
GET /durum
```

```json
{
  "calisiyor": true,
  "kaynak": "C:\\videos\\test.mp4",
  "frame_no": 184,
  "hedef_sayisi": 2,
  "model_sayisi": 45
}
```

### Video

```http
GET /video
```

Yanıt MJPEG’dir:

```text
multipart/x-mixed-replace; boundary=frame
```

Kullanım:

```html
<img src="/video" alt="Canlı analiz görüntüsü">
```

Yeni oturumda cache kırmak için:

```text
/video?_=TIMESTAMP
```

### WebSocket

```text
ws://127.0.0.1:8000/hedefler
```

Paket:

```json
{
  "frame": 325,
  "hedefler": []
}
```

Hedef örneği:

```json
{
  "id": 4,
  "sinif": "aircraft",
  "guven": 0.913,
  "bbox": [120, 80, 450, 310],
  "hiz_px_s": 24.7,
  "zigzag": 0.12,
  "hits": 38,
  "model": "F-16 Fighting Falcon",
  "model_skor": 0.842,
  "dusuk_guven": false,
  "ulke": "ABD",
  "uretici": "Lockheed Martin",
  "rol": "Savaş Uçağı",
  "adaylar": [
    {
      "model": "F-16 Fighting Falcon",
      "skor": 0.842,
      "ulke": "ABD",
      "rol": "Savaş Uçağı"
    }
  ],
  "vlm": {
    "dogrulama": "onaylandı",
    "tehdit_seviyesi": "dusuk",
    "gorsel_analiz": "Görüntüde sabit kanatlı askerî hava aracı görülmektedir.",
    "gercek_tahmin": "F-16 Fighting Falcon (Askerî Uçak / Sabit Kanat)",
    "arac_sinifi": "Sabit Kanat",
    "ulke_orjini": "Türkiye",
    "hedef_modeli_tutarlilik": "2/2"
  },
  "llm": {
    "summary": "Platform ve operasyonel kayıtlar değerlendirilmiştir.",
    "events": [],
    "risk": "MEDIUM",
    "actions": [
      "Takibi sürdür",
      "Operatör incelemesi iste",
      "Uçuş izni kayıtlarını kontrol et"
    ]
  }
}
```

Notlar:

- Alanlar analiz hazır olana kadar `null`, eksik veya boş olabilir.
- WebSocket yaklaşık her 200 ms’de tüm güncel hedef listesini gönderir.
- Bağlantı kopunca gecikmeli otomatik yeniden bağlanılmalıdır.
- Dinamik metinler ham HTML olarak basılmamalıdır.
- Mevcut backend işlem süresi ve aşama durumlarını açıkça göndermemektedir.
- `llm.events` mevcut ana UI’da kullanılmamaktadır ve zaman damgalı olay sözleşmesi garanti değildir.

### Referans görsel

```text
GET /referans?model=F-16%20Fighting%20Falcon
```

404 durumunda yerel placeholder gösterilmelidir.

## 25. Mevcut Backend Adaptör Eşlemesi

`existing-backend-adapter.ts`, mevcut Türkçe alanları canonical frontend modeline dönüştürmelidir.

Örnek eşlemeler:

```text
id                         → target.id
sinif                      → target.className
guven                      → detectionConfidence
hiz_px_s                   → detection.speedPxS
zigzag                     → detection.zigzagScore
hits                       → detection.hits
model                      → vrag.model
model_skor                 → vrag.score
dusuk_guven                → vrag.lowConfidence
ulke                       → vrag.country
uretici                    → vrag.manufacturer
rol                        → vrag.role
adaylar                    → vrag.candidates
vlm.gercek_tahmin          → vlm.visualPrediction
vlm.arac_sinifi            → vlm.vehicleClass
vlm.ulke_orjini            → vlm.countryHypothesis
vlm.tehdit_seviyesi        → vlm.threatHypothesis
vlm.dogrulama              → vlm.verification
vlm.hedef_modeli_tutarlilik→ vlm.vragConsistency
vlm.gorsel_analiz          → vlm.visualAssessment
llm.summary                → llm.summary
llm.risk                   → llm.risk
llm.actions                → llm.actions
```

Risk normalizasyonu hem Türkçe hem İngilizce değerleri karşılamalıdır:

```text
LOW, low, düşük, dusuk       → low
MEDIUM, medium, orta         → medium
HIGH, high, yüksek, yuksek   → high
CRITICAL, critical, kritik   → critical
diğer/boş                    → unknown
```

Mevcut backend’den alınamayan canonical alanlar adaptörde uydurulmamalı; `undefined`, `waiting` veya `unknown` kalmalıdır.

## 26. Entegrasyon Aşamasında Backend’e Eklenecekler

Frontend tamamlandığında backend arayüze göre genişletilecektir. Bunlar şu an mock ile geliştirilmelidir:

1. Tarayıcıdan multipart video yükleme
2. Oturum ID’si
3. Duraklat/devam
4. Başa alma/temiz yeniden başlatma
5. Video toplam süresi, mevcut süre ve ilerleme
6. Açık `completed` oturum durumu
7. Pipeline aşama durumları
8. Her aşamanın işlem süresi ve son güncellemesi
9. Zaman damgalı kalıcı olay geçmişi
10. Olay başlangıç/bitiş ve yaşam döngüsü
11. Kritik olay kareleri
12. Genel video özeti
13. Video geneli risk ve gerekçe
14. Önceliklendirilmiş yapılandırılmış aksiyonlar
15. Nihai oturum çıktısı endpointi
16. JSON/rapor indirme endpointi veya frontend üretimine uygun canonical JSON
17. Performans metrikleri: FPS, toplam süre, model gecikmeleri, bellek/donanım
18. Olay zamanına seek veya analiz edilmiş normal video kaynağı
19. Geçmiş endpointinin gerçek veri döndürmesi

Önerilen gelecekteki API şekli kesin değildir; frontend `OperatorDataSource` üzerinden soyutlandığı için endpoint adları değişebilir. Yine de hedef kabiliyetler:

```text
POST /api/videos
POST /api/sessions
POST /api/sessions/{id}/pause
POST /api/sessions/{id}/resume
POST /api/sessions/{id}/restart
POST /api/sessions/{id}/stop
GET  /api/sessions/{id}
GET  /api/sessions/{id}/events
GET  /api/sessions/{id}/result
GET  /api/sessions/{id}/metrics
WS   /api/sessions/{id}/stream
```

Bu adlar bağlayıcı değildir; entegrasyonda backend ekibiyle kesinleştirilmelidir.

## 27. Güvenlik ve Sağlamlık

- Backend metinleri `dangerouslySetInnerHTML` ile basılmamalıdır.
- Dosya türü frontend’de kontrol edilse de backend doğrulaması zorunludur.
- Dosya boyutu sınırı UI’da önceden gösterilmelidir.
- Referans görsel URL’leri encode edilmelidir.
- WebSocket JSON parse hataları uygulamayı çökertmemelidir.
- Bozuk veya eksik payload için güvenli fallback kullanılmalıdır.
- Bağlantı yeniden kurulurken exponential/backoff sınırı düşünülebilir.
- Aynı anda birden fazla başlatma isteği engellenmelidir.
- Kritik temizleme eylemleri onay istemelidir.
- Mock ve debug kontrolleri production build’den çıkarılmalıdır.

## 28. Test Kabul Kriterleri

### Yerleşim

- 16:9, 4:3, dikey ve çok yüksek çözünürlüklü video layout’u değiştirmez.
- 1366×768’de ana masaüstü ekranında sayfa dikey kaydırılmaz.
- Uzun model adı ve uzun özet yatay taşma oluşturmaz.
- Drawer açıldığında video ve ana grid yeniden boyutlanmaz.
- Timeline ayrıntısı açıldığında sayfa yüksekliği değişmez.

### Etkileşim

- Video dosyası tıklama ve sürükle-bırak ile seçilebilir.
- Kontroller oturum durumuna göre doğru etkinleşir.
- Başa Al onay ister.
- Analiz satırı drawer’ı açar.
- Her analiz aşaması açılabilir.
- Aynı anda yalnız bir accordion açıktır.
- Çalışan aşama tamamlanınca açık içerik canlı güncellenir.
- Timeline olayları tıklanabilir ve klavye erişimlidir.
- Olaydan ilgili hedef ve analiz aşaması açılabilir.
- Çoklu hedef seçimi doğru paneli günceller.

### Veri ve hata

- `null`, eksik alan ve boş listeler hata oluşturmaz.
- WebSocket kopunca son veri korunur ve yeniden bağlanma gösterilir.
- Uyarılı/kısmi sonuç nihai ve başarılı sonuç gibi sunulmaz.
- VLM tehdidi ile nihai risk ayrı gösterilir.
- `id = -1` normal hedef olarak gösterilmez.
- Referans görsel 404 olduğunda placeholder görünür.
- Türkçe karakterler doğru görünür.
- Yön bilgisi hiçbir ekranda bulunmaz.

### Tasarım

- Renkler merkezi tokenlardan gelir.
- Risk yalnız renkle anlatılmaz.
- Focus durumları görünürdür.
- Reduced-motion desteklenir.
- Harici CDN veya online asset çağrısı yoktur.

### Build ve entegrasyon

- `npm run build` başarılıdır.
- Build çıktısı göreli asset pathleriyle FastAPI alt yolundan çalışabilir.
- `/goruntule/` altında doğrudan açılış çalışır.
- API ve WebSocket URL’leri environment/config ile değiştirilebilir.
- Mock ve gerçek adaptör arasında UI kodu değiştirmeden geçiş yapılır.

## 29. FastAPI’ye Son Entegrasyon

Frontend tamamlandıktan sonra:

1. Production build alınır.
2. Mevcut `entegrasyon/web/` içeriği kontrollü biçimde yeni build ile değiştirilir.
3. Kullanıcıya ait mevcut değişiklikler silinmeden önce diff alınır.
4. FastAPI şu an `entegrasyon/web` dizinini `/goruntule` altında servis etmektedir.
5. Vite `base` ayarı `/goruntule/` veya göreli asset üretimine uygun yapılandırılmalıdır.
6. SPA router kullanılıyorsa statik servis fallback’i test edilmelidir. Tek sayfa olduğunda router kullanmamak daha basittir.
7. Aynı origin production’da API URL’leri `/durum`, `/video`, `/hedefler` gibi kök yolları kullanmalıdır; `/goruntule/durum` kullanılmamalıdır.
8. Development sırasında Vite proxy veya backend CORS ayarı kullanılmalıdır. Tercih: Vite proxy.
9. MJPEG ve WebSocket gerçek backend ile test edilmelidir.
10. Build assetlerinin offline çalıştığı ağ kapalıyken doğrulanmalıdır.

Örnek Vite geliştirme proxy fikri:

```ts
server: {
  proxy: {
    "/durum": "http://127.0.0.1:8000",
    "/oturum": "http://127.0.0.1:8000",
    "/video": "http://127.0.0.1:8000",
    "/referans": "http://127.0.0.1:8000",
    "/meta": "http://127.0.0.1:8000",
    "/hedefler": {
      target: "ws://127.0.0.1:8000",
      ws: true
    }
  }
}
```

Bu yalnız fikir örneğidir; kullanılan Vite sürümüne göre doğrulanmalıdır.

## 30. Yeni Sohbete Verilecek Uygulama Talimatı

Yeni frontend sohbetinde şu talimat bu belgeyle birlikte verilmelidir:

```text
Bu Markdown dosyasını eksiksiz oku ve MEVZUU ana operatör frontend’ini mevcut
backend projesinden ayrı, yeni bir klasörde geliştir. Önce repository/dizin durumunu
incele, uygun React + TypeScript + Vite yapısını oluştur ve mock data source ile bütün
ekran durumlarını çalışır hale getir. Backend koduna dokunma. UI bileşenlerini doğrudan
fetch/WebSocket’e bağlama; bu belgede tanımlanan canonical veri modeli ve DataSource
adaptör katmanını kullan. Tasarım kararlarını, yön bilgisi yasağını, tek viewport masaüstü
yerleşimini, tıklanabilir timeline’ı ve Analiz Süreci drawer/accordion davranışlarını eksiksiz
uygula. Testleri ve production build’i çalıştır. İş bittiğinde dosya yapısını, test sonuçlarını
ve daha sonra backend entegrasyonunda yapılacakları özetle.
```

## 31. Uygulama Önceliği

### Aşama 1: Temel sistem

- Proje kurulumu
- Tokenlar, fontlar, reset
- Canonical tipler ve DataSource
- Mock senaryo motoru
- Ana `100dvh` layout

### Aşama 2: Ana kullanıcı akışı

- Video seçme ekranı
- Kontrol çubuğu
- Sabit video alanı
- Sistem durumları
- Hedef seçimi
- Nihai sonuç paneli

### Aşama 3: Açıklanabilir analiz

- Kapalı Analiz Süreci satırı
- Drawer
- Durum timeline’ı
- Nesne/VRAG/VLM/LLM/Nihai accordion ayrıntıları
- Uyarı, hata ve kısmi sonuçlar

### Aşama 4: Zaman farkındalığı

- Tıklanabilir olay timeline’ı
- Olay ayrıntısı
- Olay filtreleri ve kümeler
- Olaydan hedef/drawer bağlantısı

### Aşama 5: Kalite

- Responsive düzen
- Erişilebilirlik
- Unit/component testleri
- Uçtan uca kritik akış testleri
- Production build
- Offline doğrulama

### Aşama 6: Backend entegrasyonu

- Mevcut backend adaptörü
- MJPEG ve WebSocket
- Planlanan backend endpointleri
- Gerçek zaman damgalı olaylar
- Nihai oturum çıktısı
- Performans ve seek özellikleri

## 32. Son Kontrol Listesi

- [ ] Ürün adı yalnız `MEVZUU`.
- [ ] Alt başlık `Hava Sahası Karar Destek Sistemi`.
- [ ] Logo uydurulmadı.
- [ ] Yön bilgisi hiçbir yerde yok.
- [ ] Ana sonuç teknik detaylardan önce geliyor.
- [ ] Video seçimi klasörden yapılabiliyor.
- [ ] Video alanı sabit 16:9 ve layout kaymıyor.
- [ ] Başlat, duraklat/devam, durdur, başa al ve tam ekran tasarlandı.
- [ ] Masaüstü ana ekranı sayfa kaydırmadan çalışıyor.
- [ ] Çoklu hedef destekleniyor.
- [ ] Analiz Süreci kapalı satırı ve drawer çalışıyor.
- [ ] Tamamlanan aşamalara tıklanınca ayrıntı açılıyor.
- [ ] Çalışan aşama canlı alt adımları gösteriyor.
- [ ] Gizli düşünce zinciri gösterilmiyor.
- [ ] VRAG adayları ve güvenleri var.
- [ ] VLM görsel doğrulama ve çelişki durumu var.
- [ ] LLM risk gerekçesi ve aksiyonları yapılandırılmış.
- [ ] VLM tehdit hipotezi ile nihai risk ayrıldı.
- [ ] Timeline zaman damgalı ve tıklanabilir.
- [ ] Timeline olayı ayrıntı, hedef ve analiz drawer’ına bağlı.
- [ ] Genel video özeti, olaylar, risk ve aksiyonlar var.
- [ ] Geçici/nihai/kısmi sonuç ayrıldı.
- [ ] JSON görüntüleme/kopyalama/indirme tasarlandı.
- [ ] Mock pipeline zaman içinde ilerliyor.
- [ ] Uyarı, hata, bağlantı kopması ve çoklu hedef senaryoları var.
- [ ] UI DataSource adaptörü arkasında.
- [ ] Mevcut backend ve planlanan backend özellikleri ayrıldı.
- [ ] Harici CDN/font/analytics yok.
- [ ] Erişilebilirlik ve reduced-motion var.
- [ ] Testler ve production build başarılı.
