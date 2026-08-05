"""VRAG komut satırı arayüzü.

Kullanım:
    python -m vrag ingest [--ekle]
    python -m vrag search <resim_yolu> [--topk N] [--kategori K]
"""
from __future__ import annotations

import argparse
import sys

from . import config


def _tablo_yazdir(adaylar) -> None:
    """Aday sonuçlarını okunur, hizalı bir tabloyla yazdırır."""
    if not adaylar:
        print("Sonuç bulunamadı.")
        return

    basliklar = ["#", "Model", "Skor", "Kategori", "Açı", "Referans"]
    satirlar = [
        [str(i), a.model, f"{a.skor:.4f}", a.kategori, a.aci, a.referans_yolu]
        for i, a in enumerate(adaylar, start=1)
    ]
    genislikler = [len(b) for b in basliklar]
    for satir in satirlar:
        for j, hucre in enumerate(satir):
            genislikler[j] = max(genislikler[j], len(hucre))

    def _bicimle(hucreler):
        return "  ".join(h.ljust(genislikler[j]) for j, h in enumerate(hucreler))

    print(_bicimle(basliklar))
    print("  ".join("-" * g for g in genislikler))
    for satir in satirlar:
        print(_bicimle(satir))


def _komut_ingest(args) -> int:
    from .indeksleme import calistir
    calistir(sifirla=not args.ekle, dizin=args.dizin)
    return 0


def _komut_search(args) -> int:
    from .arama import ara, dusuk_guven, margin
    adaylar = ara(args.resim, topk=args.topk, kategori=args.kategori)

    print(f"\nSorgu: {args.resim}")
    if args.kategori:
        print(f"Kategori filtresi: {args.kategori}")
    print()
    _tablo_yazdir(adaylar)
    if adaylar:
        print(f"\nTahmin (retrieval top-1): {adaylar[0].model} "
              f"(benzerlik {adaylar[0].skor:.4f})")
        if dusuk_guven(adaylar):
            print(f"  [!] DÜŞÜK GÜVEN: ilk iki aday çok yakın "
                  f"(margin {margin(adaylar):.4f} < {config.MARGIN_ESIGI}); "
                  f"doğrulama önerilir.")
    return 0


def main(argv=None) -> int:
    ayristirici = argparse.ArgumentParser(
        prog="python -m vrag",
        description="VRAG — hava aracı görsel retrieval hattı (SigLIP2 + Qdrant).",
    )
    alt = ayristirici.add_subparsers(dest="komut", required=True)

    p_ingest = alt.add_parser("ingest", help="Referans görselleri Qdrant'a indeksler.")
    p_ingest.add_argument("--ekle", action="store_true",
                          help="Koleksiyonu sıfırlamadan üzerine ekle (varsayılan: sıfırdan kur).")
    p_ingest.add_argument("--dizin", default=None, help="Referans klasörü (varsayılan: veriler/).")
    p_ingest.set_defaults(fn=_komut_ingest)

    p_search = alt.add_parser("search", help="Tek görüntüyü sorgular.")
    p_search.add_argument("resim", help="Sorgu görseli yolu (YOLO crop).")
    p_search.add_argument("--topk", type=int, default=config.VARSAYILAN_TOPK,
                          help=f"Kaç aday döndürülsün (varsayılan {config.VARSAYILAN_TOPK}).")
    p_search.add_argument("--kategori", default=None,
                          help="Yalnızca bu kategoride ara (ör. 'Savaş Uçağı').")
    p_search.set_defaults(fn=_komut_search)

    args = ayristirici.parse_args(argv)
    try:
        return args.fn(args)
    except (FileNotFoundError, ValueError) as e:
        print(f"HATA: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
