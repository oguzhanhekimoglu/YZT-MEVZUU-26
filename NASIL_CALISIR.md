# VRAG — Hava Aracı Tanıma: Nasıl Çalışır?

Havadan çekilmiş, kırpılmış bir uçak görüntüsünün **hangi model** olduğunu bulur
(F-16, Kaan, B-2, ANKA...). Klasik sınıflandırıcı yerine **Visual RAG**: modeli
yeniden eğitmeden, referans veritabanından **en benzeri**ni bulur.

## Boru hattı (2 katman)

```
[YOLO]  →  [RETRIEVAL]
crop       SigLIP2 → Qdrant → top-k
(repo dışı)  en benzer model = tahmin (top-1)
```

1. **Gömme:** Görüntü **SigLIP2-so400m** ile 1152 boyutlu bir vektöre çevrilir
   (L2-normalize → kosinüs benzerliği).
2. **Arama:** **Qdrant**'ta en benzer referanslar bulunur, model bazında
   tekilleştirilir (top-k = k farklı model). **Nihai tahmin = top-1.**

## İndeksleme (ingest)

`veriler/<kategori>/<model>/` taranır; her modelin `metadata.json`'u okunur. Her
referans görselden **augmentation** ile varyasyon üretilir (döndürme, ölçek, blur,
**perspektif eğim**) ve hepsi Qdrant'a yazılır → tek fotoğraftan çok açı.
**95 model, 2809 görsel → 16854 vektör.**

## Güven kapısı

Tahmin, top-1 ile top-2 skoru çok yakınsa (margin < `MARGIN_ESIGI`=0.015) **"düşük
güven"** işaretlenir — arayüzde uyarı, CLI'da not. Veriyle: yanlış tahminlerin
medyan margini 0.007, doğruların 0.057; bu eşik yanlışların ~%86'sını yakalar.

## Neden VLM yok?

Adayları bir görsel-dil modeline (Qwen2.5-VL-7B) seçtiren 3. katman denendi ama
güçlü retrieval'ı **bozdu** (top-1 %88.9→%64.4) ve sorgu başına ~100 sn sürdü
(8 GB'da encoder+VLM sığmıyor). Retrieval-only hem daha isabetli hem ~100× hızlı.

## Kullanım

```bash
python -m vrag ingest                 # indeksleme (ilk kez şart)
python app.py                         # web arayüzü → http://127.0.0.1:5000
python -m vrag search crop.jpg        # komut satırı
```

## Sınırlar
- Yalnızca veritabanındaki modeller arasından bulur (yeni model = referans + ingest).
- Sorgu havadan; referanslar çoğunlukla yandan → üstten görsel eklemek isabeti artırır.
- Güven kapısı kararsızlığı yakalar ama DB'de HİÇ olmayan uçak (gerçek OOD) ayrı problem.
