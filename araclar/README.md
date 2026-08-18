# Araçlar — Veri Genişletme

Referans veriyi büyütmek için yardımcılar + iş akışı. Retrieval kalitesi doğrudan
referansların **çeşitliliğine ve sorgu (drone/havadan) ile uyumuna** bağlıdır.

## Ne eklemeli (öncelik sırası — deneylerle doğrulandı)
1. **Havadan / üstten / oblik açılar** — gerçek sorgu böyle; en büyük etki.
2. **Çeşitlilik > sayı** — farklı açı, uzaklık, ışık, kısmi görünüm, drone kalitesi.
3. **Az fotolu modelleri güçlendir** — `veri_durum.py` en zayıfları listeler.
4. **Kaçın:** neredeyse aynı kopyalar, tanınmaz "junk", steril/arka-plansız görüntü
   (arka plan silme ölçüldü → **−5.8 puan**, yapılmadı; SigLIP2 doğal görüntü sever).

## Araçlar

### `veri_durum.py` — nereyi genişletmeli?
```bash
python araclar/veri_durum.py
```
Model başına foto sayısı, en zayıf modeller ve metadata eksiklerini raporlar.

### `video_kare.py` — videodan kare çıkar
```bash
python araclar/video_kare.py <video> <hedef_klasor> [kare_sayisi=15] [--sahne]
```
Airshow/uçuş/drone videosundan eşit aralıklı kareler üretir (`kare_001.jpg ...`).
Çok hızlı veri toplama yolu. `--sahne`: sahne değişimi karelerini seçer.

## İş akışı (ekle → indeksle)
1. **Foto topla** (yukarıdaki önceliklerle; video varsa `video_kare.py`).
2. **Doğru yere koy:**
   - Mevcut modele: `data/referans/<kategori>/<Model>/` klasörüne at.
   - Yeni model: yeni klasör aç + içine `metadata.json`:
     ```json
     {
       "model": "...", "kategori": "...", "ayirt_edici_ozellikler": "...",
       "ulke": "...", "uretici": "...", "rol": "...",
       "alternatif_adlar": [], "motor_sayisi": 2, "silahli": true
     }
     ```
     `kategori` şunlardan biri olmalı: Savaş Uçağı, Bombardıman Uçağı,
     Nakliye/Özel Görev Uçağı, Helikopter, İHA, SİHA, Yolcu Uçağı, Drone.
3. **Kontrol et:** `python araclar/veri_durum.py` (eksik metadata / zayıf model).
4. **Yeniden indeksle:** `python -m vrag ingest` (qdrant_db'yi sıfırdan kurar).
   > App açıksa önce kapat (embedded Qdrant tek erişimli) veya arayüzdeki
   > "Yeniden İndeksle" butonunu kullan.
5. **Ölç:** arayüzde *Benchmark Çalıştır* — top-1'in düşmediğini/arttığını gör.
   (Not: daha çok/zor foto benchmark'ı gerçekçi biçimde zorlaştırabilir; düşen
   sayı her zaman "kötü" demek değildir.)

## İpucu
Aynı uçağın iki adı varsa (ör. Kaan = TF-X) klasörlerin `metadata.json`'unda
ikisine de aynı `model` adını ver → retrieval'da tek modele iner (kopya olmaz).
