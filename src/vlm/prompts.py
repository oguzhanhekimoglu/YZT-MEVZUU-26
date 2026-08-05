# ============================================================
# prompts.py - VLM (Visual Language Model) Prompt Templates
# ============================================================

# Cross-check keywords between arac_sinifi enum and gorsel_analiz free text.
CROSS_CHECK_KEYWORDS = {
    "sabit_kanat": (
        "fixed-wing", "fixed wing", "straight wing", "swept wing",
        "delta wing", "monoplane", "biplane", "jet engine",
        "sabit kanat", "düz kanat", "ok açılı kanat", "delta kanat",
        "savaş uçağı", "jet motoru", "yolcu uçağı",
    ),
    "doner_kanat": (
        "multirotor", "multi-rotor", "quadcopter", "quadrotor",
        "quad-copter", "hexacopter", "octocopter", "helicopter",
        "rotor blades", "rotor arm", "propeller arm",
        "döner kanat", "çok pervaneli", "quadcopter", "helikopter",
        "rotor kanadı", "rotor kolu", "pervane kolu",
    ),
}

def generate_vlm_prompt(speed: float, zigzag: float, threat: float, yolo_class: str, yolo_conf: float, n_crops: int, vrag_context: str = "") -> str:

    if n_crops <= 1:
        collage_note = "A single cropped image of the tracked object is shown."
    elif n_crops == 2:
        collage_note = (
            "A single image with 2 side-by-side crops is shown. Both crops belong to "
            "THE SAME tracked object captured at DIFFERENT TIME MOMENTS (not two different objects). "
            "Evaluate them together — a detail hidden in one may be visible in the other."
        )
    elif n_crops == 3:
        collage_note = (
            "A single mosaic image is shown: one large high-resolution frame on top and two smaller "
            "frames side-by-side on the bottom. All frames show THE SAME tracked object at DIFFERENT "
            "TIME MOMENTS (not three different objects). Evaluate all together."
        )
    else:
        collage_note = (
            "A single image with up to 4 crops in a 2x2 grid is shown. Each non-empty cell shows "
            "THE SAME tracked object at DIFFERENT TIME MOMENTS (not different objects). "
            "Evaluate all visible cells together."
        )

    vrag_section = ""
    if vrag_context:
        vrag_section = f"""
[GÖRSEL HAFIZA (VRAG) EŞLEŞMELERİ]
{vrag_context}
ÖNEMLİ: Eğer VRAG eşleşmelerinden herhangi birinin benzerliği %80 veya üzerindeyse, bu çok güçlü bir kanıttır. Silüet tamamen farklı bir şeye benzemiyorsa mutlaka VRAG'ın verdiği 'Model' ismini doğru kabul edip kullan!
"""

    prompt = f"""Sen uzman bir askeri istihbarat ve hava aracı analistisin. Sana uçan bir hedefin hava gözetleme görüntüleri gösterilecek. Görevin görseli inceleyip verilen VRAG veritabanı eşleşmelerini yorumlamak ve kesin bir istihbarat raporu sunmaktır. ÇIKTIN SADECE VE SADECE JSON FORMATINDA OLMALIDIR.

{vrag_section}
[GÖRÜNTÜ FORMATI]
{collage_note} (Eğer birden fazla kare varsa hepsi aynı nesneye aittir).

[SİSTEM ÖN TAHMİNİ]
Hızlı tespit sistemi (YOLO) bu nesneyi geçici olarak %{yolo_conf*100:.0f} güvenle "{yolo_class}" olarak sınıflandırdı. Bunu tek başına doğru kabul etme, sadece bir ipucu olarak kullan.

[TAKİP VERİSİ]
Tahmini Hız: {speed:.1f} piksel/saniye
Zikzak (Manevra) Skoru: {zigzag:.2f}

GÖREV: Gördüğün görsel özellikleri ve VRAG eşleşmelerini birleştirerek mantıklı bir sonuca var. Yanıtın KESİNLİKLE geçerli bir JSON objesi olmalıdır. 

ÖRNEK (EĞER BİR HELİKOPTER GÖRSEYDİN ŞÖYLE YAZMALIYDIN):
{{
  "arac_sinifi": "doner_kanat",
  "tehdit_seviyesi": "orta",
  "tahmini_hedef_tipi": "gozetleme",
  "ulke_orjini": "Bilinmiyor",
  "hedef_modeli": "Bilinmiyor",
  "gorsel_analiz": "Görüntüde ana rotorlu bir helikopter görülmektedir. VRAG eşleşmesi olmadığı için detaylı model belirlenemedi."
}}

ŞİMDİ KENDİ GÖRDÜĞÜN CİSİM İÇİN (Uçak, İHA vb.) YUKARIDAKİ ŞABLONA UYGUN BİR JSON OLUŞTUR. Doğrudan {{" ile başla.
"""
    return prompt
