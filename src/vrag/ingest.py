import os
import sys
import argparse
from pathlib import Path
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.vrag.engine import VRAGEngine
from src.vrag.augmentation import varyasyonlar_uret

def main():
    parser = argparse.ArgumentParser(description="VRAG Knowledge Base Ingestion")
    parser.add_argument("--img_dir", type=str, default=str(Path(__file__).parent.parent.parent / "data" / "knowledge_base"),
                        help="Referans resimlerinin bulunduÄŸu klasÃ¶r")
    args = parser.parse_args()

    img_dir = Path(args.img_dir)
    if not img_dir.exists():
        print(f"HATA: Dizin bulunamadÄ± -> {img_dir}")
        return

    print("VRAG Engine baÅŸlatÄ±lÄ±yor (Model yÃ¼klenmesi biraz sÃ¼rebilir)...")
    engine = VRAGEngine()

    valid_extensions = {".jpg", ".jpeg", ".png", ".bmp"}

    print(f"\n'{img_dir}' taranÄ±yor...")

    # TÃ¼m desteklenen resim formatlarÄ±nÄ± rglob ile rekÃ¼rsif (alt klasÃ¶rlerle) bul
    all_files = []
    for ext in valid_extensions:
        all_files.extend(list(img_dir.rglob(f"*{ext}")))
        all_files.extend(list(img_dir.rglob(f"*{ext.upper()}")))

    if not all_files:
        print("UyarÄ±: KlasÃ¶rde desteklenen resim dosyasÄ± bulunamadÄ±.")
        return

    # BUG-FIX (tekrar ingest = kopya veri): upsert_image her seferinde rastgele
    # bir UUID kullanÄ±yor, yani ayn Ä± klasÃ¶rÃ¼ ikinci kez ingest etmek ayn Ä±
    # gÃ¶rselleri veritabanÄ±na tekrar tekrar ekliyordu. ArtÄ±k baÅŸlamadan Ã¶nce
    # zaten indekslenmiÅŸ (model, dosya adÄ±) Ã§iftlerini okuyup atlÄ±yoruz â€”
    # bu sayede "veriler/" klasÃ¶rÃ¼nÃ¼n tamamÄ±nÄ± her geniÅŸletmede gÃ¼venle
    # yeniden Ã§alÄ±ÅŸtÄ±rabilirsiniz, sadece gerÃ§ekten yeni dosyalar iÅŸlenir.
    print("Zaten indekslenmiÅŸ dosyalar kontrol ediliyor...")
    indekslenmis = engine.db.indekslenmis_dosyalari_al()
    print(f"{len(indekslenmis)} gÃ¶rsel zaten indeksli.")

    # (model, dosya adÄ±) -> Path, aynÄ± zamanda disk taramasÄ± iÃ§in kullanÄ±lÄ±yor
    diskteki: dict[tuple[str, str], Path] = {}
    for file_path in all_files:
        rel_parts = file_path.relative_to(img_dir).parts
        model_name = rel_parts[-2] if len(rel_parts) >= 2 else file_path.stem.split("_")[0]
        diskteki[(model_name, file_path.name)] = file_path

    yeni_dosyalar = [fp for key, fp in diskteki.items() if key not in indekslenmis]

    # BUG-FIX (silinen kategoriler indekste kalÄ±yordu): "veriler/" klasÃ¶rÃ¼nden
    # bir model/kategori tamamen kaldÄ±rÄ±lsa bile eski vektÃ¶rler indekste
    # kalÄ±p VRAG'Ä±n hÃ¢lÃ¢ diskte olmayan bir modeli "tanÄ±masÄ±na" yol
    # aÃ§Ä±yordu. ArtÄ±k diskte artÄ±k karÅŸÄ±lÄ±ÄŸÄ± olmayan indeks kayÄ±tlarÄ±
    # otomatik siliniyor â€” indeks her zaman "veriler/" ile birebir eÅŸleÅŸir.
    silinecekler = indekslenmis - set(diskteki.keys())
    if silinecekler:
        print(f"{len(silinecekler)} gÃ¶rsel artÄ±k diskte yok, indeksten siliniyor...")
        for model_name, source_file in silinecekler:
            engine.db.dosya_sil(model_name, source_file)
            print(f"Silindi: {source_file} -> Model: {model_name}")

    atlanacak = len(all_files) - len(yeni_dosyalar)
    print(f"Toplam {len(all_files)} gÃ¶rsel bulundu â€” {atlanacak} zaten indeksli (atlanacak), "
          f"{len(yeni_dosyalar)} yeni gÃ¶rsel iÅŸlenecek, {len(silinecekler)} silindi.")

    if not yeni_dosyalar:
        print("\nYeni gÃ¶rsel yok, eklenecek bir ÅŸey kalmadÄ±.")
        return

    all_files = yeni_dosyalar

    success_count = 0
    for file_path in all_files:
        # HiyerarÅŸi: img_dir / SÄ±nÄ±f / Model / resim.jpg
        # parent = Model, parent.parent = SÄ±nÄ±f
        rel_parts = file_path.relative_to(img_dir).parts
        
        if len(rel_parts) >= 3:
            # Ã–rn: "1. SavaÅŸ UÃ§aklarÄ±" / "F-16" / "resim1.jpg"
            vehicle_class = rel_parts[-3]
            model_name = rel_parts[-2]
        elif len(rel_parts) == 2:
            # Ã–rn: "F-16" / "resim1.jpg"
            vehicle_class = "Bilinmiyor"
            model_name = rel_parts[-2]
        else:
            # Sadece dosya (Eski sistem: model_sinif.jpg)
            name_parts = file_path.stem.split("_")
            model_name = name_parts[0]
            vehicle_class = name_parts[1] if len(name_parts) > 1 else "Bilinmiyor"
            
        try:
            img = Image.open(file_path).convert("RGB")
            variations = varyasyonlar_uret(img)
            
            for var_idx, var_img in enumerate(variations):
                emb = engine.embedder.embed_image(var_img)
                payload = {
                    "model": model_name,
                    "class": vehicle_class,
                    "source_file": file_path.name,
                    "variation": var_idx  # 0=orijinal, 1=dÃ¶ndÃ¼rme1, vb.
                }
                engine.db.upsert_image(emb, payload)
                
            print(f"Eklendi ({success_count+1}/{len(all_files)}): {file_path.name} -> Model: {model_name}, SÄ±nÄ±f: {vehicle_class} (8 Varyasyon)")
            success_count += 1
        except Exception as e:
            print(f"Hata ({file_path.name}): {e}")

    print("\nVRAG VeritabanÄ± baÅŸarÄ±yla gÃ¼ncellendi!")

if __name__ == "__main__":
    main()
